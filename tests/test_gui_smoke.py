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
    assert any(b is not None for b in win.spatial._spots.data["brush"]), \
        "per-spot brushes not applied in colour-by-count mode"
    win.spatial.set_color_mode(False)
    assert win.spatial._legend is None
    # bug fix: toggling colour-by-count OFF must drop the per-spot brushes so every
    # spot shares one uniform colour again (pyqtgraph keeps stale per-point brushes).
    assert all(b is None for b in win.spatial._spots.data["brush"]), \
        "colour-by-count brushes not cleared when toggled off"
    print("burden colour mode toggle OK")

    # Overview: every region gets its own colour; spots in >1 region go dark grey.
    from sparcal_viewer.spatial_view import MULTI_REGION_BRUSH, PALE_BRUSH
    plotted = win.spatial._barcodes
    pos = {b: i for i, b in enumerate(plotted)}
    a0, a1, shared, b3 = plotted[0], plotted[1], plotted[2], plotted[3]
    n_multi = win.spatial.show_region_overview(
        {"R1": [a0, a1, shared], "R2": [shared, b3]})   # `shared` in both -> grey
    brushes = list(win.spatial._spots.data["brush"])
    def _rgb(bc):
        return brushes[pos[bc]].color().getRgb()
    assert n_multi == 1
    assert _rgb(shared) == MULTI_REGION_BRUSH.color().getRgb(), "shared spot not dark grey"
    assert _rgb(a0) not in (PALE_BRUSH.color().getRgb(),
                            MULTI_REGION_BRUSH.color().getRgb()), "region spot mis-coloured"
    unassigned = next((b for b in plotted if b not in {a0, a1, shared, b3}), None)
    if unassigned is not None:
        assert _rgb(unassigned) == PALE_BRUSH.color().getRgb(), "unassigned spot not pale"
    # main-window wiring runs against the real profile without error
    win._show_overview()
    print(f"overview colouring OK ({n_multi} shared spot(s) dark grey)")

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

    # edit mode uses ExtendedSelection so Shift-click range-selects regions/groups
    from PySide6 import QtWidgets as _QW
    win._start_edit_regions()
    assert (win.region_tree.selectionMode()
            == _QW.QAbstractItemView.ExtendedSelection), "edit mode not ExtendedSelection"
    win._cancel_region_mode()
    assert (win.region_tree.selectionMode()
            == _QW.QAbstractItemView.SingleSelection), "selection mode not reset"
    print("edit-mode ExtendedSelection OK")

    # About: clickable app-name action on the top bar, reporting version + build time
    import sparcal_viewer as _sv
    from sparcal_viewer.main_window import APP_NAME
    assert APP_NAME in [a.text() for a in win.menuBar().actions()], "no app-name action"
    assert _sv.__version__ and _sv.build_time(), "version/build_time missing"
    print("About action present; version", _sv.__version__, "build", _sv.build_time())

    # --- profiles: selection page ↔ region page ----------------------------
    from PySide6 import QtCore as _QC
    win._show_profile_page()
    assert win.col2_stack.currentIndex() == 0, "back-button did not show profile page"
    assert win.profile_list.count() == len(win.data.profile_names())
    # open the first profile -> region page titled with its name
    target = win.data.profile_names()[0]
    for i in range(win.profile_list.count()):
        if win.profile_list.item(i).data(_QC.Qt.UserRole) == target:
            win.profile_list.setCurrentRow(i)
            break
    win._open_selected_profile()
    assert win.col2_stack.currentIndex() == 1, "opening a profile did not show region page"
    assert target in win.region_title.text() and win.data.current_profile == target
    print("profile switch OK ->", target)

    # --- hover-to-identify: change-only selects the region in column 2 ------
    if win.region_tree.topLevelItemCount():
        from sparcal_viewer.main_window import ROLE_REGION as _RR
        rname = win.region_tree.topLevelItem(0).data(0, _RR)
        win.spatial.set_hover_enabled(True)
        win._on_hover_region(rname)
        cur = win.region_tree.currentItem()
        assert cur is not None and cur.data(0, _RR) == rname, "hover did not select region"
        assert len(win.spatial._hilite.data) > 0, "hover did not highlight the region"
        print("hover-identify OK ->", rname)

    # --- reset: clears selection and paints the pale base -------------------
    from sparcal_viewer.spatial_view import PALE_BRUSH
    win._reset_view()
    assert win.snv_list.count() == 0 and win.region_tree.currentItem() is None
    assert len(win.spatial._hilite.data) == 0 and len(win.spatial._centers.data) == 0
    assert win.spatial._spots.opts["brush"] is PALE_BRUSH, "reset did not pale the spots"
    print("reset OK")

    # --- Auto dialog floats on top and resets the view ----------------------
    win._open_auto_dialog()
    adlg = win._auto_dialog
    assert bool(adlg.windowFlags() & _QC.Qt.WindowStaysOnTopHint), "auto not always-on-top"
    assert win.spatial._hover_enabled is False, "hover not suppressed while Auto open"
    adlg.close()
    assert win.spatial._hover_enabled is True, "hover not restored after Auto close"
    print("auto floating + view-reset OK")

    # --- profile-map export writes a non-empty PNG and PDF ------------------
    win.data.set_current_profile("Ground Truth")
    r2b = {r: win.data.region_in_matrix(r) for r in win.data.region_names()}
    for ext, bg in (("png", False), ("pdf", True)):
        p = os.path.join(tmp, f"map.{ext}")
        out = win.spatial.export_profile_map(r2b, bg, p)
        assert out and os.path.getsize(out) > 1000, f"export failed for {ext}"
    print("profile-map export OK")

    # --- profile comparison via the Edit/Function path ----------------------
    win._show_profile_page()
    win._start_profile_edit()
    assert win.profile_action_bar.isVisibleTo(win), "compare action bar not shown"
    from PySide6.QtCore import Qt as _Qt
    for i in range(win.profile_list.count()):
        it = win.profile_list.item(i)
        it.setSelected(it.data(_Qt.UserRole) in ("Ground Truth", "Test"))
    names = [it.data(_Qt.UserRole) for it in win.profile_list.selectedItems()]
    assert len(names) == 2
    res = win.data.compare_profiles(names[0], names[1])
    assert set(res["scores"]) == {"ari", "nmi", "homogeneity", "completeness", "v_measure"}
    assert len(res["overlap"]) > 0
    win._end_profile_edit()
    assert not win.profile_action_bar.isVisibleTo(win)
    print("profile compare path OK ->", names, round(res["scores"]["ari"], 3))

    win.close()
    shutil.rmtree(tmp)
    print("\nGUI SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
