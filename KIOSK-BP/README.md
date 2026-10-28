# KIOSK-BP: XBL for the Kiosk (QCM6125 / Nicobar)

`xbl.elf`, `xbl_config.elf` and `devcfg.mbn` in this folder are what gets
flashed. `xbl.elf` is the current release, see the table below. The other two
are Quectel's, unchanged.

The Kiosk XBL is Quectel's binary with small patches on top. There is no XBL
source, so every change is a binary patch made by `tools/build_xbl.py` from the
original image. The patches are written as assembly in `src/`. Each version
rebuilds byte for byte from `original/xbl_unsigned.elf`.

## Versions

| Tag | Signed md5 | Status | What it does |
|-----|------------|--------|--------------|
| (commit 2d17402) | b5123eab | original | Quectel XBL as delivered |
| KIOSK-BP-xbl-v0 | 4792e319 | ok | Original code, re-signed here (proves the signing flow) |
| KIOSK-BP-xbl-v1 | 5a66e228 | superseded | SBL1 drives GPIO84 low (2 mA); no visible effect |
| KIOSK-BP-xbl-v2 | 6ebc5a8f | superseded | v1 at 16 mA + pull-down, at six SBL1 points; no visible effect |
| KIOSK-BP-xbl-v3 | a8f47f5f | diagnostic, never flashed | v2 stub + 2 s hold in SBL1 |
| KIOSK-BP-xbl-v4 | 34822b23 | ok, verified | Backlight dark until the splash is on the LVDS |
| KIOSK-BP-xbl-v5 | c4759741 | ok, verified | v4 + splash shown as soon as DisplayDxe is up |
| KIOSK-BP-xbl-v6 | ec576f6d | ok, logo seen from first light | v5 + GraphicsConsoleDxe no longer clears the logo |
| KIOSK-BP-xbl-v7 | 5bc30d2b | **current**, verified | v6 + LT9211D poll 100 ms → 5 ms, power-key hold 1600 → 1500 ms |

Details of each version are in [CHANGELOG.md](CHANGELOG.md).

## Boot display sequence (v7)

1. Power-on to about 0.25 s: the backlight may glow. This is before any XBL code
   runs; only a hardware default on Disp_EN can remove it.
2. SBL1 (`src/sbl1/gpio84_low.s`) drives GPIO84 (J6 pin 4, Disp_EN) low, so the
   backlight is off.
3. DisplayDxe's Quectel "GPIO Configuration" step would drive GPIO84 high. It is
   patched to drive it low.
4. When DisplayDxe installs its protocols (display up), EnvDxe
   (`src/uefi/envdxe_early_splash.s`) sets the GOP mode and runs Quectel's splash
   callback. The callback draws the logo, starts the LT9211D MIPI-to-LVDS bridge
   (its state machine is polled every 5 ms, not 100 ms), and 250 ms later (`src/uefi/envdxe_backlight_on.s`) raises GPIO84. The 27 in
   panel spec asks for at least 200 ms of valid signal before the backlight. So
   the first thing lit is the logo, on every panel size, and the 27 in RGB
   no-signal pattern is never visible.
5. GraphicsConsoleDxe's SetMode no longer fills the screen black, so the logo
   stays on until the kernel takes over.
6. The kernel keeps GPIO84 high (`dsi_panel.c`, `pwm_inverted`).

## Build, sign, flash

```sh
tools/build_xbl.py v7 /tmp/xbl_v7_unsigned.elf     # needs the Android clang (CLANG_BIN)
tools/sign.sh /tmp/xbl_v7_unsigned.elf /tmp/xbl.elf # sectools, OEM test certs
tools/flash_edl.sh /tmp/xbl.elf                     # qdl over EDL, xbl_a and xbl_b
```

The sectools signature is not deterministic: a rebuild matches a release in
every ELF segment except the hash/signature segment (1), so compare segments,
not the md5 of the signed file.

Or flash `xbl.elf` from this folder (or `releases/vN/xbl.elf`) with QFIL as usual.

**Recovery.** If a build does not boot, force EDL by hand and flash
`releases/v0/xbl.elf` or the last good release. `adb reboot edl` needs Android
running.

## Key addresses (all checked by the build script before patching)

| Where | What |
|-------|------|
| ELF seg 6, va 0xc221000 | SBL1. Log function 0xc23594c, zero cave 0xc2217a8–0xc2217ff, "SBL1 BUILD" log call 0xc22bb78 |
| ELF seg 16, va 0x5fc00000 | DXE volume. Last FFS (seg+0x41aa8) holds a gzip GUID section (1d301fe9-…, attr 0x1, no CRC) |
| TLMM GPIO84 | cfg 0x954000, io 0x954004 (TLMM 0x400000 + SOUTH tile 0x500000 + 84 × 0x1000) |
| DisplayDxe 0x14a30 | Quectel "GPIO Configuration": GPIO 27/83/84/85 high. GpioOut(84) value at 0x14b04 |
| EnvDxe 0x2930 | Quectel SplashScreenRenderCallback: DisplayUtils RenderLogo, GPIO101 high, LT9211D init (0x331c), Ctrl+C poll loop |
| GraphicsConsoleDxe 0x1b90 | In ConOutSetMode (0x1a50): GOP->Blt black fill, taken when the GOP is already in the target mode. v6 replaces it with `mov x0, xzr` |
| GraphicsConsoleDxe 0x24f8 | Driver Start signals the "display set mode" group 29d73c39-… on every start, after the SetMode above |
| EnvDxe 0x3498 | LT9211D state machine (0x331c): 100 ms sleep between passes. v7 passes 5000 µs; cap at 0x34f4 raised from 499 to 4095 passes |
| DALSys 0x206f4 | PmicDxe power-key hold, in ms (DAL property 0x12000086 → struct {2, 1600}). v7 sets 1500 |
| EnvDxe 0x2b94 | Registers 0x2930 on the "display set mode" event group 29d73c39-…, which GraphicsConsoleDxe signals late in DXE |

Background and the disassembly trail are in the knowledge bank:
`~/Firmware-LLM/knowledge_bank/documentation/09_display_touch/mipi-lvds.md`.
