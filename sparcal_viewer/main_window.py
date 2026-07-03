"""Main window: 3 columns — spatial view | tumor regions | SNV list."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .config import load_config, StudyConfig
from .data import (StudyData, VariantGroup, GROUP_EXCLUSIVE, GROUP_GENERAL,
                   GROUP_EXCLUSIVE_THRESHOLD, GROUP_SELECTION)
from .spatial_view import SpatialView

ROLE_REGION = QtCore.Qt.UserRole + 1     # region name on a top-level item
ROLE_GROUP = QtCore.Qt.UserRole + 2      # (region, group_name) on a child item

APP_NAME = "SPARCAL Viewer"              # shown as the clickable name on the top bar


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPARCAL Spatial-SNV Viewer")
        self.resize(1500, 900)
        self.setAcceptDrops(True)

        self.cfg: Optional[StudyConfig] = None
        self.data: Optional[StudyData] = None
        self.current_selection: List[str] = []   # barcodes from last lasso
        self.current_snvs: List[str] = []         # SNVs shown in column 3
        self.current_snv_source: dict = {"regions": [], "groups": []}  # provenance
        self._auto_dialog: Optional["AutoTumorDialog"] = None

        self._build_ui()
        self._show_placeholder()

    # ============================================================== UI build
    def _build_ui(self) -> None:
        self._build_menu()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._build_spatial_pane())
        splitter.addWidget(self._build_region_pane())
        splitter.addWidget(self._build_snv_pane())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([800, 360, 340])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Open a .config file (File ▸ Open, or drag it in).")

    def _build_menu(self) -> None:
        # App-name menu on the top bar — its "About" item opens the About dialog.
        # (A bare action added straight to the menu bar does not render on macOS's
        # native menu bar; it must live inside a menu to be visible/clickable.)
        app_menu = self.menuBar().addMenu(APP_NAME)
        about = app_menu.addAction(f"About {APP_NAME}…")
        about.setMenuRole(QtGui.QAction.AboutRole)   # macOS folds this into the app menu
        about.triggered.connect(self._show_about)

        m = self.menuBar().addMenu("&File")
        act_open = m.addAction("Open config…")
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(self._open_dialog)
        m.addSeparator()
        exp = m.addMenu("Export")
        exp.addAction("Profile map (with background)…",
                      lambda: self._export_profile_map(True))
        exp.addAction("Profile map (without background)…",
                      lambda: self._export_profile_map(False))
        m.addSeparator()
        m.addAction("Quit", self.close)

    def _show_about(self) -> None:
        from . import __version__, build_time
        QtWidgets.QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>SPARCAL Spatial-SNV Viewer</b><br><br>"
            f"Version&nbsp;{__version__}<br>"
            f"Build time:&nbsp;{build_time()}")

    # ---- column 1 -------------------------------------------------------
    def _build_spatial_pane(self) -> QtWidgets.QWidget:
        self.spatial = SpatialView()
        self.spatial.selectionChanged.connect(self._on_spatial_selection)
        self.spatial.hoveredRegion.connect(self._on_hover_region)
        self.spatial.overviewRequested.connect(self._show_overview)

        # Placeholder shown before any study is loaded.
        placeholder = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(placeholder)
        pv.setAlignment(QtCore.Qt.AlignCenter)
        lbl = QtWidgets.QLabel("Click to open a config file")
        lbl.setStyleSheet("color: #888; font-size: 18px;")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        lbl.mousePressEvent = lambda ev: self._open_dialog()
        pv.addWidget(lbl)

        self.spatial_stack = QtWidgets.QStackedWidget()
        self.spatial_stack.addWidget(placeholder)   # index 0 — empty
        self.spatial_stack.addWidget(self.spatial)  # index 1 — study loaded
        self.spatial_stack.setCurrentIndex(0)
        return self.spatial_stack

    # ---- column 2 -------------------------------------------------------
    def _build_region_pane(self) -> QtWidgets.QWidget:
        """Column 2 is a two-page stack: profile selection, then that profile's
        regions. The page index is toggled by the '‹ Profiles' back-button and by
        opening a profile."""
        self.col2_stack = QtWidgets.QStackedWidget()
        self.col2_stack.addWidget(self._build_profile_page())   # index 0
        self.col2_stack.addWidget(self._build_region_page())    # index 1
        self.col2_stack.setCurrentIndex(0)
        return self.col2_stack

    # ---- column 2, page 0: profile selection ----------------------------
    def _build_profile_page(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.addWidget(QtWidgets.QLabel("<b>Tumor profiles</b>"))

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.btn_profile_new = QtWidgets.QPushButton("New")
        self.btn_profile_rename = QtWidgets.QPushButton("Rename")
        self.btn_profile_delete = QtWidgets.QPushButton("Delete")
        self.btn_profile_edit = QtWidgets.QPushButton("Edit")
        self.btn_profile_new.clicked.connect(self._new_profile)
        self.btn_profile_rename.clicked.connect(self._rename_profile)
        self.btn_profile_delete.clicked.connect(self._delete_profile)
        self.btn_profile_edit.clicked.connect(self._start_profile_edit)
        for b in (self.btn_profile_new, self.btn_profile_rename,
                  self.btn_profile_delete, self.btn_profile_edit):
            bar.addWidget(b)
        bar.addStretch(1)
        self.profile_bar = self._wrap_layout(bar)
        v.addWidget(self.profile_bar)

        self.profile_list = QtWidgets.QListWidget()
        self.profile_list.itemDoubleClicked.connect(
            lambda *_: self._open_selected_profile())
        v.addWidget(self.profile_list, 1)

        self.btn_profile_open = QtWidgets.QPushButton("Open profile ▸")
        self.btn_profile_open.clicked.connect(self._open_selected_profile)
        v.addWidget(self.btn_profile_open)

        # Edit-mode action bar: (Function ▾ = Compare) + Done. Hidden by default.
        abar = QtWidgets.QHBoxLayout()
        abar.setContentsMargins(0, 0, 0, 0)
        self.lbl_profile_mode = QtWidgets.QLabel("Pick two profiles")
        abar.addWidget(self.lbl_profile_mode)
        abar.addStretch(1)
        self.btn_profile_func = QtWidgets.QPushButton("Function ▾")
        self.btn_profile_func.clicked.connect(self._show_profile_function_menu)
        self.btn_profile_done = QtWidgets.QPushButton("Done")
        self.btn_profile_done.clicked.connect(self._end_profile_edit)
        abar.addWidget(self.btn_profile_func)
        abar.addWidget(self.btn_profile_done)
        self.profile_action_bar = self._wrap_layout(abar)
        self.profile_action_bar.setVisible(False)
        v.addWidget(self.profile_action_bar)
        return w

    @staticmethod
    def _wrap_layout(layout) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        w.setLayout(layout)
        return w

    # ---- column 2, page 1: regions of the current profile ---------------
    def _build_region_page(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        self.region_title = QtWidgets.QLabel("Tumor profile")
        self.region_title.setTextFormat(QtCore.Qt.RichText)
        v.addWidget(self.region_title)
        self.btn_back_profiles = QtWidgets.QPushButton("‹ Profiles")
        self.btn_back_profiles.setFlat(True)
        self.btn_back_profiles.setStyleSheet("text-align:left;color:#2980b9;")
        self.btn_back_profiles.setMaximumWidth(110)
        self.btn_back_profiles.clicked.connect(self._show_profile_page)
        v.addWidget(self.btn_back_profiles)

        # normal toolbar: Add / Edit / Generate
        self.region_bar = QtWidgets.QWidget()
        hb = QtWidgets.QHBoxLayout(self.region_bar)
        hb.setContentsMargins(0, 0, 0, 0)
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_auto = QtWidgets.QPushButton("Auto")
        self.btn_generate = QtWidgets.QPushButton("Generate ▾")
        self.btn_add.clicked.connect(self._start_add_region)
        self.btn_edit.clicked.connect(self._start_edit_regions)
        self.btn_auto.clicked.connect(self._open_auto_dialog)
        self.btn_generate.clicked.connect(self._show_generate_menu)
        for b in (self.btn_add, self.btn_edit, self.btn_auto, self.btn_generate):
            hb.addWidget(b)
        hb.addStretch(1)
        v.addWidget(self.region_bar)

        self.region_tree = QtWidgets.QTreeWidget()
        self.region_tree.setHeaderHidden(True)
        self.region_tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.region_tree.itemClicked.connect(self._on_tree_clicked)
        v.addWidget(self.region_tree, 1)

        # contextual action bar (Add mode: Finish/Cancel; Edit mode: Merge/Delete/Cancel)
        self.region_action_bar = QtWidgets.QWidget()
        ab = QtWidgets.QHBoxLayout(self.region_action_bar)
        ab.setContentsMargins(0, 0, 0, 0)
        self.lbl_mode = QtWidgets.QLabel("")
        ab.addWidget(self.lbl_mode)
        ab.addStretch(1)
        self.btn_finish = QtWidgets.QPushButton("Finish")
        self.btn_merge = QtWidgets.QPushButton("Merge")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_finish.clicked.connect(self._finish_add_region)
        self.btn_merge.clicked.connect(self._merge_regions)
        self.btn_delete.clicked.connect(self._delete_regions)
        self.btn_cancel.clicked.connect(self._cancel_region_mode)
        for b in (self.btn_finish, self.btn_merge, self.btn_delete, self.btn_cancel):
            ab.addWidget(b)
        v.addWidget(self.region_action_bar)
        self.region_action_bar.setVisible(False)
        return w

    # ---- column 3 -------------------------------------------------------
    def _build_snv_pane(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        self.snv_title = QtWidgets.QLabel("<b>SNVs</b>")
        v.addWidget(self.snv_title)

        hb = QtWidgets.QHBoxLayout()
        self.btn_export = QtWidgets.QPushButton("Export")
        self.btn_import = QtWidgets.QPushButton("Import")
        self.btn_select = QtWidgets.QPushButton("Select all")
        self.btn_export.clicked.connect(self._export_snvs)
        self.btn_import.clicked.connect(self._import_snvs)
        self.btn_select.clicked.connect(self._select_all_snvs)
        hb.addWidget(self.btn_export)
        hb.addWidget(self.btn_import)
        hb.addWidget(self.btn_select)
        hb.addStretch(1)
        v.addLayout(hb)

        self.snv_list = QtWidgets.QListWidget()
        self.snv_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.snv_list.setUniformItemSizes(True)
        v.addWidget(self.snv_list, 1)

        self.snv_action_bar = QtWidgets.QWidget()
        ab = QtWidgets.QHBoxLayout(self.snv_action_bar)
        ab.setContentsMargins(0, 0, 0, 0)
        self.btn_show = QtWidgets.QPushButton("Show on tissue")
        self.btn_add_spots = QtWidgets.QPushButton("Add spots → region")
        self.btn_show.clicked.connect(self._show_snv_spots)
        self.btn_add_spots.clicked.connect(self._add_spots_from_snvs)
        for b in (self.btn_show, self.btn_add_spots):
            ab.addWidget(b)
        ab.addStretch(1)
        v.addWidget(self.snv_action_bar)
        return w

    # ============================================================ open study
    def _open_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open study config", "", "Config (*.config *.yaml *.yml);;All files (*)")
        if path:
            self.open_config(path)

    def open_config(self, path: str) -> None:
        try:
            cfg = load_config(path)
            data = StudyData(cfg)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Failed to open", f"{exc}")
            return
        self.cfg, self.data = cfg, data
        self.setWindowTitle(f"SPARCAL Spatial-SNV Viewer — {cfg.title()}")
        self.spatial_stack.setCurrentIndex(1)  # show spatial view

        bcs = data.spot_barcodes
        xy = data.positions.loc[bcs, ["x", "y"]].to_numpy()
        self.spatial.set_data(cfg.hires_image, bcs, xy, data.spot_diameter)
        burden = data.per_spot_burden()
        self.spatial.set_burden(list(burden.index), burden.values)
        self.spatial.set_hover_regions(data.barcode_region_map())
        self._refresh_region_tree()
        self._refresh_profile_list()
        self.col2_stack.setCurrentIndex(0)      # start on profile selection
        self._clear_snvs()
        self.statusBar().showMessage(
            f"{cfg.title()}: {data.matrix.shape[0]} spots × {data.matrix.shape[1]} SNVs")

    def _show_placeholder(self) -> None:
        self.statusBar().showMessage("Open a .config file (File ▸ Open, or drag it in).")

    # ---- drag & drop ----------------------------------------------------
    def dragEnterEvent(self, ev: QtGui.QDragEnterEvent) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev: QtGui.QDropEvent) -> None:
        for url in ev.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self.open_config(p)
                break

    # ============================================================ profiles
    def _refresh_profile_list(self) -> None:
        self.profile_list.clear()
        if not self.data:
            return
        counts = self.data.region_counts()
        for name in self.data.profile_names():
            it = QtWidgets.QListWidgetItem(f"{name}  ({counts.get(name, 0)})")
            it.setData(QtCore.Qt.UserRole, name)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            self.profile_list.addItem(it)
            if name == self.data.current_profile:
                self.profile_list.setCurrentItem(it)

    def _selected_profile_name(self) -> Optional[str]:
        it = self.profile_list.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else None

    def _show_profile_page(self) -> None:
        """Return to the profile-selection page (the '‹ Profiles' back-button)."""
        self._cancel_region_mode()
        self._end_profile_edit()
        self._reset_view()
        self._refresh_profile_list()
        self.col2_stack.setCurrentIndex(0)

    def _open_selected_profile(self) -> None:
        name = self._selected_profile_name()
        if not name or not self.data:
            return
        self._end_profile_edit()
        self.data.set_current_profile(name)
        self._enter_region_page()

    def _enter_region_page(self) -> None:
        """Switch to the region view for data.current_profile and refresh it."""
        self.region_title.setText(
            f'Tumor profile: "<b>{self.data.current_profile}</b>"')
        self._refresh_region_tree()
        self._clear_snvs()
        self._reset_view()
        self.spatial.set_hover_regions(self.data.barcode_region_map())
        self.col2_stack.setCurrentIndex(1)

    def _new_profile(self) -> None:
        if not self.data:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "New profile", "Profile name:")
        if not ok:
            return
        pn = self.data.add_profile(name)
        self._refresh_profile_list()
        self.statusBar().showMessage(f"Created profile '{pn}' — open it to add regions")

    def _rename_profile(self) -> None:
        name = self._selected_profile_name()
        if not self.data or not name:
            return
        new, ok = QtWidgets.QInputDialog.getText(
            self, "Rename profile", "New name:", text=name)
        if not ok:
            return
        self.data.rename_profile(name, new)
        self._refresh_profile_list()

    def _delete_profile(self) -> None:
        name = self._selected_profile_name()
        if not self.data or not name:
            return
        if QtWidgets.QMessageBox.question(
                self, "Delete profile",
                f"Delete profile '{name}' and all its regions and groups?"
                ) != QtWidgets.QMessageBox.Yes:
            return
        self.data.delete_profile(name)
        self._refresh_profile_list()

    # ---- profile edit mode: multi-select + Function ▸ Compare ------------
    def _start_profile_edit(self) -> None:
        if not self.data or len(self.data.profile_names()) < 2:
            QtWidgets.QMessageBox.information(
                self, "Compare", "Need at least two profiles to compare.")
            return
        self.profile_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self.profile_bar.setVisible(False)
        self.btn_profile_open.setVisible(False)
        self.profile_action_bar.setVisible(True)

    def _end_profile_edit(self) -> None:
        self.profile_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        self.profile_action_bar.setVisible(False)
        self.profile_bar.setVisible(True)
        self.btn_profile_open.setVisible(True)

    def _show_profile_function_menu(self) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("Compare profiles (ARI / overlap)…", self._compare_profiles)
        menu.exec(self.btn_profile_func.mapToGlobal(
            self.btn_profile_func.rect().bottomLeft()))

    def _compare_profiles(self) -> None:
        names = [it.data(QtCore.Qt.UserRole)
                 for it in self.profile_list.selectedItems()]
        if len(names) != 2:
            QtWidgets.QMessageBox.information(
                self, "Compare", "Select exactly two profiles to compare.")
            return
        result = self.data.compare_profiles(names[0], names[1])
        CompareResultDialog(self, result).exec()

    # ============================================================ region tree
    def _refresh_region_tree(self) -> None:
        self.region_tree.clear()
        if not self.data:
            return
        self.spatial.set_hover_regions(self.data.barcode_region_map())
        for name in self.data.region_names():
            top = QtWidgets.QTreeWidgetItem([f"{name}  ({len(self.data.region_in_matrix(name))})"])
            top.setData(0, ROLE_REGION, name)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            for g in self.data.groups_for_region(name):
                child = QtWidgets.QTreeWidgetItem([f"{g.name}  [{len(g.snvs)}]"])
                child.setData(0, ROLE_GROUP, (g.region, g.name))
                child.setForeground(0, QtGui.QBrush(QtGui.QColor(g.color())))
                cf = child.font(0)
                cf.setBold(True)
                child.setFont(0, cf)
                top.addChild(child)
            self.region_tree.addTopLevelItem(top)
            top.setExpanded(True)

    def _on_tree_clicked(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        if self._edit_mode:
            return  # selection handled by multi-select in edit mode
        group_key = item.data(0, ROLE_GROUP)
        if group_key:
            g = self.data.variant_groups.get(group_key)
            if g:
                self._show_snvs(g.snvs, f"{g.region} ▸ {g.name}",
                                {"regions": [g.region], "groups": [g.name]})
                self.spatial.clear_centers()
                self._color_spots_by_snvs(g.snvs, f"{g.region} ▸ {g.name}")
            return
        region = item.data(0, ROLE_REGION)
        if region:
            self._highlight_region(region)

    def _highlight_region(self, region: str) -> None:
        """Highlight a whole region on the tissue + show its saved center(s)."""
        self.spatial.clear_highlight()
        self.spatial.highlight(self.data.region_in_matrix(region), "#f1c40f")
        rows = set(self.data.matrix.index)
        centers = [c for c in self.data.region_centers.get(region, []) if c in rows]
        self.spatial.mark_centers(centers)

    def _select_tree_region(self, region: str) -> None:
        """Select a region's top-level tree item (used by hover-to-identify)."""
        for i in range(self.region_tree.topLevelItemCount()):
            top = self.region_tree.topLevelItem(i)
            if top.data(0, ROLE_REGION) == region:
                self.region_tree.setCurrentItem(top)
                return

    def _on_hover_region(self, region: Optional[str]) -> None:
        """Cursor moved over a spot whose region changed (or left a region)."""
        # only react in the region view, normal (non-selection, non-edit) mode
        if (not self.data or self._add_mode or self._edit_mode
                or self.col2_stack.currentIndex() != 1):
            return
        if region and region in self.data.regions:
            self._select_tree_region(region)
            self._highlight_region(region)

    def _export_profile_map(self, with_background: bool) -> None:
        """Export the current profile's regions (each a distinct colour) to PDF/PNG."""
        if not self.data:
            return
        regions = self.data.region_names()
        if not regions:
            QtWidgets.QMessageBox.information(
                self, "Export", "The current profile has no regions to export.")
            return
        region_to_bcs = {r: self.data.region_in_matrix(r) for r in regions}
        default_dir = os.path.join(self.cfg.root, "outs") if self.cfg else ""
        if default_dir:
            os.makedirs(default_dir, exist_ok=True)
        safe = self.data.current_profile.replace(" ", "_")
        default_path = os.path.join(default_dir or "", f"{safe}_profile_map.pdf")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export profile map", default_path, "PDF (*.pdf);;PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith((".pdf", ".png")):
            path += ".pdf"
        out = self.spatial.export_profile_map(region_to_bcs, with_background, path)
        if out:
            self.statusBar().showMessage(
                f"Exported {len(regions)}-region map → {out}")
        else:
            QtWidgets.QMessageBox.warning(self, "Export", "Could not write the file.")

    def _reset_view(self) -> None:
        """Clear every selection (regions/groups/SNVs) → uniform pale-white tissue."""
        self.current_selection = []
        self.region_tree.clearSelection()
        self.region_tree.setCurrentItem(None)
        self._clear_snvs()
        self.spatial.reset_view()

    def _show_overview(self) -> None:
        """Overview button: colour the tissue by every region in the current profile
        (distinct colour each), dark grey where regions overlap."""
        if self.data is None:
            return
        region_to_bcs = {name: self.data.region_in_matrix(name)
                         for name in self.data.regions}
        region_to_bcs = {k: v for k, v in region_to_bcs.items() if v}
        if not region_to_bcs:
            self.statusBar().showMessage(
                "No tumor regions in this profile to overview")
            return
        n_multi = self.spatial.show_region_overview(region_to_bcs)
        msg = (f"Overview: {len(region_to_bcs)} region(s) in profile "
               f"'{self.data.current_profile}'")
        if n_multi:
            msg += f" — {n_multi} spot(s) in >1 region shown dark grey"
        self.statusBar().showMessage(msg)

    def _color_spots_by_snvs(self, snvs: List[str], title: str) -> None:
        """Highlight the spots carrying `snvs`, coloured by how many of those SNVs each
        spot covers, with a selection-specific legend (top-left)."""
        burden = self.data.per_spot_burden(snvs)
        self.spatial.highlight_by_burden(
            list(burden.index), burden.values, f"{title} — SNVs/spot")

    def _selected_region(self) -> Optional[str]:
        it = self.region_tree.currentItem()
        if not it:
            return None
        r = it.data(0, ROLE_REGION)
        if r:
            return r
        gk = it.data(0, ROLE_GROUP)
        return gk[0] if gk else None

    # ---- generate -------------------------------------------------------
    def _show_generate_menu(self) -> None:
        if not self.data:
            return
        region = self._selected_region()
        if not region:
            QtWidgets.QMessageBox.information(self, "Generate", "Select a tumor region first.")
            return
        menu = QtWidgets.QMenu(self)
        menu.addAction("Exclusive variants (only in this region)",
                       lambda: self._gen_exclusive(region))
        gmin = self.cfg.variant_grouping["general_min_fraction"]
        menu.addAction(f"General (> {gmin}% of all spots)",
                       lambda: self._gen_general(region))
        menu.addAction("Exclusive by threshold (max/min)…",
                       lambda: self._gen_exclusive_threshold(region))
        menu.exec(self.btn_generate.mapToGlobal(self.btn_generate.rect().bottomLeft()))

    def _gen_exclusive(self, region: str) -> None:
        snvs = self.data.generate_exclusive(region)
        self._add_group(region, "exclusive", GROUP_EXCLUSIVE, snvs)

    def _gen_general(self, region: str) -> None:
        gmin = self.cfg.variant_grouping["general_min_fraction"]
        snvs = self.data.generate_general(gmin)
        self._add_group(region, f"general_{gmin}", GROUP_GENERAL, snvs)

    def _gen_exclusive_threshold(self, region: str) -> None:
        gp = self.cfg.variant_grouping
        dlg = ThresholdDialog(self, gp["exclusive_inside_min"], gp["exclusive_outside_max"])
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        mx, mn = dlg.values()
        snvs = self.data.generate_exclusive_threshold(region, mx, mn)
        self._add_group(region, f"excl_{int(mx)}_{int(mn)}", GROUP_EXCLUSIVE_THRESHOLD, snvs)

    def _add_group(self, region: str, name: str, gtype: str, snvs: List[str]) -> None:
        if not snvs:
            QtWidgets.QMessageBox.information(
                self, "Generate", "No variants matched the criteria.")
            return
        g = self.data.add_variant_group(region, name, gtype, snvs)
        self._refresh_region_tree()
        self._show_snvs(g.snvs, f"{g.region} ▸ {g.name}",
                        {"regions": [g.region], "groups": [g.name]})
        self.spatial.clear_centers()
        self._color_spots_by_snvs(g.snvs, f"{g.region} ▸ {g.name}")
        self.statusBar().showMessage(f"Generated '{g.name}': {len(g.snvs)} SNVs")

    # ---- add region -----------------------------------------------------
    _add_mode = False
    _edit_mode = False

    def _set_region_buttons(self, normal: bool) -> None:
        self.region_bar.setVisible(normal)
        self.region_action_bar.setVisible(not normal)

    def _start_add_region(self) -> None:
        if not self.data:
            return
        self._add_mode = True
        self.current_selection = []
        self.spatial.set_hover_enabled(False)
        self.spatial.set_selection_mode(True)
        self.lbl_mode.setText("Lasso spots, then Finish")
        self.btn_finish.setVisible(True)
        self.btn_merge.setVisible(False)
        self.btn_delete.setVisible(False)
        self._set_region_buttons(False)

    def _finish_add_region(self) -> None:
        if not self.current_selection:
            QtWidgets.QMessageBox.information(self, "Add region", "No spots selected.")
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Name region", "Region name:")
        if not ok:
            return
        rn = self.data.add_region(name, self.current_selection)
        self._cancel_region_mode()
        self._refresh_region_tree()
        self.statusBar().showMessage(f"Added region '{rn}' ({len(self.current_selection)} spots)")

    def _on_spatial_selection(self, barcodes: List[str]) -> None:
        if self._auto_dialog is not None and self._auto_dialog.seed_mode():
            self._auto_dialog.on_seed_lasso(barcodes)
            return
        self.current_selection = barcodes
        self.statusBar().showMessage(f"Selected {len(barcodes)} spots")

    # ---- auto tumor regions --------------------------------------------
    def _open_auto_dialog(self) -> None:
        if not self.data:
            return
        if self._auto_dialog is not None:
            self._auto_dialog.raise_()
            self._auto_dialog.activateWindow()
            return
        self._auto_dialog = AutoTumorDialog(self)
        self._auto_dialog.show()

    def set_auto_active(self, active: bool) -> None:
        """Suppress hover-to-identify while the Auto-regions dialog drives the view."""
        self.spatial.set_hover_enabled(not active)

    # ---- edit / merge / delete -----------------------------------------
    def _start_edit_regions(self) -> None:
        if not self.data or not self.data.region_names():
            return
        self._edit_mode = True
        self.spatial.set_hover_enabled(False)
        # ExtendedSelection so Shift-click selects a contiguous range and
        # Ctrl/Cmd-click toggles individual items (MultiSelection only toggled
        # one item per click and gave no reliable Shift range-select).
        self.region_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.lbl_mode.setText("Pick regions or groups, then Merge/Delete")
        self.btn_finish.setVisible(False)
        self.btn_merge.setVisible(True)
        self.btn_delete.setVisible(True)
        self._set_region_buttons(False)

    def _selected_region_and_group_names(self):
        """Return (regions, groups) from the current tree selection.
        Groups whose parent region is *also* selected are filtered out to
        avoid double‑counting — deleting the region already deletes its groups."""
        regions: List[str] = []
        groups: List[tuple] = []        # (region_name, group_name)
        selected_regions: set = set()
        for it in self.region_tree.selectedItems():
            r = it.data(0, ROLE_REGION)
            g = it.data(0, ROLE_GROUP)
            if r and r not in regions:
                regions.append(r)
                selected_regions.add(r)
            elif g:
                if g[0] not in selected_regions and g not in groups:
                    groups.append(g)
        return regions, groups

    def _merge_regions(self) -> None:
        names, _ = self._selected_region_and_group_names()
        if len(names) < 2:
            QtWidgets.QMessageBox.information(self, "Merge", "Select at least two regions.")
            return
        new, ok = QtWidgets.QInputDialog.getText(
            self, "Merge regions", "Name for merged region:", text="_".join(names))
        if not ok:
            return
        rn = self.data.merge_regions(names, new)
        self._cancel_region_mode()
        self._refresh_region_tree()
        self.statusBar().showMessage(f"Merged {len(names)} regions into '{rn}'")

    def _delete_regions(self) -> None:
        regions, groups = self._selected_region_and_group_names()
        if not regions and not groups:
            QtWidgets.QMessageBox.information(
                self, "Delete", "No regions or groups selected.")
            return

        # Build a human-readable list of everything that will be deleted.
        affected: List[str] = []
        for r in regions:
            children = self.data.groups_for_region(r)
            if children:
                child_names = ", ".join(c.name for c in children)
                affected.append(f"Region '{r}' and its {len(children)} group(s): {child_names}")
            else:
                affected.append(f"Region '{r}' (no groups)")
        for rn, gn in groups:
            affected.append(f"Group '{gn}' from region '{rn}'")

        msg = "Delete the following?\n\n" + "\n".join(f"  • {a}" for a in affected)
        if QtWidgets.QMessageBox.question(
                self, "Delete", msg) != QtWidgets.QMessageBox.Yes:
            return

        if regions:
            self.data.delete_regions(regions)
        if groups:
            self.data.delete_variant_groups(groups)

        self._cancel_region_mode()
        self._refresh_region_tree()

    def _cancel_region_mode(self) -> None:
        self._add_mode = False
        self._edit_mode = False
        self.spatial.set_selection_mode(False)
        self.spatial.set_hover_enabled(True)
        self.current_selection = []
        self.region_tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._set_region_buttons(True)

    # ============================================================ SNV column
    def _show_snvs(self, snvs: List[str], title: str,
                    source: Optional[dict] = None) -> None:
        self.current_snvs = list(snvs)
        self.current_snv_source = source or {"regions": [], "groups": []}
        self.snv_title.setText(f"<b>SNVs</b> — {title} ({len(snvs)})")
        self.snv_list.clear()
        self.snv_list.addItems(snvs)

    def _clear_snvs(self) -> None:
        self.current_snvs = []
        self.current_snv_source = {"regions": [], "groups": []}
        self.snv_list.clear()
        self.snv_title.setText("<b>SNVs</b>")

    def _selected_or_all_snvs(self) -> List[str]:
        items = self.snv_list.selectedItems()
        if items:
            return [it.text() for it in items]
        return list(self.current_snvs)

    def _select_all_snvs(self) -> None:
        """Select every SNV in the list."""
        self.snv_list.selectAll()
        self.statusBar().showMessage(f"Selected {self.snv_list.count()} SNVs")

    def _export_snvs(self) -> None:
        snvs = self._selected_or_all_snvs()
        if not snvs:
            QtWidgets.QMessageBox.information(self, "Export", "No SNVs to export.")
            return
        # Default to <config_root>/outs/snvs.json
        default_dir = os.path.join(self.cfg.root, "outs") if self.cfg else ""
        default_path = os.path.join(default_dir, "snvs.json") if default_dir else "snvs.json"
        os.makedirs(default_dir, exist_ok=True) if default_dir else None
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export SNVs", default_path, "JSON (*.json)")
        if not path:
            return
        StudyData.export_snvs(snvs, path, self.current_snv_source)
        self.statusBar().showMessage(f"Exported {len(snvs)} SNVs → {path}")

    def _import_snvs(self) -> None:
        """Read an exported SNV JSON file and navigate to its source group.
        If the region or group no longer exists they are re-created from the
        variant list."""
        if not self.data:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import SNVs", "", "JSON (*.json)")
        if not path:
            return
        try:
            doc = StudyData.import_snvs(path)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            QtWidgets.QMessageBox.critical(
                self, "Import failed", f"Could not read file:\n{exc}")
            return

        source = doc.get("source", {})
        src_regions = source.get("regions", [])
        src_groups = source.get("groups", [])
        variants = doc.get("variants", [])

        if not variants:
            QtWidgets.QMessageBox.information(
                self, "Import", "The file contains no variants.")
            return

        # Try to find a matching (region, group) pair that still exists.
        matched_region: Optional[str] = None
        matched_group: Optional[str] = None
        for rn in src_regions:
            for gn in src_groups:
                if (rn, gn) in self.data.variant_groups:
                    matched_region, matched_group = rn, gn
                    break
            if matched_region:
                break

        if matched_region and matched_group:
            # Navigate to the existing group.
            g = self.data.variant_groups[(matched_region, matched_group)]
            self._show_snvs(g.snvs, f"{g.region} ▸ {g.name}",
                            {"regions": [g.region], "groups": [g.name]})
            self.spatial.clear_centers()
            self._color_spots_by_snvs(g.snvs, f"{g.region} ▸ {g.name}")
            self._select_tree_group(matched_region, matched_group)
            self.statusBar().showMessage(
                f"Imported '{matched_group}' from region '{matched_region}' "
                f"({len(variants)} variants)")
            return

        # -- Region / group does not exist → re-create from variants ---------
        spots = self.data.spots_with_snvs(variants)
        if not spots:
            QtWidgets.QMessageBox.information(
                self, "Import",
                "None of the variants in this file are present in the current matrix.")
            return

        created_regions = 0
        created_groups = 0
        target_region: Optional[str] = None
        target_group: Optional[str] = None

        for rn in src_regions:
            if rn not in self.data.regions:
                self.data.add_region(rn, spots)
                created_regions += 1
            else:
                # Existing region — merge the imported spots into it.
                existing = set(self.data.region_in_matrix(rn))
                merged = list(dict.fromkeys(self.data.regions[rn] + spots))
                self.data.regions[rn] = merged
                self.data.save_regions()
            target_region = rn

            for gn in src_groups:
                if (rn, gn) not in self.data.variant_groups:
                    self.data.add_variant_group(rn, gn, GROUP_SELECTION, variants)
                    created_groups += 1
                target_group = gn

        self._refresh_region_tree()

        if target_region and target_group:
            g = self.data.variant_groups.get((target_region, target_group))
            if g:
                self._show_snvs(g.snvs, f"{g.region} ▸ {g.name}",
                                {"regions": [g.region], "groups": [g.name]})
                self.spatial.clear_centers()
                self._color_spots_by_snvs(g.snvs, f"{g.region} ▸ {g.name}")
                self._select_tree_group(target_region, target_group)

        parts = []
        if created_regions:
            parts.append(f"{created_regions} region(s)")
        if created_groups:
            parts.append(f"{created_groups} group(s)")
        self.statusBar().showMessage(
            f"Imported: created {', '.join(parts)} from {len(variants)} variants")

    def _select_tree_group(self, region: str, group_name: str) -> None:
        """Expand the given region and select its group child item in the tree."""
        for i in range(self.region_tree.topLevelItemCount()):
            top = self.region_tree.topLevelItem(i)
            if top.data(0, ROLE_REGION) == region:
                top.setExpanded(True)
                for j in range(top.childCount()):
                    child = top.child(j)
                    gk = child.data(0, ROLE_GROUP)
                    if gk and gk == (region, group_name):
                        self.region_tree.setCurrentItem(child)
                        return

    def _show_snv_spots(self) -> None:
        snvs = self._selected_or_all_snvs()
        spots = self.data.spots_with_snvs(snvs)
        self.spatial.clear_centers()
        n_sel = len(self.snv_list.selectedItems())
        title = (f"{n_sel} selected SNVs" if n_sel
                 else f"{len(snvs)} SNVs")
        self._color_spots_by_snvs(snvs, title)
        self.current_selection = spots
        self.statusBar().showMessage(f"{len(spots)} spots carry the {len(snvs)} selected SNV(s)")

    def _add_spots_from_snvs(self) -> None:
        snvs = self._selected_or_all_snvs()
        spots = self.data.spots_with_snvs(snvs)
        if not spots:
            QtWidgets.QMessageBox.information(self, "Add spots", "No spots carry these SNVs.")
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Name region", "Region name:")
        if not ok:
            return
        rn = self.data.add_region(name, spots)
        self._refresh_region_tree()
        self.statusBar().showMessage(f"Added region '{rn}' from {len(spots)} spots")


