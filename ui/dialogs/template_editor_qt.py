"""
Template-Editor (Qt) — Migriert von template_editor.py (tkinter).
Kernlogik (template_engine, action_engine, bot) bleibt vollständig unangetastet.
"""
from __future__ import annotations
import os

try:
    import cv2
    import numpy as np
    import torch
    from PIL import Image
except ImportError:
    cv2 = np = torch = Image = None  # type: ignore[assignment]

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QSlider, QCheckBox, QComboBox, QFrame, QScrollArea, QSizePolicy,
    QMessageBox, QWidget, QRadioButton, QButtonGroup, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont


def _pil_to_qpixmap(pil_img) -> QPixmap:
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qi = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qi)


class TemplateCanvas(QLabel):
    """
    Zeichenfläche für Bild + Overlays (Ignore-Regionen + Klick-Zone).
    Unterstützt Drag-to-draw für Ignorier-Regionen und Einzel-Klick-Setzen.
    """
    region_drawn = pyqtSignal(tuple)     # (x0, y0, x1, y1) in Original-Koordinaten
    klick_gesetzt = pyqtSignal(float, float)  # rel_x%, rel_y%

    def __init__(self, placeholder_text="", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setObjectName("template_canvas")
        self.setFixedSize(400, 200)

        self._placeholder_text = placeholder_text
        self._scaling: float = 1.0
        self._base_pixmap: QPixmap | None = None

        # Original-Koordinaten (Original-Canvas)
        self._ignore_regionen: list[tuple] = []
        # Vorberechnete Pixel-Koordinaten (HG-Canvas)
        self._ignore_pixel: list[tuple] | None = None

        self._klick_zone: tuple | None = None   # (rel_x%, rel_y%)
        self._drag_start: QPoint | None = None
        self._drag_end: QPoint | None = None
        self._modus: str = "ignore"             # "ignore" | "klick"

    def set_bild(self, pil_img: Image.Image, max_b: int = 1100, max_h: int = 320):
        sw, sh = pil_img.size
        s = min(max_b / sw, max_h / sh)
        if s > 15.0:
            s = 15.0
        rw, rh = int(sw * s), int(sh * s)
        self._scaling = s
        disp = pil_img.resize((rw, rh), Image.NEAREST)
        self._base_pixmap = _pil_to_qpixmap(disp)
        self.setFixedSize(rw, rh)
        self.update()
        return s, rw, rh

    def set_bild_skaliert(self, pil_img: Image.Image, target_w: int, target_h: int):
        """Setzt Bild auf exakt (target_w × target_h) — für HG-Canvas."""
        resized = pil_img.resize((target_w, target_h), Image.LANCZOS)
        self._base_pixmap = _pil_to_qpixmap(resized)
        self.setFixedSize(target_w, target_h)
        self.update()

    def clear_bild(self):
        self._base_pixmap = None
        self.setFixedSize(400, 200)
        self.update()

    def set_ignore_regionen(self, regionen: list):
        """Original-Koordinaten — werden intern mit self._scaling multipliziert."""
        self._ignore_regionen = list(regionen)
        self._ignore_pixel = None
        self.update()

    def set_ignore_pixel(self, pixel_rects: list):
        """Direkte Pixel-Koordinaten (vorberechnet, z.B. für HG-Canvas)."""
        self._ignore_pixel = list(pixel_rects)
        self.update()

    def set_klick_zone(self, rel_x: float | None, rel_y: float | None = None):
        if rel_x is None:
            self._klick_zone = None
        else:
            self._klick_zone = (rel_x, rel_y)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        if self._base_pixmap:
            painter.drawPixmap(0, 0, self._base_pixmap)
        else:
            painter.fillRect(0, 0, w, h, QColor("#1a1a1a"))
            painter.setPen(QColor("#555555"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, self._placeholder_text)

        s = self._scaling
        fill_ign = QColor(255, 68, 68, 80)
        pen_ign = QPen(QColor("#ff4444"), 2)

        rects = []
        if self._ignore_pixel is not None:
            rects = self._ignore_pixel
        else:
            for (ix0, iy0, ix1, iy1) in self._ignore_regionen:
                rects.append((int(ix0 * s), int(iy0 * s), int(ix1 * s), int(iy1 * s)))

        for (rx0, ry0, rx1, ry1) in rects:
            painter.fillRect(rx0, ry0, rx1 - rx0, ry1 - ry0, fill_ign)
            painter.setPen(pen_ign)
            painter.drawRect(rx0, ry0, rx1 - rx0, ry1 - ry0)

        if self._drag_start and self._drag_end:
            x0, y0 = self._drag_start.x(), self._drag_start.y()
            x1, y1 = self._drag_end.x(), self._drag_end.y()
            painter.fillRect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), fill_ign)
            painter.setPen(pen_ign)
            painter.drawRect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))

        if self._klick_zone:
            px = int(self._klick_zone[0] / 100 * w)
            py = int(self._klick_zone[1] / 100 * h)
            painter.setPen(QPen(QColor("#ff6600"), 2))
            painter.drawLine(px - 10, py, px + 10, py)
            painter.drawLine(px, py - 10, px, py + 10)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._modus == "klick":
                w, h = self.width(), self.height()
                rel_x = round(event.pos().x() / w * 100, 1)
                rel_y = round(event.pos().y() / h * 100, 1)
                self.klick_gesetzt.emit(rel_x, rel_y)
            else:
                self._drag_start = event.pos()
                self._drag_end = None

    def mouseMoveEvent(self, event):
        if self._modus == "ignore" and self._drag_start:
            self._drag_end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._modus == "ignore" and self._drag_start and event.button() == Qt.MouseButton.LeftButton:
            end = event.pos()
            x0, y0 = self._drag_start.x(), self._drag_start.y()
            x1, y1 = end.x(), end.y()
            self._drag_start = None
            self._drag_end = None
            if abs(x1 - x0) >= 4 and abs(y1 - y0) >= 4:
                sw, sh = self.width(), self.height()
                ss = self._scaling
                reg = (
                    int(max(0, min(x0, x1)) / ss),
                    int(max(0, min(y0, y1)) / ss),
                    int(min(sw, max(x0, x1)) / ss),
                    int(min(sh, max(y0, y1)) / ss),
                )
                self.region_drawn.emit(reg)
            self.update()


# ─────────────────────────────────────────────────────────────────────────────

