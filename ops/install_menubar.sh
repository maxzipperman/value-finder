#!/bin/zsh
# Copy the built menu-bar light to ~/Applications. It does not open the app and does not
# add a login item; it prints how to do both. Build it first with ops/build_menubar.sh.
#   ops/install_menubar.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILT="$ROOT/menubar/build/Value Finder.app"
DEST_DIR="$HOME/Applications"
DEST="$DEST_DIR/Value Finder.app"
ID="com.valuefinder.menubar"

bundle_id() { /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null || true; }

[[ -d "$BUILT" ]] || { echo "Nothing to install yet. Build it first: ops/build_menubar.sh" >&2; exit 1; }
[[ "$(bundle_id "$BUILT")" == "$ID" ]] || { echo "The built app is not the Value Finder light." >&2; exit 1; }
if pgrep -f "$DEST/Contents/MacOS/ValueFinder" >/dev/null 2>&1; then
  echo "The Value Finder light is running. Choose Quit in its menu, then run this again." >&2
  exit 1
fi
if [[ -e "$DEST" ]]; then
  [[ "$(bundle_id "$DEST")" == "$ID" ]] || { echo "$DEST is some other app; leaving it alone." >&2; exit 1; }
  rm -rf "$DEST"
fi
mkdir -p "$DEST_DIR"
ditto "$BUILT" "$DEST"

cat <<EOF
Installed: $DEST

To open it now:
  open "$DEST"
  (or double-click Value Finder in the Applications folder inside your home folder)

To have it start every time you log in:
  System Settings > General > Login Items. Under "Open at Login", click +,
  then choose Value Finder in the Applications folder inside your home folder.

It shows a wind symbol in the menu bar. The dot stays gray until the dashboard is
running at http://127.0.0.1:8787/ . To remove it: ops/uninstall_menubar.sh
EOF