class CompareResultDialog(QtWidgets.QDialog):
    """Show the result of StudyData.compare_profiles: cluster-agreement scores
    plus a per-region best-match Jaccard overlap table."""

    def __init__(self, parent, result: dict):
        super().__init__(parent)
        a, b = result["profiles"]
        self.setWindowTitle(f"Compare profiles: {a} vs {b}")
        self.resize(580, 480)
        v = QtWidgets.QVBoxLayout(self)
        s = result["scores"]
        head = QtWidgets.QLabel(
            f'<b>{a}</b> vs <b>{b}</b> — {result["n_items"]} in-tissue spots '
            f'(unassigned → background)')
        head.setTextFormat(QtCore.Qt.RichText)
        v.addWidget(head)
        scores = QtWidgets.QLabel(
            f"ARI <b>{s['ari']:.3f}</b> &nbsp; NMI <b>{s['nmi']:.3f}</b><br>"
            f"homogeneity <b>{s['homogeneity']:.3f}</b> "
            f"— does a '{b}' region mix several '{a}' regions?<br>"
            f"completeness <b>{s['completeness']:.3f}</b> "
            f"— was an '{a}' region split across '{b}'?<br>"
            f"V-measure <b>{s['v_measure']:.3f}</b>")
        scores.setTextFormat(QtCore.Qt.RichText)
        v.addWidget(scores)
        v.addWidget(QtWidgets.QLabel(
            f"<b>Region overlap</b> — each '{a}' region → best '{b}' match:"))
        ov = result["overlap"]
        tbl = QtWidgets.QTableWidget(len(ov), 4)
        tbl.setHorizontalHeaderLabels([f"{a} region", "spots", f"best {b}", "Jaccard"])
        for r, o in enumerate(ov):
            best = o["best"] or "—"
            if o["also"]:
                best += f"  (+{len(o['also'])} more)"
            for c, val in enumerate((str(o["region"]), str(o["size"]), best,
                                     f"{o['best_jaccard']:.2f}")):
                tbl.setItem(r, c, QtWidgets.QTableWidgetItem(val))
        tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tbl.resizeColumnsToContents()
        v.addWidget(tbl, 1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)


