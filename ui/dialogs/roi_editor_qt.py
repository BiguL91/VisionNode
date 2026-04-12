"""
ROI-Editor-Dialog (Qt) — Ersetzt DialogeMixin._roi_editor_dialog (tkinter).
Wird im Template-Editor für Scan-Regionen (🎯) genutzt.
"""
from __future__ import annotations
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget, QScrollArea, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRectF, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QImage, QFont

try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError:
    cv2 = None
    np = None
    Image = None


def _pil_to_qpixmap(pil_img) -> QPixmap:
    if pil_img is None:
        return QPixmap()
    rgb = pil_img.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes()
    qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class ROICanvas(QLabel):
    """Zeigt das Bild skaliert an und erlaubt das Zeichnen von Rechtecken auf Original-Koordinaten."""
    regionen_geaendert = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("roi_canvas")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._pixmap = QPixmap()
        self._regionen = []  # [[x0, y0, x1, y1], ...]
        self._test_matches = []
        self._test_limit = 0.8

        self._drag_start = None
        self._drag_cur = None
        
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        
        # Font vorab initialisieren
        self._font = QFont("Segoe UI", 8)
        self._font_bold = QFont("Segoe UI", 8, QFont.Weight.Bold)

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm
        self.update()

    def _get_scaling_params(self):
        if self._pixmap.isNull():
            return 1.0, QPoint(0, 0)
        
        cw, ch = self.width(), self.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        
        s = min(cw / pw, ch / ph)
        rw, rh = int(pw * s), int(ph * s)
        ox = (cw - rw) // 2
        oy = (ch - rh) // 2
        
        return s, QPoint(ox, oy)

    def _to_original(self, pos: QPoint) -> QPoint:
        s, off = self._get_scaling_params()
        if s == 0: return pos
        x = (pos.x() - off.x()) / s
        y = (pos.y() - off.y()) / s
        return QPoint(int(x), int(y))

    def _from_original(self, x: float, y: float) -> QPoint:
        s, off = self._get_scaling_params()
        return QPoint(int(x * s + off.x()), int(y * s + off.y()))

    def set_regionen(self, regions: list):
        self._regionen = [list(r) for r in regions]
        self.update()

    def get_regionen(self) -> list:
        return self._regionen

    def set_test_results(self, matches, limit):
        self._test_matches = matches
        self._test_limit = limit
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        if self._pixmap.isNull():
            p.end()
            return

        s, off = self._get_scaling_params()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        target_rect = QRectF(off.x(), off.y(), pw * s, ph * s)
        
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(target_rect.toRect(), self._pixmap)

        # Vorhandene Regionen (🎯)
        for i, r in enumerate(self._regionen):
            p.setPen(QPen(QColor("#ffca28"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            
            p0 = self._from_original(r[0], r[1])
            p1 = self._from_original(r[2], r[3])
            
            rect = QRect(p0, p1).normalized()
            p.drawRect(rect)
            
            p.setPen(QColor("#ffca28"))
            p.setFont(self._font_bold)
            p.drawText(int(rect.x() + 2), int(rect.y() + 12), f"#{i+1}")

        # Aktueller Drag
        if self._drag_start and self._drag_cur:
            p.setPen(QPen(QColor("#1e88e5"), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            
            p0 = self._from_original(self._drag_start.x(), self._drag_start.y())
            p1 = self._from_original(self._drag_cur.x(), self._drag_cur.y())
            
            p.drawRect(QRect(p0, p1).normalized())

        # Test-Matches
        for m in self._test_matches:
            name, mx, my, mw, mh, score = m[:6]
            farbe = QColor("#4caf50") if score >= self._test_limit else QColor("#f44336")
            p.setPen(QPen(farbe, 2))
            
            p0 = self._from_original(mx, my)
            p1 = self._from_original(mx + mw, my + mh)
            p.drawRect(QRect(p0, p1).normalized())
            
            p.setPen(farbe)
            p.setFont(self._font)
            p.drawText(p0.x() + 2, p0.y() - 2, f"{score:.2f}")

        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            orig = self._to_original(e.pos())
            self._drag_start = orig
            self._drag_cur = orig
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag_start:
            self._drag_cur = self._to_original(e.pos())
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_start and e.button() == Qt.MouseButton.LeftButton:
            orig_end = self._to_original(e.pos())
            x0 = min(self._drag_start.x(), orig_end.x())
            y0 = min(self._drag_start.y(), orig_end.y())
            x1 = max(self._drag_start.x(), orig_end.x())
            y1 = max(self._drag_start.y(), orig_end.y())
            
            self._drag_start = None
            self._drag_cur = None

            if abs(x1 - x0) > 2 and abs(y1 - y0) > 2:
                self._regionen.append([x0, y0, x1, y1])
                self.regionen_geaendert.emit(self._regionen)
                self.update()

    def loesche_letzte(self):
        if self._regionen:
            self._regionen.pop()
            self.regionen_geaendert.emit(self._regionen)
            self.update()

    def alles_loeschen(self):
        self._regionen = []
        self.regionen_geaendert.emit(self._regionen)
        self.update()


class ROIEditorQt(QDialog):
    """
    Dialog zum Einlernen von Scan-Regionen (🎯).
    Zeigt das Bild in 1:1 Skalierung an.
    """
    regionen_geaendert = pyqtSignal(list)

    def __init__(self, template_name: str, regions: list, snapshot_pil=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"ROI Editor: {template_name} (1:1 Skalierung)")
        self.resize(1000, 750)

        self._snapshot_pil = snapshot_pil
        self._setup_ui()

        if snapshot_pil:
            pm = _pil_to_qpixmap(snapshot_pil)
            self._canvas.set_pixmap(pm)
            
            # Fenstergröße an Bild anpassen (ohne Vollbild-Zwang)
            screen = QApplication.primaryScreen().availableGeometry()
            # Verfügbare Fläche abzüglich Puffer für Taskleiste/Ränder
            max_w = screen.width() - 40
            max_h = screen.height() - 80
            
            target_w = min(pm.width() + 80, max_w)
            target_h = min(pm.height() + 180, max_h)
            
            self.resize(target_w, target_h)
            # Zentriere das Fenster auf dem Bildschirm
            self.move(screen.center() - self.rect().center())

        self._canvas.set_regionen(regions)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header Info
        header = QHBoxLayout()
        lbl_info = QLabel("🎯 Regionen festlegen (Scan-Beschleunigung)")
        lbl_info.setProperty("class", "lbl_header_gold")
        header.addWidget(lbl_info)
        header.addStretch()
        root.addLayout(header)

        # Scroll Area für 1:1 Anzeige
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setObjectName("roi_scroll")

        self._canvas = ROICanvas()
        self._canvas.regionen_geaendert.connect(self.regionen_geaendert)
        scroll.setWidget(self._canvas)
        root.addWidget(scroll)

        # Footer
        footer = QHBoxLayout()
        self._lbl_status = QLabel("Regionen werden in 1:1 Koordinaten gespeichert.")
        self._lbl_status.setProperty("class", "lbl_dim")
        footer.addWidget(self._lbl_status)
        footer.addStretch()

        btn_undo = QPushButton("↺ Letzte löschen")
        btn_undo.clicked.connect(self._canvas.loesche_letzte)
        footer.addWidget(btn_undo)

        btn_clear = QPushButton("✕ Alles löschen")
        btn_clear.clicked.connect(self._canvas.alles_loeschen)
        footer.addWidget(btn_clear)

        btn_close = QPushButton("Fertig")
        btn_close.setObjectName("btn_new")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)

        root.addLayout(footer)

    def set_status(self, text: str, farbe: str = "#4488ff"):
        self._lbl_status.setText(text)
        if farbe == "#00ff88":
            self._lbl_status.setProperty("class", "lbl_success")
        elif farbe in ("#ff4444", "#ff6644"):
            self._lbl_status.setProperty("class", "lbl_error")
        else:
            self._lbl_status.setProperty("class", "lbl_highlight")
        self._lbl_status.setStyle(self._lbl_status.style())

    # ── Public API (kompatibel mit altem ROIEditor) ───────────────────────────

    def set_regionen(self, regions: list):
        self._canvas.set_regionen(regions)

    def get_regions(self) -> list:
        return self._canvas.get_regionen()

    def draw_test_results(self, matches, limit: float):
        self._canvas.set_test_results(matches, limit)

    def get_current_snapshot_np(self):
        """Gibt den aktuell angezeigten Snapshot als Numpy BGR-Array zurück."""
        if self._snapshot_pil:
            arr = np.array(self._snapshot_pil.convert("RGB"))
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return None
