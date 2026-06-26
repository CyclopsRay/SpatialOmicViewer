"""Headless GUI smoke test (offscreen Qt). Exercises wiring without a display.

Run with:  QT_QPA_PLATFORM=offscreen python tests/test_gui_smoke.py
"""
import os
import sys
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PySide6 import QtWidgets, QtCore  # noqa: E402
from sparcal_viewer.main_window import MainWindow  # noqa: E402
from sparcal_viewer.data import GROUP_EXCLUSIVE  # noqa: E402

CONFIG = os.path.join(os.path.dirname(HERE), "DCIS_2_SPARCAL", "DCIS_2_SPARCAL.config")


def main():
    src = os.path.dirname(CONFIG)
    tmp = tempfile.mkdtemp(prefix="sparcal_gui_")
    work = os.path.join(tmp, "study")
    shutil.copytree(src, work)
    cfg_path = os.path.join(work, os.path.basename(CONFIG))

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    win.open_config(cfg_path)
    assert win.data is not None, "study failed to load"
    print("loaded:", win.data.matrix.shape)

    # spatial view received the spots
    assert len(win.spatial._barcodes) == win.data.matrix.shape[0]

    # simulate an 'add region' from a programmatic selection
    bcs = win.data.spot_barcodes[:30]
    win._on_spatial_selection(bcs)
    rn = win.data.add_region("gui_region", win.current_selection)
    win._refresh_region_tree()
    assert win.region_tree.topLevelItemCount() == 1
    print("region in tree:", win.region_tree.topLevelItem(0).text(0))

    # generate exclusive on that region and confirm a colored child appears
    win._gen_exclusive(rn)
    top = win.region_tree.topLevelItem(0)
    assert top.childCount() >= 1
    child = top.child(0)
    print("group child:", child.text(0), child.foreground(0).color().name())

    # clicking the group populates the SNV list (col 3)
    win._on_tree_clicked(child, 0)
    print("snv list count:", win.snv_list.count())
    assert win.snv_list.count() == len(win.current_snvs)

    # SNV 'show on tissue' path
    if win.current_snvs:
        win.snv_list.item(0).setSelected(True)
        win._show_snv_spots()
        print("highlighted spots for 1 snv:", len(win.current_selection))

    # export
    out = os.path.join(tmp, "out.txt")
    from sparcal_viewer.data import StudyData
    StudyData.export_snvs(win.current_snvs[:5], out)
    assert os.path.exists(out)

    win.close()
    shutil.rmtree(tmp)
    print("\nGUI SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
