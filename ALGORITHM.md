# Auto Tumor Region Generator — Algorithm Design

This document describes how the viewer's **Auto tumor regions** feature turns a
spots×SNV presence matrix into a set of contiguous tumor regions on the Visium
grid. It is a **marker-controlled, hysteresis-thresholded priority-flood
watershed** run on a per-spot SNV-burden signal.

All code lives in [`sparcal_viewer/data.py`](sparcal_viewer/data.py):
- `auto_tumor_regions()` — orchestrator (returns the regions + centers)
- `_watershed_basins()` — the flood + basin-merge core
- `per_spot_intensity()` / `per_spot_burden()` — the signal
- `spot_adjacency()` — the hex neighbor graph
- `_smooth()` — denoising

The dialog knobs live in `AutoTumorDialog` in
[`sparcal_viewer/main_window.py`](sparcal_viewer/main_window.py).

## One-line mental model

Smooth the per-spot SNV burden → treat it as a landscape → local maxima above a
high threshold are the **peaks** (region centers) → **flood the landscape
downward** from those peaks, but only into terrain above a lower threshold
(hysteresis) → basins that meet along a **shallow saddle merge**, those separated
by a **deep valley stay distinct** → drop tiny basins.

## Parameters (and their dialog knobs)

| `auto_tumor_regions` arg | Dialog knob | Default | Meaning |
|---|---|---|---|
| `seed_pct` | **Intensity** | 90 | Percentile a spot must exceed (and be a local max) to seed a region. Higher → fewer/smaller regions. |
| `grow_pct` | derived: `seed_pct − margin` | 80 | Percentile floor a spot must exceed to be claimable by any region. |
| — | **Grow margin** | 10 | `seed_pct − grow_pct`. Bigger → regions flood further into weaker tissue. |
| `min_size` | **Min region size (spots)** | 5 | Basins smaller than this are discarded as noise. |
| `split_depth` | **Split valley depth** | 0.40 (40%) | Minimum fractional valley depth required to keep two touching peaks as *separate* regions. 0 → always split; 1 → always merge. |
| `normalize` | **Normalize by coverage (UMI)** | on if `spot_coverage.csv` present | Use the coverage-independent burden residual instead of raw burden. |
| `extra_seeds` / `excluded_seeds` | **Add / Exclude (lasso)** | none | Manually force or remove seed spots. |
| `snvs` | — (not in dialog) | all | Restrict the burden signal to a subset of SNV columns. |

## The pipeline, step by step

### 1. Per-spot intensity — the signal being segmented
`per_spot_intensity(normalize, snvs)`:

- **Burden** = presence row-sum: for each spot, the count of SNV columns with
  value > 0 (`per_spot_burden`). Restricted to `snvs` if given.
- If `normalize` **and** a `spot_coverage.csv` (per-spot total UMI) is loaded:
  fit ordinary least squares `burden ~ total_UMI` (design matrix `[1, umi]` via
  `np.linalg.lstsq`) and use the **residual** as the intensity. Spots with
  missing UMI are filled with the median coverage so they aren't distorted.
  This removes the coverage gradient — raw burden correlates with coverage at
  r≈0.9, so without this the regions just trace high-coverage tissue.
- Otherwise: raw burden.

Output: one scalar `raw[i]` per in-tissue spot, in plot order.

### 2. Grid adjacency — the hex neighbor graph
`spot_adjacency()` builds `neighbors[i]` (indices adjacent to spot `i`):

- For each spot take its ≤6 nearest neighbors (kNN, computed in memory-bounded
  chunks).
- Keep only neighbors within **1.5× the median nearest-neighbor distance**.
  This cutoff is what makes **tissue gaps break connectivity**: a spot on the
  far side of a gap is still a kNN, but beyond 1.5× the spot pitch, so it is
  dropped. Regions therefore cannot jump across holes in the tissue.

Cached (invalidated when the spot set changes).

### 3. Smoothing — denoise
`_smooth(raw, neighbors)`: one pass of a single-ring mean,
`s[i] = mean(raw[i] + raw over neighbors[i])`. This box filter suppresses
salt-and-pepper spikes so a lone high spot does not become a spurious seed.

**Everything below runs on the smoothed `s`, never on `raw`.**

### 4. Hysteresis thresholds
- `seed_thr = percentile(s, seed_pct)` — the **high** threshold (start a region).
- `grow_thr = percentile(s, grow_pct)` — the **low** threshold (extend a region),
  with `grow_pct = max(0, seed_pct − margin)`.
- `weak = s >= grow_thr` — the boolean mask of every spot eligible to *belong*
  to a region. Spots below `grow_thr` are never claimed by anything.

Classic hysteresis: a high bar to seed, a lower bar to grow.

### 5. Seed (center) selection
A spot `i` becomes an **automatic seed** iff **both**:

