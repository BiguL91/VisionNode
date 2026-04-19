"""
Template-Editor (Qt) — Migriert von template_editor.py (tkinter).
Kernlogik (template_engine, action_engine, bot) bleibt vollständig unangetastet.
"""
from __future__ import annotations
import os
from lang import lang

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

from ui.widgets.click_step_slider import ClickStepSlider
from ui.widgets.template_canvas   import TemplateCanvas, _pil_to_qpixmap


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
        self.ausschnitt_form = "box"

        if bearbeiten_name:
            s = bot.template_engine.settings.get(bearbeiten_name, {})
            self.typ = s.get("typ") or typ or "template"
            self.kategorie = s.get("kategorie") or kategorie or "workflow"
            self.ausschnitt_form = s.get("ausschnitt_form", "box")
        else:
            self.typ = typ or "template"
            self.kategorie = kategorie or "workflow"

        self.orig_bild_ref = None
        if aktueller_ausschnitt:
            self.orig_bild_ref = aktueller_ausschnitt[0]
            if len(aktueller_ausschnitt) > 3:
                self.ausschnitt_form = aktueller_ausschnitt[3]

        self.einlern_modus_callback = einlern_modus_callback
        
        # Fokus für das Matching-Backend setzen
        if self.bot and hasattr(self.bot.app.state, "force_include"):
            if self.bearbeiten_name and self.bearbeiten_name not in self.bot.app.state.force_include:
                self.bot.app.state.force_include.append(self.bearbeiten_name)

        # Dynamischen Fenstertitel setzen
        prefix = "Template" if bearbeiten_name else "Neues Template"
        self.setWindowTitle(f"{prefix}: {bearbeiten_name or '??'}")
        
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
        self.search_only: bool = False

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
        self._btn_ignorieren.setObjectName("btn_ignorieren_action")
        self._btn_ignorieren.setCursor(Qt.CursorShape.PointingHandCursor)
        # Modus-Styling wird via property gesteuert
        self._btn_ignorieren.clicked.connect(lambda: self._modus_setzen("ignore"))

        self._btn_klick = QPushButton(f"🖱 {lang.t('btn_click')}")
        self._btn_klick.setObjectName("btn_klick_action")
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

        # ── Neu aufnehmen ────────────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedWidth(2)
        line.setStyleSheet("background: #444; margin: 4px 2px;")
        
        btn_capture = QPushButton("📷")
        btn_capture.setToolTip("Neu vom Bildschirm aufnehmen")
        btn_capture.setObjectName("btn_capture_new")
        btn_capture.setFixedSize(32, 32)
        btn_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_capture.clicked.connect(self._neue_aufnahme_starten)

        for btn in [self._btn_ignorieren, self._btn_klick, btn_roi, btn_ocr, btn_states]:
            tb_lay.addWidget(btn)
        tb_lay.addStretch()
        tb_lay.addWidget(line)
        tb_lay.addWidget(btn_capture)
        
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
        self.btn_var_prev.clicked.connect(self._variante_prev)

        self.var_label = QLabel("")
        self.var_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.var_label.setFixedWidth(100)
        self.var_label.setProperty("class", "lbl_info")

        self.btn_var_next = QPushButton("▶")
        self.btn_var_next.setObjectName("btn_sm")
        self.btn_var_next.clicked.connect(self._variante_next)

        self.btn_var_del = QPushButton("🗑")
        self.btn_var_del.setObjectName("btn_del_sm")
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
        self._schwellwert_slider = ClickStepSlider(Qt.Orientation.Horizontal)
        self._schwellwert_slider.setRange(50, 100)
        self._schwellwert_slider.setSingleStep(1)
        self._schwellwert_slider.setPageStep(1)
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

        self.smart_checkbox = QCheckBox("Smart Template")
        self.smart_checkbox.setProperty("class", "lbl_orange")
        self.smart_checkbox.setToolTip("Erlaubt das Finden mehrerer Instanzen und indexiert OCR-Bereiche (z.B. Name_1, Name_2).")
        hg_lay.addWidget(self.smart_checkbox)

        hg_lay.addStretch()
        root.addWidget(hg_widget)

        # ── Toleranz ──────────────────────────────────────────────────────────
        tol_widget = QWidget()
        tol_lay = QHBoxLayout(tol_widget)
        tol_lay.setContentsMargins(0, 4, 0, 0)
        tol_lay.setSpacing(8)

        lbl_tol = QLabel("Hintergrund-Toleranz:")
        lbl_tol.setProperty("class", "lbl_info")
        tol_lay.addWidget(lbl_tol)

        self._hg_tol_slider = ClickStepSlider(Qt.Orientation.Horizontal)
        self._hg_tol_slider.setRange(5, 80)
        self._hg_tol_slider.setSingleStep(1)
        self._hg_tol_slider.setPageStep(1)
        self._hg_tol_slider.setValue(30)
        self._hg_tol_slider.setFixedWidth(130)
        self._hg_tol_wert_lbl = QLabel("30")
        self._hg_tol_wert_lbl.setProperty("class", "lbl_info")
        self._hg_tol_slider.valueChanged.connect(lambda v: self._hg_tol_wert_lbl.setText(str(v)))
        self._hg_tol_slider.sliderReleased.connect(self._hg_vorschau_aktualisieren)

        tol_lay.addWidget(self._hg_tol_slider)
        tol_lay.addWidget(self._hg_tol_wert_lbl)
        tol_lay.addStretch()
        root.addWidget(tol_widget)

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
                self.smart_checkbox.setChecked(s.get("is_smart", False))
                v = s.get("hg_toleranz", 30)
                self._hg_tol_slider.setValue(v)
                self._hg_tol_wert_lbl.setText(str(v))
                cs = s.get("condition_states", [])
                self.condition_states = self._migrate_condition_states(cs)
                ss = s.get("set_states", {})
                self.set_states = dict(ss) if isinstance(ss, dict) else {}
                self.search_only = s.get("search_only", False)

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
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Variante löschen?")
        msg.setText(f"Variante \"{name}\" wirklich löschen?")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_nein)
        msg.exec()

        if msg.clickedButton() != btn_ja:
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
        self.smart_checkbox.setChecked(s.get("is_smart", False))
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
            condition_states=list(self.condition_states), set_states=dict(self.set_states),
            is_smart=self.smart_checkbox.isChecked())

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
        from ui.dialogs.gruppe_editor_qt import GruppeEditorQt
        
        name = self.bearbeiten_name or self.name_entry.text().strip() or "Unbenannt"
        bekannte = sorted(self.bot.app.state.game_states.keys())
        
        dlg = GruppeEditorQt(
            name, bekannte, 
            condition_states=list(self.condition_states), 
            set_states=dict(self.set_states),
            search_only=self.search_only,
            parent=self
        )
        
        def on_save(n, conditions, sets, search_only):
            self.condition_states = conditions
            self.set_states = sets
            self.search_only = search_only
            
        dlg.gespeichert.connect(on_save)
        dlg.exec()

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
                for r in self.ignore_regionen:
                    ix0, iy0, ix1, iy1 = [int(v) for v in r[:4]]
                    f = r[4] if len(r) > 4 else "box"
                    if f == "kreis":
                        cx, cy = (ix0 + ix1) // 2, (iy0 + iy1) // 2
                        rx, ry = abs(ix1 - ix0) // 2, abs(iy1 - iy0) // 2
                        cv2.ellipse(maske_raw, (cx, cy), (rx, ry), 0, 0, 360, 0, -1)
                    else:
                        maske_raw[max(0, iy0):iy1, max(0, ix0):ix1] = 0
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

            res, master_namen = self.template_engine.matches_suchen_np(snap_np)
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
                for r in self.ignore_regionen:
                    ix0, iy0, ix1, iy1 = r[:4]
                    f = r[4] if len(r) > 4 else "box"
                    if bbox:
                        bx, by, bw, bh = bbox
                        sx, sy = ab / bw, ah / bh
                        pixel_rects.append((
                            int((ix0 - bx) * sx), int((iy0 - by) * sy),
                            int((ix1 - bx) * sx), int((iy1 - by) * sy),
                            f
                        ))
                    else:
                        s = self.aktuell_skala
                        pixel_rects.append((
                            int(ix0 * s), int(iy0 * s),
                            int(ix1 * s), int(iy1 * s),
                            f
                        ))
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
            msg = QMessageBox(self)
            msg.setWindowTitle("Überschreiben?")
            msg.setText(f"'{n}' existiert bereits. Überschreiben?")
            msg.setIcon(QMessageBox.Icon.Question)
            btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
            btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
            msg.setDefaultButton(btn_nein)
            msg.exec()
            
            if msg.clickedButton() != btn_ja:
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
                ausschnitt_form=self.ausschnitt_form,
                search_only=self.search_only,
                is_smart=self.smart_checkbox.isChecked(),
            )

            if self.typ == "aktiv_gruppe" and (umbenennen or gruppe_geandert):
                self.template_engine.gruppe_umbenennen(
                    alter_name, n, neue_uebergeordnete_gruppe=uebergeordnet)
                orig_alter_name = alter_name
                self.bearbeiten_name = n
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen),
                    alter_name=orig_alter_name, **speichern_kwargs)
            elif umbenennen:
                self.template_engine.template_umbenennen(alter_name, n, gruppe_name)
                self.bot.ocr_engine.template_ocr_umbenennen(alter_name, n)
                orig_alter_name = alter_name
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
        
        # Fokus im Backend löschen
        if self.bot and hasattr(self.bot.app.state, "force_include"):
            if self.bearbeiten_name in self.bot.app.state.force_include:
                self.bot.app.state.force_include.remove(self.bearbeiten_name)

        if self.roi_editor:
            self.roi_editor.close()
        
        self.close()
        if self.einlern_modus_callback:
            self.einlern_modus_callback()

    def closeEvent(self, event):
        self.template_engine.template_loeschen("_tmp_preview")
        self.template_engine.templates.pop("test_match_preview", None)
        self.template_engine.settings.pop("test_match_preview", None)
        
        # Fokus im Backend löschen
        if self.bot and hasattr(self.bot.app.state, "force_include"):
            if self.bearbeiten_name in self.bot.app.state.force_include:
                self.bot.app.state.force_include.remove(self.bearbeiten_name)

        if self.roi_editor:
            self.roi_editor.close()
        
        if self.einlern_modus_callback:
            self.einlern_modus_callback()
        super().closeEvent(event)

    # ── Neue Aufnahme ────────────────────────────────────────────────────────

    def _neue_aufnahme_starten(self):
        """Minimiert den Editor und startet den Einlern-Modus im Hauptfenster."""
        self.showMinimized()
        if hasattr(self.parent(), "_einlern_modus_umschalten"):
            # Wir signalisieren dem Parent, dass wir ein neues Bild wollen
            # und setzen uns selbst als aktiven Editor.
            self.parent()._geplanter_typ = self.typ
            self.parent()._geplante_kategorie = self.kategorie
            self.parent()._einlern_editor = self
            self.parent()._einlern_modus_umschalten()

    def neues_bild_setzen(self, bild_pil: Image.Image):
        """Wird vom Hauptfenster aufgerufen, wenn ein neues Bild aufgenommen wurde."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        
        # Reset der Regionen (optional, meistens will man bei neuem Bild auch neue Regionen)
        self.ignore_regionen = []
        self.klick_zone = [None]
        self.klick_info.setText("Klick-Zone: nicht gesetzt")
        self.klick_info.setProperty("class", "lbl_dim")
        self.klick_info.setStyle(self.klick_info.style())
        
        tw, th = bild_pil.size
        self._vorschau_setzen(bild_pil, tw, th)
        self.bot._log("Neues Bild in Editor geladen.")
