#!/usr/bin/env bash
# Build a standalone macOS .app for the SPARCAL Spatial-SNV Viewer, with the
# DCIS_2 study bundled inside so it opens with data already loaded.
#
# Run this ON your Mac (PyInstaller can only build for the OS it runs on).
#
#   cd viewer
#   ./build_macos.sh
#
# Outputs:
#   dist/SPARCAL-SNV-Viewer.app              double-clickable; no Python needed
#   dist/SPARCAL-SNV-Viewer-macos.zip        the release asset (app, zipped)
#
# First launch of an unsigned app: right-click the .app ▸ Open ▸ Open
# (Gatekeeper), or run:  xattr -dr com.apple.quarantine dist/SPARCAL-SNV-Viewer.app
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV=".build-venv"
STUDY="DCIS_2_SPARCAL"

if [[ ! -f "$STUDY/$STUDY.config" ]]; then
  echo "!! missing study folder '$STUDY' (with its .config + snv_matrix.pkl)." >&2
  echo "   Download the data per $STUDY/DOWNLOAD_MATRIX.md before building." >&2
  exit 1
fi

echo ">> creating build venv"
rm -rf "$VENV"
"$PYTHON" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller >/dev/null

echo ">> running PyInstaller (bundling the $STUDY study)"
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
  --add-data "$STUDY:$STUDY" \
  --osx-bundle-identifier "edu.vanderbilt.maiziezhou.sparcal.snvviewer" \
  sparcal_viewer/__main__.py

echo ">> zipping the .app for release"
( cd dist && ditto -c -k --sequesterRsrc --keepParent \
    "SPARCAL-SNV-Viewer.app" "SPARCAL-SNV-Viewer-macos.zip" )

echo
echo ">> built: dist/SPARCAL-SNV-Viewer.app"
echo ">> release asset: dist/SPARCAL-SNV-Viewer-macos.zip"
echo ">> the app opens the bundled $STUDY study automatically on launch."
echo ">> publish it with:  tools/publish_release.sh <tag>   (needs gh)"
