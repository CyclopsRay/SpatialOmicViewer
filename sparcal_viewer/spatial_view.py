"""Spatial view: background image + spots, with lasso selection and highlight."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PIL import Image

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)

BASE_BRUSH = pg.mkBrush(180, 180, 180, 140)
BASE_PEN = pg.mkPen(90, 90, 90, 120)
HILITE_BRUSH = pg.mkBrush(231, 76, 60, 220)     # red
HILITE_PEN = pg.mkPen(150, 20, 20, 255)
SELECT_BRUSH = pg.mkBrush(241, 196, 15, 230)    # yellow (active lasso selection)
SELECT_PEN = pg.mkPen(120, 90, 0, 255)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._barcodes: List[str] = []
        self._xy = np.zeros((0, 2))
        self._img_item: Optional[pg.ImageItem] = None

        self.glw = pg.GraphicsLayoutWidget()
        self.vb = LassoViewBox(lockAspect=True, invertY=True, enableMenu=False)
        self.glw.addItem(self.vb)
        self.vb.sigLassoFinished.connect(self._on_lasso)

        self._spots = pg.ScatterPlotItem(pxMode=False, brush=BASE_BRUSH, pen=BASE_PEN)
        self._spots.setZValue(10)
        self._hilite = pg.ScatterPlotItem(pxMode=False, brush=HILITE_BRUSH, pen=HILITE_PEN)
        self._hilite.setZValue(20)
        self.vb.addItem(self._spots)
        self.vb.addItem(self._hilite)

        # tiny background toggle, top-right overlay
        self.bg_toggle = QtWidgets.QCheckBox("background", self)
        self.bg_toggle.setChecked(True)
        self.bg_toggle.setStyleSheet(
            "QCheckBox{background:rgba(255,255,255,180);padding:2px 4px;"
            "border-radius:3px;font-size:10px;}")
        self.bg_toggle.toggled.connect(self._on_bg_toggle)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.glw)

    # ------------------------------------------------------------------ data
    def set_data(self, image_path: str, barcodes: List[str], xy: np.ndarray,
                 spot_diameter: float) -> None:
        self._barcodes = list(barcodes)
        self._xy = np.asarray(xy, dtype=float)
        size = spot_diameter if spot_diameter and spot_diameter > 0 else 8.0

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
        self.vb.autoRange()

    def _idx_size(self) -> float:
        if self._spots.data is None or len(self._spots.data) == 0:
            return 8.0
        return float(self._spots.data["size"][0])

    # ------------------------------------------------------------ highlight
    def highlight(self, barcodes: List[str], color: str = None) -> None:
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

    # ------------------------------------------------------------ selection
    def set_selection_mode(self, enabled: bool) -> None:
        self.vb.set_lasso(enabled)
        if not enabled:
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
