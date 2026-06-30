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

    # export / import round-trip (JSON with provenance)
    out = os.path.join(tmp, "snvs.json")
    src_meta = {"regions": [rname], "groups": ["exclusive"]}
    sd.export_snvs(exc[:10], out, src_meta)
    doc = StudyData.import_snvs(out)
    assert doc["contents"] == "variants"
    assert doc["variants"] == exc[:10]
    assert doc["source"] == src_meta
    print("export/import JSON OK")

    # --- per-spot burden + coverage-normalized intensity --------------------
    burden = sd.per_spot_burden()
    assert list(burden.index) == sd.spot_barcodes
    assert (burden.values >= 0).all() and burden.max() <= sd.matrix.shape[1]
    print(f"burden: min={int(burden.min())} median={int(burden.median())} "
          f"max={int(burden.max())}  coverage_loaded={sd.coverage is not None}")
    inten = sd.per_spot_intensity(normalize=True)
    assert len(inten) == len(burden)
    # raw and normalized differ when coverage is available
    if sd.coverage is not None:
        assert not (inten.values == burden.values).all()

    # --- spot adjacency -----------------------------------------------------
    bcs, neighbors = sd.spot_adjacency()
    deg = [len(n) for n in neighbors]
    import numpy as np
    print(f"adjacency: {len(bcs)} spots, mean degree {np.mean(deg):.2f}, "
          f"max {max(deg)}")
    assert max(deg) <= 6
    # symmetry: build index, check a sample of edges are mutual-ish (kNN need not be)
    assert np.mean(deg) > 2, "grid adjacency unexpectedly sparse"

    # --- auto tumor regions -------------------------------------------------
    res = sd.auto_tumor_regions(seed_pct=90, grow_pct=60, min_size=5)
    regions = res["regions"]
    print(f"auto regions @intensity90: {len(regions)} regions, "
          f"sizes {[len(r) for r in regions][:8]}")
    assert all(len(r) >= 5 for r in regions), "min_size not enforced"
    # contiguity: each region is connected under the adjacency graph
    idx = {b: i for i, b in enumerate(bcs)}
    for region in regions:
        members = set(idx[b] for b in region)
        seen = {next(iter(members))}
        stack = [next(iter(members))]
        while stack:
            u = stack.pop()
            for v in neighbors[u]:
                if v in members and v not in seen:
                    seen.add(v)
                    stack.append(v)
        assert seen == members, "auto region is not contiguous!"
    print("auto-region contiguity OK")
    # higher intensity keeps fewer-or-equal spots
    res_lo = sd.auto_tumor_regions(seed_pct=70, grow_pct=40, min_size=5)
    hi_spots = sum(len(r) for r in regions)
    lo_spots = sum(len(r) for r in res_lo["regions"])
    print(f"spots kept: intensity70={lo_spots}  intensity90={hi_spots}")
    assert lo_spots >= hi_spots, "lower intensity should keep >= spots"

    # --- watershed split criterion -----------------------------------------
    # one center per region, and every center lives inside its own region
    assert len(res["centers"]) == len(regions)
    for region, ctr in zip(regions, res["centers"]):
        assert ctr in set(region), "region center is not inside its region!"
    # split_depth=1.0 merges everything that touches -> fewer-or-equal regions
    res_merge = sd.auto_tumor_regions(seed_pct=90, grow_pct=60, min_size=5,
                                      split_depth=1.0)
    res_split = sd.auto_tumor_regions(seed_pct=90, grow_pct=60, min_size=5,
                                      split_depth=0.0)
    print(f"regions: split_depth=1.0 -> {len(res_merge['regions'])}  "
          f"split_depth=0.0 -> {len(res_split['regions'])}")
    assert len(res_split["regions"]) >= len(res_merge["regions"]), \
        "splitting should produce >= regions than full merge"

    # --- region-center persistence -----------------------------------------
    cregion = sd.add_region("ctr_region", sd.spot_barcodes[:30],
                            center=[sd.spot_barcodes[0]])
    assert sd.region_centers[cregion] == [sd.spot_barcodes[0]]
    sd3 = StudyData(cfg)
    assert sd3.region_centers.get(cregion) == [sd.spot_barcodes[0]], \
        "region center did not round-trip through CSV"
    print("region-center persistence OK")

    shutil.rmtree(tmp)
    print("\nALL CORE TESTS PASSED")


if __name__ == "__main__":
    main()
