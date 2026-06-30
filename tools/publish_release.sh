#!/usr/bin/env bash
# Publish the built viewer to a GitHub Release so users can just download & run.
#
#   cd viewer
#   ./build_macos.sh                 # produces dist/SPARCAL-SNV-Viewer-macos.zip
#   tools/publish_release.sh v1.0.0  # creates/updates the release & uploads the app
#
# Requirements: the `gh` CLI, authenticated (`gh auth login`) with write access to
# the repo's releases. Uploads every dist/SPARCAL-SNV-Viewer-*.zip it finds, so you
# can build on macOS / Windows / Linux and run this once per platform with the same
# tag to attach all of them to one release.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "usage: tools/publish_release.sh <tag>   (e.g. v1.0.0)" >&2
  exit 2
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "!! gh CLI not found. Install it and run 'gh auth login' first." >&2
  exit 1
fi

shopt -s nullglob
ASSETS=(dist/SPARCAL-SNV-Viewer-*.zip)
if [[ ${#ASSETS[@]} -eq 0 ]]; then
  echo "!! no dist/SPARCAL-SNV-Viewer-*.zip found — run ./build_macos.sh first." >&2
  exit 1
fi

TITLE="SPARCAL Spatial-SNV Viewer ${TAG}"
NOTES="Standalone build of the SPARCAL Spatial-SNV Viewer.

Download the asset for your OS, unzip, and open it — the DCIS_2 study is bundled
and loads automatically. (macOS: first launch, right-click ▸ Open, or run
\`xattr -dr com.apple.quarantine SPARCAL-SNV-Viewer.app\`.)"

if gh release view "$TAG" >/dev/null 2>&1; then
  echo ">> updating existing release $TAG"
  gh release upload "$TAG" "${ASSETS[@]}" --clobber
else
  echo ">> creating release $TAG"
  gh release create "$TAG" "${ASSETS[@]}" --title "$TITLE" --notes "$NOTES"
fi

echo ">> done: $(gh release view "$TAG" --json url -q .url)"
