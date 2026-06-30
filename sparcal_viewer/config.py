"""Load and represent a study `.config` file.

A config is a small YAML document whose `files:` paths are resolved relative to
the directory that contains the config file, so a study folder is fully
self-contained and portable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Any

import yaml


@dataclass
class StudyConfig:
    path: str                       # absolute path to the .config file
    root: str                       # directory containing the config
    project: str
    study: str
    genome: str
    files: Dict[str, str]           # logical name -> absolute path
    image: Dict[str, Any]
    variant_grouping: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict)

    # --- convenience accessors -------------------------------------------
    @property
    def snv_matrix(self) -> str:
        return self.files["snv_matrix"]

    @property
    def tissue_positions(self) -> str:
        return self.files["tissue_positions"]

    @property
    def hires_image(self) -> str:
        return self.files["hires_image"]

    @property
    def scalefactors(self) -> str:
        return self.files["scalefactors"]

    @property
    def tumor_groups(self) -> str:
        return self.files["tumor_groups"]

    @property
    def variant_groups(self) -> str:
        return self.files["variant_groups"]

    @property
    def tumor_centers(self) -> str:
        """Per-region center barcodes for auto-generated regions. Long format:
        region_name,barcode. Written by the app; defaults next to the config."""
        return self.files["tumor_centers"]

    @property
    def spot_coverage(self) -> str:
        """Optional per-spot coverage CSV (barcode,total_umi). '' if not configured."""
        return self.files.get("spot_coverage", "")

    def title(self) -> str:
        return f"{self.project} — {self.study}"


# Defaults applied when a key is omitted from the config.
_IMAGE_DEFAULTS = {
    "x_column": "pxl_col_in_fullres",
    "y_column": "pxl_row_in_fullres",
    "scalef_key": "tissue_hires_scalef",
    "spot_diameter_key": "spot_diameter_fullres",
    "in_tissue_only": True,
}
_GROUPING_DEFAULTS = {
    "general_min_fraction": 80,
    "exclusive_inside_min": 80,
    "exclusive_outside_max": 20,
}
_REQUIRED_FILES = ("snv_matrix", "tissue_positions", "hires_image", "scalefactors")


def load_config(config_path: str) -> StudyConfig:
    config_path = os.path.abspath(config_path)
    if not os.path.isfile(config_path):
        raise FileNotFoundError(config_path)
    root = os.path.dirname(config_path)

    with open(config_path, "r") as fh:
        doc = yaml.safe_load(fh) or {}

    files_in = doc.get("files", {}) or {}
    missing = [k for k in _REQUIRED_FILES if k not in files_in]
    if missing:
        raise ValueError(f"config '{config_path}' missing required files: {missing}")

    # tumor_groups / variant_groups default to canonical names if omitted.
    files_in.setdefault("tumor_groups", "tumor_groups.csv")
    files_in.setdefault("variant_groups", "variant_groups.csv")
    files_in.setdefault("tumor_centers", "tumor_centers.csv")

    files: Dict[str, str] = {}
    for name, rel in files_in.items():
        files[name] = rel if os.path.isabs(rel) else os.path.normpath(os.path.join(root, rel))

    # Validate that the inputs we must read actually exist (writable CSVs may not yet).
    for key in _REQUIRED_FILES:
        if not os.path.exists(files[key]):
            raise FileNotFoundError(f"{key}: {files[key]} (referenced by {config_path})")

    image = {**_IMAGE_DEFAULTS, **(doc.get("image") or {})}
    grouping = {**_GROUPING_DEFAULTS, **(doc.get("variant_grouping") or {})}

    return StudyConfig(
        path=config_path,
        root=root,
        project=str(doc.get("project", "")),
        study=str(doc.get("study", "")),
        genome=str(doc.get("genome", "")),
        files=files,
        image=image,
        variant_grouping=grouping,
        raw=doc,
    )