1. `s[i] >= seed_thr` — it is in the top `(100 − seed_pct)%` of smoothed
   intensity, **and**
2. `s[i] >= s[neighbors[i]].max()` — it is a **local maximum**: no adjacent spot
   is strictly higher (a spot with no neighbors auto-qualifies).

The `>=` in the local-max test means a flat plateau of equal-valued spots
produces *several* seeds; they merge back later (§7).

Then manual overrides are applied:

- **`extra_seeds`** (lasso-add): forced `seed_mask = True`, **and** `weak = True`
  even if the spot is below `grow_thr` — a manually forced center is honored
  regardless of its intensity.
- **`excluded_seeds`** (lasso-remove): forced `seed_mask = False`.

So "centers" = local maxima above the high threshold, plus/minus manual edits.

### 6. The flood — priority-flood watershed
`_watershed_basins(s, weak, neighbors, seed_mask, grow_thr, split_depth)` floods
**from the peaks downward** (not a simple threshold BFS):

1. Seeds = spots that are both `seed_mask` and `weak`. Each gets a **distinct
   integer label** `k`; `peak[k] = s[seed]` records its summit height.
2. A **max-heap** is initialized with all seeds, keyed by `−s` so the highest
   spot pops first.
3. Repeatedly pop the current highest spot `u` (label `lu`). For each **weak**
   neighbor `v`:
   - **unlabeled** → assign it `lu` and push it on the heap.
   - **labeled, different basin** (`lv != lu`) → do *not* reassign; instead
     record a **saddle** for the unordered pair `(a, b)`:
     `saddle[(a,b)] = max(existing, min(s[u], s[v]))` — the *highest* elevation
     at which the two basins touch.

Because expansion always proceeds from the highest remaining spot, every weak
spot is claimed by the basin whose ridge descends to it first — its **nearest
peak in the topographic sense** — and basin boundaries fall naturally along the
ridgelines between peaks. Spots below `grow_thr` are never enqueued, so regions
cannot leak into low-signal tissue.

### 7. Merge basins across shallow saddles
Two adjacent peaks should not always be separate (a plateau) nor always merged.
A union-find pass over the recorded saddles decides. For each pair `(a, b)` with
contact height `h`:

```
lower = min(peak[a], peak[b])      # the shorter of the two summits
scale = lower - grow_thr           # that peak's prominence above the grow floor
depth = (lower - h) / scale        # valley drop as a fraction of prominence
                                   #   (scale <= 0  ->  depth = 1.0)
if depth < split_depth:            # shallow valley -> same region
    union(a, b)
```

`split_depth` is therefore the **minimum fractional valley depth required to keep
two peaks as separate regions**:

- `split_depth = 0` → `depth` is never below it → **always split** touching peaks.
- `split_depth = 1` → nearly everything merges → **always merge** (old behavior).
- Plateau seeds from §5 have `h ≈ lower` → `depth ≈ 0` → they merge back into one
  region, which is why plateaus don't fragment.

Spots are then grouped by `find(label[i])` into final basins.

### 8. Assemble, filter, order
Back in `auto_tumor_regions`:

- **Filter**: drop basins with fewer than `min_size` spots.
- **Centers per region**: all `seed_mask` spots inside the basin (or, if a fused
  basin has none, the single highest spot), sorted strongest-first. A basin fused
  from several peaks keeps **every** center — that is why one region can show
  multiple center stars in the preview, exposing how many sub-peaks it contains.
- **Order**: regions sorted by size, largest first; `centers` kept aligned.
- Returns `{regions, centers, seeds, intensity}`, where `seeds` is the flat union
  of all centers (used to draw the preview rings) and `intensity` is the smoothed
  signal as a `barcode -> value` Series.

## Design rationale / notes

- **Why watershed, not threshold + connected components?** A plain threshold
  merges adjacent tumor cores that touch, and can't separate two clones sharing a
  high-burden ridge. The priority-flood watershed assigns every spot to its
  dominant peak and only merges when the dividing valley is genuinely shallow
  (`split_depth`), giving control over the split/merge tradeoff.
- **Why hysteresis (two thresholds)?** A single threshold either over-segments
  (misses region margins) or bleeds regions together. The high `seed_thr` picks
  confident cores; the lower `grow_thr` lets them expand to their true extent
  without seeding noise.
- **Why coverage normalization?** Raw SNV burden ≈ a coverage map (r≈0.9), so
  un-normalized regions would track sequencing depth rather than clonal biology.
  The OLS residual removes the coverage-driven component; Moran's-I analysis
  confirmed residual burden retains real coverage-independent spatial structure.
- **Determinism.** The result is deterministic given the matrix, coverage, and
  parameters (kNN, percentiles, and a fixed heap order). Manual seed edits are
  applied before the flood, so they change the outcome reproducibly.
