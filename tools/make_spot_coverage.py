#!/usr/bin/env python
"""Generate a per-spot coverage table (`spot_coverage.csv`) from raw SpaceRanger output.

Coverage = total UMI per spot = column-sum of the 10x filtered feature-barcode matrix.
The viewer uses it to coverage-normalize the per-spot SNV burden, so that the
"auto tumor regions" intensity reflects biology rather than sequencing depth.

The matrix is read from a SpaceRanger run.  You can point at any of:
  * the run's `outs/` directory                       (auto-finds the matrix below)
  * the `outs/filtered_feature_bc_matrix/` MTX folder (barcodes/features/matrix.mtx[.gz])
  * the `outs/filtered_feature_bc_matrix.h5` file
  * the `raw_feature_bc_matrix` equivalents

Output is a 2-column CSV `barcode,total_umi` (one row per spot), written next to the
study `.config` so the folder stays self-contained.

Usage:
    python make_spot_coverage.py SPACERANGER_INPUT [-o OUTPUT.csv]

Example (precompute the demo study's coverage):
    python make_spot_coverage.py \\
      /lfs/.../spatialSNV/10x-Visium/DCIS2/spaceranger_align_DCIS2_hg38/DCIS2_output/outs \\
      -o ../DCIS_2_SPARCAL/spot_coverage.csv
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys

import numpy as np
import pandas as pd


def _find_matrix(path: str) -> str:
    """Resolve `path` (a dir or file) to a concrete matrix source the readers below
    understand: either an `.h5` file or a directory holding `matrix.mtx[.gz]`."""
    if os.path.isfile(path):
        return path
    if not os.path.isdir(path):
        raise FileNotFoundError(path)

    # A directory: it may already be the MTX folder, or an `outs/` above it.
    if any(f.startswith("matrix.mtx") for f in os.listdir(path)):
        return path
    for sub in ("filtered_feature_bc_matrix", "raw_feature_bc_matrix"):
        cand = os.path.join(path, sub)
        if os.path.isdir(cand) and any(
            f.startswith("matrix.mtx") for f in os.listdir(cand)
        ):
            return cand
        h5 = os.path.join(path, sub + ".h5")
        if os.path.isfile(h5):
            return h5
    raise FileNotFoundError(
        f"No feature-barcode matrix found in {path} "
        "(expected filtered_feature_bc_matrix[.h5] or a matrix.mtx[.gz] folder).")


def _total_umi_from_mtx(mtx_dir: str) -> pd.Series:
    """Sum UMIs per spot from a 10x MTX folder (genes×cells matrix)."""
    import scipy.io

    def _open(name: str):
        gz = os.path.join(mtx_dir, name + ".gz")
        if os.path.exists(gz):
            return gzip.open(gz, "rt")
        return open(os.path.join(mtx_dir, name), "rt")

    with _open("barcodes.tsv") as fh:
        barcodes = [ln.strip() for ln in fh if ln.strip()]

    mtx_path = os.path.join(mtx_dir, "matrix.mtx.gz")
    if not os.path.exists(mtx_path):
        mtx_path = os.path.join(mtx_dir, "matrix.mtx")
    m = scipy.io.mmread(mtx_path).tocsc()          # genes × cells (spots)
    umi = np.asarray(m.sum(axis=0)).ravel()
    return pd.Series(umi, index=barcodes, dtype=np.int64)


def _total_umi_from_h5(h5_path: str) -> pd.Series:
    """Sum UMIs per spot from a 10x .h5 (CSC: indptr over barcodes)."""
    import h5py

    with h5py.File(h5_path, "r") as f:
        grp = f["matrix"]
        barcodes = [b.decode() if isinstance(b, bytes) else str(b)
                    for b in grp["barcodes"][:]]
        data = grp["data"][:]
        indptr = grp["indptr"][:]              # length = n_barcodes + 1 (CSC by cell)
        per_spot = np.add.reduceat(data, indptr[:-1])
        # reduceat double-counts an empty trailing column; guard against zero-width cols
        widths = np.diff(indptr)
        per_spot = np.where(widths > 0, per_spot, 0)
    return pd.Series(per_spot.astype(np.int64), index=barcodes)


def total_umi_per_spot(path: str) -> pd.Series:
    src = _find_matrix(path)
    if src.endswith(".h5"):
        return _total_umi_from_h5(src)
    return _total_umi_from_mtx(src)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="SpaceRanger outs/ dir, MTX folder, or .h5 file")
    ap.add_argument("-o", "--output", default="spot_coverage.csv",
                    help="output CSV path (default: ./spot_coverage.csv)")
    args = ap.parse_args(argv)

    umi = total_umi_per_spot(args.input)
    df = umi.rename("total_umi").rename_axis("barcode").reset_index()
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"[make_spot_coverage] {len(df)} spots → {args.output}  "
          f"(UMI/spot median={int(umi.median())}, min={int(umi.min())}, "
          f"max={int(umi.max())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
