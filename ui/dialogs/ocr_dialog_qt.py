"""
OCR-Konfigurations-Dialog (Qt) — Migriert von DialogeMixin._modus_dialog (tkinter).
Erlaubt das Konfigurieren von Crop-Bereichen & OCR-Parametern pro Template.
"""
from __future__ import annotations
import threading

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QRadioButton, QButtonGroup, QDoubleSpinBox,
    QSlider, QFrame, QWidget, QScrollArea, QSizePolicy, QColorDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from PyQt6 import sip

from ui.widgets.click_step_slider import ClickStepSlider
from ui.widgets.ocr_widgets import (
    OCRMagnifier, OCRCanvas, OCRDebugWindow,
    ZONE_FARBEN, VORSCHAU_GROESSE, _pil_to_qpixmap,
)


try:
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:
    Image = None
    ImageDraw = None
    np = None


# ── Haupt-Dialog ──────────────────────────────────────────────────────────────

class OCRKonfigDialog(QDialog):
    """Qt-Port des OCR-Konfigurations-Dialogs.

    Signals:
        gespeichert() — nach erfolgreichem Speichern
        ocr_fertig(str, object, int) — (Ergebnis, Debug-Bild-Array, request_id)
    """
    gespeichert = pyqtSignal()
    ocr_fertig = pyqtSignal(str, object, int)

    def __init__(self, template_name: str, bot, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"OCR-Bereiche: {template_name}")
        self.setModal(False)
        self.resize(600, 800)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._name = template_name
        self._bot  = bot
        self._auswahl: tuple | None = None
        self._eintraege: list = []
        self._form = "box"
        self._tw = 1
        self._th = 1
        self._template_pil = None
        self._vorschau_basis_pil = None
        self._live_view_active = False
        self._live_offset = (0, 0)
        self._live_tm_size = (1, 1)
        self._target_color = [255, 255, 255]
        self._korrekturen_aktuell: list = []
        self._is_loading = False
        self._ocr_request_id = 0
        self._ocr_running = False # Flag gegen Thread-Stau
        self._ocr_pending = False # Neuer Request kam während OCR lief
        
        # Live-Update Timer
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._live_update_tick)

        # Separates Debug-Fenster für Binarisierung
        self._debug_window = OCRDebugWindow(self)

        self._setup_ui()
        self._lade_template()
        self._lade_bestehende()
        
        # Signal verbinden
        self.ocr_fertig.connect(self._on_ocr_fertig)

    # ── UI Aufbau ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header mit Bereichswahl, Reset
        header = QHBoxLayout()

        self._cb_live_view = QCheckBox("Live-Vorschau")
        self._cb_live_view.setToolTip("Nutzt das Live-Bild vom Bot für die OCR-Vorschau (Template muss im Bild gefunden werden)")
        self._cb_live_view.stateChanged.connect(self._on_live_view_toggled)
        header.addWidget(self._cb_live_view)

        self._btn_capture = QPushButton("📷 Bereich wählen")
        self._btn_capture.setToolTip("Wähle einen Bereich auf dem Hauptschirm.")
        self._btn_capture.clicked.connect(self._live_focus)
        header.addWidget(self._btn_capture)

        self._btn_reset_bg = QPushButton("↺ Reset")
        self._btn_reset_bg.setToolTip("Zurück zum Standard-Template-Bild (löscht benutzerdefinierten Bereich)")
        self._btn_reset_bg.setMinimumWidth(85)
        self._btn_reset_bg.clicked.connect(self._reset_background)
        header.addWidget(self._btn_reset_bg)

        header.addStretch()
        root.addLayout(header)

        # Canvas in ScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas = OCRCanvas()
        self._canvas.auswahl_geaendert.connect(self._on_auswahl_canvas)
        self._canvas.form_geaendert.connect(self._on_form_changed)
        self._scroll.setWidget(self._canvas)
        # self._scroll.setFixedHeight(VORSCHAU_GROESSE + 4) # FESTE HÖHE ENTFERNT
        root.addWidget(self._scroll, 1) # Streckt sich nun
        # OCR-Ergebnis Vorschau
        self._ocr_label = QLabel("—")
        self._ocr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ocr_label.setObjectName("ocr_preview_result")
        root.addWidget(self._ocr_label)

        # Parameter
        param_frame = QFrame()
        param_frame.setObjectName("group_box")
        pl = QVBoxLayout(param_frame)
        pl.setSpacing(10)

        def slider_block(label, lo, hi, step, default, factor=1.0):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(70)
            row.addWidget(lbl)

            val_lbl = QLabel(str(default))
            val_lbl.setFixedWidth(40)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_lbl.setObjectName("slider_value_label")

            sl = ClickStepSlider(Qt.Orientation.Horizontal)
            sl.setRange(int(lo * factor), int(hi * factor))
            sl.setValue(int(default * factor))
            sl.setSingleStep(1)
            sl.setPageStep(1)

            sl.valueChanged.connect(lambda v: val_lbl.setText(f"{v/factor:.1f}" if factor > 1 else str(v)))
            sl.valueChanged.connect(self._ocr_vorschau_starten)

            row.addWidget(sl)
            row.addWidget(val_lbl)
            return row, sl, factor

        r, self._sl_kontrast, self._f_k = slider_block("Kontrast", 0.5, 3.0, 0.1, 1.0, 10.0)
        pl.addLayout(r)
        r, self._sl_helligkeit, self._f_h = slider_block("Helligkeit", -100, 100, 5, 0, 1.0)
        pl.addLayout(r)
        r, self._sl_schaerfe, self._f_s = slider_block("Schärfe", 0.0, 5.0, 0.1, 1.0, 10.0)
        pl.addLayout(r)
        r, self._sl_upscale, self._f_u = slider_block("Upscale", 1.0, 8.0, 0.5, 5.0, 2.0)
        pl.addLayout(r)

        # Decoder
        decoder_row = QHBoxLayout()
        lbl_dec = QLabel("Decoder:")
        lbl_dec.setFixedWidth(70)
        decoder_row.addWidget(lbl_dec)
        self._decoder_grp = QButtonGroup(self)
        self._rb_greedy     = QRadioButton("Greedy")
        self._rb_beamsearch = QRadioButton("Beamsearch")
        self._rb_greedy.setChecked(True)
        self._decoder_grp.addButton(self._rb_greedy)
        self._decoder_grp.addButton(self._rb_beamsearch)
        decoder_row.addWidget(self._rb_greedy)
        decoder_row.addWidget(self._rb_beamsearch)
        self._lbl_bw = QLabel("Breite:")
        self._lbl_bw.setContentsMargins(8, 0, 0, 0)
        self._lbl_bw.setVisible(False)
        decoder_row.addWidget(self._lbl_bw)
        self._sl_beamwidth = ClickStepSlider(Qt.Orientation.Horizontal)
        self._sl_beamwidth.setRange(2, 20)
        self._sl_beamwidth.setValue(5)
        self._sl_beamwidth.setVisible(False)
        self._lbl_beamwidth = QLabel("5")
        self._lbl_beamwidth.setFixedWidth(25)
        self._lbl_beamwidth.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_beamwidth.setObjectName("slider_value_label")
        self._lbl_beamwidth.setVisible(False)
        self._sl_beamwidth.valueChanged.connect(lambda v: self._lbl_beamwidth.setText(str(v)))
        self._rb_beamsearch.toggled.connect(self._lbl_bw.setVisible)
        self._rb_beamsearch.toggled.connect(self._sl_beamwidth.setVisible)
        self._rb_beamsearch.toggled.connect(self._lbl_beamwidth.setVisible)
        decoder_row.addWidget(self._sl_beamwidth)
        decoder_row.addWidget(self._lbl_beamwidth)
        decoder_row.addStretch()
        pl.addLayout(decoder_row)

        # Blocklist
        blocklist_row = QHBoxLayout()
        lbl_bl = QLabel("Blocklist:")
        lbl_bl.setFixedWidth(70)
        blocklist_row.addWidget(lbl_bl)
        self._blocklist_edit = QLineEdit()
        self._blocklist_edit.setPlaceholderText("Zeichen sperren, z.B.  ]|[  (wirkt nur im Text-Modus)")
        blocklist_row.addWidget(self._blocklist_edit)
        pl.addLayout(blocklist_row)

        # Neue Checkbox für Binarisierung
        proc_row = QHBoxLayout()
        proc_row.setContentsMargins(70, 0, 0, 0)
        self._cb_adaptive = QCheckBox("Adaptives Thresholding")
        self._cb_adaptive.setToolTip("Berechnet Schwellenwerte lokal (besser bei Verläufen/Hintergründen)")
        self._cb_adaptive.stateChanged.connect(self._ocr_vorschau_starten)

        proc_row.addWidget(self._cb_adaptive)
        proc_row.addStretch()
        pl.addLayout(proc_row)

        root.addWidget(param_frame)

        # Farbfilter
        color_frame = QFrame()
        color_frame.setObjectName("group_box")
        cl = QHBoxLayout(color_frame)
        cl.setSpacing(8)

        self._cb_farbe = QCheckBox("Farbfilter")
        self._cb_farbe.stateChanged.connect(self._ocr_vorschau_starten)
        cl.addWidget(self._cb_farbe)

        self._farbe_indicator = QPushButton("      ")
        self._farbe_indicator.setObjectName("color_filter_indicator")
        self._farbe_indicator.setFixedSize(30, 20)
        self._farbe_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self._farbe_indicator.clicked.connect(self._farbe_waehlen)
        cl.addWidget(self._farbe_indicator)

        self._lbl_toleranz = QLabel("Tol: +/- 30")
        self._lbl_toleranz.setFixedWidth(75)
        cl.addWidget(self._lbl_toleranz)

        self._sl_toleranz = ClickStepSlider(Qt.Orientation.Horizontal)
        self._sl_toleranz.setRange(5, 150)
        self._sl_toleranz.setValue(30)
        self._sl_toleranz.setFixedWidth(100)
        self._sl_toleranz.valueChanged.connect(self._on_toleranz_changed)
        cl.addWidget(self._sl_toleranz)

        cl.addStretch()
        root.addWidget(color_frame)

        # Korrekturen
        korr_frame = QFrame()
        korr_frame.setObjectName("group_box")
        kl = QVBoxLayout(korr_frame)
        kl.setSpacing(4)
        kl.setContentsMargins(8, 6, 8, 6)

        korr_header = QHBoxLayout()
        korr_title = QLabel("Zeichenkorrekturen (aktive Zone):")
        korr_title.setObjectName("slider_value_label")
        korr_header.addWidget(korr_title)
        korr_header.addStretch()
        kl.addLayout(korr_header)

        self._korr_liste_widget = QWidget()
        self._korr_liste_layout = QVBoxLayout(self._korr_liste_widget)
        self._korr_liste_layout.setSpacing(2)
        self._korr_liste_layout.setContentsMargins(0, 0, 0, 0)

        korr_scroll = QScrollArea()
        korr_scroll.setWidgetResizable(True)
        korr_scroll.setFixedHeight(70)
        korr_scroll.setWidget(self._korr_liste_widget)
        korr_scroll.setObjectName("ocr_zones_scroll")
        kl.addWidget(korr_scroll)

        korr_add_row = QHBoxLayout()
        korr_add_row.setSpacing(4)
        self._korr_von = QLineEdit()
        self._korr_von.setPlaceholderText("von")
        self._korr_von.setFixedWidth(60)
        korr_add_row.addWidget(self._korr_von)
        korr_add_row.addWidget(QLabel("→"))
        self._korr_zu = QLineEdit()
        self._korr_zu.setPlaceholderText("zu")
        self._korr_zu.setFixedWidth(60)
        korr_add_row.addWidget(self._korr_zu)
        btn_korr_add = QPushButton("+ Hinzufügen")
        btn_korr_add.setObjectName("btn_new")
        btn_korr_add.clicked.connect(self._korrektur_hinzufuegen)
        korr_add_row.addWidget(btn_korr_add)
        korr_add_row.addStretch()
        kl.addLayout(korr_add_row)

        root.addWidget(korr_frame)

        # Eingabe: Name + Modus + Hinzufügen
        eingabe = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Zonenname...")
        eingabe.addWidget(self._name_edit, 2)

        self._modus_grp = QButtonGroup(self)
        for m in ["Timer", "Zahl", "Text"]:
            rb = QRadioButton(m)
            if m == "Zahl":
                rb.setChecked(True)
            self._modus_grp.addButton(rb)
            eingabe.addWidget(rb)

        self._btn_add = QPushButton("Aktualisieren")
        self._btn_add.setObjectName("btn_new")
        self._btn_add.clicked.connect(self._hinzufuegen)
        eingabe.addWidget(self._btn_add)
        root.addLayout(eingabe)

        # Tabelle bestehender Einträge
        self._tabelle_scroll = QScrollArea()
        self._tabelle_scroll.setWidgetResizable(True)
        self._tabelle_scroll.setFixedHeight(120)
        self._tabelle_scroll.setObjectName("ocr_zones_scroll")

        self._tabelle_widget = QWidget()
        self._tabelle_layout = QVBoxLayout(self._tabelle_widget)
        self._tabelle_layout.setSpacing(4)
        self._tabelle_layout.setContentsMargins(4, 4, 4, 4)
        self._tabelle_layout.addStretch() # Initial stretch

        self._tabelle_scroll.setWidget(self._tabelle_widget)
        root.addWidget(self._tabelle_scroll)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()

        btn_save = QPushButton("Speichern")
        btn_save.setObjectName("btn_new")
        btn_save.clicked.connect(self._final_speichern)
        footer.addWidget(btn_save)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _on_toleranz_changed(self, val):
        self._lbl_toleranz.setText(f"Tol: +/- {val}")
        self._ocr_vorschau_starten()

    def empfange_live_region(self, x0, y0, x1, y1):
        """Wird vom Hauptfenster aufgerufen, wenn dort ein Bereich gewählt wurde."""
        ss_pil = self._bot.app.current_screenshot_pil
        if ss_pil is None: return
        
        import os
        import json
        ref_dir = os.path.join("templates", "_ocr_refs")
        if not os.path.exists(ref_dir): os.makedirs(ref_dir)

        try:
            # 1. Den gewählten Bereich ausschneiden
            pil_crop = ss_pil.crop((x0, y0, x1, y1)).convert("RGB")
            
            # 2. Template in diesem Ausschnitt suchen, um Offset zu bestimmen
            # Wir suchen in den aktiven Matches des Bots
            matches = self._bot.app.state.active_matches
            found_match = None
            for m in matches:
                if m[0] == self._name or (len(m) > 6 and m[6] == self._name):
                    # Prüfen ob dieses Match innerhalb unserer x0,y0,x1,y1 Box liegt
                    mx, my = m[1], m[2]
                    if x0 <= mx <= x1 and y0 <= my <= y1:
                        found_match = m
                        break
            
            if found_match:
                # Offset: Wie weit ist das Template vom Crop-Rand entfernt?
                self._live_offset = (found_match[1] - x0, found_match[2] - y0)
                self._live_tm_size = (found_match[3], found_match[4]) # Match-Größe auf Screen
                print(f"[OCR-Capture] Template gefunden bei Offset: {self._live_offset}, Größe: {self._live_tm_size}")
            else:
                # Wenn nicht gefunden: Capture-Bereich selbst als Referenz nutzen
                self._live_offset = (0, 0)
                self._live_tm_size = (x1 - x0, y1 - y0)
                print("[OCR-Capture] WARNUNG: Template nicht im gewählten Bereich gefunden!")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Template nicht erkannt",
                    f"Das Template \"{self._name}\" wurde im gewählten Bereich nicht gefunden.\n\n"
                    "Möglicherweise ist der Bot gerade inaktiv oder das Template liegt außerhalb "
                    "des markierten Ausschnitts.\n\n"
                    "OCR-Zonen werden trotzdem relativ zum gewählten Ausschnitt definiert.",
                )

            # 3. SPEICHERN für Persistenz
            img_p = os.path.join(ref_dir, f"{self._name}.png")
            json_p = os.path.join(ref_dir, f"{self._name}.json")
            pil_crop.save(img_p)
            with open(json_p, "w", encoding="utf-8") as f:
                json.dump({"offset": self._live_offset, "tm_size": self._live_tm_size}, f)

            # 4. Als neuen Hintergrund setzen
            self._template_pil = pil_crop
            self._tw, self._th = pil_crop.size
            
            # Zoom anwenden und anzeigen
            self._trigger_visual_refresh()
            
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception as e:
            print(f"[OCR-Capture] Fehler: {e}")

    def _on_live_view_toggled(self, state):
        self._live_view_active = (state == Qt.CheckState.Checked.value)
        if self._live_view_active:
            self._live_timer.start(100) # 10 FPS
        else:
            self._live_timer.stop()
            self._vorschau_basis_pil = None
            self._trigger_visual_refresh()
            self._ocr_vorschau_starten() # OCR auf statischem Bild aktualisieren

    def _live_update_tick(self):
        """Aktualisiert die Vorschau mit einem Live-Bildausschnitt basierend auf dem Screenshot-Kontext."""
        if not self._live_view_active or self._bot.app.current_screenshot_pil is None:
            return

        # 1. Wo liegt das Template aktuell im Live-Bild?
        matches = self._bot.app.state.active_matches
        found_match = None
        for m in matches:
            if m[0] == self._name or (len(m) > 6 and m[6] == self._name):
                found_match = m
                break

        if found_match:
            mx, my = found_match[1], found_match[2]
            ox, oy = getattr(self, "_live_offset", (0, 0))
            sw, sh = self._tw, self._th

            crop_x = mx - ox
            crop_y = my - oy

            try:
                pil_crop = self._bot.app.current_screenshot_pil.crop(
                    (crop_x, crop_y, crop_x + sw, crop_y + sh)
                ).convert("RGB")

                # Canvas-Bild immer aktualisieren (kein OCR-Overhead, kein Flackern)
                pm = _pil_to_qpixmap(pil_crop)
                tm_size = getattr(self, "_live_tm_size", (self._orig_tw, self._orig_th))
                self._canvas.set_template_info((ox, oy), tm_size)
                self._canvas.set_pixmap(pm)
                self._canvas.setFixedSize(sw, sh)

                # OCR-Basis aktualisieren und OCR nur starten wenn kein Lauf aktiv
                self._vorschau_basis_pil = pil_crop
                if not self._ocr_running:
                    self._ocr_vorschau_starten()
            except Exception:
                pass

    def _farbe_waehlen(self):
        c = QColorDialog.getColor(QColor(*self._target_color), self, "Filter-Farbe wählen")
        if c.isValid():
            self._target_color = [c.red(), c.green(), c.blue()]
            self._farbe_indicator.setStyleSheet(f"background: {c.name()}; border: 1px solid #555;")
            self._ocr_vorschau_starten()

    # ── Laden ────────────────────────────────────────────────────────────────

    def _lade_bestehende(self):
        prefix = f"{self._name}_"
        for k, v in self._bot.ocr_engine.template_ocr_konfigurationen().items():
            if v.get("template") != self._name:
                continue
            display_n = k[len(prefix):] if k.startswith(prefix) else k
            self._eintraege.append([
                display_n,
                v.get("modus", "Zahl"),
                v.get("crop_oben", 0),
                v.get("crop_unten", 0),
                v.get("crop_links", 0),
                v.get("crop_rechts", 0),
                v.get("contrast", 1.0),
                v.get("brightness", 0),
                v.get("sharpness", 1.0),
                v.get("upscale", 5.0),
                v.get("color_filter", False),
                v.get("target_color", [255, 255, 255]),
                v.get("color_tolerance", 30),
                v.get("ausschnitt_form", "box"),
                v.get("korrekturen", []),        # index 14
                v.get("decoder", "greedy"),      # index 15
                v.get("beamWidth", 5),           # index 16
                v.get("blocklist", ""),          # index 17
                v.get("adaptive_threshold", v.get("adaptive_threshold", v.get("modus") in ["Timer", "Zahl"])) # index 18
            ])
        self._tabelle_aktualisieren()

    # ── Tabelle ──────────────────────────────────────────────────────────────

    def _tabelle_aktualisieren(self):
        # Layout komplett leeren
        while self._tabelle_layout.count():
            item = self._tabelle_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._canvas.set_eintraege(self._eintraege, self._tw, self._th)

        for i in range(len(self._eintraege)):
            e = self._eintraege[i]
            zeile = QFrame()
            zeile.setObjectName("ocr_zone_row")
            zl = QHBoxLayout(zeile)
            zl.setContentsMargins(8, 4, 8, 4)
            zl.setSpacing(10)

            # Name / Label
            lbl = QLabel(e[0])
            lbl.setProperty("class", f"ocr_zone_{i % 6}")
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            # WICHTIG: i als Default-Argument binden!
            lbl.mouseReleaseEvent = lambda _, idx=i: self._laden(idx)
            zl.addWidget(lbl, 1)

            # Modus Badge
            modus_lbl = QLabel(str(e[1]))
            modus_lbl.setObjectName("ocr_modus_badge")
            zl.addWidget(modus_lbl)

            # Löschen Button
            btn_del = QPushButton("✕")
            btn_del.setObjectName("btn_del_sm")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.clicked.connect(lambda _, idx=i: self._loeschen(idx))
            zl.addWidget(btn_del)

            self._tabelle_layout.addWidget(zeile)
        
        self._tabelle_layout.addStretch()

    def _laden(self, idx: int):
        if idx >= len(self._eintraege): return
        e = self._eintraege[idx]
        
        self._is_loading = True
        try:
            self._name_edit.setText(e[0])
            # set modus
            for btn in self._modus_grp.buttons():
                if btn.text() == e[1]:
                    btn.setChecked(True)
            self._sl_kontrast.setValue(int(e[6] * self._f_k))
            self._sl_helligkeit.setValue(int(e[7] * self._f_h))
            self._sl_schaerfe.setValue(int(e[8] * self._f_s))
            self._sl_upscale.setValue(int(e[9] * self._f_u))
            self._cb_farbe.setChecked(e[10])
            
            if len(e) > 11:
                self._target_color = list(e[11])
                self._farbe_indicator.setStyleSheet(f"background: {QColor(*self._target_color).name()}; border: 1px solid #555;")
            self._sl_toleranz.setValue(e[12] if len(e) > 12 else 30)
            self._korrekturen_aktuell = list(e[14]) if len(e) > 14 else []
            self._korrekturen_aktualisieren()
            decoder = e[15] if len(e) > 15 else "greedy"
            if decoder == "beamsearch":
                self._rb_beamsearch.setChecked(True)  # toggled-Signal zeigt Slider automatisch
            else:
                self._rb_greedy.setChecked(True)      # toggled-Signal versteckt Slider automatisch
            self._sl_beamwidth.setValue(e[16] if len(e) > 16 else 5)
            self._blocklist_edit.setText(e[17] if len(e) > 17 else "")
        finally:
            self._is_loading = False
        
        # Grafik-Update im Canvas & OCR-Vorschau
        self._on_auswahl_tabelle(idx)

    def _loeschen(self, idx: int):
        self._eintraege.pop(idx)
        self._tabelle_aktualisieren()
        self._final_speichern() # Sofort persistent speichern

    # ── Korrekturen ──────────────────────────────────────────────────────────

    def _korrektur_hinzufuegen(self):
        von = self._korr_von.text()
        zu  = self._korr_zu.text()
        if not von:
            return
        # Duplikat überschreiben
        for k in self._korrekturen_aktuell:
            if k["von"] == von:
                k["zu"] = zu
                self._korrekturen_aktualisieren()
                return
        self._korrekturen_aktuell.append({"von": von, "zu": zu})
        self._korr_von.clear()
        self._korr_zu.clear()
        self._korrekturen_aktualisieren()

    def _korrektur_loeschen(self, idx: int):
        self._korrekturen_aktuell.pop(idx)
        self._korrekturen_aktualisieren()

    def _korrekturen_aktualisieren(self):
        while self._korr_liste_layout.count():
            item = self._korr_liste_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, k in enumerate(self._korrekturen_aktuell):
            zeile = QWidget()
            zl = QHBoxLayout(zeile)
            zl.setContentsMargins(0, 0, 0, 0)
            zl.setSpacing(4)
            zl.addWidget(QLabel(f'"{k["von"]}"  →  "{k["zu"]}"'))
            zl.addStretch()
            btn = QPushButton("✕")
            btn.setObjectName("btn_del_sm")
            btn.setFixedSize(22, 18)
            btn.clicked.connect(lambda _, idx=i: self._korrektur_loeschen(idx))
            zl.addWidget(btn)
            self._korr_liste_layout.addWidget(zeile)

        self._korr_liste_layout.addStretch()

    # ── Interaktion ──────────────────────────────────────────────────────────

    def _on_auswahl_canvas(self, auswahl: tuple):
        """Wird vom Canvas emittiert bei Maus-Aktionen."""
        self._auswahl = auswahl
        self._ocr_vorschau_starten()

    def _on_auswahl_tabelle(self, idx: int):
        """Wird aufgerufen, wenn ein Eintrag in der Tabelle angeklickt wird."""
        if idx >= len(self._eintraege): return
        e = self._eintraege[idx]
        
        # Prozentsätze: oben, unten, links, rechts
        co, cu, cl, cr = e[2], e[3], e[4], e[5]
        form = e[13] if len(e) > 13 else (e[6] if len(e) > 6 and isinstance(e[6], str) else "box")

        # Aktuelle Referenz-Größe für die Umrechnung (Prozent -> Pixel)
        tw_eff, th_eff = getattr(self, "_live_tm_size", (self._orig_tw, self._orig_th))

        # Umrechnen: Prozente -> 1:1 Pixel im Template-Raum (effektiv)
        rel_x0 = cl / 100 * tw_eff
        rel_y0 = co / 100 * th_eff
        rel_x1 = tw_eff - (cr / 100 * tw_eff)
        rel_y1 = th_eff - (cu / 100 * th_eff)
        
        # Pixel im Hintergrund-Raum (Capture)
        ox, oy = getattr(self, "_live_offset", (0, 0))
        bg_x0 = rel_x0 + ox
        bg_y0 = rel_y0 + oy
        bg_x1 = rel_x1 + ox
        bg_y1 = rel_y1 + oy
        
        # Pixel auf dem Canvas (Ohne Zoom)
        ax0 = int(bg_x0)
        ay0 = int(bg_y0)
        ax1 = int(bg_x1)
        ay1 = int(bg_y1)

        self._auswahl = (ax0, ay0, ax1, ay1, form)
        self._canvas.set_auswahl(self._auswahl)
        self._ocr_vorschau_starten()

    def _on_form_changed(self, form: str):
        self._form = form
        if self._auswahl:
            # Bestehende Auswahl auf neue Form umstellen
            self._auswahl = self._auswahl[:4] + (form,)
            self._canvas.set_auswahl(self._auswahl)
            self._ocr_vorschau_starten()

    def _get_modus(self) -> str:
        btn = self._modus_grp.checkedButton()
        return btn.text() if btn else "Zahl"

    def _crop_prozent(self) -> tuple[float, float, float, float]:
        """Liefert (crop_links, crop_oben, crop_rechts, crop_unten) in % relativ zum Template."""
        if not self._auswahl:
            return 0.0, 0.0, 0.0, 0.0
        x0, y0, x1, y1 = self._auswahl[:4]
        
        # Da Canvas und Hintergrund nun 1:1 sind, sind x0/y0 direkt die bg_ Koordinaten
        bg_x0 = x0
        bg_y0 = y0
        bg_x1 = x1
        bg_y1 = y1
        
        # Relativ zum Template-Offset (wo fängt das Template im Hintergrund an?)
        off_x, off_y = getattr(self, "_live_offset", (0, 0))
        rel_x0 = bg_x0 - off_x
        rel_y0 = bg_y0 - off_y
        rel_x1 = bg_x1 - off_x
        rel_y1 = bg_y1 - off_y
        
        # Aktuelle Referenz-Größe für die Prozent-Berechnung
        # Wenn wir im Capture-Modus sind, ist das die Match-Größe auf dem Screen
        # Wenn wir im PNG-Modus sind, ist es die Original-Größe
        tw_eff, th_eff = getattr(self, "_live_tm_size", (self._orig_tw, self._orig_th))

        # Prozentual zur EFFEKTIVEN GRÖSSE
        cl = round(rel_x0 / tw_eff * 100, 1)
        co = round(rel_y0 / th_eff * 100, 1)
        cr = round((tw_eff - rel_x1) / tw_eff * 100, 1)
        cu = round((th_eff - rel_y1) / th_eff * 100, 1)
        
        return cl, co, cr, cu

    def _hinzufuegen(self):
        n = self._name_edit.text().strip()
        if not n or not self._auswahl:
            return
        cl, co, cr, cu = self._crop_prozent()
        af = self._auswahl[4] if len(self._auswahl) > 4 else "box"
        neu = [
            n,
            self._get_modus(),
            co, cu, cl, cr,
            self._sl_kontrast.value() / self._f_k,
            self._sl_helligkeit.value() / self._f_h,
            self._sl_schaerfe.value() / self._f_s,
            self._sl_upscale.value() / self._f_u,
            self._cb_farbe.isChecked(),
            list(self._target_color),
            self._sl_toleranz.value(),
            af,
            list(self._korrekturen_aktuell),                                       # index 14
            "beamsearch" if self._rb_beamsearch.isChecked() else "greedy",         # index 15
            self._sl_beamwidth.value(),                                           # index 16
            self._blocklist_edit.text().strip(),                                    # index 17
        ]
        for i, e in enumerate(self._eintraege):
            if e[0] == n:
                self._eintraege[i] = neu
                self._tabelle_aktualisieren()
                self._final_speichern() # Automatisch persistent speichern
                return
        self._eintraege.append(neu)
        self._tabelle_aktualisieren()
        self._final_speichern() # Automatisch persistent speichern

    def _live_focus(self):
        """Hebt Grab auf damit die Live-Vorschau im Hauptfenster genutzt werden kann."""
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.hide() # Dialog ausblenden damit er die Sicht nicht versperrt
        
        # Wir registrieren uns als Empfänger für die nächste OCR-Region-Wahl
        if hasattr(self._bot, "set_live_ocr_receiver"):
            self._bot.set_live_ocr_receiver(self)
        
        # Hauptfenster suchen und OCR-Modus dort aktivieren
        p = self.parent()
        while p and not hasattr(p, "_ocr_modus_umschalten"):
            p = p.parent()
        
        if p:
            if not getattr(p, "ocr_modus", False):
                p._ocr_modus_umschalten()
            p.window().raise_()
            p.window().activateWindow()

    def _reset_background(self):
        """Löscht den benutzerdefinierten Bereich und kehrt zum PNG zurück."""
        import os
        ref_dir = os.path.join("templates", "_ocr_refs")
        img_p = os.path.join(ref_dir, f"{self._name}.png")
        json_p = os.path.join(ref_dir, f"{self._name}.json")
        
        if os.path.exists(img_p): os.remove(img_p)
        if os.path.exists(json_p): os.remove(json_p)
        
        self._live_offset = (0, 0)
        self._live_tm_size = (self._orig_tw, self._orig_th)
        self._template_pil = None
        self._lade_template()

    def _lade_template(self):
        if Image is None:
            return
        import os
        import json
        te = self._bot.template_engine
        
        # Original-Größe aus Engine holen
        tpl_data = te.templates.get(self._name)
        if tpl_data:
            self._orig_tw, self._orig_th = tpl_data["orig_size"]
            if tpl_data.get("bbox"):
                self._orig_tw, self._orig_th = tpl_data["bbox"][2], tpl_data["bbox"][3]
        else:
            self._orig_tw, self._orig_th = 1, 1 # Fallback

        self._live_tm_size = (self._orig_tw, self._orig_th) # Default

        # 1. PRÜFEN OB REFERENZ-BILD EXISTIERT
        ref_dir = os.path.join("templates", "_ocr_refs")
        img_p = os.path.join(ref_dir, f"{self._name}.png")
        json_p = os.path.join(ref_dir, f"{self._name}.json")
        
        if os.path.exists(img_p) and os.path.exists(json_p):
            try:
                self._template_pil = Image.open(img_p).convert("RGB")
                with open(json_p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._live_offset = tuple(data.get("offset", (0, 0)))
                    if "tm_size" in data:
                        self._live_tm_size = tuple(data["tm_size"])
                self._tw, self._th = self._template_pil.size
                self._trigger_visual_refresh()
                return
            except Exception:
                pass

        # 2. FALLBACK AUF STANDARD-PNG
        pfad = te.templates.get(self._name, {}).get("pfad") or os.path.join(
            "templates", f"{self._name}.png")
        try:
            # ORIGINAL-PIXEL LADEN (RGBA)
            pil_orig = Image.open(pfad).convert("RGBA")
            
            # RAW-RGB EXTRAHIEREN (Alpha ignorieren)
            r, g, b, a = pil_orig.split()
            pil_view = Image.merge("RGB", (r, g, b))
            
            bbox = te.templates.get(self._name, {}).get("bbox")
            if bbox:
                bx, by, bw, bh = bbox
                pil_view = pil_view.crop((bx, by, bx + bw, by + bh))
            
            self._template_pil = pil_view
            self._tw, self._th = pil_view.size
            self._live_offset = (0, 0)
            self._live_tm_size = (self._orig_tw, self._orig_th)
            self._trigger_visual_refresh()
        except Exception:
            self._template_pil = None
            return

    def _ocr_vorschau_starten(self):
        if self._is_loading:
            return
        if not self._auswahl or (self._template_pil is None and self._vorschau_basis_pil is None):
            return
        if self._ocr_running:
            self._ocr_pending = True  # Merken: nach aktuellem Run nochmal starten
            return

        self._ocr_request_id += 1
        rid = self._ocr_request_id
        self._ocr_running = True
        self._ocr_pending = False

        # Fire OCR in background thread
        cl, co, cr, cu = self._crop_prozent()
        af = self._auswahl[4] if len(self._auswahl) > 4 else "box"
        
        # Upscale-Sicherheit für Texte (Vermeidung von RAM-Explosion)
        upscale = self._sl_upscale.value() / self._f_u
        if self._get_modus() == "Text" and upscale > 3.0:
            upscale = 3.0 # Deckelung für Text, da EasyOCR sonst ewig braucht

        # Offset berücksichtigen (Wo liegt das Template im aktuellen Hintergrund-Bild?)
        off_x, off_y = getattr(self, "_live_offset", (0, 0))
        tm_w, tm_h = self._live_tm_size

        region = {
            "name": f"Vorschau_{self._name}",
            "x": off_x, "y": off_y, # Startpunkt des Templates im Bild
            "breite": tm_w, "hoehe": tm_h, # Maße des Templates (effektiv)
            "modus": self._get_modus(),
            "crop_oben": co, "crop_unten": cu,
            "crop_links": cl, "crop_rechts": cr,
            "contrast": self._sl_kontrast.value() / self._f_k,
            "brightness": self._sl_helligkeit.value() / self._f_h,
            "sharpness": self._sl_schaerfe.value() / self._f_s,
            "upscale": upscale,
            "color_filter": self._cb_farbe.isChecked(),
            "target_color": list(self._target_color),
            "color_tolerance": self._sl_toleranz.value(),
            "ausschnitt_form": af
        }
        
        # Basis wählen: Entweder Live-Crop (wenn aktiv) oder gespeichertes Bild
        pil_basis = self._vorschau_basis_pil if (self._live_view_active and self._vorschau_basis_pil) else self._template_pil

        def run():
            try:
                res, debug_info = self._bot.ocr_engine.region_scannen(pil_basis, region, debug=True)
                if sip.isdeleted(self):
                    return
                # Signal senden
                self.ocr_fertig.emit(res, debug_info, rid)
            except Exception as e:
                print(f"[OCR-Vorschau] Fehler: {e}")
                if not sip.isdeleted(self):
                    self.ocr_fertig.emit(f"Fehler: {e}", None, rid)

        threading.Thread(target=run, daemon=True).start()

    def _on_ocr_fertig(self, res, d_info, rid):
        """Wird im Haupt-Thread aufgerufen, wenn die OCR-Vorschau fertig ist."""
        self._ocr_running = False  # Sperre aufheben

        if rid == self._ocr_request_id:
            ergebnis = res if res else "—"
            self._ocr_label.setText(ergebnis)
            self._canvas.set_ergebnis(ergebnis)

            if d_info and len(d_info) >= 5 and d_info[4] is not None:
                bin_img_np = d_info[4].copy()
                self._debug_window.update_image(bin_img_np)
            else:
                self._debug_window.update_image(None)

        # Wenn während des Laufs eine neue Anfrage kam, sofort nochmal starten
        if self._ocr_pending:
            self._ocr_vorschau_starten()

    def closeEvent(self, event):
        """Wird aufgerufen, wenn der Dialog geschlossen wird."""
        self._live_timer.stop()
        # Signal trennen bevor wir schließen — sonst öffnet ein laufender OCR-Thread
        # das Debug-Fenster via update_image()/show() nach dem Schließen wieder.
        try:
            self.ocr_fertig.disconnect(self._on_ocr_fertig)
        except RuntimeError:
            pass
        if hasattr(self, "_debug_window"):
            self._debug_window.hide()
            self._debug_window.close()
        if hasattr(self, "_canvas") and hasattr(self._canvas, "_magnifier"):
            self._canvas._magnifier.hide()
            self._canvas._magnifier.close()
        super().closeEvent(event)

    def _trigger_visual_refresh(self):
        """Erzwingt ein Neu-Laden des Bildes (statisch oder captured)."""
        if self._template_pil is None:
            self._lade_template()
            return

        # Anzeige-Pixmap erstellen (Originalgröße)
        nw, nh = self._tw, self._th
        pm = _pil_to_qpixmap(self._template_pil)
        
        # Canvas informieren über Offset und die Größe, die das Template auf dem Canvas hat
        # (Entweder Screen-Pixel vom Match oder Referenz-Pixel vom PNG)
        tm_size = getattr(self, "_live_tm_size", (self._orig_tw, self._orig_th))
        self._canvas.set_template_info(getattr(self, "_live_offset", (0,0)), tm_size)
        self._canvas.set_pixmap(pm)
        self._canvas.setFixedSize(nw, nh) # Größe fixieren damit ScrollArea sie kennt
        
        # Wir zwingen die ScrollArea auf die Bildgröße + kleiner Puffer für den Rahmen
        # Das verhindert, dass die ScrollArea vom Layout "erdrückt" wird.
        self._scroll.setMinimumSize(min(nw + 4, 1000), min(nh + 4, 800))
        
        # Dialog-Größe anpassen
        screen = self.screen().availableGeometry()
        
        # Erhöhter Puffer für die restliche UI (Slider, Tabelle, Margins)
        # 620px ist ein sicherer Wert für alle Elemente inklusive Abstände
        ui_height = 620 
        
        # Mindestbreite 750px für die Slider-Zeilen, damit diese nicht gequetscht wirken
        target_w = max(750, nw + 100)
        target_h = nh + ui_height
        
        # Grenzen des Bildschirms einhalten
        target_w = min(target_w, screen.width() - 40)
        target_h = min(target_h, screen.height() - 40)
        
        self.resize(target_w, target_h)
        # adjustSize() am Ende hilft Qt, die restlichen Abstände perfekt zu berechnen
        QTimer.singleShot(50, self.adjustSize)

    def _final_speichern(self):
        """Speichert alle Einträge im OCR-Engine persistent."""
        ocr = self._bot.ocr_engine
        prefix = f"{self._name}_"
        
        # 1. Aktuellen Stand aus der Engine/Datei laden
        konfig = dict(ocr.template_ocr_konfigurationen())
        
        # 2. Alle alten Einträge für dieses Template entfernen
        zu_entfernen = [k for k, v in konfig.items() if v.get("template") == self._name]
        for k in zu_entfernen:
            konfig.pop(k, None)
            
        # 3. Neue Einträge aus der UI-Liste hinzufügen
        for e in self._eintraege:
            if len(e) < 10: continue
            
            n = e[0]
            m = e[1]
            co, cu, cl, cr = e[2], e[3], e[4], e[5]
            con, br, sh, up = e[6], e[7], e[8], e[9]
            cf   = e[10] if len(e) > 10 else False
            tc   = e[11] if len(e) > 11 else [255, 255, 255]
            ct   = e[12] if len(e) > 12 else 30
            af   = e[13] if len(e) > 13 else "box"
            korr     = e[14] if len(e) > 14 else []
            decoder  = e[15] if len(e) > 15 else "greedy"
            beamw    = e[16] if len(e) > 16 else 5
            blocklist= e[17] if len(e) > 17 else ""

            key = n if n.startswith(prefix) else f"{prefix}{n}"
            konfig[key] = {
                "template":    self._name,
                "modus":       m,
                "crop_oben":   co,
                "crop_unten":  cu,
                "crop_links":  cl,
                "crop_rechts": cr,
                "contrast":    con,
                "brightness":  br,
                "sharpness":   sh,
                "upscale":     up,
                "color_filter": cf,
                "target_color": tc,
                "color_tolerance": ct,
                "ausschnitt_form": af,
                "korrekturen": korr,
                "decoder":     decoder,
                "beamWidth":   beamw,
                "blocklist":   blocklist,
            }

        # 4. Zurück an die Engine geben (die speichert es persistent)
        ocr._template_ocr_speichern(konfig)
        self.gespeichert.emit()
        # self.close() # BLEIBT OFFEN AUF WUNSCH
