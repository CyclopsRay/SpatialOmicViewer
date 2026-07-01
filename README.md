# SPARCAL Spatial-SNV Viewer

A desktop app to explore a spatial SNV presence matrix: a tissue view, tumor
**profiles** (named separations of the tissue into regions), and per-region
variant (SNV) groups.

```
┌──────────────────────┬────────────────────────┬──────────────────────┐
│  Spatial view        │  Tumor profiles ↔ regions │ SNV list           │
│  (hires image+spots) │  [New][Rename][Del][Edit] │ [Export][Import][⋯]│
│  [Reset] ▢ background │   Ground Truth (10)       │ chrom_pos_ref…     │
│  ▢ color by SNV count│   Test (16)  · Other (2)  │ …                  │
│  hover → region label│  ── open a profile ──▸    │                    │
│  ▦ burden legend     │  Tumor profile: "…"  ‹Prof│                    │
│                      │  [Add][Edit][Auto][Gen ▾] │                    │
│                      │   region ├ exclusive 🟪   │                    │
│                      │          └ general   🟩   │                    │
└──────────────────────┴────────────────────────┴──────────────────────┘
```

Click the app name on the top bar (**About**) to see the version and build time.

## Download & run (no Python)

Grab the build for your OS from the
[**Releases**](https://github.com/CyclopsRay/SpatialOmicViewer/releases) page,
unzip, and open it — **the DCIS_2 example study is bundled and loads automatically**,
so there is nothing else to download or configure.

- **macOS:** open `SPARCAL-SNV-Viewer.app`. First launch of the unsigned app:
  right-click ▸ **Open** ▸ **Open**, or run
  `xattr -dr com.apple.quarantine SPARCAL-SNV-Viewer.app`.

The bundled study is copied to a writable per-user folder on first launch
(`~/Library/Application Support/SPARCAL-SNV-Viewer/` on macOS) so the regions,
groups, and centers you create persist. To open a *different* study, just drag
its `.config` into the window (File ▸ Open).

## Open more example studies

Extra studies are published as zip assets on the
[**SPARCAL-studies-v1** release](https://github.com/CyclopsRay/SpatialOmicViewer/releases/tag/SPARCAL-studies-v1).
Each zip is fully self-contained (SNV matrix + Visium image/positions + config),
so there is nothing else to download.

| Study | Tissue | Notes |
|---|---|---|
| `DLPFC_151507_SPARCAL.zip` | DLPFC (spatialLIBD) | ships a **Ground Truth** profile of cortical layers L1–L6 + WM |
| `DLPFC_151669_SPARCAL.zip` | DLPFC | Ground Truth profile (5 annotated layers for this section) |
| `DLPFC_151673_SPARCAL.zip` | DLPFC | Ground Truth profile (L1–L6 + WM) |
| `P4_rep1_SPARCAL.zip` | cSCC P4 (Visium rep1) | tumor section, no preset profile |
| `P6_rep1_SPARCAL.zip` | cSCC P6 (Visium rep1) | tumor section, no preset profile |

**To open one:**
1. Download a zip from the release page (or `curl -L -O <asset-url>`).
2. Unzip it — you get a folder like `DLPFC_151507_SPARCAL/` with a `.config` inside.
3. **Drag the `.config` onto the viewer window**, or use **File ▸ Open** and pick it.

The DLPFC studies open on the profile list with a **Ground Truth** profile — open
it to see the layer regions, or use **Edit ▸ Function ▸ Compare** to score another
profile against it. Anything you add (profiles, regions, groups) is saved back
into that unzipped folder, so it persists the next time you open the `.config`.

Any study folder that follows the layout in
[A study config folder](#a-study-config-folder) works the same way — these
release zips are just prebuilt examples.

## Get the example data (only to build/run from source)

The `DCIS_2_SPARCAL/` bundle ships in the repo **except** the 235 MB SNV matrix,
which is a [Release asset](https://github.com/CyclopsRay/SpatialOmicViewer/releases).
See [DCIS_2_SPARCAL/DOWNLOAD_MATRIX.md](DCIS_2_SPARCAL/DOWNLOAD_MATRIX.md) — drop
`snv_matrix.pkl` next to the `.config` and the study opens. (The viewer works
with any such study folder; the matrix only matters for this bundled example.)

## Run from source (development)

```bash
pip install -r requirements.txt
python run_dev.py DCIS_2_SPARCAL/DCIS_2_SPARCAL.config   # or open from File ▸ menu
```

## Build & publish a standalone app

PyInstaller builds for the OS it runs on, so **run this on your Mac**. The build
bundles the `DCIS_2_SPARCAL/` study **inside** the app (so it opens with data
already loaded) and zips it for release:

```bash
./build_macos.sh
# → dist/SPARCAL-SNV-Viewer.app        (double-click; no Python needed)
# → dist/SPARCAL-SNV-Viewer-macos.zip  (the release asset)
```

Then attach it to a GitHub Release so users can just download & run (needs the
`gh` CLI, authenticated with `gh auth login`):

```bash
tools/publish_release.sh v1.0.0
```

`publish_release.sh` uploads every `dist/SPARCAL-SNV-Viewer-*.zip` it finds, so
building on more than one OS and re-running it with the same tag attaches all the
platform builds to one release.

First launch of the unsigned app: right-click ▸ Open ▸ Open, or
`xattr -dr com.apple.quarantine dist/SPARCAL-SNV-Viewer.app`.

## A study config folder

Everything for one study lives in a self-contained folder with a `.config`
file (drag it into the app, or File ▸ Open). Example: `DCIS_2_SPARCAL/`.

| File | What |
|---|---|
| `*.config` | YAML; `files:` paths are **relative** to the folder |
| `snv_matrix.pkl` | pandas uint8, rows=barcodes (`AAAC…-1`), cols=`{chrom}_{pos}_{ref}_{alt}` |
| `tissue_positions.csv` | Visium spot coordinates |
| `tissue_hires_image.png` | background image |
| `scalefactors_json.json` | Visium scale factors |
| `tumor_groups.csv` | regions the app saves (`profile,region_name,barcode`) |
| `variant_groups.csv` | variant groups the app saves (`profile,region_name,group_name,group_type,snv_key`) |
| `tumor_centers.csv` | center seeds of each **Auto** region (`profile,region_name,barcode`); a region can have several centers, each highlighted ★ when selected |
| `spot_coverage.csv` *(optional)* | per-spot UMI (`barcode,total_umi`) for coverage-normalized **Auto** tumor detection |

To make a new study, copy the four input files + a `.config` into a new folder
and edit the header fields. The three saved CSVs can start as just their header
row. The leading `profile` column groups regions into named profiles; a CSV
written by an older version (no `profile` column) loads into a single `Default`
profile automatically.

### Per-spot coverage (optional, for **Auto** regions)

`Auto` tumor detection works best when it normalizes SNV burden by sequencing
depth, so it grows real tumor structure instead of a coverage map. Generate the
coverage table once from the raw SpaceRanger output:

```bash
python tools/make_spot_coverage.py /path/to/spaceranger/outs \
  -o MyStudy/spot_coverage.csv     # accepts outs/, the MTX folder, or the .h5
```

If `spot_coverage.csv` is absent the app falls back to raw burden (the **Auto**
dialog disables its "Normalize by coverage" checkbox).

## Using it

**Spatial view (col 1)** — pan/zoom; a **Reset** button top-left and two toggles
top-right:
- **Reset** — clear every region/group/SNV selection; the tissue goes uniform
  pale white (a blank canvas).
- **background** — show/hide the tissue image.
- **color by SNV count** — colour each spot by how many SNVs it carries, on a
  **sky-blue → purple** ramp (quantile-scaled so the skewed burden spreads out).
  A legend top-left maps colour to the actual SNV count at each quantile.
- **Hover to identify** — in normal mode (no lasso), hovering a spot shows its
  region name as a label at the cursor and selects/shows that region in column 2.
  The label snaps to the nearest spot even in the gaps between spots.

**Tumor profiles (col 2, top layer)** — a *profile* is a named separation of the
tissue into regions (e.g. ground-truth annotations, a manual set, or an Auto run).
Column 2 opens on the profile list:
- **New / Rename / Delete** a profile.
- Double-click (or select + **Open profile ▸**) to drop into that profile's
  regions. A **‹ Profiles** back-button returns to this list.
- **Edit** → multi-select two profiles → **Function ▾ ▸ Compare profiles** — see
  [Comparing profiles](#comparing-profiles).

**Tumor regions (col 2, per-profile)** — titled `Tumor profile: "<name>"`:
- **Add** → lasso spots on the tissue → **Finish** → name the region.
- **Edit** → multi-select regions/groups (Shift-click for a range, Ctrl/Cmd-click
  to toggle) → **Merge** (new region, removes the originals, prompts for a name)
  or **Delete**.
- **Auto** → auto-detect contiguous tumor regions from SNV-burden intensity. The
  Auto window floats over the app and blanks the tissue so the coloured region
  preview reads clearly.
  - **Intensity** slider — higher keeps fewer / smaller regions.
  - **Grow margin** — how far below the seed threshold a region may grow
    (hysteresis); **Min region size** drops specks.
  - **Normalize by coverage** — divide out per-spot UMI depth (needs
    `spot_coverage.csv`; see above).
  - **Split valley depth** — when two centers grow into each other, keep them as
    **separate** regions only if the valley between them is at least this deep
    (% of peak height). Lower = split more eagerly; 100% = always merge touching
    regions. This is a watershed: each spot is claimed by its nearest peak, and
    two basins fuse only across a shallow saddle.
  - **Add seeds / Exclude (lasso)** — force-add or remove seed spots by lassoing
    the tissue; the preview updates live. **Create regions** writes them out.
    Each region keeps **all** its seed centers (not just the strongest), saved to
    `tumor_centers.csv` and marked with ★ when the region is selected — so a
    region fused from several peaks shows several stars, a hint that it may be a
    merge of several underlying regions.

  Seeds are high-intensity local maxima; regions flood-fill outward over the
  Visium grid so they stay contiguous (no scattered spots).
- Click a region, then **Generate ▾**:
  - **Exclusive** — SNVs present only in this region (absent everywhere else). 🟪
  - **General** — SNVs in > *N*% of *all* in-tissue spots (default 80). 🟩
  - **Exclusive by threshold** — present in > max% inside **and** < min% outside
    (defaults 80 / 20). 🟪
- Each generated group appears as a colored tag under the region; click it to
  list its SNVs in column 3 and highlight the carrying spots, **coloured by how
  many of the group's SNVs each spot covers** — with a legend top-left keyed to
  *that* group's count range.

**SNV list (col 3)**
- **Export** → write the SNVs (selected, or all if none selected) to a `.json`
  carrying the variant list plus its source region/group provenance.
- **Import** → re-open an exported `.json`, re-creating the region/group if it's
  gone.
- **Select all** (or pick any subset), then **Show on tissue** highlights spots
  carrying the chosen SNVs, coloured by per-spot count with a selection-specific
  legend top-left; **Add spots → region** turns those spots into a new tumor region.

Profiles, regions, centers, and variant groups are written back to the CSVs
immediately, so they reload next time you open the config.
<img width="1503" height="929" alt="image" src="https://github.com/user-attachments/assets/52ea12ce-7124-4ebb-a525-519aa1ea0b61" />

## Comparing profiles

Two profiles are two clusterings of the same spots, so you can measure how well
they agree. On the profile list: **Edit** → select **exactly two** profiles →
**Function ▾ ▸ Compare profiles (ARI / overlap)**. The result dialog shows:

- a **region × region overlap** table — for each region in profile A, its
  best-matching region in profile B by **Jaccard** (`|∩| / |∪|`), so you can see
  which regions correspond and whether one region spans several others;
- **cluster-agreement scores**: **ARI**, **NMI**, **homogeneity** (does a
  B-region mix several A-regions?), **completeness** (was an A-region split across
  B?), and **V-measure**.

The item set is all in-tissue spots; spots in no region get a shared `background`
label, and where regions overlap the smallest one wins. Scores are computed in
pure NumPy (so they work in the packaged app) and match scikit-learn. ARI is
pairwise — two profiles at a time.

## Exporting a profile map

**File ▸ Export ▸ Profile map (with background)** / **(without background)**
renders every region of the current profile in its own colour to **PDF** (vector)
or **PNG**, chosen by the file extension. (Column 3's **Export/Import** separately
save an SNV *list* as `.json` with its region/group provenance.)

## Defaults (config `variant_grouping:`)

`general_min_fraction: 80`, `exclusive_inside_min: 80`, `exclusive_outside_max: 20`.

## Tests (headless)

```bash
python tests/test_core.py                              # data-layer logic
QT_QPA_PLATFORM=offscreen python tests/test_gui_smoke.py   # GUI wiring
```
