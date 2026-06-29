#!/usr/bin/env bash
# Build a standalone macOS .app for the SPARCAL Spatial-SNV Viewer.
# Run this ON your Mac (PyInstaller can only build for the OS it runs on).
#
#   cd viewer
#   ./build_macos.sh
#
# Output: dist/SPARCAL-SNV-Viewer.app   (double-clickable; no Python needed)
#
# First launch of an unsigned app: right-click the .app ▸ Open ▸ Open
# (Gatekeeper), or run:  xattr -dr com.apple.quarantine dist/SPARCAL-SNV-Viewer.app
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV=".build-venv"

echo ">> creating build venv"
rm -rf "$VENV"
"$PYTHON" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller >/dev/null

echo ">> running PyInstaller"
rm -rf build dist
# Anaconda Python may leak Qt plugin paths into the isolated child processes
# that PyInstaller spawns for submodule collection, causing "Could not find
# the Qt platform plugin 'cocoa'" errors.  Offscreen prevents that.
export QT_QPA_PLATFORM=offscreen
pyinstaller \
  --name "SPARCAL-SNV-Viewer" \
  --windowed \
  --noconfirm \
  --collect-submodules pyqtgraph \
  --hidden-import PySide6.QtSvg \
  --osx-bundle-identifier "edu.vanderbilt.maiziezhou.sparcal.snvviewer" \
  sparcal_viewer/__main__.py

echo
echo ">> built: dist/SPARCAL-SNV-Viewer.app"
echo ">> NOTE: study data (the .config folder) stays separate — open it from the app."
