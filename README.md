# SPARCAL Spatial-SNV Viewer

A desktop app to explore a spatial SNV presence matrix: a tissue view, tumor
regions, and per-region variant (SNV) groups.

```
┌──────────────────────┬────────────────────────┬──────────────────────┐
│  Spatial view        │  Tumor regions         │  SNV list            │
│  (hires image+spots) │  [Add][Edit][Auto][Gen]│  [Export][Import][⋯] │
│  ▢ background         │  region                │  chrom_pos_ref…      │
│  ▢ color by SNV count│   ├─ exclusive 🟪      │  …                   │
│  ▦ burden legend     │   └─ general   🟩      │                      │
└──────────────────────┴────────────────────────┴──────────────────────┘
```

## Get the example data

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

## Build the standalone macOS app

PyInstaller builds for the OS it runs on, so **run this on your Mac**:

```bash
./build_macos.sh
# → dist/SPARCAL-SNV-Viewer.app  (double-click; no Python needed)
```

First launch of the unsigned app: right-click ▸ Open ▸ Open, or
`xattr -dr com.apple.quarantine dist/SPARCAL-SNV-Viewer.app`.

The app is a small (~150 MB) viewer; **study data stays separate** in a config
folder that you open from within the app.

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
| `tumor_groups.csv` | regions the app saves (`region_name,barcode`) |
| `variant_groups.csv` | variant groups the app saves (`region_name,group_name,group_type,snv_key`) |
| `spot_coverage.csv` *(optional)* | per-spot UMI (`barcode,total_umi`) for coverage-normalized **Auto** tumor detection |

To make a new study, copy the four input files + a `.config` into a new folder
and edit the header fields. The two CSVs can start as just their header row.

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

**Spatial view (col 1)** — pan/zoom; two toggles top-right:
- **background** — show/hide the tissue image.
- **color by SNV count** — colour each spot by how many SNVs it carries, on a
  **sky-blue → purple** ramp (quantile-scaled so the skewed burden spreads out).
  A legend top-left maps colour to the actual SNV count at each quantile.

**Tumor regions (col 2)**
- **Add** → lasso spots on the tissue → **Finish** → name the region.
- **Edit** → multi-select regions → **Merge** (makes a new region, removes the
  originals, prompts for a name) or **Delete**.
- **Auto** → auto-detect contiguous tumor regions from SNV-burden intensity:
  - **Intensity** slider — higher keeps fewer / smaller regions.
  - **Grow margin** — how far below the seed threshold a region may grow
    (hysteresis); **Min region size** drops specks.
  - **Normalize by coverage** — divide out per-spot UMI depth (needs
    `spot_coverage.csv`; see above).
  - **Add seeds / Exclude (lasso)** — force-add or remove seed spots by lassoing
    the tissue; the preview updates live. **Create regions** writes them out.

  Seeds are high-intensity local maxima; regions flood-fill outward over the
  Visium grid so they stay contiguous (no scattered spots).
- Click a region, then **Generate ▾**:
  - **Exclusive** — SNVs present only in this region (absent everywhere else). 🟪
  - **General** — SNVs in > *N*% of *all* in-tissue spots (default 80). 🟩
  - **Exclusive by threshold** — present in > max% inside **and** < min% outside
    (defaults 80 / 20). 🟪
- Each generated group appears as a colored tag under the region; click it to
  list its SNVs in column 3 and highlight the carrying spots.

**SNV list (col 3)**
- **Export** → write the SNVs (selected, or all if none selected) to a `.json`
  carrying the variant list plus its source region/group provenance.
- **Import** → re-open an exported `.json`, re-creating the region/group if it's
  gone.
- **Select all**, then **Show on tissue** highlights spots carrying the chosen
  SNVs; **Add spots → region** turns those spots into a new tumor region.

Regions and variant groups are written back to the two CSVs immediately, so they
reload next time you open the config.
<img width="1503" height="929" alt="image" src="https://github.com/user-attachments/assets/52ea12ce-7124-4ebb-a525-519aa1ea0b61" />

## Defaults (config `variant_grouping:`)

`general_min_fraction: 80`, `exclusive_inside_min: 80`, `exclusive_outside_max: 20`.

## Tests (headless)

```bash
python tests/test_core.py                              # data-layer logic
QT_QPA_PLATFORM=offscreen python tests/test_gui_smoke.py   # GUI wiring
```
