"""
OCR-Konfigurations-Dialog (Qt) — Migriert von DialogeMixin._modus_dialog (tkinter).
Erlaubt das Konfigurieren von Crop-Bereichen & OCR-Parametern pro Template.
"""
from __future__ import annotations
import threading

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QRadioButton, QButtonGroup, QDoubleSpinBox, QSpinBox,
    QSlider, QFrame, QWidget, QScrollArea, QSizePolicy, QColorDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QImage, QFont

from ui.widgets.click_step_slider import ClickStepSlider


try:
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:
    Image = None
    ImageDraw = None
    np = None


# ── Farben für Zonen-Rechtecke ──────────────────────────────────────────────
ZONE_FARBEN = ["#ff5555", "#55aaff", "#55ff88", "#ffcc44", "#cc55ff", "#ff8844"]

VORSCHAU_GROESSE = 360


def _pil_to_qpixmap(pil_img) -> QPixmap:
    if pil_img is None:
        return QPixmap()
    rgb = pil_img.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes()
    qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ── Vorschau-Canvas ──────────────────────────────────────────────────────────

class OCRCanvas(QLabel):
    """Zeigt Template-Vorschau + eingetragene Zonen-Rechtecke.
    Maus-Drag erzeugt neue Auswahl.
    """
    auswahl_geaendert = pyqtSignal(tuple)  # (x0,y0,x1,y1, form) in canvas-koordinaten
    form_geaendert = pyqtSignal(str)       # "box" | "kreis"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ocr_canvas")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._pixmap: QPixmap = QPixmap()
        self._eintraege: list = []        # [(name,modus,co,cu,cl,cr, form), ...]
        self._auswahl: tuple | None = None
        self._drag_start = None
        self._drag_cur   = None
        self._form: str = "box"
        self._offset = (0, 0)
        self._orig_size = (1, 1)

    def set_template_info(self, offset: tuple, orig_size: tuple):
        """Setzt die Position und Größe des Templates innerhalb des aktuellen Hintergrunds."""
        self._offset = offset
        self._orig_size = orig_size
        self.update()

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        a_box = menu.addAction("■ Rechteck-Zone")
        a_kreis = menu.addAction("● Kreis-Zone")
        a_box.setCheckable(True)
        a_kreis.setCheckable(True)
        a_box.setChecked(self._form == "box")
        a_kreis.setChecked(self._form == "kreis")
        action = menu.exec(event.globalPos())
        if action == a_box: 
            self._form = "box"
            self.form_geaendert.emit(self._form)
        elif action == a_kreis: 
            self._form = "kreis"
            self.form_geaendert.emit(self._form)
        self.update()

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm
        self.setFixedSize(pm.width(), pm.height())
        self.update()

    def set_eintraege(self, eintraege: list, tw: int, th: int):
        self._eintraege = eintraege
        self._tw = tw
        self._th = th
        self.update()

    def set_auswahl(self, auswahl: tuple | None):
        self._auswahl = auswahl
        self.update()

    def _draw_checkerboard(self, painter, w, h):
        size = 8
        c1 = QColor("#1a1a1a")
        c2 = QColor("#242424")
        for y in range(0, h, size):
            for x in range(0, w, size):
                painter.fillRect(x, y, size, size, c1 if (x // size + y // size) % 2 == 0 else c2)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        
        # 1. Schachbrett
        self._draw_checkerboard(p, w, h)

        # 2. Bild
        if not self._pixmap.isNull():
            p.drawPixmap(0, 0, self._pixmap)

        # 3. Eingetragene Zonen
        # Skalierung zwischen 1:1 Hintergrund und Canvas
        # self._tw/th sind die 1:1 Größen des Hintergrunds (z.B. Captured Area)
        # w/h sind die aktuellen Canvas Größen (inkl. Zoom)
        sx = w / self._tw if self._tw > 0 else 1.0
        sy = h / self._th if self._th > 0 else 1.0
        
        ox, oy = self._offset
        otw, oth = self._orig_size

        for i, e in enumerate(self._eintraege):
            if len(e) < 6: continue
            farbe = QColor(ZONE_FARBEN[i % len(ZONE_FARBEN)])
            cl, co, cr, cu = e[4], e[2], e[5], e[3]
            f = e[13] if len(e) > 13 else (e[6] if len(e) > 6 and isinstance(e[6], str) else "box")
            
            # cl/co/cr/cu sind % relativ zum TEMPLATE (orig_size)
            # 1. Pixel-Koordinaten im 1:1 Template-Raum
            rel_x0 = cl / 100 * otw
            rel_y0 = co / 100 * oth
            rel_x1 = otw - (cr / 100 * otw)
            rel_y1 = oth - (cu / 100 * oth)
            
            # 2. Pixel-Koordinaten im 1:1 Hintergrund-Raum (Capture)
            bg_x0 = rel_x0 + ox
            bg_y0 = rel_y0 + oy
            bg_x1 = rel_x1 + ox
            bg_y1 = rel_y1 + oy
            
            # 3. Pixel-Koordinaten auf dem skalierten Canvas
            x0 = int(bg_x0 * sx)
            y0 = int(bg_y0 * sy)
            x1 = int(bg_x1 * sx)
            y1 = int(bg_y1 * sy)
            
            p.setPen(QPen(farbe, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if f == "kreis":
                p.drawEllipse(x0, y0, x1 - x0, y1 - y0)
            else:
                p.drawRect(x0, y0, x1 - x0, y1 - y0)
            p.setPen(farbe)
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(x0 + 2, y0 + 12, e[0])

        # 4. Aktuelle Auswahl
        if self._auswahl:
            ax0, ay0, ax1, ay1, af = self._auswahl
            p.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
            if af == "kreis":
                p.drawEllipse(ax0, ay0, ax1 - ax0, ay1 - ay0)
            else:
                p.drawRect(ax0, ay0, ax1 - ax0, ay1 - ay0)

        # 5. Live Drag
        if self._drag_start and self._drag_cur:
            x0 = min(self._drag_start[0], self._drag_cur[0])
            y0 = min(self._drag_start[1], self._drag_cur[1])
            x1 = max(self._drag_start[0], self._drag_cur[0])
            y1 = max(self._drag_start[1], self._drag_cur[1])
            p.setPen(QPen(QColor("#1e88e5"), 2, Qt.PenStyle.DashLine))
            if self._form == "kreis":
                p.drawEllipse(x0, y0, x1 - x0, y1 - y0)
            else:
                p.drawRect(x0, y0, x1 - x0, y1 - y0)

        p.end()

    def mousePressEvent(self, e):
        self._drag_start = (e.pos().x(), e.pos().y())
        self._drag_cur = self._drag_start
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag_start:
            self._drag_cur = (e.pos().x(), e.pos().y())
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._drag_start:
            return
        x0 = min(self._drag_start[0], e.pos().x())
        y0 = min(self._drag_start[1], e.pos().y())
        x1 = max(self._drag_start[0], e.pos().x())
        y1 = max(self._drag_start[1], e.pos().y())
        form = self._form
        self._drag_start = None
        self._drag_cur = None
        if abs(x1 - x0) > 4 and abs(y1 - y0) > 4:
            self._auswahl = (x0, y0, x1, y1, form)
            self.auswahl_geaendert.emit(self._auswahl)
        self.update()


# ── Debug-Fenster für Binarisierung ──────────────────────────────────────────

class OCRDebugWindow(QDialog):
    """Ein separates, schwebendes Fenster für das binarisierte OCR-Bild."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OCR Binarisierung (Debug)")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.resize(300, 100)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.label = QLabel("Warte auf Daten...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: #000; color: #555;")
        layout.addWidget(self.label)
        self._last_img = None

    def update_image(self, bin_img_np):
        if bin_img_np is None: return
        try:
            # Sicherheits-Kopie und Konvertierung
            # Wir stellen sicher, dass das Array im Speicher zusammenhängend ist
            img_data = np.ascontiguousarray(bin_img_np)
            h, w = img_data.shape[:2]
            
            if len(img_data.shape) == 2:
                # Graustufen (Binarisiert)
                qimg = QImage(img_data.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
            else:
                # BGR (Farbfilter)
                qimg = QImage(img_data.data, w, h, w*3, QImage.Format.Format_BGR888).copy()
            
            if qimg.isNull():
                print("[OCR-Debug] QImage konnte nicht erstellt werden!")
                return

            pm = QPixmap.fromImage(qimg)
            self.label.setPixmap(pm)
            self.setFixedSize(pm.width() + 10, pm.height() + 10)
            self.show()
            self.raise_()
        except Exception as e:
            print(f"[OCR-Debug] Fehler beim Bild-Update: {e}")


# ── Haupt-Dialog ──────────────────────────────────────────────────────────────

class OCRKonfigDialog(QDialog):
    """Qt-Port des OCR-Konfigurations-Dialogs.

    Signals:
        gespeichert() — nach erfolgreichem Speichern
        ocr_fertig(str, object) — (Ergebnis, Debug-Bild-Array)
    """
    gespeichert = pyqtSignal()
    ocr_fertig = pyqtSignal(str, object)

    def __init__(self, template_name: str, bot, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"OCR-Bereiche: {template_name}")
        self.setModal(False)
        self.resize(460, 640)
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
        self._target_color = [255, 255, 255]
        self._live_view_active = False
        
        # Separates Debug-Fenster für Binarisierung
        self._debug_window = OCRDebugWindow(self)

        self._setup_ui()
        self._lade_template()
        self._lade_bestehende()
        
        # Live-Update Timer (10 FPS für die Vorschau)
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._live_update_tick)
        self._live_timer.start(100)
        
        # Signal verbinden
        self.ocr_fertig.connect(self._on_ocr_fertig)

    # ── UI Aufbau ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header mit Bereichswahl, Reset und Zoom
        header = QHBoxLayout()
        self._cb_live_view = QCheckBox("Live-Vorschau")
        self._cb_live_view.setToolTip("Zeigt das aktuelle Live-Bild wenn das Template gefunden wird")
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

        header.addWidget(QLabel("Zoom:"))
        self._sl_zoom = QSlider(Qt.Orientation.Horizontal)
        self._sl_zoom.setRange(100, 400)
        self._sl_zoom.setValue(150)
        self._sl_zoom.setFixedWidth(80)
        self._sl_zoom.valueChanged.connect(lambda _: self._trigger_visual_refresh())
        header.addWidget(self._sl_zoom)
        root.addLayout(header)

        # Canvas in ScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas = OCRCanvas()
        self._canvas.auswahl_geaendert.connect(self._on_auswahl_canvas)
        self._canvas.form_geaendert.connect(self._on_form_changed)
        self._scroll.setWidget(self._canvas)
        self._scroll.setFixedHeight(VORSCHAU_GROESSE + 4)
        root.addWidget(self._scroll)
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
                print(f"[OCR-Capture] Template gefunden bei Offset: {self._live_offset}")
            else:
                # Wenn nicht gefunden, setzen wir Offset auf 0 (User muss selbst zielen)
                self._live_offset = (0, 0)
                print("[OCR-Capture] WARNUNG: Template nicht im gewählten Bereich gefunden!")

            # 3. Als neuen Hintergrund setzen
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
        if not self._live_view_active:
            # Zurück zum statischen Template/Capture
            self._trigger_visual_refresh()

    def _trigger_visual_refresh(self):
        """Erzwingt ein Neu-Laden des Bildes (statisch oder captured) mit aktuellem Zoom."""
        if self._template_pil is None:
            self._lade_template()
            return

        # Anzeige-Pixmap erstellen (Zoom berücksichtigen)
        z = self._sl_zoom.value() / 100.0
        nw, nh = int(self._tw * z), int(self._th * z)
        scaled = self._template_pil.resize((nw, nh), Image.LANCZOS)
        pm = _pil_to_qpixmap(scaled)
        
        # Canvas informieren über Offset und Original-Größe
        self._canvas.set_template_info(getattr(self, "_live_offset", (0,0)), (self._orig_tw, self._orig_th))
        self._canvas.set_pixmap(pm)

    def _live_update_tick(self):
        """Aktualisiert die Vorschau mit einem Live-Crop, falls gefunden."""
        if not self._live_view_active or self._bot.app.current_screenshot_pil is None:
            return

        matches = self._bot.app.state.active_matches
        found_match = None
        for m in matches:
            if m[0] == self._name or (len(m) > 6 and m[6] == self._name):
                found_match = m
                break
        
        if found_match:
            # Crop aus dem aktuellen Screenshot
            mx, my, mw, mh = found_match[1], found_match[2], found_match[3], found_match[4]
            try:
                # Da matches oft auf skalierten Bildern basieren oder Boxen haben:
                # Wir nehmen den Bereich des Matches
                pil_crop = self._bot.app.current_screenshot_pil.crop((mx, my, mx + mw, my + mh)).convert("RGB")
                
                # Wir müssen sicherstellen dass die Größe zum Canvas passt
                # (Normalerweise sollte ein Match die gleiche Größe wie das Template-Bild haben)
                # Falls das Template maskiert (bbox) ist, müssen wir das berücksichtigen
                te = self._bot.template_engine
                bbox = te.templates.get(self._name, {}).get("bbox")
                
                # Wenn wir hier ein Live-Bild haben, nutzen wir es für die Anzeige
                z = self._sl_zoom.value() / 100.0
                nw, nh = int(pil_crop.size[0] * z), int(pil_crop.size[1] * z)
                scaled = pil_crop.resize((nw, nh), Image.LANCZOS)
                pm = _pil_to_qpixmap(scaled)
                
                # Canvas informieren: Im Live-Crop ist das Template immer bei 0,0
                self._canvas.set_template_info((0, 0), (pil_crop.size[0], pil_crop.size[1]))
                self._canvas.set_pixmap(pm)
                
                # Auch für die Binarisierungsvorschau nutzen (optional, aber sinnvoll)
                self._vorschau_basis_pil = pil_crop
                self._ocr_vorschau_starten()
            except Exception as e:
                print(f"[OCR-Live] Fehler beim Croppen: {e}")

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
                v.get("ausschnitt_form", "box")
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
        
        # Grafik-Update im Canvas & OCR-Vorschau
        self._on_auswahl_tabelle(idx)

    def _loeschen(self, idx: int):
        self._eintraege.pop(idx)
        self._tabelle_aktualisieren()

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

        # Umrechnen: Prozente -> 1:1 Pixel im Template-Raum
        rel_x0 = cl / 100 * self._orig_tw
        rel_y0 = co / 100 * self._orig_th
        rel_x1 = self._orig_tw - (cr / 100 * self._orig_tw)
        rel_y1 = self._orig_th - (cu / 100 * self._orig_th)
        
        # Pixel im Hintergrund-Raum (Capture)
        ox, oy = getattr(self, "_live_offset", (0, 0))
        bg_x0 = rel_x0 + ox
        bg_y0 = rel_y0 + oy
        bg_x1 = rel_x1 + ox
        bg_y1 = rel_y1 + oy
        
        # Pixel auf dem Canvas (Zoom berücksichtigen)
        z = self._sl_zoom.value() / 100.0
        ax0 = int(bg_x0 * z)
        ay0 = int(bg_y0 * z)
        ax1 = int(bg_x1 * z)
        ay1 = int(bg_y1 * z)

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
        
        # Aktuelle Canvas-Größe (Zoomed)
        cw = self._canvas.width()
        ch = self._canvas.height()
        
        # Umrechnen in 1:1 Koordinaten des Hintergrund-Bildes (self._tw, self._th)
        bg_x0 = x0 / cw * self._tw
        bg_y0 = y0 / ch * self._th
        bg_x1 = x1 / cw * self._tw
        bg_y1 = y1 / ch * self._th
        
        # Relativ zum Template-Offset (wo fängt das Template im Hintergrund an?)
        off_x, off_y = getattr(self, "_live_offset", (0, 0))
        rel_x0 = bg_x0 - off_x
        rel_y0 = bg_y0 - off_y
        rel_x1 = bg_x1 - off_x
        rel_y1 = bg_y1 - off_y
        
        # Prozentual zur ORIGINAL-TEMPLATE-GRÖSSE
        # cl=0% bedeutet: Startet exakt am linken Rand des Templates
        cl = round(rel_x0 / self._orig_tw * 100, 1)
        co = round(rel_y0 / self._orig_th * 100, 1)
        cr = round((self._orig_tw - rel_x1) / self._orig_tw * 100, 1)
        cu = round((self._orig_th - rel_y1) / self._orig_th * 100, 1)
        
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
            af
        ]
        for i, e in enumerate(self._eintraege):
            if e[0] == n:
                self._eintraege[i] = neu
                self._tabelle_aktualisieren()
                return
        self._eintraege.append(neu)
        self._tabelle_aktualisieren()

    def _live_focus(self):
        """Hebt Grab auf damit die Live-Vorschau im Hauptfenster genutzt werden kann."""
        self.setWindowModality(Qt.WindowModality.NonModal)
        
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
        self._template_pil = None
        self._lade_template()

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
            matches = self._bot.app.state.active_matches
            found_match = None
            for m in matches:
                if m[0] == self._name or (len(m) > 6 and m[6] == self._name):
                    mx, my = m[1], m[2]
                    if x0 <= mx <= x1 and y0 <= my <= y1:
                        found_match = m
                        break
            
            offset = (0, 0)
            if found_match:
                offset = (found_match[1] - x0, found_match[2] - y0)
            
            # 3. SPEICHERN für Persistenz
            img_p = os.path.join(ref_dir, f"{self._name}.png")
            json_p = os.path.join(ref_dir, f"{self._name}.json")
            pil_crop.save(img_p)
            with open(json_p, "w", encoding="utf-8") as f:
                json.dump({"offset": offset}, f)

            # 4. Als neuen Hintergrund setzen
            self._live_offset = offset
            self._template_pil = pil_crop
            self._tw, self._th = pil_crop.size
            self._trigger_visual_refresh()
            
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception as e:
            print(f"[OCR-Capture] Fehler: {e}")

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
            self._trigger_visual_refresh()
        except Exception:
            self._template_pil = None
            return

    def _ocr_vorschau_starten(self):
        if not self._auswahl or self._template_pil is None:
            return
        
        # Fire OCR in background thread
        cl, co, cr, cu = self._crop_prozent()
        af = self._auswahl[4] if len(self._auswahl) > 4 else "box"
        
        # Offset berücksichtigen (Wo liegt das Template im aktuellen Hintergrund-Bild?)
        off_x, off_y = getattr(self, "_live_offset", (0, 0))

        region = {
            "name": f"Vorschau_{self._name}",
            "x": off_x, "y": off_y, # Startpunkt des Templates im Bild
            "breite": self._orig_tw, "hoehe": self._orig_th, # Echte Maße des Templates
            "modus": self._get_modus(),
            "crop_oben": co, "crop_unten": cu,
            "crop_links": cl, "crop_rechts": cr,
            "contrast": self._sl_kontrast.value() / self._f_k,
            "brightness": self._sl_helligkeit.value() / self._f_h,
            "sharpness": self._sl_schaerfe.value() / self._f_s,
            "upscale": self._sl_upscale.value() / self._f_u,
            "color_filter": self._cb_farbe.isChecked(),
            "target_color": list(self._target_color),
            "color_tolerance": self._sl_toleranz.value(),
            "ausschnitt_form": af
        }
        pil_basis = self._template_pil

        def run():
            try:
                res, debug_info = self._bot.ocr_engine.region_scannen(pil_basis, region, debug=True)
                # Signal senden
                self.ocr_fertig.emit(res, debug_info)
            except Exception as e:
                print(f"[OCR-Vorschau] Fehler: {e}")
                self.ocr_fertig.emit(f"Fehler: {e}", None)

        threading.Thread(target=run, daemon=True).start()

    def _on_ocr_fertig(self, res, d_info):
        """Wird im Haupt-Thread aufgerufen, wenn die OCR-Vorschau fertig ist."""
        self._ocr_label.setText(res if res else "—")
        
        if d_info and len(d_info) >= 5 and d_info[4] is not None:
            # Wir müssen das NumPy-Array kopieren, bevor es im Thread gelöscht wird
            bin_img_np = d_info[4].copy()
            self._debug_window.update_image(bin_img_np)
        else:
            self._debug_window.show()

    def closeEvent(self, event):
        """Wird aufgerufen, wenn der Dialog geschlossen wird."""
        if hasattr(self, "_debug_window"):
            self._debug_window.close()
        super().closeEvent(event)

    def _trigger_visual_refresh(self):
        """Erzwingt ein Neu-Laden des Bildes (statisch oder captured) mit aktuellem Zoom."""
        if self._template_pil is None:
            self._lade_template()
            return

        # Anzeige-Pixmap erstellen (Zoom berücksichtigen)
        z = self._sl_zoom.value() / 100.0
        nw, nh = int(self._tw * z), int(self._th * z)
        scaled = self._template_pil.resize((nw, nh), Image.LANCZOS)
        pm = _pil_to_qpixmap(scaled)
        self._canvas.set_pixmap(pm)

    def _final_speichern(self):
        """Speichert alle Einträge im OCR-Engine."""
        ocr = self._bot.ocr_engine
        prefix = f"{self._name}_"
        # Alte Einträge für dieses Template löschen
        for k, v in list(ocr.template_ocr_konfigurationen().items()):
            if v.get("template") == self._name:
                ocr.template_ocr_deaktivieren(k)
        # Neue Einträge registrieren
        for e in self._eintraege:
            n, m, co, cu, cl, cr, con, br, sh, up, cf, tc, ct = e[:13]
            af = e[13] if len(e) > 13 else "box"
            key = n if n.startswith(prefix) else f"{prefix}{n}"
            ocr.template_ocr_aktivieren(
                key, self._name, m,
                crop_oben=co, crop_unten=cu, crop_links=cl, crop_rechts=cr,
                contrast=con, brightness=br, sharpness=sh, upscale=up,
                color_filter=cf, target_color=tc, color_tolerance=ct,
                ausschnitt_form=af
            )
        self.gespeichert.emit()
        # self.close() # BLEIBT OFFEN AUF WUNSCH
