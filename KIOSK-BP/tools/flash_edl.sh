#!/bin/bash
# Flash one signed XBL to xbl_a and xbl_b over EDL with qdl.
# usage: tools/flash_edl.sh signed_xbl.elf
# If Android is up, the device is sent to EDL first (adb reboot edl).
# Recovery if the board no longer boots: force EDL by hand and flash
# releases/v0/xbl.elf (the original code, re-signed) or the last good version.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
FIREHOSE=${FIREHOSE:-/nvme/A15/kiosk22/Unpacking_Tool/qfil_download_emmc/prog_firehose_ddr.elf}
img=$(realpath "$1")
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cp "$img" "$tmp/xbl.elf"; cp "$FIREHOSE" "$tmp/prog_firehose_ddr.elf"
cp "$here/rawprogram_xbl.xml" "$tmp/"
if ! lsusb | grep -q 05c6:9008; then
    adb reboot edl
    for _ in $(seq 30); do lsusb | grep -q 05c6:9008 && break; sleep 1; done
fi
cd "$tmp" && qdl -s emmc prog_firehose_ddr.elf rawprogram_xbl.xml
