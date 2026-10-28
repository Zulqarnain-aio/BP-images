#!/bin/bash
# Sign an XBL with the OEM test certs (same as the stock build), via sectools.
# usage: tools/sign.sh unsigned.elf signed_out.elf
# UNPACKING_TOOL points at the tree that holds common/sectools (Python 2.7).
set -euo pipefail
UT=${UNPACKING_TOOL:-/nvme/A15/QCOM6125_A15_Kiosk_22/Unpacking_Tool}
in=$(realpath "$1"); out=$(realpath -m "$2")
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/in"; cp "$in" "$tmp/in/xbl.elf"
(cd "$UT" && python common/sectools/sectools.py secimage -i "$tmp/in/xbl.elf" \
    -c common/sectools/config/nicobar/nicobar_secimage.xml -g xbl -sa \
    --cfg_selected_cert_config=oem_certs -o "$tmp/out" | tail -2)
cp "$tmp/out/nicobar/xbl/xbl.elf" "$out"
md5sum "$out"
