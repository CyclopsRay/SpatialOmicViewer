# SPARCAL Spatial-SNV Viewer — project rules

This repo (github `CyclopsRay/SpatialOmicViewer`) is the PySide6 desktop viewer.

## Versioning — required on every update
Every change committed to this repo **must bump the version forward one step and
record it in the changelog**, unless the request explicitly says otherwise.

- **Default bump = one minor step** of `sparcal_viewer/__init__.py:__version__`
  (e.g. `0.4.0 → 0.5.0 → 0.6.0`). Only deviate when the user specifically asks
  for a different bump (e.g. a patch `0.4.0 → 0.4.1` or a major `0.4.0 → 1.0.0`).
- **Update [CHANGELOG.md](CHANGELOG.md)** in the same commit: add a new
  `## X.Y.Z` section at the top describing what changed, written like the
  existing entries. The changelog is the version tracker shown to users.
- The About dialog (click the app name on the top bar) reports
  `__version__` + build time, so the bumped version is what ships.

Do **not** push — leave that to the user, who pushes manually.

## Branching
Without specific clarification, **always commit to `main`**. Only work on a
feature branch when the user explicitly asks for one.

## Build time
`build_macos.sh` stamps `sparcal_viewer/_build_info.py` (gitignored) at build
time; `sparcal_viewer.build_time()` falls back to the source mtime from a
checkout. The About dialog shows whichever is available.

## Tests
Tests are plain scripts (no pytest). Run them headless before committing:

```
QT_QPA_PLATFORM=offscreen python tests/test_core.py
QT_QPA_PLATFORM=offscreen python tests/test_gui_smoke.py
```

The smoke test needs the bundled `DCIS_2_SPARCAL` study (its `snv_matrix.pkl`
is distributed via GitHub Releases, not git). Extend the tests when adding
behaviour, matching the existing assert-and-print style.
