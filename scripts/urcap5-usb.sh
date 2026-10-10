#!/usr/bin/env bash
# Put the current URCaps on a USB stick for the pendant, safely: no macOS "._"
# AppleDouble files (PolyScope's URCap picker would list "._perceptronic-….urcap" and
# fail on it), checksum-verified, then ejected. On the stick afterwards:
#
#   perceptronic-ps5-<ver>.urcap      the PolyScope 5 URCap, for Settings → System → URCaps → +
#   perceptronic-<ver>.urcapx         the PolyScope X URCap, for System Manager (PolyScope X
#                                     runs nothing from a stick)
#
#   scripts/urcap5-usb.sh                 # the stick named "URE MODELS"
#   scripts/urcap5-usb.sh "MY STICK"      # another FAT32 stick
#
# On the pendant: ☰ → Settings → System → URCaps → + → the file → Open → Restart. Nothing on
# the stick runs by itself: the urmagic_*.sh auto-install file was dropped on 2026-10-08
# (it restarted the controller the moment the stick went in), and any copy of it left on
# the stick from an earlier build is deleted below so no robot ever runs it again.
set -euo pipefail
cd "$(dirname "$0")/.."

volume="/Volumes/${1:-URE MODELS}"
urcap="$(find integrations/urcap/dist -maxdepth 1 -name 'perceptronic-ps5-*.urcap' | sort | tail -1)"
[[ -d "$volume" ]] || { echo "no stick at $volume — plug it in (or pass its name)"; exit 1; }
[[ -f "$urcap" ]] || { echo "no $urcap — make urcap5-package"; exit 1; }

urcapx="$(find integrations/urcap/dist -maxdepth 1 -name 'perceptronic-*.urcapx' | sort | tail -1)"

# replace any earlier build of the URCaps on the stick, and remove the retired auto-install
# file (+ its log) an older run of this script may have left there
find "$volume" -maxdepth 1 \( -name 'perceptronic-ps5-*.urcap' -o -name '._perceptronic-ps5-*' \
  -o -name 'perceptronic-*.urcapx' -o -name '._perceptronic-*.urcapx' \
  -o -name 'urmagic_perceptronic.*' -o -name '._urmagic_perceptronic.*' \) -delete
cp -X "$urcap" "$volume/"
[[ -f "$urcapx" ]] && cp -X "$urcapx" "$volume/"
dot_clean -m "$volume" 2>/dev/null || true
sync

want="$(shasum -a 256 "$urcap" | cut -d' ' -f1)"
got="$(shasum -a 256 "$volume/$(basename "$urcap")" | cut -d' ' -f1)"
[[ "$want" == "$got" ]] || { echo "checksum mismatch on the stick — try again"; exit 1; }
if find "$volume" -maxdepth 1 -name '._*' | grep -q .; then
  echo "warning: ._ files remain on the stick"
fi
echo "copied $(basename "$urcap") (sha256 ${want:0:12}…) to $volume"
[[ -f "$urcapx" ]] && echo "copied $(basename "$urcapx") (PolyScope X: install it through System Manager)"
echo "on the pendant: ☰ → Settings → System → URCaps → + → $(basename "$urcap") → Open → Restart"
diskutil eject "$volume" >/dev/null && echo "ejected — take it to the pendant"
