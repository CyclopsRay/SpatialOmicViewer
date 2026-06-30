# Changelog

Version history for the SPARCAL Spatial-SNV Viewer. The running version is
`sparcal_viewer.__version__`; the About dialog (click the app name on the top
bar) shows it alongside the build time.

## 0.4.0
- **Region/group edit selection:** Edit mode now uses extended selection so
  **Shift-click selects a contiguous range** and Ctrl/Cmd-click toggles
  individual regions or groups (previously single-toggle only, with no working
  Shift range-select).
- **About dialog:** clicking the app name on the top bar opens an About box
  showing the version and build time. Build time is stamped into
  `_build_info.py` by `build_macos.sh`, falling back to the source mtime when
  running from a checkout.

## 0.3.0
Watershed regions, selection legend, saved centers.
- Auto tumor regions now use a seeded watershed: two centers that grow into each
  other fuse only across a shallow saddle (new "Split valley depth" control)
  instead of always merging on contact.
- Showing a group / selected SNVs on tissue colours spots by how many of the
  selected SNVs each covers, with a selection-specific legend (top-left).
- Auto regions save their center (strongest seed) to `tumor_centers.csv` and
  mark it with a star when the region is selected.
- Packaging: `build_macos.sh` bundles the DCIS_2 study inside the `.app` and the
  app opens that bundled config by default (copied to a writable per-user dir
  when frozen so edits persist); `tools/publish_release.sh` uploads built zips
  to a GitHub Release.

## 0.2.0
SNV-burden spot coloring and auto tumor-region detection.
- Colour on-tissue spots by per-spot SNV count on a sky-blue→purple quantile
  ramp, with a count legend ("color by SNV count" toggle).
- "Auto" tumor regions via hysteresis-thresholded seeded region growing on the
  Visium grid: intensity slider, grow margin, min region size, optional coverage
  normalization, and manual seed add/exclude by lasso.
- Optional per-spot `spot_coverage.csv` (barcode,total_umi) for coverage
  normalization; `tools/make_spot_coverage.py` generates it from raw SpaceRanger
  output.

## 0.1.0
SNV variant file converted to JSON; file management upgrade.
- Export SNVs as `.json` with contents/source/variants structure tracking the
  originating region and group for provenance.
- Import reads `.json` and navigates to the matching region/group, re-creating
  them from the variant list if they no longer exist.
- Edit mode supports deleting individual variant groups (not just whole
  regions), with a confirmation dialog listing everything affected.
- Column-3 action bar always visible (Show on tissue / Add spots); Import
  button added; empty spatial pane shows a "Click to open a config file" prompt.
