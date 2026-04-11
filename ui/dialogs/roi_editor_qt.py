"""
ROI-Editor (Qt) — Scannbereiche per Drag & Drop auf Snapshot festlegen.

Ersetzt ROIEditor (tkinter). Die Bot-Kopplung (Live-View Callback) ist
via Signal gelöst: live_region_requested → Host setzt Callback zurück.
"""
import os
import cv2
import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QFont, QCursor
)


def _pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qi = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qi)


class ROICanvas(QLabel):
    """
    QLabel-Subklasse die als Zeichenfläche für ROI-Regionen dient.
    - Hintergrundbild via setPixmap
    - Regionen per Drag zeichnen
    - Zeigt bestehende Regionen + Live-Rechteck beim Ziehen
    """
    region_added = pyqtSignal(tuple)   # (x0, y0, x1, y1) in Original-Koordinaten

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet("background: #000000;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 150)

        self._scaling: float = 1.0
        self._regionen: list[tuple] = []          # Original-Koordinaten
        self._test_results: list = []
        self._drag_start: QPoint | None = None
        self._drag_end: QPoint | None = None
        self._base_pixmap: QPixmap | None = None

    def set_bild(self, pil_img: Image.Image, max_h: int = 700):
        sw, sh = pil_img.size
        self._scaling = min(max_h / sh, 1.0) if sh > max_h else 1.0
        rw, rh = int(sw * self._scaling), int(sh * self._scaling)
        disp = pil_img.resize((rw, rh), Image.LANCZOS) if self._scaling != 1.0 else pil_img
        self._base_pixmap = _pil_to_qpixmap(disp)
        self.setFixedSize(rw, rh)
        self.update()

    def set_kein_bild(self):
        self._base_pixmap = None
        self.setMinimumSize(400, 250)
        self.update()

    def set_regionen(self, regionen: list):
        self._regionen = list(regionen)
        self.update()

    def get_regionen(self) -> list:
        return self._regionen

    def region_hinzufuegen(self, region: tuple):
        self._regionen.append(region)
        self.update()

    def clear_regionen(self):
        self._regionen.clear()
        self._test_results.clear()
        self.update()

    def undo_last(self):
        if self._regionen:
            self._regionen.pop()
        self.update()

    def set_test_results(self, matches, limit: float):
        self._test_results = [(m, limit) for m in matches]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        if self._base_pixmap:
            painter.drawPixmap(0, 0, self._base_pixmap)
        else:
            painter.fillRect(self.rect(), QColor("#000000"))
            painter.setPen(QColor("#555555"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Kein Screenshot verfügbar\n🔄 Aktualisieren klicken")

        s = self._scaling

        # Gespeicherte Regionen
        pen_roi = QPen(QColor("#00ff00"), 3)
        painter.setPen(pen_roi)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        for i, (rx0, ry0, rx1, ry1) in enumerate(self._regionen):
            rect = QRect(int(rx0 * s), int(ry0 * s), int((rx1 - rx0) * s), int((ry1 - ry0) * s))
            painter.drawRect(rect)
            painter.setPen(QColor("#00ff00"))
            painter.drawText(rect.topLeft() + QPoint(4, 14), str(i + 1))
            painter.setPen(pen_roi)

        # Test-Ergebnisse
        for m, limit in self._test_results:
            name, rx, ry, rw, rh, score = m[:6]
            farbe = QColor("#00ff00") if score >= limit else QColor("#ffcc00")
            painter.setPen(QPen(farbe, 2, Qt.PenStyle.DashLine))
            painter.drawRect(int(rx * s), int(ry * s), int(rw * s), int(rh * s))
            painter.setPen(farbe)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(int(rx * s), int(ry * s) - 2, f"{score:.2f}")

        # Live-Rechteck beim Ziehen
        if self._drag_start and self._drag_end:
            painter.setPen(QPen(QColor("#ffff00"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRect(self._drag_start, self._drag_end).normalized()
            painter.drawRect(rect)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self._drag_end = self._drag_start
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start and event.buttons() & Qt.MouseButton.LeftButton:
            self._drag_end = event.position().toPoint()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start:
            end = event.position().toPoint()
            x0, y0 = self._drag_start.x(), self._drag_start.y()
            x1, y1 = end.x(), end.y()
            self._drag_start = None
            self._drag_end = None

            if abs(x1 - x0) > 5 and abs(y1 - y0) > 5:
                s = self._scaling
                region = (
                    int(min(x0, x1) / s), int(min(y0, y1) / s),
                    int(max(x0, x1) / s), int(max(y0, y1) / s),
                )
                self._regionen.append(region)
                self.region_added.emit(region)
                self.update()
        super().mouseReleaseEvent(event)


class ROIEditorQt(QDialog):
    """
    Scannbereiche-Editor (Qt). Ersetzt ROIEditor (tkinter).

    Signals:
        regionen_geaendert(list)  — immer wenn Regionen sich ändern
        live_modus_an()           — User klickt "Live wählen", Host soll Callback setzen
        live_modus_aus()          — User deaktiviert Live-Modus

    Parameter:
        t_name            — Template-Name für Fenstertitel
        initial_regions   — Initiale Regions-Liste [(x0,y0,x1,y1), ...]
        get_live_snap_func — Callable () → PIL.Image | None
    """
    regionen_geaendert = pyqtSignal(list)
    live_modus_an = pyqtSignal()
    live_modus_aus = pyqtSignal()

    def __init__(self, t_name: str, initial_regions: list,
                 get_live_snap_func=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scannbereiche — {t_name}")
        self.setModal(False)  # Nicht-modal wie das Original
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._t_name = t_name
        self._get_live_snap_func = get_live_snap_func
        self._live_aktiv = False
        self._snapshot_pil: Image.Image | None = None

        self._setup_ui()
        self.set_regionen(list(initial_regions))
        self._snap_aktualisieren()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setStyleSheet("background: #2d2d2d;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)

        lbl_src = QLabel("Quelle:")
        lbl_src.setStyleSheet("color: #888888; font-size: 10px;")
        tb_layout.addWidget(lbl_src)

        self._combo_snap = QComboBox()
        self._combo_snap.setMinimumWidth(200)
        self._combo_snap.currentTextChanged.connect(self._on_snap_change)
        tb_layout.addWidget(self._combo_snap)
        self._snap_liste_laden()

        btn_refresh = QPushButton("🔄 Aktualisieren")
        btn_refresh.setObjectName("btn_icon")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self.refresh_live_snap)
        tb_layout.addWidget(btn_refresh)

        self._btn_live = QPushButton("📍 Live wählen")
        self._btn_live.setObjectName("btn_icon")
        self._btn_live.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_live.clicked.connect(self._toggle_live_mode)
        tb_layout.addWidget(self._btn_live)

        tb_layout.addStretch()
        root.addWidget(toolbar)

        # ── Canvas ────────────────────────────────────────────────────────────
        from PyQt6.QtWidgets import QScrollArea
        self._canvas = ROICanvas()
        self._canvas.region_added.connect(lambda r: self.regionen_geaendert.emit(self._canvas.get_regionen()))

        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("background: #000000; border: none;")
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        root.addWidget(scroll, stretch=1)

        # ── Unterleiste ───────────────────────────────────────────────────────
        ctrl = QFrame()
        ctrl.setStyleSheet("background: #2d2d2d;")
        c_layout = QHBoxLayout(ctrl)
        c_layout.setContentsMargins(8, 4, 8, 4)
        c_layout.setSpacing(6)

        btn_clear = QPushButton("× Alle weg")
        btn_clear.setObjectName("btn_danger")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_alle)
        c_layout.addWidget(btn_clear)

        btn_undo = QPushButton("↩ Rückgängig")
        btn_undo.setObjectName("btn_icon")
        btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_undo.clicked.connect(self._undo)
        c_layout.addWidget(btn_undo)

        c_layout.addStretch()

        self._lbl_status = QLabel("Suchbereiche (ROI) festlegen")
        self._lbl_status.setStyleSheet("color: #888888; font-size: 10px;")
        c_layout.addWidget(self._lbl_status)

        root.addWidget(ctrl)

        self.resize(820, 600)

    # ── Snapshot-Logik ─────────────────────────────────────────────────────────

    def _snap_liste_laden(self):
        self._combo_snap.blockSignals(True)
        self._combo_snap.clear()
        self._combo_snap.addItem("Live Snapshot")
        if os.path.exists("snapshots"):
            files = sorted(f[:-4] for f in os.listdir("snapshots") if f.endswith(".png"))
            self._combo_snap.addItems(files)
        self._combo_snap.blockSignals(False)

    def _on_snap_change(self, val: str):
        if val == "Live Snapshot":
            self._snap_aktualisieren()
        else:
            pfad = os.path.join("snapshots", f"{val}.png")
            if os.path.exists(pfad):
                arr = cv2.imdecode(np.fromfile(pfad, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if arr is not None:
                    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                    self._snapshot_pil = Image.fromarray(rgb)
                    self._canvas.set_bild(self._snapshot_pil)

    def _snap_aktualisieren(self):
        if self._get_live_snap_func:
            snap = self._get_live_snap_func()
            if snap:
                self._snapshot_pil = snap
                self._canvas.set_bild(snap)
                self.set_status("Live Snapshot geladen", "#55ff88")
                return
        self._canvas.set_kein_bild()
        self.set_status("Kein Screenshot verfügbar", "#da3633")

    def refresh_live_snap(self):
        if self._combo_snap.currentText() == "Live Snapshot":
            self._snap_aktualisieren()
        else:
            self._combo_snap.setCurrentText("Live Snapshot")

    # ── Live-Modus ─────────────────────────────────────────────────────────────

    def _toggle_live_mode(self):
        self._live_aktiv = not self._live_aktiv
        if self._live_aktiv:
            self._btn_live.setStyleSheet("background: #1a3a5a; color: #ffffff;")
            self.live_modus_an.emit()
            self.set_status("Live-Auswahl aktiv – Region auf Live-Vorschau ziehen.", "#ffca28")
        else:
            self._btn_live.setStyleSheet("")
            self.live_modus_aus.emit()
            self.set_status("Suchbereiche (ROI) festlegen", "#888888")

    def on_live_selection(self, x0: int, y0: int, x1: int, y1: int):
        """Wird vom Host aufgerufen wenn eine Live-Region gezogen wurde."""
        self._canvas.region_hinzufuegen((x0, y0, x1, y1))
        self.regionen_geaendert.emit(self._canvas.get_regionen())
        self.set_status(f"Region via Live-View: {x1-x0}×{y1-y0}px", "#55ff88")

    # ── Canvas-Aktionen ────────────────────────────────────────────────────────

    def _clear_alle(self):
        self._canvas.clear_regionen()
        self.regionen_geaendert.emit([])

    def _undo(self):
        self._canvas.undo_last()
        self.regionen_geaendert.emit(self._canvas.get_regionen())

    def set_status(self, text: str, farbe: str = "#4488ff"):
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(f"color: {farbe}; font-size: 10px;")

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
