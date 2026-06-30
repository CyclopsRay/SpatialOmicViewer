# Changelog

Version history for the SPARCAL Spatial-SNV Viewer. The running version is
`sparcal_viewer.__version__`; the About dialog (click the app name on the top
bar) shows it alongside the build time.

## 1.0.0
- **Hover hit-radius fix:** the region label now appears even when the cursor is
  in the gap *between* spots — the snap radius is derived from the spot pitch
  instead of a fraction of the spot size.
- **Multiple centers per Auto region:** an Auto region keeps *all* its seed
  centers (not just the strongest), so a basin fused from several peaks shows
  several stars — exposing how many potential sub-regions a collection contains.
- **Export profile map:** File ▸ Export ▸ "Profile map (with/without background)"
  renders every region of the current profile in its own colour to **PDF** (vector)
  or **PNG** (by file extension).
- **Compare profiles:** on the profile page, Edit → select two profiles →
  Function ▸ "Compare profiles" shows a region×region Jaccard overlap table plus
  cluster-agreement scores (ARI, NMI, homogeneity, completeness, V-measure), all
  computed pure-numpy. Item set = all in-tissue spots, unassigned → background.

## 0.5.0
- **Tumor profiles:** Regions are now organized into named *profiles* (separate
  separations of the tissue — e.g. "Ground Truth", "Test", auto-detected). Column 2
  has a new top layer: pick a profile, then its regions; the region view is titled
  `Tumor profile: "<name>"` with a `‹ Profiles` back-button. New/Rename/Delete
  profile management. Persistence adds a `profile` column to `tumor_groups.csv`,
  `tumor_centers.csv`, and `variant_groups.csv`; files without it load into a
  single `Default` profile (back-compatible). DCIS_2 ships as Ground Truth
  (T1–T11), Test (Test_1–Test_16), and Other (ALL, T3Eexclusive).
- **Reset:** new top-left button on the spatial view clears all region/group/SNV
  selection and paints every spot a uniform pale white.
- **Auto regions — clearer view:** opening the Auto dialog resets the tissue so
  the coloured region preview reads against a blank background, and the dialog now
  always floats on top of the main window.
- **Hover-to-identify:** in normal mode, hovering a spot shows its region name as
  a label at the cursor and selects/shows that region in column 2 (live, updating
  only when the hovered region changes).

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
