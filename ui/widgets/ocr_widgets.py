"""
OCR-Widgets — extrahiert aus ocr_dialog_qt.py.
Enthält OCRMagnifier, OCRCanvas, OCRDebugWindow sowie Hilfsfunktionen.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QDialog, QVBoxLayout, QMenu, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QPixmap, QImage, QFont,
    QPainterPath, QRegion,
)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

# ── Konstanten ────────────────────────────────────────────────────────────────
ZONE_FARBEN      = ["#ff5555", "#55aaff", "#55ff88", "#ffcc44", "#cc55ff", "#ff8844"]
VORSCHAU_GROESSE = 360


def _pil_to_qpixmap(pil_img) -> QPixmap:
    if pil_img is None:
        return QPixmap()
    rgb  = pil_img.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes()
    qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


from ui.widgets.magnifier import OCRMagnifier

# ── Canvas ────────────────────────────────────────────────────────────────────
class OCRCanvas(QLabel):
    """Widget zur Anzeige des Template-Bildes und Auswahl von Bereichen."""
    auswahl_geaendert = pyqtSignal(tuple)  # (x0,y0,x1,y1,form)
    form_geaendert    = pyqtSignal(str)    # "box" | "kreis"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ocr_canvas")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pixmap:    QPixmap      = QPixmap()
        self._img_w:     int          = 1
        self._img_h:     int          = 1
        self._eintraege: list         = []
        self._auswahl:   tuple | None = None
        self._drag_start              = None
        self._drag_cur                = None
        self._form:      str          = "box"
        self._offset     = (0, 0)
        self._orig_size  = (1, 1)
        self._mouse_pos  = QPoint(-100, -100)
        self._magnifier  = OCRMagnifier(size=160, zoom=4)
        self._ergebnis   = ""

    def sizeHint(self) -> QSize:
        return QSize(self._img_w, self._img_h)

    def minimumSizeHint(self) -> QSize:
        return QSize(150, 100)

    def _get_scale(self) -> float:
        """Gleichmäßiger Skalierungsfaktor Bild → Widget, nie größer als 1:1."""
        if self._img_w <= 0 or self._img_h <= 0:
            return 1.0
        return min(self.width() / self._img_w, self.height() / self._img_h, 1.0)

    def _clamp_to_image(self, x: float, y: float) -> tuple[float, float]:
        return max(0.0, min(float(self._img_w), x)), max(0.0, min(float(self._img_h), y))

    def set_template_info(self, offset: tuple, orig_size: tuple):
        self._offset    = offset
        self._orig_size = orig_size
        self.update()

    def contextMenuEvent(self, event):
        menu    = QMenu(self)
        a_box   = menu.addAction("■ Rechteck-Zone")
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
        if not pm.isNull():
            self._img_w = pm.width()
            self._img_h = pm.height()
            self.setMaximumSize(pm.width(), pm.height())
        self.updateGeometry()
        self.update()

    def set_eintraege(self, eintraege: list, tw: int, th: int):
        self._eintraege = eintraege
        self._tw = tw
        self._th = th
        self.update()

    def set_auswahl(self, auswahl: tuple | None):
        self._auswahl  = auswahl
        self._ergebnis = ""
        self.update()

    def set_ergebnis(self, text: str):
        self._ergebnis = text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#1a1a1a"))

        if not self._pixmap.isNull():
            s = self._get_scale()
            p.save()
            p.scale(s, s)

            p.drawPixmap(0, 0, self._pixmap)

            ox, oy   = self._offset
            otw, oth = self._orig_size
            for i, e in enumerate(self._eintraege):
                if len(e) < 6:
                    continue
                farbe = QColor(ZONE_FARBEN[i % len(ZONE_FARBEN)])
                cl, co, cr, cu = e[4], e[2], e[5], e[3]
                f = e[13] if len(e) > 13 else (e[6] if len(e) > 6 and isinstance(e[6], str) else "box")
                x0 = int(cl / 100 * otw + ox)
                y0 = int(co / 100 * oth + oy)
                x1 = int(otw - cr / 100 * otw + ox)
                y1 = int(oth - cu / 100 * oth + oy)
                p.setPen(QPen(farbe, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                if f == "kreis":
                    p.drawEllipse(x0, y0, x1 - x0, y1 - y0)
                else:
                    p.drawRect(x0, y0, x1 - x0, y1 - y0)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 180))
                p.drawRect(x0, y0 - 15, max(30, len(e[0]) * 7), 15)
                p.setPen(QColor(200, 200, 200))
                p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                p.drawText(x0 + 2, y0 - 3, e[0])

            if self._auswahl:
                ax0, ay0, ax1, ay1, af = self._auswahl
                ax0, ay0, ax1, ay1 = int(ax0), int(ay0), int(ax1), int(ay1)
                p.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
                if af == "kreis":
                    p.drawEllipse(ax0, ay0, ax1 - ax0, ay1 - ay0)
                else:
                    p.drawRect(ax0, ay0, ax1 - ax0, ay1 - ay0)
                if self._ergebnis:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(0, 0, 0, 220))
                    tw = len(self._ergebnis) * 8 + 20
                    p.drawRect(ax0, ay1 + 5, tw, 25)
                    p.setPen(QColor("#55ff88"))
                    p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                    p.drawText(ax0 + 5, ay1 + 22, self._ergebnis)

            if self._drag_start and self._drag_cur:
                x0 = int(min(self._drag_start[0], self._drag_cur[0]))
                y0 = int(min(self._drag_start[1], self._drag_cur[1]))
                x1 = int(max(self._drag_start[0], self._drag_cur[0]))
                y1 = int(max(self._drag_start[1], self._drag_cur[1]))
                p.setPen(QPen(QColor("#1e88e5"), 2, Qt.PenStyle.DashLine))
                if self._form == "kreis":
                    p.drawEllipse(x0, y0, x1 - x0, y1 - y0)
                else:
                    p.drawRect(x0, y0, x1 - x0, y1 - y0)

            p.restore()

        # Fadenkreuz in Widget-Koordinaten (kein Scale)
        if self.underMouse() and self._mouse_pos.x() >= 0:
            p.setPen(QPen(QColor(0, 255, 255, 120), 1, Qt.PenStyle.DashLine))
            p.drawLine(0, self._mouse_pos.y(), self.width(), self._mouse_pos.y())
            p.drawLine(self._mouse_pos.x(), 0, self._mouse_pos.x(), self.height())

        p.end()

    def mousePressEvent(self, e):
        s = self._get_scale()
        self._drag_start = self._clamp_to_image(e.pos().x() / s, e.pos().y() / s)
        self._drag_cur   = self._drag_start
        self._mouse_pos  = e.pos()
        self.update()

    def mouseMoveEvent(self, e):
        self._mouse_pos = e.pos()
        s = self._get_scale()
        if self._drag_start:
            self._drag_cur = self._clamp_to_image(e.pos().x() / s, e.pos().y() / s)
        if not self._pixmap.isNull():
            # Lupe aus dem skalierten Bild samplen
            scaled_pm = self._pixmap.scaled(
                int(self._img_w * s), int(self._img_h * s),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            m_zoom   = self._magnifier._zoom
            m_size   = self._magnifier._size
            src_size = m_size // m_zoom
            sx   = e.pos().x() - src_size // 2
            sy   = e.pos().y() - src_size // 2

            full_crop = QPixmap(src_size, src_size)
            p_crop = QPainter(full_crop)
            p_crop.fillRect(0, 0, src_size, src_size, QColor("#1a1a1a"))
            p_crop.drawPixmap(-sx, -sy, scaled_pm)
            p_crop.end()

            self._magnifier.update_view(full_crop, self.mapToGlobal(e.pos()))
        self.update()

    def leaveEvent(self, event):
        self._mouse_pos = QPoint(-100, -100)
        self._magnifier.hide()
        self.update()

    def mouseReleaseEvent(self, e):
        self._mouse_pos = e.pos()
        if not self._drag_start:
            return
        s = self._get_scale()
        ex, ey = self._clamp_to_image(e.pos().x() / s, e.pos().y() / s)
        x0 = min(self._drag_start[0], ex)
        y0 = min(self._drag_start[1], ey)
        x1 = max(self._drag_start[0], ex)
        y1 = max(self._drag_start[1], ey)
        form = self._form
        self._drag_start = None
        self._drag_cur   = None
        if (x1 - x0) * s > 4 and (y1 - y0) * s > 4:
            self._auswahl = (x0, y0, x1, y1, form)
            self.auswahl_geaendert.emit(self._auswahl)
        self.update()


# ── Debug-Fenster ─────────────────────────────────────────────────────────────
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
        self.label.setObjectName("ocr_debug_label")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self._last_img = None

    def update_image(self, bin_img_np):
        if bin_img_np is None:
            self.label.setText("Keine Bilddaten")
            self.label.setPixmap(QPixmap())
            return
        try:
            img_data = np.ascontiguousarray(bin_img_np)
            h, w     = img_data.shape[:2]
            if len(img_data.shape) == 2:
                qimg = QImage(img_data.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
            else:
                qimg = QImage(img_data.data, w, h, w * 3, QImage.Format.Format_BGR888).copy()
            if qimg.isNull():
                return
            pm = QPixmap.fromImage(qimg)
            self.label.setPixmap(pm)
            self.setFixedSize(pm.width() + 10, pm.height() + 10)
            self.show()
            self.raise_()
        except Exception as e:
            print(f"[OCR-Debug] Fehler beim Bild-Update: {e}")