class ThresholdDialog(QtWidgets.QDialog):
    """max (inside %) / min (outside %) for exclusive-by-threshold."""

    def __init__(self, parent, default_max, default_min):
        super().__init__(parent)
        self.setWindowTitle("Exclusive by threshold")
        form = QtWidgets.QFormLayout(self)
        self.sp_max = QtWidgets.QSpinBox()
        self.sp_max.setRange(0, 100)
        self.sp_max.setValue(int(default_max))
        self.sp_min = QtWidgets.QSpinBox()
        self.sp_min.setRange(0, 100)
        self.sp_min.setValue(int(default_min))
        form.addRow("max — present in > this % INSIDE region", self.sp_max)
        form.addRow("min — present in < this % OUTSIDE region", self.sp_min)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        return float(self.sp_max.value()), float(self.sp_min.value())


class AutoTumorDialog(QtWidgets.QDialog):
    """Non-modal panel: auto-detect contiguous tumor regions by SNV-burden intensity.

    Two methods (top selector):
      raw_burden  tumor EXTENT from un-normalized SNV burden (≈ cellularity; the
                  best-scoring extent detector on the DCIS ground truth).
      customized  the fully tunable detector, incl. optional coverage (UMI)
                  normalization — the prior default behaviour.

    Higher intensity keeps fewer/smaller regions. The user can lasso spots on the
    tissue to force-add or exclude seeds, then create the regions."""

    def __init__(self, main: "MainWindow"):
        super().__init__(main)
        self.main = main
        self.data = main.data
        self.spatial = main.spatial
        self.setWindowTitle("Auto tumor regions")
        self.setModal(False)
        # always float above the main window so the preview stays visible
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        # clear the tissue so the colored region preview reads clearly on a blank view
        main.set_auto_active(True)
        main._reset_view()
        self._seed_mode = None              # None | "add" | "exclude"
        self.extra_seeds: List[str] = []
        self.excluded_seeds: List[str] = []
        self._last = {"regions": [], "seeds": []}

        form = QtWidgets.QFormLayout(self)

        # Detection method. raw_burden = tumor EXTENT from un-normalized SNV burden
        # (best extent detector on the DCIS GT); customized = the fully tunable
        # detector incl. the optional coverage normalization (prior default).
        self.cb_method = QtWidgets.QComboBox()
        self.cb_method.addItems(["raw_burden", "customized"])
        self.cb_method.setToolTip(
            "raw_burden: tumor extent from raw (un-normalized) SNV burden — best "
            "for delineating the tumor mass.\n"
            "customized: fully tunable; enables 'Normalize by coverage (UMI)'.")
        form.addRow("Method", self.cb_method)

        # every knob is a slider + spin box (drag, step, or type a number)
        self.sl, self.sp_intensity, int_row = self._slider_spin(50, 99, 90)
        form.addRow("Intensity (higher = fewer spots)", int_row)

        sl_margin, self.sp_margin, margin_row = self._slider_spin(0, 50, 10)
        form.addRow("Grow margin (percentile below seed)", margin_row)

        sl_minsize, self.sp_minsize, minsize_row = self._slider_spin(1, 200, 5)
        form.addRow("Min region size (spots)", minsize_row)

        # how deep the valley between two centers must be before they stay separate
        sl_split, self.sp_split, split_row = self._slider_spin(0, 100, 40, suffix=" %")
        split_tip = (
            "When growing from two centers meets, keep them as SEPARATE regions only "
            "if the valley between them drops by at least this % of the peak height.\n"
            "Lower = split more eagerly; 100% = always merge touching regions.")
        self.sp_split.setToolTip(split_tip)
        sl_split.setToolTip(split_tip)
        form.addRow("Split valley depth", split_row)

        self.cb_norm = QtWidgets.QCheckBox("Normalize by coverage (UMI)")
        has_cov = self.data is not None and self.data.coverage is not None
        self.cb_norm.setChecked(has_cov)
        self.cb_norm.setEnabled(has_cov)
        if not has_cov:
            self.cb_norm.setToolTip("No spot_coverage.csv found for this study; "
                                    "using raw SNV burden.")
        form.addRow(self.cb_norm)

        # manual seed override
        self.btn_add_seed = QtWidgets.QPushButton("Add seeds (lasso)")
        self.btn_excl_seed = QtWidgets.QPushButton("Exclude (lasso)")
        self.btn_add_seed.setCheckable(True)
        self.btn_excl_seed.setCheckable(True)
        self.btn_clear_seed = QtWidgets.QPushButton("Clear manual")
        self.btn_add_seed.clicked.connect(lambda: self._toggle_seed_mode("add"))
        self.btn_excl_seed.clicked.connect(lambda: self._toggle_seed_mode("exclude"))
        self.btn_clear_seed.clicked.connect(self._clear_manual)
        srow = QtWidgets.QHBoxLayout()
        for b in (self.btn_add_seed, self.btn_excl_seed, self.btn_clear_seed):
            srow.addWidget(b)
        form.addRow("Manual seeds", self._wrap(srow))
        self.lbl_manual = QtWidgets.QLabel("manual: +0 / −0")
        form.addRow("", self.lbl_manual)

        self.lbl_preview = QtWidgets.QLabel("—")
        self.lbl_preview.setStyleSheet("font-weight: bold;")
        form.addRow("Preview", self.lbl_preview)

        bb = QtWidgets.QDialogButtonBox()
        self.btn_create = bb.addButton("Create regions",
                                       QtWidgets.QDialogButtonBox.AcceptRole)
        bb.addButton(QtWidgets.QDialogButtonBox.Close)
        self.btn_create.clicked.connect(self._create)
        bb.rejected.connect(self.close)
        form.addRow(bb)

        # the four slider/spin pairs already call _recompute via _slider_spin
        self.cb_norm.toggled.connect(lambda _: self._recompute())
        self.cb_method.currentTextChanged.connect(
            lambda _: (self._on_method_changed(), self._recompute()))
        self._on_method_changed()      # apply the default method's coverage setting
        self._recompute()

    @staticmethod
    def _wrap(layout) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _slider_spin(self, lo: int, hi: int, val: int, suffix: str = ""):
        """A horizontal slider paired with a spin box (drag, step with the
        up/down arrows, or type a number). The two stay in sync and each fires
        `_recompute`. Returns (slider, spinbox, container_widget)."""
        sl = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        sl.setRange(lo, hi)
        sp = QtWidgets.QSpinBox()
        sp.setRange(lo, hi)
        if suffix:
            sp.setSuffix(suffix)
        sl.setValue(val)
        sp.setValue(val)
        sl.valueChanged.connect(sp.setValue)   # slider drag → spin box
        sp.valueChanged.connect(sl.setValue)   # typed/stepped value → slider
        sp.valueChanged.connect(lambda _: self._recompute())
        row = QtWidgets.QHBoxLayout()
        row.addWidget(sl, 1)
        row.addWidget(sp)
        return sl, sp, self._wrap(row)

    # -- recompute -------------------------------------------------------
    def _recompute(self) -> None:
        if not self.data:
            return
        seed_pct = float(self.sl.value())
        grow_pct = max(0.0, seed_pct - float(self.sp_margin.value()))
        res = self.data.auto_tumor_regions(
            seed_pct=seed_pct, grow_pct=grow_pct,
            min_size=int(self.sp_minsize.value()),
            normalize=self.cb_norm.isChecked(),
            split_depth=float(self.sp_split.value()) / 100.0,
            extra_seeds=self.extra_seeds, excluded_seeds=self.excluded_seeds)
        self._last = res
        n_spots = sum(len(r) for r in res["regions"])
        self.lbl_preview.setText(f"{len(res['regions'])} regions · {n_spots} spots")
        self.spatial.preview_regions(res["regions"], res["seeds"])

    def _on_method_changed(self) -> None:
        """raw_burden forces un-normalized burden and disables the coverage
        checkbox; customized restores the tunable coverage-normalize option."""
        raw = self.cb_method.currentText() == "raw_burden"
        has_cov = self.data is not None and self.data.coverage is not None
        self.cb_norm.blockSignals(True)
        if raw:
            self.cb_norm.setChecked(False)
            self.cb_norm.setEnabled(False)
        else:
            self.cb_norm.setEnabled(has_cov)
            self.cb_norm.setChecked(has_cov)
        self.cb_norm.blockSignals(False)

    # -- manual seed editing ---------------------------------------------
    def seed_mode(self) -> bool:
        return self._seed_mode is not None

    def _toggle_seed_mode(self, mode: str) -> None:
        btn = self.btn_add_seed if mode == "add" else self.btn_excl_seed
        other = self.btn_excl_seed if mode == "add" else self.btn_add_seed
        if btn.isChecked():
            other.setChecked(False)
            self._seed_mode = mode
            self.spatial.set_selection_mode(True)
        else:
            self._seed_mode = None
            self.spatial.set_selection_mode(False)

    def on_seed_lasso(self, barcodes: List[str]) -> None:
        if self._seed_mode == "add":
            for b in barcodes:
                if b not in self.extra_seeds:
                    self.extra_seeds.append(b)
                if b in self.excluded_seeds:
                    self.excluded_seeds.remove(b)
        elif self._seed_mode == "exclude":
            for b in barcodes:
                if b not in self.excluded_seeds:
                    self.excluded_seeds.append(b)
                if b in self.extra_seeds:
                    self.extra_seeds.remove(b)
        self.lbl_manual.setText(
            f"manual: +{len(self.extra_seeds)} / −{len(self.excluded_seeds)}")
        self._recompute()

    def _clear_manual(self) -> None:
        self.extra_seeds = []
        self.excluded_seeds = []
        self.lbl_manual.setText("manual: +0 / −0")
        self._recompute()

    # -- create / teardown -----------------------------------------------
    def _create(self) -> None:
        regions = self._last.get("regions", [])
        if not regions:
            QtWidgets.QMessageBox.information(self, "Auto", "No regions to create.")
            return
        base, ok = QtWidgets.QInputDialog.getText(
            self, "Name regions", "Name prefix:", text="auto")
        if not ok:
            return
        centers = self._last.get("centers", [])
        created = [
            self.data.add_region(
                f"{base}_{i + 1}", r,
                center=centers[i] if i < len(centers) and centers[i] else None)
            for i, r in enumerate(regions)]
        self.main._refresh_region_tree()
        self.main.statusBar().showMessage(
            f"Created {len(created)} auto region(s): {', '.join(created)}")
        self.close()

    def closeEvent(self, ev) -> None:
        self.spatial.set_selection_mode(False)
        self.spatial.clear_preview()
        self.main.set_auto_active(False)
        self.main._auto_dialog = None
        super().closeEvent(ev)
