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
        m = self.menuBar().addMenu("&File")
        act_open = m.addAction("Open config…")
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(self._open_dialog)
        m.addSeparator()
        m.addAction("Quit", self.close)

    # ---- column 1 -------------------------------------------------------
    def _build_spatial_pane(self) -> QtWidgets.QWidget:
        self.spatial = SpatialView()
        self.spatial.selectionChanged.connect(self._on_spatial_selection)

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
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.addWidget(QtWidgets.QLabel("<b>Tumor regions</b>"))

        # normal toolbar: Add / Edit / Generate
        self.region_bar = QtWidgets.QWidget()
        hb = QtWidgets.QHBoxLayout(self.region_bar)
        hb.setContentsMargins(0, 0, 0, 0)
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_generate = QtWidgets.QPushButton("Generate ▾")
        self.btn_add.clicked.connect(self._start_add_region)
        self.btn_edit.clicked.connect(self._start_edit_regions)
        self.btn_generate.clicked.connect(self._show_generate_menu)
        for b in (self.btn_add, self.btn_edit, self.btn_generate):
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
        self._refresh_region_tree()
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

    # ============================================================ region tree
    def _refresh_region_tree(self) -> None:
        self.region_tree.clear()
        if not self.data:
            return
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
                self.spatial.highlight(self.data.spots_with_snvs(g.snvs), g.color())
            return
        region = item.data(0, ROLE_REGION)
        if region:
            self.spatial.clear_highlight()
            self.spatial.highlight(self.data.region_in_matrix(region), "#f1c40f")

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
        self.spatial.highlight(self.data.spots_with_snvs(g.snvs), g.color())
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
        self.current_selection = barcodes
        self.statusBar().showMessage(f"Selected {len(barcodes)} spots")

    # ---- edit / merge / delete -----------------------------------------
    def _start_edit_regions(self) -> None:
        if not self.data or not self.data.region_names():
            return
        self._edit_mode = True
        self.region_tree.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
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
            self.spatial.highlight(self.data.spots_with_snvs(g.snvs), g.color())
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
                self.spatial.highlight(self.data.spots_with_snvs(g.snvs), g.color())
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
        self.spatial.highlight(spots, "#2980b9")
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