class TemplateEditorQt(QDialog):
    """
    Template-Editor (Qt). Ersetzt TemplateEditor (tkinter).

    Parameter:
        parent                — Elternfenster (QWidget oder None)
        bot                   — TilesBot-Instanz
        bearbeiten_name       — Name des zu bearbeitenden Templates (None = neu)
        aktueller_ausschnitt  — tuple(PIL.Image, ...) oder None
        einlern_modus_callback— Callable, wird beim Schließen aufgerufen
        typ                   — "template" | "aktiv_gruppe" | "passiv_gruppe"
        kategorie             — "workflow" | ...
    """

    def __init__(self, parent, bot, bearbeiten_name=None, aktueller_ausschnitt=None,
                 einlern_modus_callback=None, typ=None, kategorie=None):
        super().__init__(parent)
        self.bot = bot
        self.template_engine = bot.template_engine
        self.action_engine = bot.action_engine
        self.bearbeiten_name = bearbeiten_name

        if bearbeiten_name:
            s = bot.template_engine.settings.get(bearbeiten_name, {})
            self.typ = s.get("typ") or typ or "template"
            self.kategorie = s.get("kategorie") or kategorie or "workflow"
        else:
            self.typ = typ or "template"
            self.kategorie = kategorie or "workflow"

        self.orig_bild_ref = None
        if aktueller_ausschnitt:
            self.orig_bild_ref = aktueller_ausschnitt[0]
        self.einlern_modus_callback = einlern_modus_callback

        self.setWindowTitle("Template aktualisieren" if bearbeiten_name else "Template speichern")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(False)

        self._canvas_modus = "ignore"
        self.roi_editor = None

        self.aktuell_skala = 1.0
        self.aktuell_b = 400
        self.aktuell_h = 200
        self._hg_preview_bbox = None

        self.ignore_regionen: list = []
        self.klick_zone: list = [None]

        self._nach_vorschau_cb = None
        self.initial_scan_regions: list = []
        if self.bearbeiten_name:
            self.initial_scan_regions = self.template_engine.settings.get(
                self.bearbeiten_name, {}).get("scan_regions", [])

        self.varianten_liste: list = []
        self.aktuelle_variante_idx: int = 0
        self.condition_states: list = []
        self.set_states: dict = {}

        self._setup_ui()
        self._load_existing_data()

        if parent:
            geo = parent.geometry()
            self.move(geo.x() + geo.width() + 8, geo.y())

    # ─────────────────────────────────────────────────────────────────────────
    #  UI Aufbau
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        tb = QFrame()
        tb.setObjectName("template_editor_toolbar")
        tb_lay = QHBoxLayout(tb)
        tb_lay.setContentsMargins(0, 0, 0, 0)
        tb_lay.setSpacing(4)

        self._btn_ignorieren = QPushButton("■ Ignorieren")
        self._btn_ignorieren.setObjectName("btn_sm")
        self._btn_ignorieren.setCursor(Qt.CursorShape.PointingHandCursor)
        # Modus-Styling wird via property gesteuert
        self._btn_ignorieren.clicked.connect(lambda: self._modus_setzen("ignore"))

        self._btn_klick = QPushButton("⊕ Klick-Zone")
        self._btn_klick.setObjectName("btn_sm")
        self._btn_klick.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_klick.clicked.connect(lambda: self._modus_setzen("klick"))

        btn_roi = QPushButton("🔍 Scannbereiche")
        btn_roi.setObjectName("btn_roi")
        btn_roi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_roi.clicked.connect(self._roi_fenster_oeffnen)

        btn_ocr = QPushButton("🔤 OCR")
        btn_ocr.setObjectName("btn_ocr_action")
        btn_ocr.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ocr.clicked.connect(self._ocr_konfigurieren)

        btn_states = QPushButton("🚩 Zustände")
        btn_states.setObjectName("btn_states_action")
        btn_states.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_states.clicked.connect(self._states_konfigurieren)

        for btn in [self._btn_ignorieren, self._btn_klick, btn_roi, btn_ocr, btn_states]:
            tb_lay.addWidget(btn)
        tb_lay.addStretch()
        root.addWidget(tb)
        root.addSpacing(6)

        # ── Canvases ─────────────────────────────────────────────────────────
        self.canvas = TemplateCanvas("Live-Vorschau")
        self.canvas.region_drawn.connect(self._on_region_drawn)
        self.canvas.klick_gesetzt.connect(self._on_klick_gesetzt)

        self.canvas_hg = TemplateCanvas("GPU-Mathematik")
        self.canvas_hg.setEnabled(False)

        root.addWidget(self.canvas)
        root.addSpacing(4)
        root.addWidget(self.canvas_hg)
        root.addSpacing(3)

        # ── Info + Steuerung ─────────────────────────────────────────────────
        self.info_label = QLabel("")
        self.info_label.setProperty("class", "lbl_info")
        root.addWidget(self.info_label)

        ign_row = QHBoxLayout()
        ign_row.addStretch()
        btn_ign_undo = QPushButton("↩ Letzten entfernen")
        btn_ign_undo.setObjectName("btn_sm")
        btn_ign_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ign_undo.clicked.connect(self._ignore_letzten_entfernen)
        ign_row.addWidget(btn_ign_undo)
        root.addLayout(ign_row)

        self.klick_info = QLabel("Klick-Zone: nicht gesetzt")
        self.klick_info.setProperty("class", "lbl_dim")
        root.addWidget(self.klick_info)

        klick_row = QHBoxLayout()
        btn_klick_del = QPushButton("× Klick entfernen")
        btn_klick_del.setObjectName("btn_sm")
        btn_klick_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_klick_del.clicked.connect(self._klick_entfernen)
        klick_row.addWidget(btn_klick_del)
        klick_row.addStretch()
        root.addLayout(klick_row)
        root.addSpacing(4)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("class", "separator")
        sep.setFixedHeight(1)
        root.addWidget(sep)
        root.addSpacing(10)

        # ── Name ─────────────────────────────────────────────────────────────
        lbl_name = QLabel("Name:")
        lbl_name.setProperty("class", "lbl_header_dim")
        root.addWidget(lbl_name)
        root.addSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        self.name_entry = QLineEdit(self.bearbeiten_name or "")
        self.name_entry.setPlaceholderText("Template-Name eingeben…")
        self.name_entry.textChanged.connect(self._on_name_geaendert)
        name_row.addWidget(self.name_entry)

        # Varianten-Navigation
        self.varianten_nav = QWidget()
        vn_lay = QHBoxLayout(self.varianten_nav)
        vn_lay.setContentsMargins(0, 0, 0, 0)
        vn_lay.setSpacing(2)

        self.btn_var_prev = QPushButton("◀")
        self.btn_var_prev.setObjectName("btn_sm")
        self.btn_var_prev.setFixedWidth(26)
        self.btn_var_prev.clicked.connect(self._variante_prev)

        self.var_label = QLabel("")
        self.var_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.var_label.setFixedWidth(100)
        self.var_label.setProperty("class", "lbl_info")

        self.btn_var_next = QPushButton("▶")
        self.btn_var_next.setObjectName("btn_sm")
        self.btn_var_next.setFixedWidth(26)
        self.btn_var_next.clicked.connect(self._variante_next)

        self.btn_var_del = QPushButton("🗑")
        self.btn_var_del.setObjectName("btn_del")
        self.btn_var_del.setFixedWidth(26)
        self.btn_var_del.clicked.connect(self._variante_loeschen)

        for w in [self.btn_var_prev, self.var_label, self.btn_var_next, self.btn_var_del]:
            vn_lay.addWidget(w)

        self.varianten_nav.hide()
        name_row.addWidget(self.varianten_nav)
        root.addLayout(name_row)

        self.version_info_label = QLabel("")
        self.version_info_label.setObjectName("version_info_label")
        root.addWidget(self.version_info_label)
        root.addSpacing(2)

        # "Als neue Variante speichern"
        self.variante_btn_frame = QWidget()
        vbf_lay = QHBoxLayout(self.variante_btn_frame)
        vbf_lay.setContentsMargins(0, 0, 0, 0)
        self.btn_neue_variante = QPushButton("➕ Als neue Variante speichern")
        self.btn_neue_variante.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_neue_variante.setObjectName("btn_variant_save")
        self.btn_neue_variante.clicked.connect(self._als_neue_variante_speichern)
        vbf_lay.addWidget(self.btn_neue_variante)
        vbf_lay.addStretch()
        self.variante_btn_frame.hide()
        root.addWidget(self.variante_btn_frame)

        # ── Gruppe ────────────────────────────────────────────────────────────
        self._gruppe_widget = QWidget()
        g_lay = QVBoxLayout(self._gruppe_widget)
        g_lay.setContentsMargins(0, 8, 0, 0)
        g_lay.setSpacing(2)

        gruppe_label_text = {
            "aktiv_gruppe": None,
            "passiv_gruppe": "Übergeordnete Gruppe (optional):",
            "template": "Gruppe: *",
        }.get(self.typ, "Gruppe:")
        self._gruppe_label = QLabel(gruppe_label_text or "Gruppe:")
        self._gruppe_label.setProperty("class", "lbl_header_dim")
        g_lay.addWidget(self._gruppe_label)

        alle_gruppen = self.template_engine.get_gruppen(kategorie=self.kategorie)
        gruppen_liste = [g for g in alle_gruppen if g != self.bearbeiten_name]
        self._gruppe_combo = QComboBox()
        self._gruppe_combo.setEditable(True)
        self._gruppe_combo.addItems(gruppen_liste)
        start_gruppe = ""
        if self.bearbeiten_name:
            start_gruppe = self.template_engine.settings.get(self.bearbeiten_name, {}).get("gruppe", "")
        self._gruppe_combo.setCurrentText(start_gruppe)
        g_lay.addWidget(self._gruppe_combo)
        root.addWidget(self._gruppe_widget)
        self._typ_anwenden()

        # ── Schwellwert ───────────────────────────────────────────────────────
        self._schwellwert_widget = QWidget()
        sw_lay = QVBoxLayout(self._schwellwert_widget)
        sw_lay.setContentsMargins(0, 8, 0, 0)
        sw_lay.setSpacing(2)

        lbl_sw = QLabel("Match-Schwellwert:")
        lbl_sw.setProperty("class", "lbl_header_dim")
        sw_lay.addWidget(lbl_sw)

        sw_row = QHBoxLayout()
        self._schwellwert_slider = QSlider(Qt.Orientation.Horizontal)
        self._schwellwert_slider.setRange(50, 100)
        start_sw = int(round(
            self.template_engine.settings.get(self.bearbeiten_name, {}).get("match_schwellwert", 0.85) * 100
            if self.bearbeiten_name else 85
        ))
        self._schwellwert_slider.setValue(start_sw)
        self._schwellwert_wert_lbl = QLabel(f"{start_sw / 100:.2f}")
        self._schwellwert_wert_lbl.setProperty("class", "lbl_info")
        self._schwellwert_wert_lbl.setFixedWidth(34)
        self._schwellwert_slider.valueChanged.connect(
            lambda v: self._schwellwert_wert_lbl.setText(f"{v / 100:.2f}"))
        sw_row.addWidget(self._schwellwert_slider)
        sw_row.addWidget(self._schwellwert_wert_lbl)
        sw_lay.addLayout(sw_row)
        root.addWidget(self._schwellwert_widget)

        # ── Hintergrund ───────────────────────────────────────────────────────
        hg_widget = QWidget()
        hg_lay = QHBoxLayout(hg_widget)
        hg_lay.setContentsMargins(0, 10, 0, 0)
        hg_lay.setSpacing(8)

        self.hg_checkbox = QCheckBox("Hintergrund entfernen")
        self.hg_checkbox.setChecked(True)
        self.hg_checkbox.stateChanged.connect(lambda _: self._hg_vorschau_aktualisieren())
        hg_lay.addWidget(self.hg_checkbox)

        lbl_tol = QLabel("Toleranz:")
        lbl_tol.setProperty("class", "lbl_info")
        hg_lay.addWidget(lbl_tol)

        self._hg_tol_slider = QSlider(Qt.Orientation.Horizontal)
        self._hg_tol_slider.setRange(5, 80)
        self._hg_tol_slider.setValue(30)
        self._hg_tol_slider.setFixedWidth(130)
        self._hg_tol_wert_lbl = QLabel("30")
        self._hg_tol_wert_lbl.setProperty("class", "lbl_info")
        self._hg_tol_slider.valueChanged.connect(lambda v: self._hg_tol_wert_lbl.setText(str(v)))
        self._hg_tol_slider.sliderReleased.connect(self._hg_vorschau_aktualisieren)

        hg_lay.addWidget(self._hg_tol_slider)
        hg_lay.addWidget(self._hg_tol_wert_lbl)
        hg_lay.addStretch()
        root.addWidget(hg_widget)

        # ── Buttons ───────────────────────────────────────────────────────────
        root.addSpacing(16)
        btn_leiste = QHBoxLayout()

        btn_test = QPushButton("🚀 Test")
        btn_test.setObjectName("btn_test_action")
        btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_test.clicked.connect(self._erkennung_test)
        btn_leiste.addWidget(btn_test)
        btn_leiste.addStretch()

        btn_schliessen = QPushButton("Schließen")
        btn_schliessen.setObjectName("btn_sm")
        btn_schliessen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_schliessen.clicked.connect(self._schliessen)
        btn_leiste.addWidget(btn_schliessen)

        btn_speichern = QPushButton("Speichern")
        btn_speichern.setObjectName("btn_new")
        btn_speichern.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_speichern.clicked.connect(self._speichern)
        btn_leiste.addWidget(btn_speichern)

        root.addLayout(btn_leiste)
        self.name_entry.setFocus()

    # ─────────────────────────────────────────────────────────────────────────
    #  Modus
    # ─────────────────────────────────────────────────────────────────────────

    def _modus_setzen(self, modus: str):
        self._canvas_modus = modus
        self.canvas._modus = modus
        
        self._btn_ignorieren.setProperty("active", modus == "ignore")
        self._btn_klick.setProperty("active", modus == "klick")
        
        self._btn_ignorieren.setStyle(self._btn_ignorieren.style())
        self._btn_klick.setStyle(self._btn_klick.style())

    # ─────────────────────────────────────────────────────────────────────────
    #  Laden
    # ─────────────────────────────────────────────────────────────────────────

    def _typ_anwenden(self):
        verstecken = (self.typ == "aktiv_gruppe")
        if self.typ == "passiv_gruppe" and self.bearbeiten_name:
            s = self.template_engine.settings.get(self.bearbeiten_name, {})
            if s.get("gruppe", "") in ("", self.bearbeiten_name):
                verstecken = True
        if verstecken:
            self._gruppe_widget.hide()
        else:
            self._gruppe_widget.show()
            label_text = "Übergeordnete Gruppe (optional):" if self.typ == "passiv_gruppe" else "Gruppe: *"
            self._gruppe_label.setText(label_text)

    def _load_existing_data(self):
        if self.bearbeiten_name:
            name = self.bearbeiten_name
            if name in self.template_engine.settings:
                s = self.template_engine.settings[name]
                self.hg_checkbox.setChecked(s.get("hg_entfernen", True))
                v = s.get("hg_toleranz", 30)
                self._hg_tol_slider.setValue(v)
                self._hg_tol_wert_lbl.setText(str(v))
                cs = s.get("condition_states", [])
                self.condition_states = self._migrate_condition_states(cs)
                ss = s.get("set_states", {})
                self.set_states = dict(ss) if isinstance(ss, dict) else {}

            if name in self.template_engine.templates:
                pfad = self.template_engine.templates[name]["pfad"]
                if os.path.exists(pfad):
                    try:
                        tpl = Image.open(pfad).convert("RGB")
                        tw, th = tpl.size
                        QTimer.singleShot(50, lambda: self._vorschau_setzen(tpl, tw, th))
                    except Exception:
                        pass

            for r in self.template_engine.settings.get(name, {}).get("ignore_regionen", []):
                self.ignore_regionen.append(tuple(r))

            klick_konfig = self.action_engine.klickzonen_laden()
            if name in klick_konfig:
                k = klick_konfig[name]
                self.klick_zone[0] = (k["klick_rel_x"], k["klick_rel_y"])
                self.klick_info.setText(f"Klick-Zone: {k['klick_rel_x']:.0f}% / {k['klick_rel_y']:.0f}%")
                self.klick_info.setProperty("class", "lbl_orange")
                self.klick_info.setStyle(self.klick_info.style())

            self._varianten_erkennen(name)
            QTimer.singleShot(120, self._overlays_zeichnen)

        elif self.orig_bild_ref:
            tw, th = self.orig_bild_ref.size
            QTimer.singleShot(50, lambda: self._vorschau_setzen(self.orig_bild_ref, tw, th))

    def _varianten_erkennen(self, name: str):
        basis = name.split("__")[0]
        varianten = sorted(
            [n for n in self.template_engine.templates.keys()
             if n == basis or n.startswith(f"{basis}__")])
        if len(varianten) > 1:
            self.varianten_liste = varianten
            self.aktuelle_variante_idx = varianten.index(name) if name in varianten else 0
        else:
            self.varianten_liste = []
            self.aktuelle_variante_idx = 0
        self._varianten_nav_aktualisieren()

    # ─────────────────────────────────────────────────────────────────────────
    #  Varianten-Navigation
    # ─────────────────────────────────────────────────────────────────────────

    def _varianten_nav_aktualisieren(self):
        n = len(self.varianten_liste)
        idx = self.aktuelle_variante_idx
        if n > 1:
            self.varianten_nav.show()
            if idx == 0:
                self.var_label.setText(f"★ Master  1/{n}")
                self.var_label.setProperty("class", "lbl_master")
            else:
                self.var_label.setText(f"V.{idx + 1}  {idx + 1}/{n}")
                self.var_label.setProperty("class", "lbl_dim")
            self.var_label.setStyle(self.var_label.style())
            self.btn_var_prev.setEnabled(idx > 0)
            self.btn_var_next.setEnabled(idx < n - 1)
            self.btn_var_del.setEnabled(idx > 0)
        else:
            self.varianten_nav.hide()
        self._version_info_aktualisieren()

    def _version_info_aktualisieren(self):
        name = self.bearbeiten_name
        if not name:
            self.version_info_label.setText("")
            return
        n = len(self.varianten_liste)
        basis = name.split("__")[0]
        if n > 1:
            idx = self.aktuelle_variante_idx
            if idx == 0:
                self.version_info_label.setText(
                    f"★ Master-Version von \"{basis}\" · {n} Variante(n) gesamt")
                self.version_info_label.setProperty("master", True)
            else:
                self.version_info_label.setText(f"Variante {idx + 1} von \"{basis}\" · {n} gesamt")
                self.version_info_label.setProperty("master", False)
        else:
            self.version_info_label.setText("Keine weiteren Varianten")
            self.version_info_label.setProperty("master", False)
        
        self.version_info_label.setStyle(self.version_info_label.style())

    def _variante_prev(self):
        if self.aktuelle_variante_idx > 0:
            self._variante_wechseln(self.aktuelle_variante_idx - 1)

    def _variante_next(self):
        if self.aktuelle_variante_idx < len(self.varianten_liste) - 1:
            self._variante_wechseln(self.aktuelle_variante_idx + 1)

    def _variante_loeschen(self):
        if self.aktuelle_variante_idx == 0:
            return
        name = self.varianten_liste[self.aktuelle_variante_idx]
        if QMessageBox.question(
                self, "Variante löschen?", f"Variante \"{name}\" wirklich löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self.template_engine.template_loeschen(name)
        try:
            self.bot.ocr_engine.template_ocr_alle_loeschen(name)
        except Exception:
            pass
        self.action_engine.klickzone_loeschen(name)
        self.bot._panels_aktualisieren()
        self.bot.app.reload_templates()
        self.bot._timer_panel_aktualisieren()
        self.bot._log(f"Variante gelöscht: \"{name}\"")

        ziel_idx = self.aktuelle_variante_idx - 1
        basis = name.split("__")[0]
        self._varianten_erkennen(basis)
        ziel_idx = min(ziel_idx, len(self.varianten_liste) - 1)
        if self.varianten_liste:
            self._variante_wechseln(ziel_idx)

    def _variante_wechseln(self, idx: int):
        name = self.varianten_liste[idx]
        self.aktuelle_variante_idx = idx
        self.bearbeiten_name = name
        self.name_entry.blockSignals(True)
        self.name_entry.setText(name)
        self.name_entry.blockSignals(False)

        s = self.template_engine.settings.get(name, {})
        self.hg_checkbox.setChecked(s.get("hg_entfernen", True))
        v = s.get("hg_toleranz", 30)
        self._hg_tol_slider.setValue(v)
        self._hg_tol_wert_lbl.setText(str(v))
        sw = int(round(s.get("match_schwellwert", 0.85) * 100))
        self._schwellwert_slider.setValue(sw)
        self._schwellwert_wert_lbl.setText(f"{sw / 100:.2f}")
        self._gruppe_combo.setCurrentText(s.get("gruppe", ""))
        cs = s.get("condition_states", [])
        self.condition_states = self._migrate_condition_states(cs)
        ss = s.get("set_states", {})
        self.set_states = dict(ss) if isinstance(ss, dict) else {}
        self.ignore_regionen = [tuple(r) for r in s.get("ignore_regionen", [])]

        klick_konfig = self.action_engine.klickzonen_laden()
        if name in klick_konfig:
            k = klick_konfig[name]
            self.klick_zone[0] = (k["klick_rel_x"], k["klick_rel_y"])
            self.klick_info.setText(f"Klick-Zone: {k['klick_rel_x']:.0f}% / {k['klick_rel_y']:.0f}%")
            self.klick_info.setProperty("class", "lbl_orange")
            self.klick_info.setStyle(self.klick_info.style())
        else:
            self.klick_zone[0] = None
            self.klick_info.setText("Klick-Zone: nicht gesetzt")
            self.klick_info.setProperty("class", "lbl_dim")
            self.klick_info.setStyle(self.klick_info.style())

        self.initial_scan_regions = s.get("scan_regions", [])
        if self.roi_editor and self.roi_editor.isVisible():
            self.roi_editor.close()
            self.roi_editor = None

        if name in self.template_engine.templates:
            pfad = self.template_engine.templates[name]["pfad"]
            if os.path.exists(pfad):
                try:
                    tpl = Image.open(pfad).convert("RGB")
                    tw, th = tpl.size
                    self.orig_bild_ref = tpl
                    self._vorschau_setzen(tpl, tw, th)
                except Exception:
                    pass

        self._varianten_nav_aktualisieren()

    # ─────────────────────────────────────────────────────────────────────────
    #  Name-Änderung
    # ─────────────────────────────────────────────────────────────────────────

    def _on_name_geaendert(self, text: str):
        n = text.strip()
        existiert = n in self.template_engine.templates and n != self.bearbeiten_name
        if existiert:
            self.variante_btn_frame.show()
        else:
            self.variante_btn_frame.hide()

    def _als_neue_variante_speichern(self):
        basis = self.name_entry.text().strip()
        if not basis or self.orig_bild_ref is None:
            return
        n = 2
        while f"{basis}__{n}" in self.template_engine.templates:
            n += 1
        neuer_name = f"{basis}__{n}"

        entferne_hg = self.hg_checkbox.isChecked()
        hg_toleranz = self._hg_tol_slider.value()
        match_s = self._schwellwert_slider.value() / 100
        gruppe_name = self.template_engine.settings.get(basis, {}).get("gruppe", basis)

        aktuelle_scan_regions = self.initial_scan_regions
        if self.roi_editor and self.roi_editor.isVisible():
            aktuelle_scan_regions = self.roi_editor.get_regions()

        self.template_engine.template_speichern(
            neuer_name, self.orig_bild_ref, entferne_hg, list(self.ignore_regionen),
            hintergrund_toleranz=hg_toleranz, gruppe=gruppe_name,
            match_schwellwert=match_s, scan_regions=list(aktuelle_scan_regions),
            condition_states=list(self.condition_states), set_states=dict(self.set_states))

        self.bot._log(f"Neue Variante gespeichert: \"{neuer_name}\"")
        self.bot._panels_aktualisieren()
        self.bot.app.reload_templates()
        self.bot._timer_panel_aktualisieren()

        self.bearbeiten_name = neuer_name
        self.name_entry.blockSignals(True)
        self.name_entry.setText(neuer_name)
        self.name_entry.blockSignals(False)
        self._varianten_erkennen(neuer_name)
        self.aktuelle_variante_idx = (
            self.varianten_liste.index(neuer_name) if neuer_name in self.varianten_liste else 0)
        self._varianten_nav_aktualisieren()

    # ─────────────────────────────────────────────────────────────────────────
    #  OCR
    # ─────────────────────────────────────────────────────────────────────────

    def _ocr_konfigurieren(self):
        from ui.dialogs.ocr_dialog_qt import OCRKonfigDialog
        name = self.bearbeiten_name or self.name_entry.text().strip()
        if not name:
            return
        dlg = OCRKonfigDialog(name, bot=self.bot, parent=self)
        dlg.gespeichert.connect(self.bot._panels_aktualisieren)
        dlg.show()

    # ─────────────────────────────────────────────────────────────────────────
    #  Zustände-Dialog
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _migrate_condition_states(raw):
        if not raw:
            return []
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            if "states" in raw[0] or "connector" in raw[0]:
                return raw
            return [{"connector": None if i == 0 else "OR", "states": dict(item)}
                    for i, item in enumerate(raw)]
        return []

    def _states_konfigurieren(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Zustände konfigurieren")
        dialog.setMinimumSize(600, 540)
        dialog.setObjectName("template_states_dialog")
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        try:
            bekannte = sorted(self.bot.app.state.game_states.keys())
        except Exception:
            bekannte = []

        root_lay = QVBoxLayout(dialog)
        root_lay.setContentsMargins(20, 14, 20, 14)
        root_lay.setSpacing(4)

        lbl_head = QLabel("Aktiv wenn:")
        lbl_head.setProperty("class", "lbl_master")
        root_lay.addWidget(lbl_head)

        lbl_hint = QLabel("Bedingungen innerhalb einer Gruppe sind AND-verknüpft.\n"
                          "Gruppen untereinander können AND oder OR verknüpft werden.")
        lbl_hint.setProperty("class", "lbl_dim")
        root_lay.addWidget(lbl_hint)
        root_lay.addSpacing(8)

        gruppen_scroll = QScrollArea()
        gruppen_scroll.setWidgetResizable(True)
        gruppen_scroll.setObjectName("selector_scroll")
        gruppen_container_w = QWidget()
        gruppen_container_w.setObjectName("selector_container")
        gruppen_lay = QVBoxLayout(gruppen_container_w)
        gruppen_lay.setContentsMargins(0, 0, 0, 0)
        gruppen_lay.setSpacing(2)
        gruppen_scroll.setWidget(gruppen_container_w)
        root_lay.addWidget(gruppen_scroll, stretch=1)

        gruppen = []

        def refresh_first_connector():
            for i, g in enumerate(gruppen):
                g["connector_widget"].setVisible(i > 0)

        def gruppe_loeschen(g):
            gruppen.remove(g)
            g["widget"].deleteLater()
            refresh_first_connector()

        def zeile_in_gruppe_bauen(g, state_name="", state_val=True):
            z_widget = QWidget()
            z_widget.setProperty("class", "bg_box_dark")
            z_lay = QHBoxLayout(z_widget)
            z_lay.setContentsMargins(6, 4, 6, 4)
            z_lay.setSpacing(4)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(bekannte)
            combo.setCurrentText(state_name)
            combo.setMinimumWidth(180)
            chk = QCheckBox("True")
            chk.setChecked(state_val)
            chk.setProperty("class", "lbl_dim")
            btn_del = QPushButton("✕")
            btn_del.setObjectName("btn_del")
            btn_del.setFixedSize(22, 22)
            z_lay.addWidget(combo)
            z_lay.addWidget(chk)
            z_lay.addStretch()
            z_lay.addWidget(btn_del)
            g["zeilen_lay"].addWidget(z_widget)
            entry = (z_widget, combo, chk)
            g["zeilen"].append(entry)

            def _del():
                if entry in g["zeilen"]:
                    g["zeilen"].remove(entry)
                z_widget.deleteLater()
            btn_del.clicked.connect(_del)

        def gruppe_bauen(gruppe_data):
            wrapper = QWidget()
            wrapper.setProperty("class", "bg_dialog_mid")
            w_lay = QVBoxLayout(wrapper)
            w_lay.setContentsMargins(0, 0, 0, 2)
            w_lay.setSpacing(0)

            g = {"widget": wrapper, "connector_widget": None,
                 "connector_var": [gruppe_data.get("connector") or "OR"],
                 "zeilen_lay": None, "zeilen": []}

            conn_w = QWidget()
            conn_w.setProperty("class", "bg_dialog_mid")
            conn_lay = QHBoxLayout(conn_w)
            conn_lay.setContentsMargins(0, 8, 0, 3)
            conn_lay.setSpacing(4)
            conn_lay.addWidget(QLabel("Verknüpfung:"))
            bg = QButtonGroup(conn_w)
            for txt, clr in [("AND", "#55aaff"), ("OR", "#ffca28")]:
                rb = QRadioButton(txt)
                rb.setProperty("type", txt.lower())
                rb.setChecked(txt == (gruppe_data.get("connector") or "OR"))
                rb.toggled.connect(
                    lambda checked, t=txt, ref=g: ref["connector_var"].__setitem__(0, t) if checked else None)
                bg.addButton(rb)
                conn_lay.addWidget(rb)
            conn_lay.addStretch()
            g["connector_widget"] = conn_w
            w_lay.addWidget(conn_w)

            nr = len(gruppen) + 1
            box = QFrame()
            box.setFrameShape(QFrame.Shape.StyledPanel)
            box.setProperty("class", "bg_box_dark")
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(0, 0, 0, 4)
            box_lay.setSpacing(0)

            hdr = QFrame()
            hdr.setProperty("class", "bg_header")
            hdr_lay = QHBoxLayout(hdr)
            hdr_lay.setContentsMargins(8, 4, 8, 4)
            lbl_nr = QLabel(f"Gruppe {nr}")
            lbl_nr.setProperty("class", "lbl_header_dim")
            hdr_lay.addWidget(lbl_nr)
            hdr_lay.addStretch()
            btn_del_g = QPushButton("Gruppe löschen")
            btn_del_g.setObjectName("btn_sm")
            btn_del_g.setProperty("class", "lbl_error")
            btn_del_g.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del_g.clicked.connect(lambda _, ref=g: gruppe_loeschen(ref))
            hdr_lay.addWidget(btn_del_g)
            box_lay.addWidget(hdr)

            zeilen_container = QWidget()
            zeilen_container.setProperty("class", "bg_box_dark")
            zeilen_lay = QVBoxLayout(zeilen_container)
            zeilen_lay.setContentsMargins(4, 4, 4, 0)
            zeilen_lay.setSpacing(2)
            g["zeilen_lay"] = zeilen_lay
            box_lay.addWidget(zeilen_container)

            for sn, sv in gruppe_data.get("states", {}).items():
                zeile_in_gruppe_bauen(g, sn, sv)

            btn_add_z = QPushButton("+ Bedingung hinzufügen")
            btn_add_z.setObjectName("btn_sm")
            btn_add_z.setProperty("class", "lbl_dim")
            btn_add_z.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_add_z.clicked.connect(lambda _, ref=g: zeile_in_gruppe_bauen(ref))
            box_lay.addWidget(btn_add_z, alignment=Qt.AlignmentFlag.AlignLeft)

            w_lay.addWidget(box)
            gruppen_lay.addWidget(wrapper)
            gruppen.append(g)
            refresh_first_connector()

        daten = self._migrate_condition_states(self.condition_states)
        if not daten:
            daten = [{"connector": None, "states": {}}]
        for gd in daten:
            gruppe_bauen(gd)

        btn_neue_gruppe = QPushButton("＋ Neue Gruppe hinzufügen")
        btn_neue_gruppe.setObjectName("btn_variant_save")
        btn_neue_gruppe.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_neue_gruppe.clicked.connect(lambda: gruppe_bauen({"connector": "OR", "states": {}}))
        gruppen_lay.addWidget(btn_neue_gruppe, alignment=Qt.AlignmentFlag.AlignLeft)
        gruppen_lay.addStretch()

        # ── set_states ────────────────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setProperty("class", "separator")
        sep2.setFixedHeight(1)
        root_lay.addWidget(sep2)

        lbl_set = QLabel("Setzt Zustände (bei Erkennung):")
        lbl_set.setProperty("class", "lbl_success")
        root_lay.addWidget(lbl_set)

        set_container = QWidget()
        set_container.setProperty("class", "bg_box_dark")
        set_lay = QVBoxLayout(set_container)
        set_lay.setContentsMargins(0, 0, 0, 0)
        set_lay.setSpacing(2)
        root_lay.addWidget(set_container)

        set_zeilen = []

        def set_zeile_bauen(state_name="", state_val=True):
            z = QWidget()
            z.setProperty("class", "bg_box_dark")
            z_lay = QHBoxLayout(z)
            z_lay.setContentsMargins(6, 4, 6, 4)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(bekannte)
            combo.setCurrentText(state_name)
            combo.setMinimumWidth(180)
            chk = QCheckBox("True")
            chk.setChecked(state_val)
            chk.setProperty("class", "lbl_dim")
            btn_del = QPushButton("✕")
            btn_del.setObjectName("btn_del")
            btn_del.setFixedSize(22, 22)
            z_lay.addWidget(combo)
            z_lay.addWidget(chk)
            z_lay.addStretch()
            z_lay.addWidget(btn_del)
            set_lay.addWidget(z)
            entry = (z, combo, chk)
            set_zeilen.append(entry)

            def _del():
                if entry in set_zeilen:
                    set_zeilen.remove(entry)
                z.deleteLater()
            btn_del.clicked.connect(_del)

        for sk, sv in self.set_states.items():
            set_zeile_bauen(sk, sv)

        btn_add_set = QPushButton("+ Zustand hinzufügen")
        btn_add_set.setObjectName("btn_sm")
        btn_add_set.setProperty("class", "lbl_dim")
        btn_add_set.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_set.clicked.connect(set_zeile_bauen)
        root_lay.addWidget(btn_add_set, alignment=Qt.AlignmentFlag.AlignLeft)

        # ── Dialog-Buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def speichern():
            self.condition_states = []
            for g in gruppen:
                states = {}
                for (_, combo, chk) in g["zeilen"]:
                    n = combo.currentText().strip()
                    if n:
                        states[n] = chk.isChecked()
                if states:
                    self.condition_states.append({
                        "connector": g["connector_var"][0],
                        "states": states,
                    })
            if self.condition_states:
                self.condition_states[0]["connector"] = None
            self.set_states = {}
            for (_, combo, chk) in set_zeilen:
                n = combo.currentText().strip()
                if n:
                    self.set_states[n] = chk.isChecked()
            dialog.accept()

        btn_abbruch = QPushButton("Abbrechen")
        btn_abbruch.setObjectName("btn_sm")
        btn_abbruch.clicked.connect(dialog.reject)
        btn_uebernehmen = QPushButton("Übernehmen")
        btn_uebernehmen.setObjectName("btn_new")
        btn_uebernehmen.clicked.connect(speichern)
        btn_row.addWidget(btn_abbruch)
        btn_row.addWidget(btn_uebernehmen)
        root_lay.addLayout(btn_row)

        dialog.move(self.x() + 40, self.y() + 40)
        dialog.exec()

    # ─────────────────────────────────────────────────────────────────────────
    #  ROI / Test
    # ─────────────────────────────────────────────────────────────────────────

    def _roi_fenster_oeffnen(self):
        if self.roi_editor and self.roi_editor.isVisible():
            self.roi_editor.raise_()
            self.roi_editor.activateWindow()
            return

        from ui.dialogs.roi_editor_qt import ROIEditorQt

        t_name = self.bearbeiten_name or self.name_entry.text().strip() or "Unbenannt"
        snap_pil = None
        if self.bot and hasattr(self.bot.app, "current_screenshot_np"):
            snap_np = self.bot.app.current_screenshot_np
            if snap_np is not None:
                snap_pil = Image.fromarray(cv2.cvtColor(snap_np, cv2.COLOR_BGR2RGB))

        self.roi_editor = ROIEditorQt(t_name, self.initial_scan_regions, snap_pil, parent=self)
        self.roi_editor.regionen_geaendert.connect(self._on_roi_changed)
        self.roi_editor.show()

    def _on_roi_changed(self, regions):
        self.initial_scan_regions = regions

    def _erkennung_test(self):
        if not (self.roi_editor and self.roi_editor.isVisible()):
            self._roi_fenster_oeffnen()

        if not self.roi_editor:
            QMessageBox.warning(self, "Kein Screenshot",
                                "Scannbereiche-Fenster konnte nicht geöffnet werden.\n"
                                "Bitte zuerst einen Live-Screenshot aufnehmen.")
            return

        self.roi_editor.raise_()
        self.roi_editor.activateWindow()
        snap_np = self.roi_editor.get_current_snapshot_np()

        if snap_np is None:
            live = getattr(getattr(self.bot, "app", None), "current_screenshot_np", None)
            if live is not None:
                snap_np = live
            else:
                QMessageBox.warning(self, "Kein Screenshot",
                                    "Kein Screenshot verfügbar.\n"
                                    "Bitte MEMUPlayer verbinden und den Bot starten.")
                return

        if self.orig_bild_ref is None:
            QMessageBox.warning(self, "Kein Template", "Bitte zuerst ein Bild als Template laden.")
            return

        n_tmp = "test_match_preview"
        aktuelle_rois = self.roi_editor.get_regions()
        match_s = self._schwellwert_slider.value() / 100

        try:
            bild_np = np.array(self.orig_bild_ref.convert("RGB"))
            bild_bgr = cv2.cvtColor(bild_np, cv2.COLOR_RGB2BGR)

            if self.hg_checkbox.isChecked():
                maske_raw = self.template_engine._hintergrund_maske_erstellen(
                    bild_np, toleranz=self._hg_tol_slider.value())
                for (ix0, iy0, ix1, iy1) in self.ignore_regionen:
                    maske_raw[max(0, int(iy0)):int(iy1), max(0, int(ix0)):int(ix1)] = 0
                maske_np = np.where(maske_raw > 10, 1.0, 0.0).astype(np.float32)
                bbox = self.template_engine._maske_bbox((maske_np > 0.5).astype(np.uint8))
                if bbox:
                    bx, by, bw, bh = bbox
                    bild_bgr = bild_bgr[by:by + bh, bx:bx + bw]
                    maske_np = maske_np[by:by + bh, bx:bx + bw]
            else:
                maske_np = None
                bbox = None

            dev = self.template_engine.device
            t_bild = torch.from_numpy(
                bild_bgr.transpose(2, 0, 1)).float().div(255.0).to(dev).unsqueeze(0)
            t_maske = (torch.from_numpy(maske_np).float().to(dev).unsqueeze(0).unsqueeze(0)
                       if maske_np is not None else None)

            self.template_engine.templates[n_tmp] = {
                "tensor": t_bild, "maske": t_maske,
                "orig_size": (self.orig_bild_ref.width, self.orig_bild_ref.height),
                "gruppe": n_tmp, "pfad": "",
                "match_schwellwert": match_s,
                "scan_regions": aktuelle_rois, "bbox": bbox,
            }
            self.template_engine.settings[n_tmp] = {
                "match_schwellwert": match_s,
                "scan_regions": aktuelle_rois,
                "condition_states": {}, "set_states": {},
            }

            res = self.template_engine.matches_suchen_np(snap_np)
            my_matches = [m for m in res if m[0] == n_tmp]
            self.roi_editor.draw_test_results(my_matches, match_s)

            if my_matches:
                best = max(my_matches, key=lambda m: m[5])
                self.roi_editor.set_status(
                    f"✓ {len(my_matches)} Treffer  |  Bester Score: {best[5]:.3f}", "#00ff88")
            else:
                self.roi_editor.set_status(
                    f"✗ Kein Treffer  (Schwelle: {match_s:.2f})", "#ff6644")
        except Exception as e:
            if self.roi_editor:
                self.roi_editor.set_status(f"Fehler: {e}", "#ff4444")
        finally:
            self.template_engine.templates.pop(n_tmp, None)
            self.template_engine.settings.pop(n_tmp, None)
            for key in [k for k in self.template_engine._gpu_cache if k[0] == n_tmp]:
                del self.template_engine._gpu_cache[key]

    # ─────────────────────────────────────────────────────────────────────────
    #  Vorschau
    # ─────────────────────────────────────────────────────────────────────────

    def _vorschau_setzen(self, bild: Image.Image, breite: int, hoehe: int):
        self.orig_bild_ref = bild
        s, ab, ah = self.canvas.set_bild(bild)
        self.aktuell_skala, self.aktuell_b, self.aktuell_h = s, ab, ah
        self.canvas_hg.setFixedSize(ab, ah)
        self._overlays_zeichnen()
        self.info_label.setText(f"{breite}x{hoehe}px")
        if self._nach_vorschau_cb:
            QTimer.singleShot(30, self._nach_vorschau_cb)
        else:
            self._hg_vorschau_aktualisieren()

    def _overlays_zeichnen(self):
        self.canvas.set_ignore_regionen(self.ignore_regionen)
        if self.klick_zone[0]:
            rx, ry = self.klick_zone[0]
            self.canvas.set_klick_zone(rx, ry)
            self.canvas_hg.set_klick_zone(rx, ry)
        else:
            self.canvas.set_klick_zone(None)
            self.canvas_hg.set_klick_zone(None)

    # ─────────────────────────────────────────────────────────────────────────
    #  Canvas-Signale
    # ─────────────────────────────────────────────────────────────────────────

    def _on_region_drawn(self, region: tuple):
        self.ignore_regionen.append(region)
        self._overlays_zeichnen()
        self._hg_vorschau_aktualisieren()

    def _on_klick_gesetzt(self, rel_x: float, rel_y: float):
        self.klick_zone[0] = (rel_x, rel_y)
        self.klick_info.setText(f"Klick-Zone: {rel_x:.0f}% / {rel_y:.0f}%")
        self.klick_info.setProperty("class", "lbl_orange")
        self.klick_info.setStyle(self.klick_info.style())
        self._overlays_zeichnen()

    def _ignore_letzten_entfernen(self):
        if self.ignore_regionen:
            self.ignore_regionen.pop()
        self._overlays_zeichnen()
        self._hg_vorschau_aktualisieren()

    def _klick_entfernen(self):
        self.klick_zone[0] = None
        self.klick_info.setText("Klick-Zone: nicht gesetzt")
        self.klick_info.setProperty("class", "lbl_dim")
        self.klick_info.setStyle(self.klick_info.style())
        self._overlays_zeichnen()

    # ─────────────────────────────────────────────────────────────────────────
    #  Hintergrund-Vorschau
    # ─────────────────────────────────────────────────────────────────────────

    def _hg_vorschau_aktualisieren(self):
        if self.orig_bild_ref is None:
            return
        n_tmp = "_tmp_preview"
        try:
            self.template_engine.template_speichern(
                n_tmp, self.orig_bild_ref, self.hg_checkbox.isChecked(),
                list(self.ignore_regionen), hintergrund_toleranz=self._hg_tol_slider.value(),
                gruppe="temp_preview")

            bbox = self.template_engine.templates.get(n_tmp, {}).get("bbox")
            self._hg_preview_bbox = bbox

            preview = self.template_engine.get_mathematik_vorschau(n_tmp)
            if preview:
                ab, ah = self.aktuell_b, self.aktuell_h
                if preview.mode == "RGBA":
                    bild_np = np.array(preview)
                    rgb_ch = bild_np[:, :, :3]
                    alpha_ch = bild_np[:, :, 3] / 255.0
                    checker = self._schachbrett(bild_np.shape[1], bild_np.shape[0])
                    preview = Image.fromarray(
                        (rgb_ch * alpha_ch[:, :, None] + checker * (1 - alpha_ch[:, :, None])
                         ).astype(np.uint8))
                self.canvas_hg.set_bild_skaliert(preview, ab, ah)

                pixel_rects = []
                for (ix0, iy0, ix1, iy1) in self.ignore_regionen:
                    if bbox:
                        bx, by, bw, bh = bbox
                        sx, sy = ab / bw, ah / bh
                        pixel_rects.append((
                            int((ix0 - bx) * sx), int((iy0 - by) * sy),
                            int((ix1 - bx) * sx), int((iy1 - by) * sy),
                        ))
                    else:
                        s = self.aktuell_skala
                        pixel_rects.append((
                            int(ix0 * s), int(iy0 * s), int(ix1 * s), int(iy1 * s)))
                self.canvas_hg.set_ignore_pixel(pixel_rects)
        except Exception as e:
            self.bot._log(f"Vorschau-Fehler: {e}")
        finally:
            self.template_engine.template_loeschen("_tmp_preview")

    def _schachbrett(self, w: int, h: int) -> np.ndarray:
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for iy in range(h):
            for ix in range(w):
                arr[iy, ix] = (180, 180, 180) if (ix // 8 + iy // 8) % 2 == 0 else (120, 120, 120)
        return arr

    # ─────────────────────────────────────────────────────────────────────────
    #  Speichern / Schließen
    # ─────────────────────────────────────────────────────────────────────────

    def _speichern(self):
        n = self.name_entry.text().strip()
        if not n:
            return

        alter_name = self.bearbeiten_name
        uebergeordnet = self._gruppe_combo.currentText().strip() if self.typ != "aktiv_gruppe" else ""
        existiert = n in self.template_engine.templates or n in self.template_engine.settings

        if existiert and n != alter_name:
            if QMessageBox.question(
                    self, "Überschreiben?", f"'{n}' existiert bereits. Überschreiben?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

        try:
            img_to_save = self.orig_bild_ref
            if img_to_save is None and alter_name and alter_name in self.template_engine.templates:
                pfad_alt = self.template_engine.templates[alter_name].get("pfad")
                if pfad_alt and os.path.exists(pfad_alt):
                    _arr = cv2.imdecode(np.fromfile(pfad_alt, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if _arr is not None:
                        if len(_arr.shape) == 3 and _arr.shape[2] == 4:
                            img_to_save = Image.fromarray(cv2.cvtColor(_arr[:, :, :3], cv2.COLOR_BGR2RGB))
                        else:
                            img_to_save = Image.fromarray(cv2.cvtColor(_arr, cv2.COLOR_BGR2RGB))

            entferne_hg = self.hg_checkbox.isChecked()
            hg_toleranz = self._hg_tol_slider.value()
            match_s = self._schwellwert_slider.value() / 100

            aktuelle_scan_regions = self.initial_scan_regions
            if self.roi_editor and self.roi_editor.isVisible():
                aktuelle_scan_regions = self.roi_editor.get_regions()

            if img_to_save is None or self.typ == "passiv_gruppe":
                n = self.name_entry.text().strip()
                if not n:
                    self.bot._log("Fehler beim Speichern: Kein Name angegeben.")
                    return

                umbenennen = alter_name and (alter_name != n)
                gruppe_geandert = False
                if alter_name:
                    alte_ug = self.template_engine.settings.get(alter_name, {}).get("gruppe", "")
                    ist_alter_master = (alte_ug in ("", alter_name))
                    ist_neuer_master = (uebergeordnet == "")
                    if ist_alter_master:
                        if not ist_neuer_master:
                            gruppe_geandert = True
                    else:
                        if alte_ug != uebergeordnet:
                            gruppe_geandert = True

                if umbenennen or gruppe_geandert:
                    self.template_engine.gruppe_umbenennen(
                        alter_name, n, neue_uebergeordnete_gruppe=uebergeordnet)

                self.template_engine.gruppe_config_speichern(
                    n, list(self.condition_states),
                    uebergeordnete_gruppe=uebergeordnet, kategorie=self.kategorie,
                    scan_regions=list(aktuelle_scan_regions))

                aktion = "umbenannt" if umbenennen else ("aktualisiert" if alter_name else "erstellt")
                self.bot._log(f"Passive Gruppe {aktion}: \"{n}\"")
                self.bot.app.reload_templates()
                self.bot._panels_aktualisieren()
                return

            if self.typ == "aktiv_gruppe":
                gruppe_name = n
            else:
                gruppe_name = self._gruppe_combo.currentText().strip() or n

            umbenennen = alter_name and (alter_name != n)
            gruppe_geandert = False
            if alter_name:
                alte_ug = self.template_engine.settings.get(alter_name, {}).get("gruppe", "")
                ist_alter_master = (alte_ug in ("", alter_name))
                ist_neuer_master = (gruppe_name == n)
                if ist_alter_master:
                    if not ist_neuer_master:
                        gruppe_geandert = True
                else:
                    if alte_ug != gruppe_name:
                        gruppe_geandert = True

            speichern_kwargs = dict(
                hintergrund_toleranz=hg_toleranz,
                gruppe=gruppe_name,
                match_schwellwert=match_s,
                scan_regions=list(aktuelle_scan_regions),
                condition_states=list(self.condition_states),
                set_states=dict(self.set_states),
                typ=self.typ,
                kategorie=self.kategorie,
            )

            if self.typ == "aktiv_gruppe" and (umbenennen or gruppe_geandert):
                self.template_engine.gruppe_umbenennen(
                    alter_name, n, neue_uebergeordnete_gruppe=uebergeordnet)
                orig_alter_name = alter_name
                alter_name = n
                self.bearbeiten_name = n
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen),
                    alter_name=orig_alter_name, **speichern_kwargs)
            elif umbenennen:
                self.template_engine.template_umbenennen(alter_name, n, gruppe_name)
                orig_alter_name = alter_name
                alter_name = n
                self.bearbeiten_name = n
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen),
                    alter_name=orig_alter_name, **speichern_kwargs)
            else:
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen), **speichern_kwargs)

            if umbenennen:
                self.action_engine.klickzone_loeschen(alter_name)
            if self.klick_zone[0]:
                self.action_engine.klickzone_speichern(n, self.klick_zone[0][0], self.klick_zone[0][1])
            elif alter_name and not umbenennen:
                self.action_engine.klickzone_loeschen(n)

            self.bot._log(f"Template {'aktualisiert' if alter_name else 'gespeichert'}: \"{n}\"")
            self.bot._panels_aktualisieren()
            self.bot.app.reload_templates()
            self.bot._timer_panel_aktualisieren()

            self.bearbeiten_name = n
            self._varianten_erkennen(n)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.bot._log(f"Speicher-Fehler: {e}")

    def _schliessen(self):
        self.template_engine.template_loeschen("_tmp_preview")
        self.template_engine.templates.pop("test_match_preview", None)
        self.template_engine.settings.pop("test_match_preview", None)
        self.close()
        if self.einlern_modus_callback:
            self.einlern_modus_callback()

    def closeEvent(self, event):
        self.template_engine.template_loeschen("_tmp_preview")
        self.template_engine.templates.pop("test_match_preview", None)
        self.template_engine.settings.pop("test_match_preview", None)
        if self.einlern_modus_callback:
            self.einlern_modus_callback()
        super().closeEvent(event)
