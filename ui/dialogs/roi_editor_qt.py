"""
ROI-Editor-Dialog (Qt) — Ersetzt DialogeMixin._roi_editor_dialog (tkinter).
Wird im Template-Editor für Scan-Regionen (🎯) genutzt.
"""
from __future__ import annotations
import os
import cv2
import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget, QSizePolicy, QApplication,
    QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRectF, QRect, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QImage, QFont

def _pil_to_qpixmap(pil_img) -> QPixmap:
    if pil_img is None:
        return QPixmap()
    rgb = pil_img.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes()
    qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class ROICanvas(QLabel):
    """Zeigt das Bild proportional skaliert an und erlaubt das Zeichnen von ROI-Rechtecken."""
    regionen_geaendert = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("roi_canvas")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)

        self._pixmap = QPixmap()
        self._regionen = []  # [[x0, y0, x1, y1], ...]
        self._test_matches = []
        self._test_limit = 0.8

        self._drag_start = None
        self._drag_cur = None
        
        # Hilfswerte für Umrechnung
        self._last_scale = 1.0
        self._last_offset = QPoint(0, 0)
        
        self._font = QFont("Segoe UI", 9)
        self._font_bold = QFont("Segoe UI", 9, QFont.Weight.Bold)

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm
        self.update()

    def _get_params(self):
        """Berechnet Skalierung und Offset basierend auf aktueller Widget-Größe."""
        if self._pixmap.isNull():
            return 1.0, QPoint(0, 0)
        
        pw, ph = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        
        s = min(cw / pw, ch / ph)
        rw, rh = int(pw * s), int(ph * s)
        ox = (cw - rw) // 2
        oy = (ch - rh) // 2
        
        self._last_scale = s
        self._last_offset = QPoint(ox, oy)
        return s, self._last_offset

    def _to_original(self, pos: QPoint) -> QPoint:
        s, off = self._get_params()
        if s == 0: return pos
        x = (pos.x() - off.x()) / s
        y = (pos.y() - off.y()) / s
        return QPoint(int(x), int(y))

    def _from_original(self, x: float, y: float) -> QPoint:
        s, off = self._get_params()
        return QPoint(int(x * s + off.x()), int(y * s + off.y()))

    def paintEvent(self, event):
        p = QPainter(self)
        if self._pixmap.isNull():
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Kein Bild geladen")
            return

        s, off = self._get_params()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        target_rect = QRect(off.x(), off.y(), int(pw * s), int(ph * s))
        
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(target_rect, self._pixmap)

        # Regionen zeichnen
        for i, r in enumerate(self._regionen):
            p.setPen(QPen(QColor("#ffca28"), 2))
            p0 = self._from_original(r[0], r[1])
            p1 = self._from_original(r[2], r[3])
            rect = QRect(p0, p1).normalized()
            p.drawRect(rect)
            
            p.setPen(QColor("#ffca28"))
            p.setFont(self._font_bold)
            p.drawText(rect.x() + 4, rect.y() + 15, f"#{i+1}")

        # Drag Vorschau
        if self._drag_start and self._drag_cur:
            p.setPen(QPen(QColor("#1e88e5"), 2, Qt.PenStyle.DashLine))
            p0 = self._from_original(self._drag_start.x(), self._drag_start.y())
            p1 = self._from_original(self._drag_cur.x(), self._drag_cur.y())
            p.drawRect(QRect(p0, p1).normalized())

        # Test-Ergebnisse
        for m in self._test_matches:
            name, mx, my, mw, mh, score = m[:6]
            farbe = QColor("#4caf50") if score >= self._test_limit else QColor("#f44336")
            p.setPen(QPen(farbe, 2))
            p0 = self._from_original(mx, my)
            p1 = self._from_original(mx + mw, my + mh)
            p.drawRect(QRect(p0, p1).normalized())
            p.setPen(farbe)
            p.setFont(self._font)
            p.drawText(p0.x() + 2, p0.y() - 4, f"{score:.2f}")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self._to_original(e.pos())
            self._drag_cur = self._drag_start
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag_start:
            self._drag_cur = self._to_original(e.pos())
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_start and e.button() == Qt.MouseButton.LeftButton:
            orig_end = self._to_original(e.pos())
            x0, y0 = self._drag_start.x(), self._drag_start.y()
            x1, y1 = orig_end.x(), orig_end.y()
            self._drag_start = None
            self._drag_cur = None

            if abs(x1 - x0) > 2 and abs(y1 - y0) > 2:
                self._regionen.append([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)])
                self.regionen_geaendert.emit(self._regionen)
                self.update()

    def set_regionen(self, regions: list):
        self._regionen = [list(r) for r in regions]
        self.update()

    def get_regionen(self) -> list:
        return self._regionen

    def set_test_results(self, matches, limit):
        self._test_matches = matches
        self._test_limit = limit
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
    """Dialog zum Festlegen von Scan-Regionen (🎯). Skaliert das Bild proportional."""
    regionen_geaendert = pyqtSignal(list)

    def __init__(self, template_name: str, regions: list, snapshot_pil=None, parent=None, bot=None):
        super().__init__(parent)
        self.setWindowTitle(f"ROI Editor: {template_name}")
        self.setObjectName("roi_editor")
        
        # Fenstergröße auf ein angenehmes Maß setzen
        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.6)
        h = int(screen.height() * 0.8)
        self.resize(w, h)
        self.setMinimumSize(800, 600)

        self.template_name = template_name
        self.bot = bot
        if not self.bot and parent and hasattr(parent, "bot"):
            self.bot = parent.bot

        self._snapshot_pil = snapshot_pil
        self._setup_ui()

        if snapshot_pil:
            self._bild_anzeigen(snapshot_pil)
        self._canvas.set_regionen(regions)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        lbl_info = QLabel("🎯 Scan-Regionen festlegen")
        lbl_info.setObjectName("dialog_header_title_gold_small")
        header.addWidget(lbl_info)
        header.addStretch()

        btn_live = QPushButton("📷 Live Bild")
        btn_live.clicked.connect(self._live_vorschau_holen)
        header.addWidget(btn_live)

        btn_snap = QPushButton("🖼 Snapshot laden")
        btn_snap.clicked.connect(self._snapshot_laden)
        header.addWidget(btn_snap)
        root.addLayout(header)

        # Canvas (Direkt im Layout für Skalierung)
        self._canvas = ROICanvas()
        self._canvas.setStyleSheet("background-color: #111111; border: 1px solid #3d3d3d;")
        self._canvas.regionen_geaendert.connect(self.regionen_geaendert)
        root.addWidget(self._canvas, stretch=1)

        # Footer
        footer = QHBoxLayout()
        self._lbl_status = QLabel("Regionen werden proportional skaliert.")
        self._lbl_status.setProperty("class", "lbl_dim")
        footer.addWidget(self._lbl_status)
        footer.addStretch()

        btn_undo = QPushButton("↺ Rückgängig")
        btn_undo.clicked.connect(self._canvas.loesche_letzte)
        footer.addWidget(btn_undo)

        btn_clear = QPushButton("✕ Alles löschen")
        btn_clear.clicked.connect(self._canvas.alles_loeschen)
        footer.addWidget(btn_clear)

        btn_test = QPushButton("🔍 Test")
        btn_test.setObjectName("btn_highlight")
        if self.parent() and hasattr(self.parent(), "_erkennung_test"):
            btn_test.clicked.connect(self.parent()._erkennung_test)
        footer.addWidget(btn_test)

        btn_close = QPushButton("Fertig")
        btn_close.setObjectName("btn_new")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _bild_anzeigen(self, pil_img):
        self._snapshot_pil = pil_img
        pm = _pil_to_qpixmap(pil_img)
        self._canvas.set_pixmap(pm)
        
        # Fenstergröße dynamisch an Bild-Format anpassen
        screen = QApplication.primaryScreen().availableGeometry()
        
        # Wir nehmen 80% der Bildschirmhöhe als Fixpunkt
        target_h = int(screen.height() * 0.8)
        
        # Berechne Breite basierend auf Bild-Verhältnis (plus Puffer für UI-Ränder)
        ratio = pil_img.width / pil_img.height
        target_w = int(target_h * ratio) + 40 # 40px Puffer für Ränder
        
        # Absichern gegen zu breite Fenster
        max_w = int(screen.width() * 0.95)
        if target_w > max_w:
            target_w = max_w
            target_h = int(target_w / ratio)

        self.resize(target_w, target_h)
        
        # Fenster zentrieren
        self.move(screen.center() - self.rect().center())

    def _live_vorschau_holen(self):
        if not self.bot: return
        snap_np = self.bot.app.current_screenshot_np
        if snap_np is not None:
            pil = Image.fromarray(cv2.cvtColor(snap_np, cv2.COLOR_BGR2RGB))
            self._bild_anzeigen(pil)
            self.set_status("Live-Bild geladen", "#00ff88")

    def _snapshot_laden(self):
        from ui.dialogs.snapshot_manager_qt import SnapshotManagerDialog
        dlg = SnapshotManagerDialog(parent=self, picker_mode=True)
        
        def on_bild_gewaehlt(pfad):
            if pfad and os.path.exists(pfad):
                try:
                    pil = Image.open(pfad).convert("RGB")
                    self._bild_anzeigen(pil)
                    self.set_status(f"Snapshot geladen: {os.path.basename(pfad)}", "#00ff88")
                except Exception as e:
                    self.set_status(f"Fehler beim Laden: {e}", "#ff4444")

        dlg.bild_gewaehlt.connect(on_bild_gewaehlt)
        dlg.exec()

    def set_status(self, text: str, farbe: str = "#4488ff"):
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(f"color: {farbe};")

    def get_regions(self): return self._canvas.get_regionen()
    def draw_test_results(self, m, l): self._canvas.set_test_results(m, l)
    
    def get_current_snapshot_np(self):
        if self._snapshot_pil:
            arr = np.array(self._snapshot_pil.convert("RGB"))
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return None
