# Changelog

Version history for the SPARCAL Spatial-SNV Viewer. The running version is
`sparcal_viewer.__version__`; the About dialog (click the app name on the top
bar) shows it alongside the build time.

## 1.5.0
- **Auto tumor regions: new "Method" selector.** `raw_burden` detects tumor
  **extent** from un-normalized SNV burden — validated on the DCIS sec2 ground
  truth as the best extent detector (raw burden ≈ per-spot coverage/cellularity,
  which tracks the dense DCIS ducts; coverage-normalizing it *removes* that
  signal). `customized` keeps the prior fully tunable behaviour, including the
  optional "Normalize by coverage (UMI)" checkbox. Default is `raw_burden`;
  selecting it forces normalization off and disables the checkbox, while
  `customized` re-enables it (checked when a study has coverage). A profile /
  latent-factor method for clonal *substructure* is planned separately.

## 1.4.0
- **Colour-blind-safe Overview palette.** The Overview / profile-map export no
  longer cycles the full HSV rainbow (`pg.intColor`), which put a pink region hue
  right next to the grey "multiple regions" marker — indistinguishable under
  colour-vision deficiency. Regions now use a fixed 8-hue categorical palette
  validated CVD-safe (worst adjacent ΔE 24.2), and the multiply-assigned marker
  is now **near-black** (`#1a1a19`) so it can never collide with a region hue.
  With >8 regions the palette repeats; position + the region list keep them
  distinguishable (colour is no longer the sole cue).

## 1.3.0
- **New "Overview" button** (left view, directly under **Reset**): paints every
  tumor region in the current profile its own colour so the whole profile is
  visible at a glance. Spots claimed by **more than one region are shown dark
  grey**; spots in no region stay pale. Hover still names the region under the
  cursor, and **Reset** clears the overview.
- **Fix: turning off "color by SNV count" now restores a uniform colour.** Spots
  kept their per-spot burden colours because pyqtgraph's single-brush `setBrush`
  leaves stale per-point brushes in place; the view now clears them, so toggling
  the mode off (and Reset / Overview) repaints every spot uniformly.

## 1.2.0
- **Magnitude-aware burden — gene-expression studies now carry real expression.**
  The per-spot burden is now the **row-sum of the matrix values** instead of a
  count of nonzero columns. For the binary SNV studies this is identical (values
  are 0/1), but a magnitude matrix (e.g. a gene-expression study) now drives the
  burden/`Auto`-region signal by expression level, not mere gene presence.
  - `DLPFC_151507_GEX.zip` was rebuilt: values now encode **log-normalized
    expression** — `normalize_total(1e4)` per spot → `log1p` → `round(x * 36)` →
    `uint8` (0 = absent, preserved exactly).
  - The "% of spots" variant grouping (`generate_*`) and the cached per-feature
    total now use a **presence** count (`value > 0`), so they stay correct
    regardless of whether the matrix stores presence or magnitudes.

## 1.1.0
- **New example studies on the `SPARCAL-studies-v1` release:**
  - `DCIS_1_SPARCAL.zip` — DCIS section 1, SPARCAL SNV calls (merged germline +
    UPV + somatic matrix).
  - `DCIS_2_SpatialSNV.zip` — DCIS section 2, SNVs called by **SpatialSNV**
    (Mutect2-based); same Visium section as the bundled `DCIS_2_SPARCAL`.
  - `DLPFC_151507_GEX.zip` — DLPFC 151507 **gene-expression** study. The matrix is
    a per-spot gene-presence matrix (gene detected → 1) from the Visium
    filtered_feature_bc_matrix, so per-spot "burden" is gene complexity and the
    SNV list / Auto regions operate on genes.
- **P4/P6 now ship coverage:** `P4_rep1_SPARCAL.zip` and `P6_rep1_SPARCAL.zip` now
  include a `spot_coverage.csv`, so **Auto** tumor detection coverage-normalizes
  the SNV burden for those sections instead of falling back to raw burden.
- Every new/updated study bundles a `spot_coverage.csv` (per-spot total UMI).

## 1.0.1
- **Auto tumor regions — every knob is now a slider + spin box:** Intensity, Grow
  margin, Min region size, and Split valley depth each pair a drag slider with a
  spin box, so you can drag, step with the up/down arrows, or type a number; the
  two stay in sync. New defaults: **Grow margin 10** (was 30) and **Split valley
  depth 40%** (was 30%).
- **About dialog now reachable:** the app name on the top bar was a bare menu-bar
  action, which does not render on macOS's native menu bar. It's now a proper
  app-name menu whose "About …" item (folded into the application menu on macOS)
  opens the version/build-time dialog.

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
