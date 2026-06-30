"""Study data model: matrix, spot coordinates, tumor regions, variant groups.

This module holds all logic that does NOT depend on Qt, so it can be unit
tested headless. The matrix is a presence matrix (uint8, spots x SNVs); every
"fraction" below is computed over the spots that exist in that matrix (i.e. the
spots we actually have SNV data for, which for Visium are the in-tissue spots).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional

import numpy as np
import pandas as pd

from .config import StudyConfig

# Profile used when a study's CSVs carry no `profile` column (back-compat).
DEFAULT_PROFILE = "Default"

# Variant-group types and their tag colours (used by the GUI).
GROUP_EXCLUSIVE = "exclusive"
GROUP_GENERAL = "general"
GROUP_EXCLUSIVE_THRESHOLD = "exclusive_threshold"
GROUP_SELECTION = "selection"

GROUP_COLORS = {
    GROUP_EXCLUSIVE: "#8e44ad",            # purple
    GROUP_EXCLUSIVE_THRESHOLD: "#8e44ad",  # purple (also an exclusive-style group)
    GROUP_GENERAL: "#27ae60",              # green
    GROUP_SELECTION: "#2980b9",            # blue (manually selected SNV set)
}


@dataclass
class VariantGroup:
    region: str
    name: str
    gtype: str
    snvs: List[str] = field(default_factory=list)

    def color(self) -> str:
        return GROUP_COLORS.get(self.gtype, "#7f8c8d")


class StudyData:
    """Loads a study and answers all the questions the GUI needs."""

    def __init__(self, cfg: StudyConfig):
        self.cfg = cfg
        self.matrix: pd.DataFrame = pd.DataFrame()
        self.positions: pd.DataFrame = pd.DataFrame()  # indexed by barcode: x, y, in_tissue
        self.scalef: float = 1.0
        self.spot_diameter: float = 0.0
        # cached per-SNV total presence count over all matrix spots
        self._total_counts: Optional[pd.Series] = None
        # optional per-spot total UMI (barcode -> count); None if no coverage file
        self.coverage: Optional[pd.Series] = None
        # cached spot adjacency: (plot-order barcodes, list[np.ndarray] neighbor idx)
        self._adj: Optional[tuple] = None

        # Profiles: a profile is a named separation of the tissue into regions
        # (e.g. "Ground Truth", "Test"). Each profile namespaces its own regions,
        # centers, and variant groups, so region names may repeat across profiles.
        # profile name -> {"regions", "region_centers", "variant_groups"}
        self.profiles: Dict[str, dict] = {}
        self.current_profile: str = DEFAULT_PROFILE
        # barcode -> region cache, keyed by profile name (built lazily for hover)
        self._barcode_region: Dict[str, Dict[str, str]] = {}

        self._load()

    # --------------------------------------------------- profile proxies
    # The GUI was written against flat region/center/group dicts; these proxy to
    # the *current* profile so existing call sites keep working unchanged.
    def _cur(self) -> dict:
        prof = self.profiles.setdefault(
            self.current_profile,
            {"regions": {}, "region_centers": {}, "variant_groups": {}})
        return prof

    @property
    def regions(self) -> Dict[str, List[str]]:
        return self._cur()["regions"]

    @regions.setter
    def regions(self, value: Dict[str, List[str]]) -> None:
        self._cur()["regions"] = value

    @property
    def region_centers(self) -> Dict[str, List[str]]:
        return self._cur()["region_centers"]

    @region_centers.setter
    def region_centers(self, value: Dict[str, List[str]]) -> None:
        self._cur()["region_centers"] = value

    @property
    def variant_groups(self) -> Dict[tuple, VariantGroup]:
        return self._cur()["variant_groups"]

    @variant_groups.setter
    def variant_groups(self, value: Dict[tuple, VariantGroup]) -> None:
        self._cur()["variant_groups"] = value

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        self.matrix = pd.read_pickle(self.cfg.snv_matrix)
        if self.matrix.index.has_duplicates:
            self.matrix = self.matrix[~self.matrix.index.duplicated(keep="first")]
        self._total_counts = self.matrix.sum(axis=0)

        with open(self.cfg.scalefactors) as fh:
            sf = json.load(fh)
        self.scalef = float(sf.get(self.cfg.image["scalef_key"], 1.0))
        self.spot_diameter = float(sf.get(self.cfg.image["spot_diameter_key"], 0.0)) * self.scalef

        pos = pd.read_csv(self.cfg.tissue_positions)
        xcol, ycol = self.cfg.image["x_column"], self.cfg.image["y_column"]
        pos = pos.rename(columns={xcol: "x_full", ycol: "y_full"})
        pos = pos.set_index("barcode")
        if self.cfg.image.get("in_tissue_only", True) and "in_tissue" in pos.columns:
            pos = pos[pos["in_tissue"] == 1]
        df = pd.DataFrame(index=pos.index)
        df["x"] = pos["x_full"].astype(float) * self.scalef
        df["y"] = pos["y_full"].astype(float) * self.scalef
        df["in_tissue"] = pos.get("in_tissue", 1)
        self.positions = df

        self._load_coverage()
        self._load_regions()
        self._load_centers()
        self._load_variant_groups()

    def _load_coverage(self) -> None:
        """Load optional per-spot coverage (barcode,total_umi). Falls back to a
        `spot_coverage.csv` next to the config if the config doesn't name one."""
        self.coverage = None
        path = self.cfg.spot_coverage
        if not path:
            cand = os.path.join(self.cfg.root, "spot_coverage.csv")
            path = cand if os.path.exists(cand) else ""
        if not path or not os.path.exists(path):
            return
        df = pd.read_csv(path)
        cols = {c.lower(): c for c in df.columns}
        bc = cols.get("barcode", df.columns[0])
        umi = cols.get("total_umi", df.columns[-1])
        self.coverage = pd.Series(
            df[umi].astype(float).values, index=df[bc].astype(str).values)
        self.coverage = self.coverage[~self.coverage.index.duplicated(keep="first")]

    def _profile_bucket(self, name: str) -> dict:
        """Return (creating if needed) the per-profile container of dicts."""
        return self.profiles.setdefault(
            name, {"regions": {}, "region_centers": {}, "variant_groups": {}})

    @staticmethod
    def _with_profile(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure a usable `profile` column (back-compat: missing -> Default)."""
        if "profile" not in df.columns:
            df["profile"] = DEFAULT_PROFILE
        df["profile"] = df["profile"].fillna(DEFAULT_PROFILE).replace("", DEFAULT_PROFILE)
        return df

    def _load_regions(self) -> None:
        self.profiles = {}
        self._barcode_region = {}
        path = self.cfg.tumor_groups
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            df = pd.read_csv(path, dtype=str)
            if {"region_name", "barcode"}.issubset(df.columns):
                df = self._with_profile(df)
                for (prof, name), sub in df.groupby(["profile", "region_name"], sort=False):
                    self._profile_bucket(str(prof))["regions"][str(name)] = \
                        list(dict.fromkeys(sub["barcode"].tolist()))
        if not self.profiles:                      # empty study -> one default profile
            self._profile_bucket(DEFAULT_PROFILE)
        self.current_profile = next(iter(self.profiles))

    def _load_centers(self) -> None:
        """Load per-region center barcodes (auto-region seeds) if present."""
        path = self.cfg.tumor_centers
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            df = pd.read_csv(path, dtype=str)
            if {"region_name", "barcode"}.issubset(df.columns):
                df = self._with_profile(df)
                for (prof, name), sub in df.groupby(["profile", "region_name"], sort=False):
                    self._profile_bucket(str(prof))["region_centers"][str(name)] = \
                        list(dict.fromkeys(sub["barcode"].tolist()))

    def _load_variant_groups(self) -> None:
        path = self.cfg.variant_groups
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            df = pd.read_csv(path, dtype=str)
            need = {"region_name", "group_name", "group_type", "snv_key"}
            if need.issubset(df.columns):
                df = self._with_profile(df)
                for (prof, region, gname, gtype), sub in df.groupby(
                    ["profile", "region_name", "group_name", "group_type"], sort=False
                ):
                    g = VariantGroup(str(region), str(gname), str(gtype),
                                     list(dict.fromkeys(sub["snv_key"].tolist())))
                    self._profile_bucket(str(prof))["variant_groups"][(g.region, g.name)] = g

    # ------------------------------------------------------------- accessors
    @property
    def spot_barcodes(self) -> List[str]:
        """Spots that have both coordinates and a matrix row, in plot order."""
        return [b for b in self.positions.index if b in self.matrix.index]

    @property
    def n_spots(self) -> int:
        return self.matrix.shape[0]

    def region_names(self) -> List[str]:
        return list(self.regions.keys())

    def region_in_matrix(self, region: str) -> List[str]:
        rows = set(self.matrix.index)
        return [b for b in self.regions.get(region, []) if b in rows]

    def groups_for_region(self, region: str) -> List[VariantGroup]:
        return [g for (r, _), g in self.variant_groups.items() if r == region]

    # ------------------------------------------------------------- profiles
    def profile_names(self) -> List[str]:
        return list(self.profiles.keys())

    def set_current_profile(self, name: str) -> None:
        if name in self.profiles:
            self.current_profile = name

    def add_profile(self, name: str) -> str:
        name = self._unique_profile_name(name)
        self._profile_bucket(name)
        self.current_profile = name
        self.save_regions()           # persist the (empty) profile so it survives reload
        return name

    def rename_profile(self, old: str, new: str) -> str:
        if old not in self.profiles:
            return old
        new = self._unique_profile_name(new, ignore=old)
        self.profiles = {(new if k == old else k): v for k, v in self.profiles.items()}
        if self.current_profile == old:
            self.current_profile = new
        self._barcode_region.pop(old, None)
        self._save_all()
        return new

    def delete_profile(self, name: str) -> None:
        if name not in self.profiles:
            return
        del self.profiles[name]
        self._barcode_region.pop(name, None)
        if not self.profiles:                       # never leave zero profiles
            self._profile_bucket(DEFAULT_PROFILE)
        if self.current_profile not in self.profiles:
            self.current_profile = next(iter(self.profiles))
        self._save_all()

    def _unique_profile_name(self, name: str, ignore: Optional[str] = None) -> str:
        name = (name or "profile").strip() or "profile"
        existing = {k for k in self.profiles if k != ignore}
        if name not in existing:
            return name
        i = 2
        while f"{name}_{i}" in existing:
            i += 1
        return f"{name}_{i}"

    def region_counts(self) -> Dict[str, int]:
        """Region count per profile (for the profile-selection list)."""
        return {p: len(b["regions"]) for p, b in self.profiles.items()}

    def barcode_region_map(self, profile: Optional[str] = None) -> Dict[str, str]:
        """barcode -> region name for the given profile (default: current). When a
        spot belongs to several regions the *smallest* region wins (most specific).
        Cached per profile; invalidated on any region edit."""
        prof = profile or self.current_profile
        if prof in self._barcode_region:
            return self._barcode_region[prof]
        regions = self.profiles.get(prof, {}).get("regions", {})
        # assign in descending size order so smaller regions overwrite larger ones
        out: Dict[str, str] = {}
        for name in sorted(regions, key=lambda n: len(regions[n]), reverse=True):
            for bc in regions[name]:
                out[bc] = name
        self._barcode_region[prof] = out
        return out

    def spots_with_snvs(self, snvs: List[str]) -> List[str]:
        """Barcodes that carry at least one of the given SNVs (presence > 0)."""
        cols = [s for s in snvs if s in self.matrix.columns]
        if not cols:
            return []
        sub = self.matrix[cols]
        mask = (sub.values > 0).any(axis=1)
        return list(self.matrix.index[mask])

    # ----------------------------------------------------- per-spot burden
    def per_spot_burden(self, snvs: Optional[List[str]] = None) -> pd.Series:
        """Number of SNVs present per plotted spot (presence row-sum), in plot order.

        If `snvs` is given the burden is restricted to those columns; otherwise it
        is over the whole matrix."""
        bcs = self.spot_barcodes
        if not bcs:
            return pd.Series(dtype=np.int64)
        if snvs is not None:
            cols = [s for s in snvs if s in self.matrix.columns]
            sub = self.matrix.loc[bcs, cols] if cols else None
            if sub is None:
                return pd.Series(0, index=bcs, dtype=np.int64)
            vals = (sub.values > 0).sum(axis=1)
        else:
            vals = (self.matrix.loc[bcs].values > 0).sum(axis=1)
        return pd.Series(vals.astype(np.int64), index=bcs)

    def per_spot_intensity(self, normalize: bool = True,
                           snvs: Optional[List[str]] = None) -> pd.Series:
        """Per-spot intensity used for tumor detection, in plot order.

        With `normalize` and a coverage table available, returns the OLS residual of
        burden ~ total_UMI (coverage-independent signal). Otherwise returns raw burden.
        """
        burden = self.per_spot_burden(snvs).astype(float)
        if not normalize or self.coverage is None or burden.empty:
            return burden
        umi = self.coverage.reindex(burden.index).astype(float)
        if umi.isna().all():
            return burden
        # fill missing coverage with the median so those spots aren't distorted
        umi = umi.fillna(umi.median())
        x = umi.values
        y = burden.values
        A = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        resid = y - A @ coef
        return pd.Series(resid, index=burden.index)

    # ----------------------------------------------------- spot adjacency
    def spot_adjacency(self) -> tuple:
        """Return (barcodes, neighbors) where neighbors[i] is an int array of the
        indices adjacent to spot i on the Visium grid. Adjacency = up to 6 nearest
        spots within 1.5x the median nearest-neighbour distance (so tissue gaps
        break connectivity). Cached."""
        bcs = self.spot_barcodes
        if self._adj is not None and self._adj[0] == bcs:
            return self._adj
        xy = self.positions.loc[bcs, ["x", "y"]].to_numpy(dtype=float)
        n = len(bcs)
        neighbors: List[np.ndarray] = [np.empty(0, dtype=int) for _ in range(n)]
        if n >= 2:
            k = min(6, n - 1)
            nn1 = np.empty(n)
            knn = [None] * n
            # chunked pairwise distances to keep memory bounded for big sections
            chunk = 1024
            for s in range(0, n, chunk):
                e = min(s + chunk, n)
                d = np.linalg.norm(xy[s:e, None, :] - xy[None, :, :], axis=2)
                for r in range(e - s):
                    i = s + r
                    order = np.argpartition(d[r], k)[:k + 1]
                    order = order[order != i][:k]
                    knn[i] = order
                    nn1[i] = d[r][order].min() if len(order) else np.inf
            cutoff = 1.5 * np.median(nn1[np.isfinite(nn1)]) if n else 0.0
            for i in range(n):
                order = knn[i]
                dist = np.linalg.norm(xy[order] - xy[i], axis=1)
                neighbors[i] = order[dist <= cutoff]
        self._adj = (bcs, neighbors)
        return self._adj

    def _smooth(self, values: np.ndarray, neighbors: List[np.ndarray]) -> np.ndarray:
        """Mean of each spot with its neighbours (denoise salt-and-pepper)."""
        out = np.empty_like(values, dtype=float)
        for i, nb in enumerate(neighbors):
            if len(nb):
                out[i] = (values[i] + values[nb].sum()) / (len(nb) + 1)
            else:
                out[i] = values[i]
        return out

    # ----------------------------------------------------- auto tumor regions
    def auto_tumor_regions(self, seed_pct: float = 90.0, grow_pct: float = 60.0,
                           min_size: int = 5, normalize: bool = True,
                           snvs: Optional[List[str]] = None,
                           extra_seeds: Optional[List[str]] = None,
                           excluded_seeds: Optional[List[str]] = None,
                           split_depth: float = 0.30) -> dict:
        """Seeded watershed region growing on the spot grid.

        Smooth the per-spot intensity, take spots above `seed_pct` percentile that are
        local maxima as seeds (plus any `extra_seeds`, minus `excluded_seeds`), then
        flood the `grow_pct`-percentile "weak" set from those seeds in descending
        intensity order so every weak spot is claimed by its nearest peak (a watershed).

        Two adjacent basins that collide are *not* blindly merged: they fuse only when
        the saddle (the highest point of contact between them) is shallow — i.e. the
        valley separating the two centers reclaims less than `split_depth` of the
        smaller peak's height above the grow floor. A deep valley keeps them as
        distinct regions. Basins with a seed and >= `min_size` spots become regions.

        Returns {'regions': list[list[barcode]], 'seeds'/'centers': list[barcode]
                 (one representative center per region, aligned with 'regions'),
                 'intensity': Series(barcode->smoothed intensity)}.
        """
        bcs, neighbors = self.spot_adjacency()
        n = len(bcs)
        if n == 0:
            return {"regions": [], "seeds": [], "centers": [],
                    "intensity": pd.Series(dtype=float)}
        raw = self.per_spot_intensity(normalize=normalize, snvs=snvs).reindex(bcs).values
        s = self._smooth(raw, neighbors)
        idx = {b: i for i, b in enumerate(bcs)}

        seed_thr = np.percentile(s, seed_pct)
        grow_thr = np.percentile(s, grow_pct)
        weak = s >= grow_thr

        # auto seeds: above seed threshold AND a local maximum among neighbours
        seed_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            if s[i] >= seed_thr and (len(neighbors[i]) == 0 or s[i] >= s[neighbors[i]].max()):
                seed_mask[i] = True
        for b in (extra_seeds or []):
            if b in idx:
                seed_mask[idx[b]] = True
                weak[idx[b]] = True       # honour a manual seed even if below grow_thr
        for b in (excluded_seeds or []):
            if b in idx:
                seed_mask[idx[b]] = False

        basins = self._watershed_basins(s, weak, neighbors, seed_mask,
                                        grow_thr, split_depth)

        # build output regions; keep basins big enough (every basin has >= 1 seed)
        out: List[List[str]] = []
        centers: List[str] = []
        for members in basins:
            if len(members) < min_size:
                continue
            out.append([bcs[m] for m in members])
            seed_members = [m for m in members if seed_mask[m]]
            pool = seed_members or members
            center = max(pool, key=lambda m: s[m])   # highest-intensity seed = center
            centers.append(bcs[center])
        order = sorted(range(len(out)), key=lambda i: len(out[i]), reverse=True)
        out = [out[i] for i in order]
        centers = [centers[i] for i in order]
        return {"regions": out, "seeds": centers, "centers": centers,
                "intensity": pd.Series(s, index=bcs)}

    @staticmethod
    def _watershed_basins(s: np.ndarray, weak: np.ndarray,
                          neighbors: List[np.ndarray], seed_mask: np.ndarray,
                          grow_thr: float, split_depth: float) -> List[List[int]]:
        """Priority-flood watershed from seeds, then merge basins whose dividing
        saddle is shallow. Returns a list of basins (each a list of spot indices).

        `split_depth` in [0,1]: two basins stay separate when the valley between their
        peaks drops by at least this fraction of the shorter peak's height above
        `grow_thr`. 0 -> always split touching peaks; 1 -> always merge (old behaviour).
        """
        import heapq

        n = len(s)
        seeds = [i for i in range(n) if seed_mask[i] and weak[i]]
        label = -np.ones(n, dtype=int)
        peak: List[float] = []
        for k, sd in enumerate(seeds):
            label[sd] = k
            peak.append(float(s[sd]))

        heap = [(-float(s[sd]), sd) for sd in seeds]
        heapq.heapify(heap)
        saddle: Dict[tuple, float] = {}    # (label_a, label_b) -> highest contact level
        while heap:
            _, u = heapq.heappop(heap)
            lu = label[u]
            for v in neighbors[u]:
                if not weak[v]:
                    continue
                lv = label[v]
                if lv < 0:
                    label[v] = lu
                    heapq.heappush(heap, (-float(s[v]), v))
                elif lv != lu:
                    a, b = (lu, lv) if lu < lv else (lv, lu)
                    h = min(float(s[u]), float(s[v]))
                    if h > saddle.get((a, b), -np.inf):
                        saddle[(a, b)] = h

        # union-find merge of basins separated only by a shallow saddle
        parent = list(range(len(seeds)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for (a, b), h in saddle.items():
            lower = min(peak[a], peak[b])
            scale = lower - grow_thr
            depth = 1.0 if scale <= 0 else (lower - h) / scale
            if depth < split_depth:            # shallow valley -> same region
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra

        grouped: Dict[int, List[int]] = {}
        for i in range(n):
            if label[i] >= 0:
                grouped.setdefault(find(label[i]), []).append(i)
        return list(grouped.values())

    # ----------------------------------------------------- variant generation
    def _inside_counts(self, region: str) -> tuple:
        """Return (counts_inside: Series, n_inside, n_outside)."""
        inside_bcs = self.region_in_matrix(region)
        n_inside = len(inside_bcs)
        n_total = self.matrix.shape[0]
        n_outside = n_total - n_inside
        if n_inside == 0:
            zeros = pd.Series(0, index=self.matrix.columns, dtype=np.int64)
            return zeros, 0, n_outside
        counts_inside = self.matrix.loc[inside_bcs].sum(axis=0).astype(np.int64)
        return counts_inside, n_inside, n_outside

    def generate_exclusive(self, region: str) -> List[str]:
        """SNVs present in >=1 spot inside the region and 0 spots outside it."""
        counts_inside, n_inside, _ = self._inside_counts(region)
        if n_inside == 0:
            return []
        counts_outside = self._total_counts.astype(np.int64) - counts_inside
        mask = (counts_inside.values > 0) & (counts_outside.values == 0)
        return list(self.matrix.columns[mask])

    def generate_general(self, min_fraction: float) -> List[str]:
        """SNVs present in more than `min_fraction` percent of all matrix spots."""
        n = self.matrix.shape[0]
        if n == 0:
            return []
        frac = self._total_counts.values.astype(float) / n * 100.0
        mask = frac > float(min_fraction)
        return list(self.matrix.columns[mask])

    def generate_exclusive_threshold(self, region: str,
                                     inside_min: float, outside_max: float) -> List[str]:
        """SNVs in > inside_min% of region spots and < outside_max% of outside spots."""
        counts_inside, n_inside, n_outside = self._inside_counts(region)
        if n_inside == 0:
            return []
        frac_inside = counts_inside.values.astype(float) / n_inside * 100.0
        counts_outside = self._total_counts.astype(np.int64).values - counts_inside.values
        if n_outside > 0:
            frac_outside = counts_outside.astype(float) / n_outside * 100.0
        else:
            frac_outside = np.zeros_like(frac_inside)
        mask = (frac_inside > float(inside_min)) & (frac_outside < float(outside_max))
        return list(self.matrix.columns[mask])

    # ------------------------------------------------------------- mutation
    def add_region(self, name: str, barcodes: List[str],
                   center: Optional[List[str]] = None) -> str:
        name = self._unique_region_name(name)
        self.regions[name] = list(dict.fromkeys(barcodes))
        if center:
            centers = center if isinstance(center, (list, tuple)) else [center]
            self.region_centers[name] = list(dict.fromkeys(c for c in centers if c))
        self.save_regions()
        self.save_centers()
        return name

    def delete_regions(self, names: List[str]) -> None:
        for n in names:
            self.regions.pop(n, None)
            self.region_centers.pop(n, None)
            for key in [k for k in self.variant_groups if k[0] == n]:
                self.variant_groups.pop(key, None)
        self.save_regions()
        self.save_centers()
        self.save_variant_groups()

    def merge_regions(self, names: List[str], new_name: str) -> str:
        merged: List[str] = []
        centers: List[str] = []
        for n in names:
            merged.extend(self.regions.get(n, []))
            centers.extend(self.region_centers.get(n, []))
        merged = list(dict.fromkeys(merged))
        self.delete_regions(names)
        return self.add_region(new_name, merged, center=centers or None)

    def rename_region(self, old: str, new: str) -> str:
        if old not in self.regions:
            return old
        new = self._unique_region_name(new, ignore=old)
        self.regions = {(new if k == old else k): v for k, v in self.regions.items()}
        if old in self.region_centers:
            self.region_centers[new] = self.region_centers.pop(old)
        for key in [k for k in self.variant_groups if k[0] == old]:
            g = self.variant_groups.pop(key)
            g.region = new
            self.variant_groups[(new, g.name)] = g
        self.save_regions()
        self.save_centers()
        self.save_variant_groups()
        return new

    def add_variant_group(self, region: str, name: str, gtype: str,
                          snvs: List[str]) -> VariantGroup:
        name = self._unique_group_name(region, name)
        g = VariantGroup(region, name, gtype, list(dict.fromkeys(snvs)))
        self.variant_groups[(region, name)] = g
        self.save_variant_groups()
        return g

    def delete_variant_group(self, region: str, name: str) -> None:
        self.variant_groups.pop((region, name), None)
        self.save_variant_groups()

    def _unique_region_name(self, name: str, ignore: Optional[str] = None) -> str:
        name = (name or "region").strip() or "region"
        existing = {k for k in self.regions if k != ignore}
        if name not in existing:
            return name
        i = 2
        while f"{name}_{i}" in existing:
            i += 1
        return f"{name}_{i}"

    def _unique_group_name(self, region: str, name: str) -> str:
        name = (name or "group").strip() or "group"
        existing = {k[1] for k in self.variant_groups if k[0] == region}
        if name not in existing:
            return name
        i = 2
        while f"{name}_{i}" in existing:
            i += 1
        return f"{name}_{i}"

    # ------------------------------------------------------------- persistence
    def _save_all(self) -> None:
        self.save_regions()
        self.save_centers()
        self.save_variant_groups()

    def save_regions(self) -> None:
        self._barcode_region = {}            # region edits invalidate the hover map
        rows = [(prof, name, bc)
                for prof, b in self.profiles.items()
                for name, bcs in b["regions"].items() for bc in bcs]
        df = pd.DataFrame(rows, columns=["profile", "region_name", "barcode"])
        df.to_csv(self.cfg.tumor_groups, index=False)

    def save_centers(self) -> None:
        rows = [(prof, name, bc)
                for prof, b in self.profiles.items()
                for name, bcs in b["region_centers"].items() for bc in bcs]
        df = pd.DataFrame(rows, columns=["profile", "region_name", "barcode"])
        df.to_csv(self.cfg.tumor_centers, index=False)

    def save_variant_groups(self) -> None:
        rows = []
        for prof, b in self.profiles.items():
            for g in b["variant_groups"].values():
                for s in g.snvs:
                    rows.append((prof, g.region, g.name, g.gtype, s))
        df = pd.DataFrame(
            rows, columns=["profile", "region_name", "group_name", "group_type", "snv_key"])
        df.to_csv(self.cfg.variant_groups, index=False)

    @staticmethod
    def export_snvs(snvs: List[str], path: str,
                    source: Optional[Dict] = None) -> None:
        """Export SNVs as JSON with provenance metadata."""
        doc = {
            "contents": "variants",
            "source": source or {"regions": [], "groups": []},
            "variants": snvs,
        }
        with open(path, "w") as fh:
            json.dump(doc, fh, indent=2)

    @staticmethod
    def import_snvs(path: str) -> dict:
        """Read an exported SNV JSON file.  Returns the parsed dict on success;
        raises ValueError for unknown contents types."""
        with open(path) as fh:
            doc = json.load(fh)
        if doc.get("contents") != "variants":
            raise ValueError(
                f"Unsupported contents type: {doc.get('contents')}")
        required = {"variants", "source"}
        missing = required - set(doc.keys())
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")
        return doc

    def delete_variant_groups(self, groups: List[tuple]) -> None:
        """Delete multiple variant groups at once.  Each item is (region, name)."""
        for key in groups:
            self.variant_groups.pop(key, None)
        self.save_variant_groups()
