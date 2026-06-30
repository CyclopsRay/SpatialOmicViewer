"""Spatial view: background image + spots, with lasso selection and highlight."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PIL import Image

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)

BASE_BRUSH = pg.mkBrush(180, 180, 180, 140)
PALE_BRUSH = pg.mkBrush(245, 245, 245, 150)     # uniform near-white (Reset / clean view)
BASE_PEN = pg.mkPen(90, 90, 90, 120)
HILITE_BRUSH = pg.mkBrush(231, 76, 60, 220)     # red
HILITE_PEN = pg.mkPen(150, 20, 20, 255)
SELECT_BRUSH = pg.mkBrush(241, 196, 15, 230)    # yellow (active lasso selection)
SELECT_PEN = pg.mkPen(120, 90, 0, 255)

# Burden colour ramp: sky blue (low SNV count) -> purple (high).
BURDEN_CMAP = pg.ColorMap([0.0, 0.5, 1.0],
                          [(135, 206, 235), (120, 110, 200), (142, 68, 173)])


class TitledGradientLegend(pg.GradientLegend):
    """A GradientLegend that also draws a one-line title above the colour bar."""

    def __init__(self, size, offset, title: str = ""):
        super().__init__(size, offset)
        self._title = title

    def setTitle(self, title: str) -> None:
        self._title = title
        self.update()

    def paint(self, p, opt, widget):
        super().paint(p, opt, widget)
        if not self._title or not hasattr(self, "b"):
            return
        view = self.getViewBox()
        if view is None:
            return
        p.save()
        p.setTransform(view.sceneTransform())
        p.setPen(self.textPen)
        x1, x2, x3, y1, y2, _ = self.b
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRectF(x1 - 2, y1 - 20, max(x3 - x1 + 120, 140), 16),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self._title)
        p.restore()


class LassoViewBox(pg.ViewBox):
    """ViewBox that, in lasso mode, captures a freehand polygon on left-drag."""

    sigLassoFinished = QtCore.Signal(object)  # emits list[QPointF] (data coords)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lasso_enabled = False
        self._pts: List[QtCore.QPointF] = []
        self._curve = pg.PlotCurveItem(pen=pg.mkPen(241, 196, 15, 230, width=2))
        self._curve.setZValue(50)
        self.addItem(self._curve)

    def set_lasso(self, enabled: bool) -> None:
        self.lasso_enabled = enabled
        self.setMouseEnabled(not enabled, not enabled)
        if not enabled:
            self._pts = []
            self._curve.setData([], [])

    def mouseDragEvent(self, ev, axis=None):
        if not self.lasso_enabled or ev.button() != QtCore.Qt.LeftButton:
            return super().mouseDragEvent(ev, axis)
        ev.accept()
        p = self.mapSceneToView(ev.scenePos())
        if ev.isStart():
            self._pts = [p]
        else:
            self._pts.append(p)
        xs = [pt.x() for pt in self._pts]
        ys = [pt.y() for pt in self._pts]
        self._curve.setData(xs, ys)
        if ev.isFinish():
            pts = list(self._pts)
            self._pts = []
            self._curve.setData([], [])
            if len(pts) >= 3:
                self.sigLassoFinished.emit(pts)


class SpatialView(QtWidgets.QWidget):
    """Left column: tissue image + spots. Emits selectionChanged on lasso."""

    selectionChanged = QtCore.Signal(list)  # list[str] barcodes
    hoveredRegion = QtCore.Signal(object)   # region name (str) or None — change-only

    def __init__(self, parent=None):
        super().__init__(parent)
        self._barcodes: List[str] = []
        self._xy = np.zeros((0, 2))
        self._img_item: Optional[pg.ImageItem] = None
        self._burden: Optional[np.ndarray] = None   # per-plotted-spot SNV count
        self._color_mode = False
        self._legend: Optional[pg.GradientLegend] = None
        self._sel_legend: Optional[TitledGradientLegend] = None  # per-selection legend
        # hover-to-identify state
        self._barcode_region: dict = {}     # barcode -> region name (current profile)
        self._hover_enabled = True
        self._hover_region: Optional[str] = None   # last emitted region (change detection)
        self._hit_radius = 8.0              # cursor->spot snap radius (set in set_data)

        self.glw = pg.GraphicsLayoutWidget()
        self.vb = LassoViewBox(lockAspect=True, invertY=True, enableMenu=False)
        self.glw.addItem(self.vb)
        self.vb.sigLassoFinished.connect(self._on_lasso)
        self.glw.scene().sigMouseMoved.connect(self._on_mouse_moved)

        self._spots = pg.ScatterPlotItem(pxMode=False, brush=BASE_BRUSH, pen=BASE_PEN)
        self._spots.setZValue(10)
        self._hilite = pg.ScatterPlotItem(pxMode=False, brush=HILITE_BRUSH, pen=HILITE_PEN)
        self._hilite.setZValue(20)
        self._preview = pg.ScatterPlotItem(pxMode=False, pen=None)   # auto-region preview
        self._preview.setZValue(18)
        self._seeds = pg.ScatterPlotItem(pxMode=False, brush=pg.mkBrush(20, 20, 20, 0),
                                         pen=pg.mkPen(0, 0, 0, 255, width=2))  # seed rings
        self._seeds.setZValue(22)
        # saved region centers: a star marker drawn when a region with a center is picked
        self._centers = pg.ScatterPlotItem(pxMode=False, symbol="star",
                                           brush=pg.mkBrush(255, 255, 0, 255),
                                           pen=pg.mkPen(0, 0, 0, 255, width=1.5))
        self._centers.setZValue(30)
        # floating label that names the region under the cursor (hover-to-identify)
        self._hover_label = pg.TextItem(color=(20, 20, 20), anchor=(0, 0.5),
                                        fill=pg.mkBrush(255, 255, 255, 220))
        self._hover_label.setZValue(60)
        self._hover_label.setVisible(False)
        self.vb.addItem(self._spots)
        self.vb.addItem(self._preview)
        self.vb.addItem(self._hilite)
        self.vb.addItem(self._seeds)
        self.vb.addItem(self._centers)
        self.vb.addItem(self._hover_label)

        # tiny background toggle, top-right overlay
        self.bg_toggle = QtWidgets.QCheckBox("background", self)
        self.bg_toggle.setChecked(True)
        self.bg_toggle.setStyleSheet(
            "QCheckBox{background:rgba(255,255,255,180);padding:2px 4px;"
            "border-radius:3px;font-size:10px;}")
        self.bg_toggle.toggled.connect(self._on_bg_toggle)

        # toggle: colour spots by SNV count (top-right, under the bg toggle)
        self.color_toggle = QtWidgets.QCheckBox("color by SNV count", self)
        self.color_toggle.setChecked(False)
        self.color_toggle.setStyleSheet(
            "QCheckBox{background:rgba(255,255,255,180);padding:2px 4px;"
            "border-radius:3px;font-size:10px;}")
        self.color_toggle.toggled.connect(self.set_color_mode)

        # Reset button, top-left overlay: clears everything to a pale-white tissue.
        self.btn_reset = QtWidgets.QPushButton("Reset", self)
        self.btn_reset.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,200);padding:2px 8px;"
            "border:1px solid #aaa;border-radius:3px;font-size:10px;}")
        self.btn_reset.clicked.connect(self.reset_view)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.glw)

    # ------------------------------------------------------------------ data
    def set_data(self, image_path: str, barcodes: List[str], xy: np.ndarray,
                 spot_diameter: float) -> None:
        self._barcodes = list(barcodes)
        self._xy = np.asarray(xy, dtype=float)
        size = spot_diameter if spot_diameter and spot_diameter > 0 else 8.0
        self._hit_radius = self._compute_hit_radius(size)

        if self._img_item is not None:
            self.vb.removeItem(self._img_item)
            self._img_item = None
        try:
            arr = np.asarray(Image.open(image_path).convert("RGB"))
            self._img_item = pg.ImageItem(arr)
            self._img_item.setZValue(0)
            self.vb.addItem(self._img_item)
            self._img_item.setVisible(self.bg_toggle.isChecked())
        except Exception as exc:  # noqa: BLE001
            print(f"[spatial_view] could not load image {image_path}: {exc}")

        spots = [{"pos": (self._xy[i, 0], self._xy[i, 1]), "size": size,
                  "data": self._barcodes[i]} for i in range(len(self._barcodes))]
        self._spots.setData(spots)
        self._hilite.setData([])
        self.clear_centers()
        self._remove_sel_legend()
        self._hide_hover_label()
        self._hover_region = None
        self._burden = None
        self._apply_color_mode()
        self.vb.autoRange()

    # ------------------------------------------------------- burden colouring
    def set_burden(self, barcodes: List[str], counts) -> None:
        """Provide the per-spot SNV count used by the 'color by SNV count' mode."""
        lut = {b: float(c) for b, c in zip(barcodes, counts)}
        self._burden = np.array([lut.get(b, 0.0) for b in self._barcodes], dtype=float)
        if self._color_mode:
            self._apply_color_mode()

    def set_color_mode(self, on: bool) -> None:
        self._color_mode = bool(on)
        if self.color_toggle.isChecked() != self._color_mode:
            self.color_toggle.setChecked(self._color_mode)
        self._apply_color_mode()

    def _apply_color_mode(self) -> None:
        """Recolour base spots by SNV-count rank and show/hide the legend."""
        self._remove_legend()
        if (not self._color_mode or self._burden is None
                or len(self._burden) != len(self._barcodes) or len(self._barcodes) == 0):
            self._spots.setBrush(BASE_BRUSH)
            return
        b = self._burden
        # quantile-rank in [0,1] so the ramp spreads across the (skewed) population
        order = b.argsort()
        rank = np.empty_like(b)
        rank[order] = np.linspace(0.0, 1.0, len(b)) if len(b) > 1 else 0.0
        colors = BURDEN_CMAP.map(rank, mode="qcolor")
        self._spots.setBrush([pg.mkBrush(c) for c in colors])
        self._add_legend(b)

    def _add_legend(self, b: np.ndarray) -> None:
        legend = pg.GradientLegend(size=(18, 150), offset=(12, 36))
        grad = QtGui.QLinearGradient(0, 0, 0, 1)
        for stop in np.linspace(0, 1, 11):
            grad.setColorAt(float(stop), BURDEN_CMAP.map(float(stop), mode="qcolor"))
        legend.setGradient(grad)
        # label ticks with the actual SNV count at each quantile of the ramp
        labels = {}
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            labels[str(int(round(np.quantile(b, f))))] = f
        legend.setLabels(labels)
        legend.setParentItem(self.vb)
        self._legend = legend

    def _remove_legend(self) -> None:
        if self._legend is not None:
            try:
                self._legend.setParentItem(None)
                self.vb.scene().removeItem(self._legend)
            except Exception:  # noqa: BLE001
                pass
            self._legend = None

    def _idx_size(self) -> float:
        if self._spots.data is None or len(self._spots.data) == 0:
            return 8.0
        return float(self._spots.data["size"][0])

    # ------------------------------------------------------------ highlight
    def highlight(self, barcodes: List[str], color: str = None) -> None:
        self._remove_sel_legend()
        bset = set(barcodes)
        size = self._idx_size() * 1.05
        pts = [{"pos": (self._xy[i, 0], self._xy[i, 1]), "size": size}
               for i, bc in enumerate(self._barcodes) if bc in bset]
        if color:
            self._hilite.setBrush(pg.mkBrush(color))
        else:
            self._hilite.setBrush(HILITE_BRUSH)
        self._hilite.setData(pts)

    def clear_highlight(self) -> None:
        self._hilite.setData([])

    # ----------------------------------------- selection-burden colouring
    def highlight_by_burden(self, barcodes: List[str], counts, title: str = "") -> None:
        """Highlight `barcodes`, colouring each spot by `counts` (e.g. the number of
        currently-selected SNVs it carries) along the burden ramp, and show a legend
        (top-left) keyed to *this* selection's count range.

        Only spots with count > 0 are drawn."""
        lut = {b: float(c) for b, c in zip(barcodes, counts)}
        size = self._idx_size() * 1.05
        idxs, vals = [], []
        for i, bc in enumerate(self._barcodes):
            c = lut.get(bc, 0.0)
            if c > 0:
                idxs.append(i)
                vals.append(c)
        if not idxs:
            self._hilite.setData([])
            self._remove_sel_legend()
            return
        v = np.asarray(vals, dtype=float)
        vmax = v.max()
        norm = (v - 1.0) / (vmax - 1.0) if vmax > 1 else np.zeros_like(v)
        colors = BURDEN_CMAP.map(norm, mode="qcolor")
        spots = [{"pos": (self._xy[i, 0], self._xy[i, 1]), "size": size,
                  "brush": pg.mkBrush(colors[k])} for k, i in enumerate(idxs)]
        self._hilite.setPen(HILITE_PEN)
        self._hilite.setData(spots)
        self._add_sel_legend(v, title)

    def _add_sel_legend(self, v: np.ndarray, title: str) -> None:
        self._remove_sel_legend()
        legend = TitledGradientLegend(size=(18, 150), offset=(12, 60), title=title)
        grad = QtGui.QLinearGradient(0, 0, 0, 1)
        for stop in np.linspace(0, 1, 11):
            grad.setColorAt(float(stop), BURDEN_CMAP.map(float(stop), mode="qcolor"))
        legend.setGradient(grad)
        vmax = float(v.max())
        vmin = 1.0
        labels = {}
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            labels[str(int(round(vmin + f * (vmax - vmin))))] = f
        legend.setLabels(labels)
        legend.setParentItem(self.vb)
        self._sel_legend = legend

    def _remove_sel_legend(self) -> None:
        if self._sel_legend is not None:
            try:
                self._sel_legend.setParentItem(None)
                self.vb.scene().removeItem(self._sel_legend)
            except Exception:  # noqa: BLE001
                pass
            self._sel_legend = None

    def clear_selection_legend(self) -> None:
        self._remove_sel_legend()

    # ------------------------------------------------ saved region centers
    def mark_centers(self, barcodes: List[str]) -> None:
        bset = set(barcodes)
        size = self._idx_size() * 1.4
        pts = [{"pos": (self._xy[i, 0], self._xy[i, 1]), "size": size}
               for i, bc in enumerate(self._barcodes) if bc in bset]
        self._centers.setData(pts)

    def clear_centers(self) -> None:
        self._centers.setData([])

    # ------------------------------------------------ auto-region preview
    PREVIEW_PALETTE = [(230, 126, 34), (41, 128, 185), (39, 174, 96),
                       (142, 68, 173), (192, 57, 43), (22, 160, 133),
                       (211, 84, 0), (52, 73, 94)]

    def preview_regions(self, regions: List[List[str]],
                        seeds: Optional[List[str]] = None) -> None:
        """Show candidate auto-regions (one colour each) and seed rings."""
        size = self._idx_size() * 1.05
        pos = {bc: (self._xy[i, 0], self._xy[i, 1])
               for i, bc in enumerate(self._barcodes)}
        spots = []
        for ri, region in enumerate(regions):
            r, g, b = self.PREVIEW_PALETTE[ri % len(self.PREVIEW_PALETTE)]
            brush = pg.mkBrush(r, g, b, 200)
            for bc in region:
                if bc in pos:
                    spots.append({"pos": pos[bc], "size": size, "brush": brush})
        self._preview.setData(spots)
        seed_pts = [{"pos": pos[bc], "size": size * 0.6}
                    for bc in (seeds or []) if bc in pos]
        self._seeds.setData(seed_pts)

    def clear_preview(self) -> None:
        self._preview.setData([])
        self._seeds.setData([])

    # ------------------------------------------------------- profile export
    def export_profile_map(self, region_to_bcs: dict, with_background: bool,
                           path: str) -> str:
        """Render a 'profile map' — every region in its own colour over a pale
        tissue, with/without the background image — to a PDF (vector) or PNG file
        (chosen by extension). Returns the written path ('' on failure)."""
        self.reset_view()                       # clean canvas: pale base, no overlays
        n = max(1, len(region_to_bcs))
        pos = {bc: (self._xy[i, 0], self._xy[i, 1])
               for i, bc in enumerate(self._barcodes)}
        size = self._idx_size() * 1.05
        spots = []
        for ri, (_name, bcs) in enumerate(region_to_bcs.items()):
            brush = pg.mkBrush(pg.intColor(ri, hues=n))
            for bc in bcs:
                if bc in pos:
                    spots.append({"pos": pos[bc], "size": size, "brush": brush})
        self._preview.setData(spots)
        if self._img_item is not None:
            self._img_item.setVisible(with_background)
        QtWidgets.QApplication.processEvents()
        try:
            ok = self._render_scene(path)
        finally:                                # always restore the live view
            self._preview.setData([])
            if self._img_item is not None:
                self._img_item.setVisible(self.bg_toggle.isChecked())
        return path if ok else ""

    def _render_scene(self, path: str) -> bool:
        """Paint the ViewBox area of the scene to PNG or vector PDF."""
        src = self.vb.sceneBoundingRect()
        if src.width() <= 0 or src.height() <= 0:
            return False
        aspect = src.width() / src.height()
        scene = self.glw.scene()
        if path.lower().endswith(".pdf"):
            writer = QtGui.QPdfWriter(path)
            writer.setResolution(300)
            win = 8.0                            # 8-inch wide page, height by aspect
            writer.setPageSize(QtGui.QPageSize(
                QtCore.QSizeF(win, win / aspect), QtGui.QPageSize.Inch))
            painter = QtGui.QPainter(writer)
            target = QtCore.QRectF(painter.viewport())
            painter.fillRect(target, QtCore.Qt.white)
            scene.render(painter, target, src)
            painter.end()
            return True
        # PNG (default)
        w = 2000
        h = max(1, int(round(w / aspect)))
        img = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32)
        img.fill(QtCore.Qt.white)
        painter = QtGui.QPainter(img)
        scene.render(painter, QtCore.QRectF(0, 0, w, h), src)
        painter.end()
        return bool(img.save(path))

    # ----------------------------------------------------------------- reset
    def reset_view(self) -> None:
        """Clear every overlay/selection and paint all spots a uniform pale white."""
        self.clear_highlight()
        self.clear_centers()
        self.clear_preview()
        self._remove_sel_legend()
        self._remove_legend()
        self._color_mode = False
        if self.color_toggle.isChecked():
            self.color_toggle.setChecked(False)
        self._hide_hover_label()
        self._spots.setBrush(PALE_BRUSH)

    # ----------------------------------------------------- hover-to-identify
    def set_hover_regions(self, mapping: dict) -> None:
        """Provide the barcode -> region-name lookup for the current profile."""
        self._barcode_region = dict(mapping or {})
        self._hover_region = None

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = bool(enabled)
        if not enabled:
            self._hide_hover_label()
            if self._hover_region is not None:
                self._hover_region = None

    def _hide_hover_label(self) -> None:
        self._hover_label.setVisible(False)

    def _compute_hit_radius(self, size: float) -> float:
        """Cursor->spot snap radius: ~0.6 of the spot pitch so a cursor in the gap
        *between* spots still snaps to the nearest one (Visium pitch > spot size)."""
        xy = self._xy
        n = len(xy)
        if n < 2:
            return max(size, 8.0)
        idx = np.arange(n)
        if n > 400:                                   # subsample for speed
            idx = np.random.default_rng(0).choice(n, 400, replace=False)
        nn = np.empty(len(idx))
        for k, i in enumerate(idx):
            d2 = (xy[:, 0] - xy[i, 0]) ** 2 + (xy[:, 1] - xy[i, 1]) ** 2
            d2[i] = np.inf
            nn[k] = np.sqrt(d2.min())
        pitch = float(np.median(nn[np.isfinite(nn)])) if len(nn) else size
        return max(size, pitch) * 0.6

    def _nearest_spot(self, x: float, y: float) -> Optional[int]:
        if len(self._barcodes) == 0:
            return None
        d2 = (self._xy[:, 0] - x) ** 2 + (self._xy[:, 1] - y) ** 2
        i = int(np.argmin(d2))
        r = self._hit_radius
        return i if d2[i] <= r * r else None

    def _on_mouse_moved(self, scene_pos) -> None:
        if not self._hover_enabled or self.vb.lasso_enabled or len(self._barcodes) == 0:
            return
        if not self.vb.sceneBoundingRect().contains(scene_pos):
            self._set_hover_region(None)
            return
        p = self.vb.mapSceneToView(scene_pos)
        i = self._nearest_spot(p.x(), p.y())
        region = self._barcode_region.get(self._barcodes[i]) if i is not None else None
        if region:
            self._hover_label.setText(region)
            self._hover_label.setPos(p.x() + self._idx_size() * 0.8, p.y())
            self._hover_label.setVisible(True)
        else:
            self._hide_hover_label()
        self._set_hover_region(region)

    def _set_hover_region(self, region: Optional[str]) -> None:
        """Emit hoveredRegion only when the region under the cursor changes."""
        if region != self._hover_region:
            self._hover_region = region
            self.hoveredRegion.emit(region)

    # ------------------------------------------------------------ selection
    def set_selection_mode(self, enabled: bool) -> None:
        self.vb.set_lasso(enabled)
        if enabled:
            self._hide_hover_label()      # no region naming while lassoing
        else:
            self.clear_highlight()

    def _on_lasso(self, pts) -> None:
        poly = QtGui.QPolygonF(pts)
        selected = [self._barcodes[i] for i in range(len(self._barcodes))
                    if poly.containsPoint(QtCore.QPointF(self._xy[i, 0], self._xy[i, 1]),
                                          QtCore.Qt.OddEvenFill)]
        self._hilite.setBrush(SELECT_BRUSH)
        self.highlight(selected)
        self._hilite.setBrush(SELECT_BRUSH)
        self.selectionChanged.emit(selected)

    # --------------------------------------------------------------- events
    def _on_bg_toggle(self, on: bool) -> None:
        if self._img_item is not None:
            self._img_item.setVisible(on)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        m = 6
        self.bg_toggle.adjustSize()
        self.bg_toggle.move(self.width() - self.bg_toggle.width() - m, m)
        self.bg_toggle.raise_()
        self.color_toggle.adjustSize()
        self.color_toggle.move(self.width() - self.color_toggle.width() - m,
                               m + self.bg_toggle.height() + 4)
        self.color_toggle.raise_()
        self.btn_reset.adjustSize()
        self.btn_reset.move(m, m)            # top-left
        self.btn_reset.raise_()
