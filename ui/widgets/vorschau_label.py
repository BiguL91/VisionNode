"""
VorschauLabel — Live-Preview Widget für das Hauptfenster.
Zeichnet Frame + Overlays (Match-Boxen, OCR-Regionen) via paintEvent.
Emittiert region_ausgewaehlt (x0, y0, x1, y1, form) bei Maus-Drag.
"""
from __future__ import annotations

import threading

from PyQt6.QtWidgets import QLabel, QSizePolicy, QMenu
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont

try:
    import cv2
except ImportError:
    cv2 = None

from core.helpers import _template_farbe
from ui.widgets.magnifier import OCRMagnifier


def _frame_to_qpixmap(frame_bgr, max_w: int, max_h: int) -> tuple:
    """BGR numpy → (QPixmap, skala, offset_x, offset_y). Wird von externen Dialogen genutzt."""
    if cv2 is None or frame_bgr is None:
        return QPixmap(), 1.0, 0.0, 0.0
    try:
        h, w = frame_bgr.shape[:2]
        skala = min(max_w / w, max_h / h)
        nw, nh = int(round(w * skala)), int(round(h * skala))
        if nw < 1 or nh < 1:
            return QPixmap(), 1.0, 0.0, 0.0
        resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, nw, nh, nw * 3, QImage.Format.Format_RGB888)
        pm = QPixmap.fromImage(qimg)
        ox = (max_w - nw) / 2.0
        oy = (max_h - nh) / 2.0
        return pm, skala, ox, oy
    except Exception:
        return QPixmap(), 1.0, 0.0, 0.0


