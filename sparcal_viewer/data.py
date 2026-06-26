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

        # tumor regions: name -> ordered list of barcodes
        self.regions: Dict[str, List[str]] = {}
        # variant groups keyed by (region, group_name)
        self.variant_groups: Dict[tuple, VariantGroup] = {}

        self._load()

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

        self._load_regions()
        self._load_variant_groups()

    def _load_regions(self) -> None:
        self.regions = {}
        path = self.cfg.tumor_groups
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            df = pd.read_csv(path, dtype=str)
            if {"region_name", "barcode"}.issubset(df.columns):
                for name, sub in df.groupby("region_name", sort=False):
                    self.regions[str(name)] = list(dict.fromkeys(sub["barcode"].tolist()))

    def _load_variant_groups(self) -> None:
        self.variant_groups = {}
        path = self.cfg.variant_groups
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            df = pd.read_csv(path, dtype=str)
            need = {"region_name", "group_name", "group_type", "snv_key"}
            if need.issubset(df.columns):
                for (region, gname, gtype), sub in df.groupby(
                    ["region_name", "group_name", "group_type"], sort=False
                ):
                    g = VariantGroup(str(region), str(gname), str(gtype),
                                     list(dict.fromkeys(sub["snv_key"].tolist())))
                    self.variant_groups[(g.region, g.name)] = g

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

    def spots_with_snvs(self, snvs: List[str]) -> List[str]:
        """Barcodes that carry at least one of the given SNVs (presence > 0)."""
        cols = [s for s in snvs if s in self.matrix.columns]
        if not cols:
            return []
        sub = self.matrix[cols]
        mask = (sub.values > 0).any(axis=1)
        return list(self.matrix.index[mask])

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
    def add_region(self, name: str, barcodes: List[str]) -> str:
        name = self._unique_region_name(name)
        self.regions[name] = list(dict.fromkeys(barcodes))
        self.save_regions()
        return name

    def delete_regions(self, names: List[str]) -> None:
        for n in names:
            self.regions.pop(n, None)
            for key in [k for k in self.variant_groups if k[0] == n]:
                self.variant_groups.pop(key, None)
        self.save_regions()
        self.save_variant_groups()

    def merge_regions(self, names: List[str], new_name: str) -> str:
        merged: List[str] = []
        for n in names:
            merged.extend(self.regions.get(n, []))
        merged = list(dict.fromkeys(merged))
        self.delete_regions(names)
        return self.add_region(new_name, merged)

    def rename_region(self, old: str, new: str) -> str:
        if old not in self.regions:
            return old
        new = self._unique_region_name(new, ignore=old)
        self.regions = {(new if k == old else k): v for k, v in self.regions.items()}
        for key in [k for k in self.variant_groups if k[0] == old]:
            g = self.variant_groups.pop(key)
            g.region = new
            self.variant_groups[(new, g.name)] = g
        self.save_regions()
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
    def save_regions(self) -> None:
        rows = [(name, bc) for name, bcs in self.regions.items() for bc in bcs]
        df = pd.DataFrame(rows, columns=["region_name", "barcode"])
        df.to_csv(self.cfg.tumor_groups, index=False)

    def save_variant_groups(self) -> None:
        rows = []
        for g in self.variant_groups.values():
            for s in g.snvs:
                rows.append((g.region, g.name, g.gtype, s))
        df = pd.DataFrame(rows, columns=["region_name", "group_name", "group_type", "snv_key"])
        df.to_csv(self.cfg.variant_groups, index=False)

    @staticmethod
    def export_snvs(snvs: List[str], path: str) -> None:
        with open(path, "w") as fh:
            for s in snvs:
                fh.write(f"{s}\n")
