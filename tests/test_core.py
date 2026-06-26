"""Headless smoke/logic test of the data layer against the DCIS_2 study.

Run from the `viewer/` dir:  python tests/test_core.py
"""
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparcal_viewer.config import load_config
from sparcal_viewer.data import StudyData, GROUP_EXCLUSIVE

CONFIG = os.path.join(os.path.dirname(HERE), "DCIS_2_SPARCAL", "DCIS_2_SPARCAL.config")


def main():
    # Work on a copy so we don't clobber the real csvs.
    src = os.path.dirname(CONFIG)
    tmp = tempfile.mkdtemp(prefix="sparcal_test_")
    work = os.path.join(tmp, "study")
    shutil.copytree(src, work)
    cfg = load_config(os.path.join(work, os.path.basename(CONFIG)))
    print(f"config: {cfg.title()}  genome={cfg.genome}")

    sd = StudyData(cfg)
    print(f"matrix: {sd.matrix.shape}  spots(plotable)={len(sd.spot_barcodes)}  "
          f"scalef={sd.scalef}  spot_diam_px={sd.spot_diameter:.2f}")
    assert sd.matrix.shape[0] > 0 and sd.matrix.shape[1] > 0
    assert len(sd.spot_barcodes) == sd.matrix.shape[0]

    # general over all in-tissue spots
    gen = sd.generate_general(cfg.variant_grouping["general_min_fraction"])
    print(f"general (>{cfg.variant_grouping['general_min_fraction']}%): {len(gen)} SNVs")

    # Build a synthetic region from the first 40 spots and test exclusivity logic.
    region_bcs = sd.spot_barcodes[:40]
    rname = sd.add_region("test_region", region_bcs)
    assert rname in sd.regions

    exc = sd.generate_exclusive(rname)
    print(f"exclusive(strict) in '{rname}': {len(exc)} SNVs")
    # verify: every exclusive SNV is absent outside the region
    outside = set(sd.matrix.index) - set(sd.region_in_matrix(rname))
    if exc:
        sub = sd.matrix.loc[list(outside), exc[:200]]
        assert sub.values.sum() == 0, "exclusive SNV present outside region!"

    thr = sd.generate_exclusive_threshold(rname, 80, 20)
    print(f"exclusive_threshold(80/20) in '{rname}': {len(thr)} SNVs")

    # save a variant group, persist, reload, confirm round-trip
    g = sd.add_variant_group(rname, "exclusive", GROUP_EXCLUSIVE, exc[:50])
    sd2 = StudyData(cfg)
    assert (rname, "exclusive") in sd2.variant_groups
    assert sd2.variant_groups[(rname, "exclusive")].snvs == exc[:50]
    assert sd2.regions[rname][:5] == region_bcs[:5]
    print(f"persistence round-trip OK (group color {g.color()})")

    # spots_with_snvs sanity
    hits = sd.spots_with_snvs(gen[:5]) if gen else []
    print(f"spots carrying first 5 'general' SNVs: {len(hits)}")

    # export
    out = os.path.join(tmp, "snvs.txt")
    sd.export_snvs(exc[:10], out)
    assert sum(1 for _ in open(out)) == min(10, len(exc))
    print("export OK")

    shutil.rmtree(tmp)
    print("\nALL CORE TESTS PASSED")


if __name__ == "__main__":
    main()
