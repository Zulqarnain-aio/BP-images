#!/usr/bin/env python3
"""Rebuild a Kiosk XBL version from the original Quectel XBL.

usage: build_xbl.py VERSION OUT.elf [--orig original/xbl_unsigned.elf]

Writes an UNSIGNED xbl.elf; sign it with tools/sign.sh before flashing.
Needs the Android clang toolchain (clang, ld.lld, llvm-objcopy); set CLANG_BIN
to its bin directory if the default below does not exist.

Every patch site is checked against the original instruction before it is
changed, so running this on any other XBL fails loudly instead of producing
a broken image.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLANG_BIN = os.environ.get(
    'CLANG_BIN', '/nvme/A15/QCOM6125_A15_Kiosk_22/target/kernel_platform/'
    'prebuilts/clang/host/linux-x86/clang-r450784e/bin')

# ---- SBL1 (ELF segment 6, va 0xc221000) -----------------------------------
SBL1_SEG = 6
SBL1_VA = 0xc221000
SBL1_LOG = 0xc23594c          # boot log function; every hook replaces a bl to it
SBL1_CAVE = 0xc2217a8         # 88 zero bytes, unreferenced, before code at 0xc221800
SBL1_CAVE_END = 0xc221800
HOOK_BUILD = 0xc22bb78        # "SBL1 BUILD @ ..." (~0.25 s after power-on)
HOOKS_V2 = [HOOK_BUILD,
            0xc236798,        # boot_flash_init, Start
            0xc22c7e0,        # xblconfig_init, Start
            0xc23933c,        # boot_config_data_table_init, Start
            0xc22c314,        # pm_device_init, Start
            0xc22ad30]        # SBL1, End

# ---- UEFI DXE volume (ELF segment 16, va 0x5fc00000) ----------------------
UEFI_SEG = 16
GZ_FFS = 0x41aa8              # FFS file (segment offset) holding the gzip section
GZ_FFS_GUID = uuid.UUID('9e21fd93-9c72-4c15-8c4b-e77f1db2d792')
GZ_FREE_FROM = 0x1e9210       # original end of the FFS (8-aligned); 0xFF up to 0x200000
# PE32 images inside the decompressed volume: (offset, size)
PE = {'DisplayDxe': (0x316664, 0x3d000), 'EnvDxe': (0x166d34, 0x14000),
      'GraphicsConsoleDxe': (0x12db84, 0xc000)}

ENV_CAVE = 0x11800            # zero padding at the end of EnvDxe .text
ENV_EARLY = 0x11880
ENV_DELAY = 0x7bc0            # MicroSecondDelay
ENV_SYMS = {'TLMM_PTR': 0x12580, 'ENV_DELAY': ENV_DELAY, 'GBS_PTR': 0x126b8,
            'DU_GUID': 0x12138, 'FLAG': 0x12ff0, 'RET_2C0C': 0x2c0c,
            'CALLBACK': 0x2930}

VERSIONS = {
    'v0': dict(desc='original, re-signed with the OEM test certs'),
    'v1': dict(sbl1=('gpio84_low_2ma.s', [HOOK_BUILD])),
    'v2': dict(sbl1=('gpio84_low.s', HOOKS_V2)),
    'v3': dict(sbl1=('gpio84_low_hold2s.s', [HOOK_BUILD])),
    'v4': dict(sbl1=('gpio84_low.s', [HOOK_BUILD]),
               uefi=['displaydxe_bl_low', 'envdxe_bl_on']),
    'v5': dict(sbl1=('gpio84_low.s', [HOOK_BUILD]),
               uefi=['displaydxe_bl_low', 'envdxe_bl_on', 'envdxe_early_splash']),
    'v6': dict(sbl1=('gpio84_low.s', [HOOK_BUILD]),
               uefi=['displaydxe_bl_low', 'envdxe_bl_on', 'envdxe_early_splash',
                     'gc_no_clear']),
}


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def p32(b, o, v):
    struct.pack_into('<I', b, o, v)


def u24(b, o):
    return b[o] | b[o + 1] << 8 | b[o + 2] << 16


def bl(frm, to):
    return 0x94000000 | (((to - frm) >> 2) & 0x3ffffff)


def b_(frm, to):
    return 0x14000000 | (((to - frm) >> 2) & 0x3ffffff)


def bl_target(word, at):
    assert word >> 26 == 0x25, f'not a bl at {at:#x}'
    i = word & 0x3ffffff
    if i & (1 << 25):
        i -= 1 << 26
    return at + 4 * i


def assemble(src, base, syms, want=()):
    """Assemble and link src at base; return the raw .text bytes, plus the
    addresses of the symbols named in want if any are asked for."""
    with tempfile.TemporaryDirectory() as d:
        o, elf, out = (os.path.join(d, n) for n in ('a.o', 'a.elf', 'a.bin'))
        subprocess.run([f'{CLANG_BIN}/clang', '--target=aarch64-linux-gnu', '-c',
                        src, '-o', o], check=True)
        defs = [f'--defsym={k}={v:#x}' for k, v in syms.items()]
        subprocess.run([f'{CLANG_BIN}/ld.lld', '-m', 'aarch64elf', f'-Ttext={base:#x}',
                        '-e', f'{base:#x}', *defs, '-o', elf, o], check=True)
        subprocess.run([f'{CLANG_BIN}/llvm-objcopy', '-O', 'binary', '-j', '.text',
                        elf, out], check=True)
        code = open(out, 'rb').read()
        if not want:
            return code
        nm = subprocess.run([f'{CLANG_BIN}/llvm-nm', elf], check=True,
                            capture_output=True, text=True).stdout
        addr = {l.split()[2]: int(l.split()[0], 16) for l in nm.splitlines()}
        return code, [addr[w] for w in want]


def segment(b, i):
    phoff, = struct.unpack_from('<Q', b, 0x20)
    t, fl, off, va, pa, fsz, msz, al = struct.unpack_from('<IIQQQQQQ', b, phoff + i * 56)
    return off, va, fsz


def patch_sbl1(b, stub_name, hooks):
    off, va, fsz = segment(b, SBL1_SEG)
    assert va == SBL1_VA
    fo = lambda a: off + (a - va)
    for h in hooks:
        assert bl_target(u32(b, fo(h)), h) == SBL1_LOG, f'hook {h:#x}'
    assert b[fo(SBL1_CAVE):fo(SBL1_CAVE_END)] == bytes(SBL1_CAVE_END - SBL1_CAVE)
    stub = assemble(os.path.join(ROOT, 'src/sbl1', stub_name), SBL1_CAVE,
                    {'SBL1_LOG': SBL1_LOG})
    assert SBL1_CAVE + len(stub) <= SBL1_CAVE_END, 'SBL1 stub too big'
    b[fo(SBL1_CAVE):fo(SBL1_CAVE) + len(stub)] = stub
    for h in hooks:
        p32(b, fo(h), bl(h, SBL1_CAVE))


def patch_displaydxe_bl_low(pe):
    # "admin DisplayDxe: GPIO Configuration!" drives GPIO 27/83/84/85 high.
    # GpioOut(84, 1) -> GpioOut(84, 0): Disp_EN stays low until EnvDxe raises it.
    assert u32(pe['DisplayDxe'], 0x14b04) == 0x320003e1    # orr w1, wzr, #1
    p32(pe['DisplayDxe'], 0x14b04, 0x2a1f03e1)              # mov w1, wzr


def patch_envdxe_bl_on(pe):
    e = pe['EnvDxe']
    assert bl_target(u32(e, 0x2a50), 0x2a50) == ENV_DELAY  # bl MicroSecondDelay
    assert u32(e, 0x2a4c) == 0xaa1303e0                    # mov x0, x19
    code = assemble(os.path.join(ROOT, 'src/uefi/envdxe_backlight_on.s'), ENV_CAVE, ENV_SYMS)
    assert e[ENV_CAVE:ENV_CAVE + len(code)] == bytes(len(code))
    assert ENV_CAVE + len(code) <= ENV_EARLY
    e[ENV_CAVE:ENV_CAVE + len(code)] = code
    p32(e, 0x2a50, bl(0x2a50, ENV_CAVE))


def patch_envdxe_early_splash(pe):
    e = pe['EnvDxe']
    code, (reg_hook, wrapper) = assemble(
        os.path.join(ROOT, 'src/uefi/envdxe_early_splash.s'), ENV_EARLY, ENV_SYMS,
        want=('reg_hook', 'wrapper'))
    assert reg_hook == ENV_EARLY
    assert e[ENV_EARLY:ENV_EARLY + len(code)] == bytes(len(code))
    assert ENV_EARLY + len(code) <= 0x12000
    assert e[0x12ff0:0x13000] == bytes(16)                 # run-once flag lives here
    e[ENV_EARLY:ENV_EARLY + len(code)] = code
    # tail of the event registration: ldp x29, x30, [sp, #16] -> b reg_hook
    assert u32(e, 0x2c08) == 0xa9417bfd
    p32(e, 0x2c08, b_(0x2c08, reg_hook))
    # notify function of the "display set mode" event: 0x2930 -> wrapper
    assert u32(e, 0x2ba4) & 0x9f00001f == 0x90000002 and u32(e, 0x2bb4) == 0x9124c042
    pages = (wrapper >> 12) - (0x2ba4 >> 12)
    p32(e, 0x2ba4, 0x90000002 | ((pages & 3) << 29) | (((pages >> 2) & 0x7ffff) << 5))
    p32(e, 0x2bb4, 0x91000042 | ((wrapper & 0xfff) << 10))
    # Ctrl+C poll loop: 1000 -> 300 iterations (backlight still comes on at 250)
    assert u32(e, 0x2a58) == 0x710f9e9f                    # cmp w20, #999
    p32(e, 0x2a58, 0x7100001f | (299 << 10) | (20 << 5))


def patch_gc_no_clear(pe):
    # GraphicsConsoleConOutSetMode (0x1a50): when the GOP is already in the
    # target mode it fills the screen black instead of calling SetMode. v5
    # sets the mode early, so that fill wipes the logo. Skip it (EFI_SUCCESS).
    g = pe['GraphicsConsoleDxe']
    assert u32(g, 0x1b6c) == 0x2a1f03e2                    # mov w2, wzr (EfiBltVideoFill)
    assert u32(g, 0x1b8c) == 0xa9007ff9                    # stp x25, xzr, [sp] (Height, Delta)
    assert u32(g, 0x1b90) == 0xd63f02a0                    # blr x21 (GOP->Blt)
    p32(g, 0x1b90, 0xaa1f03e0)                              # mov x0, xzr


UEFI_PATCHES = {'displaydxe_bl_low': patch_displaydxe_bl_low,
                'envdxe_bl_on': patch_envdxe_bl_on,
                'envdxe_early_splash': patch_envdxe_early_splash,
                'gc_no_clear': patch_gc_no_clear}


def patch_uefi(b, names):
    off, va, fsz = segment(b, UEFI_SEG)
    assert va == 0x5fc00000 and fsz == 0x200000
    sg = bytearray(b[off:off + fsz])
    F = GZ_FFS
    assert uuid.UUID(bytes_le=bytes(sg[F:F + 16])) == GZ_FFS_GUID
    so = F + 24
    ssz = u24(sg, so)
    doff, sattr = struct.unpack_from('<HH', sg, so + 20)
    assert sg[so + 3] == 0x02 and doff == 0x18 and sattr == 0x1
    assert (F + u24(sg, F + 20) + 7) & ~7 == GZ_FREE_FROM
    assert sg[GZ_FREE_FROM:] == b'\xff' * (fsz - GZ_FREE_FROM)
    inner = bytearray(zlib.decompress(bytes(sg[so + doff:so + ssz]), 31))
    pe = {n: bytearray(inner[o:o + s]) for n, (o, s) in PE.items()}
    for n in names:
        UEFI_PATCHES[n](pe)
    for n, (o, s) in PE.items():
        assert len(pe[n]) == s
        inner[o:o + s] = pe[n]
    co = zlib.compressobj(9, zlib.DEFLATED, 31, 9)
    gz = co.compress(bytes(inner)) + co.flush()
    nssz = 0x18 + len(gz)
    nfsize = 24 + nssz
    assert ((F + nfsize + 7) & ~7) <= fsz, 'UEFI volume does not fit'
    sec = bytearray(sg[so:so + 0x18])
    sec[0:3] = nssz.to_bytes(3, 'little')
    hdr = bytearray(sg[F:F + 24])
    hdr[20:23] = nfsize.to_bytes(3, 'little')
    state = hdr[23]
    hdr[16] = hdr[17] = hdr[23] = 0
    hdr[16] = (-sum(hdr)) & 0xff                           # FFS header checksum
    hdr[17] = 0xaa                                         # no file checksum
    hdr[23] = state
    new = bytes(sg[:F]) + bytes(hdr) + bytes(sec) + gz
    b[off:off + fsz] = new + b'\xff' * (fsz - len(new))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('version', choices=sorted(VERSIONS))
    ap.add_argument('out')
    ap.add_argument('--orig', default=os.path.join(ROOT, 'original/xbl_unsigned.elf'))
    a = ap.parse_args()
    v = VERSIONS[a.version]
    b = bytearray(open(a.orig, 'rb').read())
    if 'sbl1' in v:
        patch_sbl1(b, *v['sbl1'])
    if 'uefi' in v:
        patch_uefi(b, v['uefi'])
    open(a.out, 'wb').write(b)
    print(f'{a.version}: wrote {a.out} (unsigned)')


if __name__ == '__main__':
    sys.exit(main())
