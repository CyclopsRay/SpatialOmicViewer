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
from sparcal_viewer.main_window import MainWindow, ROLE_REGION as _ROLE_REGION  # noqa: E402
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
    n_before = win.region_tree.topLevelItemCount()
    bcs = win.data.spot_barcodes[:30]
    win._on_spatial_selection(bcs)
    rn = win.data.add_region("gui_region", win.current_selection)
    win._refresh_region_tree()
    assert win.region_tree.topLevelItemCount() == n_before + 1
    def _find_top(name):
        return next(win.region_tree.topLevelItem(i)
                    for i in range(win.region_tree.topLevelItemCount())
                    if win.region_tree.topLevelItem(i).data(0, _ROLE_REGION) == name)
    print("region in tree:", _find_top(rn).text(0))

    # generate exclusive on that region and confirm a colored child appears
    win._gen_exclusive(rn)
    top = _find_top(rn)               # tree was rebuilt; re-fetch the item
    assert top.childCount() >= 1
    child = top.child(0)
    print("group child:", child.text(0), child.foreground(0).color().name())

    # clicking the group populates the SNV list (col 3)
    win._on_tree_clicked(child, 0)
    print("snv list count:", win.snv_list.count())
    assert win.snv_list.count() == len(win.current_snvs)

    # SNV 'show on tissue' path -> selection-specific burden legend appears
    if win.current_snvs:
        win.snv_list.item(0).setSelected(True)
        win._show_snv_spots()
        print("highlighted spots for 1 snv:", len(win.current_selection))
        assert win.spatial._sel_legend is not None, "selection legend not shown"
        # a plain region highlight should drop the selection legend
        win.spatial.highlight(win.current_selection, "#f1c40f")
        assert win.spatial._sel_legend is None, "selection legend not cleared"

    # export
    out = os.path.join(tmp, "out.txt")
    from sparcal_viewer.data import StudyData
    StudyData.export_snvs(win.current_snvs[:5], out)
    assert os.path.exists(out)

    # burden colouring: toggle on, legend appears, brushes recoloured
    assert win.spatial._burden is not None
    win.spatial.set_color_mode(True)
    assert win.spatial._legend is not None
    win.spatial.set_color_mode(False)
    assert win.spatial._legend is None
    print("burden colour mode toggle OK")

    # auto tumor regions dialog: open, recompute, create
    win._open_auto_dialog()
    dlg = win._auto_dialog
    assert dlg is not None
    dlg.sl.setValue(85)
    n_before = len(win.data.region_names())
    n_regions = len(dlg._last["regions"])
    print("auto dialog preview regions:", n_regions)
    if n_regions:
        # drive _create without the name prompt
        from PySide6 import QtWidgets as _Q
        orig = _Q.QInputDialog.getText
        _Q.QInputDialog.getText = staticmethod(lambda *a, **k: ("auto", True))
        try:
            dlg._create()
        finally:
            _Q.QInputDialog.getText = orig
        assert len(win.data.region_names()) == n_before + n_regions
        print("auto-created regions:", len(win.data.region_names()) - n_before)
        # auto regions saved a center; clicking one marks it on the tissue
        auto_names = [n for n in win.data.region_names()
                      if win.data.region_centers.get(n)]
        assert auto_names, "auto regions did not persist a center"
        win._refresh_region_tree()
        top = _find_top(auto_names[0])
        win._on_tree_clicked(top, 0)
        assert len(win.spatial._centers.data) >= 1, "center marker not drawn"
        print("center marker drawn for", auto_names[0])
    assert win._auto_dialog is None, "dialog should clear itself on close"

    win.close()
    shutil.rmtree(tmp)
    print("\nGUI SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
