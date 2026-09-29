#!/bin/zsh
# Remove the menu-bar light's copy from ~/Applications. Quit it first (Quit in its menu).
# It removes nothing else: take it out of Login Items yourself if you added it there.
#   ops/uninstall_menubar.sh
set -euo pipefail
DEST="$HOME/Applications/Value Finder.app"
ID="com.valuefinder.menubar"

if [[ ! -e "$DEST" ]]; then
  echo "Not installed: there is no $DEST"
  exit 0
fi
found_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$DEST/Contents/Info.plist" 2>/dev/null || true)"
[[ "$found_id" == "$ID" ]] || { echo "$DEST is some other app; leaving it alone." >&2; exit 1; }
if pgrep -f "$DEST/Contents/MacOS/ValueFinder" >/dev/null 2>&1; then
  echo "The Value Finder light is running. Choose Quit in its menu, then run this again." >&2
  exit 1
fi
rm -rf "$DEST"
echo "Removed $DEST"
echo "If you added it to Login Items, remove it there too: System Settings > General > Login Items."
