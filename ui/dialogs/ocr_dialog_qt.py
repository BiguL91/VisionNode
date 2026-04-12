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
    from PIL import Image
    import numpy as np
except ImportError:
    Image = None
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
        if action == a_box: self._form = "box"
        elif action == a_kreis: self._form = "kreis"
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
        for i, e in enumerate(self._eintraege):
            if len(e) < 6: continue
            farbe = QColor(ZONE_FARBEN[i % len(ZONE_FARBEN)])
            cl, co, cr, cu = e[4], e[2], e[5], e[3]
            f = e[6] if len(e) > 6 else "box"
            x0 = int(cl / 100 * w)
            y0 = int(co / 100 * h)
            x1 = int((1 - cr / 100) * w)
            y1 = int((1 - cu / 100) * h)
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


# ── Haupt-Dialog ──────────────────────────────────────────────────────────────

class OCRKonfigDialog(QDialog):
    """Qt-Port des OCR-Konfigurations-Dialogs.

    Signals:
        gespeichert() — nach erfolgreichem Speichern
    """
    gespeichert = pyqtSignal()

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
        self._tw = 1
        self._th = 1
        self._template_pil = None
        self._vorschau_basis_pil = None
        self._target_color = [255, 255, 255]

        self._setup_ui()
        self._lade_template()
        self._lade_bestehende()

    # ── UI Aufbau ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Canvas in ScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas = OCRCanvas()
        self._canvas.auswahl_geaendert.connect(self._on_auswahl)
        scroll.setWidget(self._canvas)
        scroll.setFixedHeight(VORSCHAU_GROESSE + 4)
        root.addWidget(scroll)

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

        self._sb_toleranz = QSpinBox()
        self._sb_toleranz.setRange(5, 150)
        self._sb_toleranz.setValue(30)
        self._sb_toleranz.setPrefix("Tol: ")
        self._sb_toleranz.valueChanged.connect(self._ocr_vorschau_starten)
        cl.addWidget(self._sb_toleranz)
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

        btn_add = QPushButton("+ Hinzufügen")
        btn_add.setObjectName("btn_new")
        btn_add.clicked.connect(self._hinzufuegen)
        eingabe.addWidget(btn_add)
        root.addLayout(eingabe)

        # Tabelle bestehender Einträge
        self._tabelle_widget = QWidget()
        self._tabelle_layout = QVBoxLayout(self._tabelle_widget)
        self._tabelle_layout.setSpacing(2)
        self._tabelle_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._tabelle_widget)

        root.addStretch()

        # Footer
        footer = QHBoxLayout()
        self._live_btn = QPushButton("📍 Live wählen")
        self._live_btn.setObjectName("btn_live_select")
        self._live_btn.clicked.connect(self._live_focus)
        footer.addWidget(self._live_btn)
        footer.addStretch()

        btn_save = QPushButton("Speichern")
        btn_save.setObjectName("btn_new")
        btn_save.clicked.connect(self._final_speichern)
        footer.addWidget(btn_save)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _farbe_waehlen(self):
        c = QColorDialog.getColor(QColor(*self._target_color), self, "Filter-Farbe wählen")
        if c.isValid():
            self._target_color = [c.red(), c.green(), c.blue()]
            self._farbe_indicator.setStyleSheet(f"background: {c.name()}; border: 1px solid #555;")
            self._ocr_vorschau_starten()

    # ── Laden ────────────────────────────────────────────────────────────────

    def _lade_template(self):
        if Image is None:
            return
        import os
        te = self._bot.template_engine
        pfad = te.templates.get(self._name, {}).get("pfad") or os.path.join(
            "templates", f"{self._name}.png")
        try:
            pil = Image.open(pfad).convert("RGBA")
            bbox = te.templates.get(self._name, {}).get("bbox")
            if bbox:
                bx, by, bw, bh = bbox
                pil = pil.crop((bx, by, bx + bw, by + bh))
            self._template_pil = pil
            self._tw, self._th = pil.size
        except Exception:
            self._template_pil = None
            return

        # Scale to fit VORSCHAU_GROESSE
        tw, th = self._template_pil.size
        s = min(VORSCHAU_GROESSE / tw, VORSCHAU_GROESSE / th)
        nw, nh = int(tw * s), int(th * s)
        scaled = self._template_pil.resize((nw, nh), Image.LANCZOS)
        pm = _pil_to_qpixmap(scaled)
        self._canvas.set_pixmap(pm)

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
        # Clear
        while self._tabelle_layout.count():
            item = self._tabelle_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._canvas.set_eintraege(self._eintraege, self._tw, self._th)

        for i, e in enumerate(self._eintraege):
            zeile = QWidget()
            zl = QHBoxLayout(zeile)
            zl.setContentsMargins(4, 2, 4, 2)
            lbl = QLabel(e[0])
            lbl.setProperty("class", f"ocr_zone_{i % 6}")
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mouseReleaseEvent = lambda _, idx=i: self._laden(idx)
            zl.addWidget(lbl, 1)
            btn_del = QPushButton("✕")
            btn_del.setObjectName("btn_del")
            btn_del.setFixedSize(22, 22)
            btn_del.clicked.connect(lambda _, idx=i: self._loeschen(idx))
            zl.addWidget(btn_del)
            self._tabelle_layout.addWidget(zeile)

    def _laden(self, idx: int):
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
        self._sb_toleranz.setValue(e[12] if len(e) > 12 else 30)

        # Restore auswahl from crop percentages
        tw_disp = self._canvas.width()
        th_disp = self._canvas.height()
        cl, co, cr, cu = e[4], e[2], e[5], e[3]
        f = e[13] if len(e) > 13 else "box"
        x0 = int(cl / 100 * tw_disp)
        y0 = int(co / 100 * th_disp)
        x1 = int((1 - cr / 100) * tw_disp)
        y1 = int((1 - cu / 100) * th_disp)
        self._auswahl = (x0, y0, x1, y1, f)
        self._canvas.set_auswahl(self._auswahl)
        self._ocr_vorschau_starten()

    def _loeschen(self, idx: int):
        self._eintraege.pop(idx)
        self._tabelle_aktualisieren()

    # ── Interaktion ──────────────────────────────────────────────────────────

    def _on_auswahl(self, auswahl: tuple):
        self._auswahl = auswahl
        self._ocr_vorschau_starten()

    def _get_modus(self) -> str:
        btn = self._modus_grp.checkedButton()
        return btn.text() if btn else "Zahl"

    def _crop_prozent(self) -> tuple[float, float, float, float]:
        """Liefert (crop_links, crop_oben, crop_rechts, crop_unten) in % aus Auswahl."""
        if not self._auswahl:
            return 0.0, 0.0, 0.0, 0.0
        x0, y0, x1, y1 = self._auswahl[:4]
        tw = self._canvas.width()
        th = self._canvas.height()
        cl = round(x0 / tw * 100, 1)
        co = round(y0 / th * 100, 1)
        cr = round((tw - x1) / tw * 100, 1)
        cu = round((th - y1) / th * 100, 1)
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
            self._sb_toleranz.value(),
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
        parent = self.parent()
        if parent:
            parent.window().raise_()
            parent.window().activateWindow()

    def _ocr_vorschau_starten(self):
        if not self._auswahl or self._template_pil is None:
            return
        # Fire OCR in background thread
        cl, co, cr, cu = self._crop_prozent()
        af = self._auswahl[4] if len(self._auswahl) > 4 else "box"
        region = {
            "name": f"Vorschau_{self._name}",
            "x": 0, "y": 0,
            "breite": self._tw, "hoehe": self._th,
            "modus": self._get_modus(),
            "crop_oben": co, "crop_unten": cu,
            "crop_links": cl, "crop_rechts": cr,
            "contrast": self._sl_kontrast.value() / self._f_k,
            "brightness": self._sl_helligkeit.value() / self._f_h,
            "sharpness": self._sl_schaerfe.value() / self._f_s,
            "upscale": self._sl_upscale.value() / self._f_u,
            "color_filter": self._cb_farbe.isChecked(),
            "target_color": list(self._target_color),
            "color_tolerance": self._sb_toleranz.value(),
            "ausschnitt_form": af
        }
        pil_basis = self._template_pil

        def run():
            try:
                res, _ = self._bot.ocr_engine.region_scannen(pil_basis, region, debug=True)
                QTimer.singleShot(0, lambda: self._ocr_label.setText(
                    res if res else "—"
                ))
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

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
        self.close()
