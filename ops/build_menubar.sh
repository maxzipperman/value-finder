#!/bin/zsh
# Build the menu-bar light into menubar/build/Value Finder.app (menubar/.gitignore keeps
# that folder out of git). It compiles the Swift files in menubar/Sources with swiftc
# (Xcode's command-line tools; no Xcode project, no packages) and writes nothing else.
# It does not install or open the app: ops/install_menubar.sh does the install.
#   ops/build_menubar.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/menubar/Sources"
OUT="$ROOT/menubar/build"
APP="$OUT/Value Finder.app"
BIN_NAME="ValueFinder"
ARCH="$(uname -m)"
MIN_MACOS="13.0"   # MenuBarExtra needs macOS 13

command -v swiftc >/dev/null || { echo "swiftc not found: install Xcode or its command-line tools." >&2; exit 1; }

STAGE="$OUT/.staging"
rm -rf "$STAGE"
mkdir -p "$STAGE/Value Finder.app/Contents/MacOS" "$STAGE/Value Finder.app/Contents/Resources"
STAGED="$STAGE/Value Finder.app"

echo "Compiling $(ls "$SRC"/*.swift | wc -l | tr -d ' ') Swift files for $ARCH (macOS $MIN_MACOS or later)..."
swiftc \
  -O \
  -swift-version 5 \
  -parse-as-library \
  -module-name ValueFinder \
  -target "$ARCH-apple-macosx$MIN_MACOS" \
  -framework AppKit -framework SwiftUI \
  -o "$STAGED/Contents/MacOS/$BIN_NAME" \
  "$SRC"/*.swift

cp "$ROOT/menubar/Info.plist" "$STAGED/Contents/Info.plist"
printf 'APPL????' > "$STAGED/Contents/PkgInfo"
plutil -lint "$STAGED/Contents/Info.plist" >/dev/null

# Seal the bundle with an ad-hoc signature (no certificate, nothing leaves the Mac).
# Not required: the compiler already signs the program itself, so a failure here only warns.
if command -v codesign >/dev/null; then
  codesign --force --sign - --timestamp=none "$STAGED" 2>/dev/null \
    || echo "note: ad-hoc signing failed; the app still runs." >&2
fi

rm -rf "$APP"
mv "$STAGED" "$APP"
rm -rf "$STAGE"
echo "Built: $APP"
echo "Check it without opening it:  \"$APP/Contents/MacOS/$BIN_NAME\" --selftest http://127.0.0.1:8787/api/summary"
echo "Install it:                   ops/install_menubar.sh"
