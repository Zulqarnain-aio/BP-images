# KIOSK-BP XBL changelog

Newest first. md5 is of the signed `releases/vN/xbl.elf`.

## v5: show the splash as soon as the display is up (c4759741, current)
- Before v5, the splash callback (logo, LT9211D, backlight) ran on the "display
  set mode" event. GraphicsConsoleDxe signals that event late in DXE. EnvDxe now
  also registers for the installation of EFI_DISPLAY_UTILS, which DisplayDxe
  installs as soon as the panel is initialised. The first time it fires,
  EnvDxe calls GOP SetMode(0) (so the later console SetMode is a no-op and does
  not reinitialise the bridge) and runs the callback. Later events only redraw
  the logo.
- The Ctrl+C pin-test window after the LT9211D init is cut from 1 s to 0.3 s.
- Measured: ABL starts 1.2 s earlier (MPM 269098 → 229691 at 32768 Hz). The
  splash was still intact at the kernel handover.

## v4: backlight dark until the splash is on the LVDS (34822b23)
- Root cause: Quectel's DisplayDxe "GPIO Configuration" drives GPIO84
  (Disp_EN) high at about 1 s, long before the LT9211D sends a picture. That is
  the empty backlight on 18/22 in and the RGB no-signal pattern on 27 in.
- SBL1 drives GPIO84 low at "SBL1 BUILD" (16 mA, pull-down).
- DisplayDxe 0x14b04: GpioOut(84, 1) → GpioOut(84, 0).
- EnvDxe: 250 ms after the LT9211D init, GpioOut(84, 1).
- Verified on a Kiosk: the splash comes up directly, with no empty backlight and
  no RGB pattern.

## v3: diagnostic, never flashed (a8f47f5f)
- v2 stub plus a 2 s hold in SBL1, to make the GPIO84 effect obvious. Made
  unnecessary once DisplayDxe was found to re-raise GPIO84.

## v2: stronger drive, more points (6ebc5a8f, superseded)
- GPIO84 low at 16 mA with pull-down, at six SBL1 log points (BUILD,
  boot_flash_init, xblconfig_init, boot_config_data_table_init, pm_device_init,
  SBL1 End). Boots, but the backlight was unchanged (DisplayDxe re-raises it).

## v1: SBL1 drives GPIO84 low (5a66e228, superseded)
- 2 mA, at "SBL1 BUILD" only. Boots, but there was no visible change.

## v0: original code, re-signed (4792e319)
- Quectel's XBL, re-signed with the OEM test certs through sectools. Confirms
  the device takes our signatures.