def _render_overlay_image(
    max_w: int, max_h: int,
    skala: float, ox: float, oy: float,
    matches: list, ocr_regionen: dict, ocr_werte: dict,
    ocr_konf: dict, scanned_regions: list, show_roi: bool,
) -> "QImage | None":
    """Rendert alle Overlays in ein transparentes QImage.
    Läuft im _FrameWorker-Thread (QPainter auf QImage ist thread-sicher).
    Gibt None zurück wenn nichts zu zeichnen ist.
    """
    if not matches and not ocr_regionen and not (show_roi and scanned_regions):
        return None

    img = QImage(max_w, max_h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setFont(QFont("Segoe UI", 7))

    # 0. Gescannte Regionen (Debug)
    if show_roi and scanned_regions:
        p.setPen(QPen(QColor(255, 0, 255, 150), 1, Qt.PenStyle.SolidLine))
        p.setBrush(QColor(255, 0, 255, 20))
        for r in scanned_regions:
            rx0 = int(round(ox + r[0] * skala))
            ry0 = int(round(oy + r[1] * skala))
            rx1 = int(round(ox + r[2] * skala))
            ry1 = int(round(oy + r[3] * skala))
            p.drawRect(rx0, ry0, rx1 - rx0, ry1 - ry0)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # 1. Globale OCR-Regionen
    p.setPen(QPen(QColor("#ffca28"), 1, Qt.PenStyle.DashLine))
    for r_name, r in ocr_regionen.items():
        rx = int(round(ox + r["x"] * skala))
        ry = int(round(oy + r["y"] * skala))
        rw = int(round(r["breite"] * skala))
        rh = int(round(r["hoehe"] * skala))
        p.drawRect(rx, ry, rw, rh)
        val = ocr_werte.get(r_name, "")
        p.setPen(QColor("#ffca28"))
        p.drawText(rx + 2, ry + 12, f"{r_name}: {val}")
        p.setPen(QPen(QColor("#ffca28"), 1, Qt.PenStyle.DashLine))

    # 2. Template-OCR nach Template gruppieren
    ocr_by_tmpl: dict[str, list] = {}
    for k, cfg in ocr_konf.items():
        ocr_by_tmpl.setdefault(cfg.get("template", k), []).append(cfg)

    # 3. Matches
    for match in matches:
        name, mx, my, mw, mh, score = match[:6]
        farbe = QColor(_template_farbe(name))
        cx = int(round(ox + mx * skala))
        cy = int(round(oy + my * skala))
        cw = int(round(mw * skala))
        ch = int(round(mh * skala))
        p.setPen(QPen(farbe, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(cx, cy, cw, ch)
        p.setPen(farbe)
        p.drawText(cx + 2, max(cy - 2, 10), f"{name} {score:.2f}")

        for cfg in ocr_by_tmpl.get(name, []):
            cl = cfg.get("crop_links",  0) / 100
            co = cfg.get("crop_oben",   0) / 100
            cr = cfg.get("crop_rechts", 0) / 100
            cu = cfg.get("crop_unten",  0) / 100
            rx0 = int(round(ox + (mx + cl * mw) * skala))
            ry0 = int(round(oy + (my + co * mh) * skala))
            rx1 = int(round(ox + (mx + mw - cr * mw) * skala))
            ry1 = int(round(oy + (my + mh - cu * mh) * skala))
            p.setPen(QPen(QColor("#00bcd4"), 1, Qt.PenStyle.DashLine))
            if cfg.get("ausschnitt_form", "box") == "kreis":
                p.drawEllipse(rx0, ry0, rx1 - rx0, ry1 - ry0)
            else:
                p.drawRect(rx0, ry0, rx1 - rx0, ry1 - ry0)

    p.end()
    return img


class _FrameWorker(QThread):
    """Konvertiert BGR-Frames und rendert Overlays im Hintergrund.
    Kein Signal — Ergebnis liegt im Result-Slot.
    _display_tick liest den Slot und ruft repaint() direkt auf (funktioniert im Windows Modal-Loop).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._submit_lock = threading.Lock()
        self._result_lock = threading.Lock()
        self._pending = None
        self._result  = None          # (frame_QImage, overlay_QImage|None, skala, ox, oy)
        self._event   = threading.Event()
        self._running = True

    def submit(self, frame_bgr, max_w: int, max_h: int, overlay_data: tuple | None = None):
        with self._submit_lock:
            self._pending = (frame_bgr, max_w, max_h, overlay_data)
        self._event.set()

    def get_and_clear(self):
        """Gibt das letzte fertige Ergebnis zurück und leert den Slot (GUI-Thread)."""
        with self._result_lock:
            r = self._result
            self._result = None
            return r

    def run(self):
        while self._running:
            self._event.wait()
            self._event.clear()
            with self._submit_lock:
                task = self._pending
                self._pending = None
            if task is None:
                continue
            frame_bgr, max_w, max_h, overlay_data = task
            if cv2 is None or frame_bgr is None:
                continue
            try:
                h, w = frame_bgr.shape[:2]
                skala = min(max_w / w, max_h / h)
                nw, nh = int(round(w * skala)), int(round(h * skala))
                if nw < 1 or nh < 1:
                    continue
                resized    = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
                rgb        = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                frame_qimg = QImage(rgb.data, nw, nh, nw * 3, QImage.Format.Format_RGB888).copy()
                ox = (max_w - nw) / 2.0
                oy = (max_h - nh) / 2.0

                # Overlay im gleichen Hintergrund-Thread rendern (QPainter auf QImage ist thread-sicher)
                overlay_qimg = None
                if overlay_data is not None:
                    matches, ocr_regionen, ocr_werte, ocr_konf, scanned_regions, show_roi = overlay_data
                    overlay_qimg = _render_overlay_image(
                        max_w, max_h, skala, ox, oy,
                        matches, ocr_regionen, ocr_werte, ocr_konf, scanned_regions, show_roi,
                    )

                with self._result_lock:
                    self._result = (frame_qimg, overlay_qimg, skala, ox, oy)
            except Exception:
                with self._result_lock:
                    self._result = (frame_qimg, None, skala, ox, oy)

    def stop(self):
        self._running = False
        self._event.set()
        self.wait(300)


class VorschauLabel(QLabel):
    """Live-Preview Widget.
    - Zeichnet Frame + Overlays (Match-Boxen, OCR-Regionen) via paintEvent
    - Maus-Drag für Einlern-/OCR-Modus: emittiert region_ausgewaehlt
    - Direktsteuerung: emittiert direkt_klick / direkt_wischen für Interaktion
    """
    region_ausgewaehlt = pyqtSignal(int, int, int, int, str)  # orig x0,y0,x1,y1, form
    direkt_klick       = pyqtSignal(int, int)                # orig x, y
    direkt_wischen     = pyqtSignal(int, int, int, int)      # orig x0, y0, x1, y1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("preview")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)

        self._pixmap:         QPixmap | None = None
        self._overlay_pixmap: QPixmap | None = None
        self._skala:     float          = 1.0
        self._offset_x:  float          = 0.0
        self._offset_y:  float          = 0.0
        self._status:    str            = "Suche MEMUPlayer..."

        self._matches:        list  = []
        self._ocr_regionen:   dict  = {}
        self._ocr_werte:      dict  = {}
        self._ocr_konf:       dict  = {}
        self._scanned_regions: list = []
        self._show_roi:        bool = False

        self._aktiv:         bool          = False
        self._direkt_aktiv:  bool          = False
        self._form:          str           = "box"
        self._start:         QPoint | None = None
        self._current:       QPoint | None = None
        self._mouse_pos = QPoint(-100, -100)
        self._magnifier = OCRMagnifier(size=160, zoom=4)

        self._frame_worker = _FrameWorker(self)
        self._frame_worker.start()

    def contextMenuEvent(self, event):
        if not self._aktiv:
            return
        menu = QMenu(self)
        a_box   = menu.addAction("■ Rechteck-Ausschnitt")
        a_kreis = menu.addAction("● Kreis-Ausschnitt")
        a_box.setCheckable(True)
        a_kreis.setCheckable(True)
        a_box.setChecked(self._form == "box")
        a_kreis.setChecked(self._form == "kreis")
        action = menu.exec(event.globalPos())
        if action == a_box:   self._form = "box"
        elif action == a_kreis: self._form = "kreis"
        self.update()

    # ── Daten-Update ──────────────────────────────────────────────────────────

    def set_frame(self, frame_bgr, matches, ocr_regionen, ocr_werte, template_ocr_konf, scanned_regions=None, show_roi=False):
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return
        scanned_regions = scanned_regions or []
        self._matches         = matches
        self._ocr_regionen    = ocr_regionen
        self._ocr_werte       = ocr_werte
        self._ocr_konf        = template_ocr_konf
        self._scanned_regions = scanned_regions
        self._show_roi        = show_roi
        overlay_data = (matches, ocr_regionen, ocr_werte, template_ocr_konf, scanned_regions, show_roi)
        self._frame_worker.submit(frame_bgr, w, h, overlay_data)

    def apply_pending_frame(self):
        """Übernimmt Frame + Overlay vom Worker (GUI-Thread). Vor repaint() aufrufen."""
        result = self._frame_worker.get_and_clear()
        if result is None:
            return
        frame_qimg, overlay_qimg, skala, ox, oy = result
        self._pixmap         = QPixmap.fromImage(frame_qimg)
        self._overlay_pixmap = QPixmap.fromImage(overlay_qimg) if overlay_qimg is not None else None
        self._skala    = skala
        self._offset_x = ox
        self._offset_y = oy

    def set_status(self, text: str):
        self._status = text
        self._pixmap = None
        self.update()

    # ── Einlern-Modus ─────────────────────────────────────────────────────────

    def set_aktiv(self, aktiv: bool):
        self._aktiv   = aktiv
        self._start   = None
        self._current = None
        self.setMouseTracking(aktiv)
        self.setCursor(Qt.CursorShape.CrossCursor if (aktiv or self._direkt_aktiv) else Qt.CursorShape.ArrowCursor)
        if not aktiv:
            self._magnifier.hide()
        self.update()

    def set_direktsteuerung(self, aktiv: bool):
        self._direkt_aktiv = aktiv
        self._start        = None
        self._current      = None
        self.setCursor(Qt.CursorShape.CrossCursor if (aktiv or self._aktiv) else Qt.CursorShape.ArrowCursor)
        self.update()

    def _screen_to_orig(self, pos: QPoint) -> tuple[int, int]:
        return (
            int((pos.x() - self._offset_x) / self._skala),
            int((pos.y() - self._offset_y) / self._skala),
        )

    def mousePressEvent(self, e):
        if not self._aktiv and not self._direkt_aktiv:
            return
        self._mouse_pos = e.pos()
        self._start   = e.pos()
        self._current = e.pos()
        self.update()

    def mouseMoveEvent(self, e):
        self._mouse_pos = e.pos()
        if self._aktiv and self._start:
            self._current = e.pos()

        # Lupe nur im Einlern-Modus anzeigen
        if self._aktiv:
            m_zoom   = self._magnifier._zoom
            m_size   = self._magnifier._size
            src_size = m_size // m_zoom
            sx = e.pos().x() - src_size // 2
            sy = e.pos().y() - src_size // 2

            source_rect = QRect(sx, sy, src_size, src_size)
            full_crop = QPixmap(src_size, src_size)
            full_crop.fill(QColor("#1a1a1a"))

            p_crop = QPainter(full_crop)
            pix = self.grab(source_rect)
            p_crop.drawPixmap(0, 0, pix)
            p_crop.end()

            self._magnifier.update_view(full_crop, self.mapToGlobal(e.pos()))

        self.update()

    def leaveEvent(self, event):
        self._mouse_pos = QPoint(-100, -100)
        self._magnifier.hide()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, e):
        if (not self._aktiv and not self._direkt_aktiv) or not self._start:
            return
        x0, y0 = self._screen_to_orig(self._start)
        x1, y1 = self._screen_to_orig(e.pos())
        form = self._form
        self._start   = None
        self._current = None
        self.update()

        if self._aktiv:
            if abs(x1 - x0) > 4 and abs(y1 - y0) > 4:
                self.region_ausgewaehlt.emit(
                    min(x0, x1), min(y0, y1),
                    max(x0, x1), max(y0, y1),
                    form,
                )
        elif self._direkt_aktiv:
            dist = ((x1-x0)**2 + (y1-y0)**2)**0.5
            if dist > 10:
                self.direkt_wischen.emit(x0, y0, x1, y1)
            else:
                self.direkt_klick.emit(x1, y1)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pixmap:
            p.drawPixmap(int(round(self._offset_x)), int(round(self._offset_y)), self._pixmap)
            if self._overlay_pixmap:
                p.drawPixmap(0, 0, self._overlay_pixmap)
        else:
            p.setPen(QColor("#555555"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._status)

        if self._aktiv and self._start and self._current:
            is_kreis = (self._form == "kreis")
            color = QColor("#ffca28") if is_kreis else QColor("#1e88e5")
            p.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            x0 = min(self._start.x(), self._current.x())
            y0 = min(self._start.y(), self._current.y())
            x1 = max(self._start.x(), self._current.x())
            y1 = max(self._start.y(), self._current.y())
            if is_kreis:
                p.drawEllipse(x0, y0, x1 - x0, y1 - y0)
            else:
                p.drawRect(x0, y0, x1 - x0, y1 - y0)

        if self._aktiv and self.underMouse() and self._mouse_pos.x() >= 0:
            p.setPen(QPen(QColor(0, 255, 255, 120), 1, Qt.PenStyle.DashLine))
            p.drawLine(0, self._mouse_pos.y(), self.width(), self._mouse_pos.y())
            p.drawLine(self._mouse_pos.x(), 0, self._mouse_pos.x(), self.height())

        p.end()
