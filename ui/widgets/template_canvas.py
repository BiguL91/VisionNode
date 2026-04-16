"""
TemplateCanvas — Zeichenfläche für Template-Vorschau + Overlays.
Unterstützt Drag-to-draw für Ignorier-Regionen und Einzel-Klick für Klick-Zone.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]


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
    region_drawn  = pyqtSignal(tuple)        # (x0, y0, x1, y1, form) in Original-Koordinaten
    klick_gesetzt = pyqtSignal(float, float) # rel_x%, rel_y%

    def __init__(self, placeholder_text="", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setObjectName("template_canvas")
        self.setFixedSize(400, 200)

        self._placeholder_text = placeholder_text
        self._scaling: float = 1.0
        self._base_pixmap: QPixmap | None = None

        self._ignore_regionen: list[tuple] = []   # Original-Koordinaten
        self._ignore_pixel: list[tuple] | None = None  # Vorberechnete Pixel-Koordinaten

        self._klick_zone: tuple | None = None   # (rel_x%, rel_y%)
        self._drag_start: QPoint | None = None
        self._drag_end:   QPoint | None = None
        self._modus: str = "ignore"   # "ignore" | "klick"
        self._form:  str = "box"      # "box" | "kreis"

    def contextMenuEvent(self, event):
        if self._modus != "ignore":
            return
        menu = QMenu(self)
        a_box   = menu.addAction("■ Rechteck-Region")
        a_kreis = menu.addAction("● Kreis-Region")
        a_box.setCheckable(True)
        a_kreis.setCheckable(True)
        a_box.setChecked(self._form == "box")
        a_kreis.setChecked(self._form == "kreis")
        action = menu.exec(event.globalPos())
        if action == a_box:   self._form = "box"
        elif action == a_kreis: self._form = "kreis"
        self.update()

    def set_bild(self, pil_img, max_b: int = 1100, max_h: int = 320):
        sw, sh = pil_img.size
        s = min(min(max_b / sw, max_h / sh), 15.0)
        rw, rh = int(sw * s), int(sh * s)
        self._scaling = s
        disp = pil_img.resize((rw, rh), Image.NEAREST)
        if disp.mode == "RGBA":
            data = disp.tobytes("raw", "RGBA")
            qi = QImage(data, rw, rh, rw * 4, QImage.Format.Format_RGBA8888)
            self._base_pixmap = QPixmap.fromImage(qi)
        else:
            self._base_pixmap = _pil_to_qpixmap(disp)
        self.setFixedSize(rw, rh)
        self.update()
        return s, rw, rh

    def set_bild_skaliert(self, pil_img, target_w: int, target_h: int):
        """Setzt Bild auf exakt (target_w × target_h) — für HG-Canvas."""
        resized = pil_img.resize((target_w, target_h), Image.LANCZOS)
        if resized.mode == "RGBA":
            data = resized.tobytes("raw", "RGBA")
            qi = QImage(data, target_w, target_h, target_w * 4, QImage.Format.Format_RGBA8888)
            self._base_pixmap = QPixmap.fromImage(qi)
        else:
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
        self._klick_zone = None if rel_x is None else (rel_x, rel_y)
        self.update()

    def _draw_checkerboard(self, painter, w, h):
        size = 8
        c1, c2 = QColor("#1a1a1a"), QColor("#242424")
        for y in range(0, h, size):
            for x in range(0, w, size):
                painter.fillRect(x, y, size, size, c1 if (x // size + y // size) % 2 == 0 else c2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        self._draw_checkerboard(painter, w, h)

        if self._base_pixmap:
            painter.drawPixmap(0, 0, self._base_pixmap)
        else:
            painter.setPen(QColor("#555555"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, self._placeholder_text)

        s = self._scaling
        fill_ign = QColor(255, 68, 68, 80)
        pen_ign  = QPen(QColor("#ff4444"), 2)

        rects = []
        if self._ignore_pixel is not None:
            rects = self._ignore_pixel
        else:
            for r in self._ignore_regionen:
                ix0, iy0, ix1, iy1 = r[:4]
                f = r[4] if len(r) > 4 else "box"
                rects.append((int(ix0 * s), int(iy0 * s), int(ix1 * s), int(iy1 * s), f))

        painter.setPen(pen_ign)
        painter.setBrush(fill_ign)
        for r in rects:
            rx0, ry0, rx1, ry1 = r[:4]
            f = r[4] if len(r) > 4 else "box"
            if f == "kreis":
                painter.drawEllipse(rx0, ry0, rx1 - rx0, ry1 - ry0)
            else:
                painter.drawRect(rx0, ry0, rx1 - rx0, ry1 - ry0)

        if self._drag_start and self._drag_end:
            x0 = min(self._drag_start.x(), self._drag_end.x())
            y0 = min(self._drag_start.y(), self._drag_end.y())
            x1 = max(self._drag_start.x(), self._drag_end.x())
            y1 = max(self._drag_start.y(), self._drag_end.y())
            if self._form == "kreis":
                painter.drawEllipse(x0, y0, x1 - x0, y1 - y0)
            else:
                painter.drawRect(x0, y0, x1 - x0, y1 - y0)

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
                self.klick_gesetzt.emit(
                    round(event.pos().x() / w * 100, 1),
                    round(event.pos().y() / h * 100, 1),
                )
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
            self._drag_end   = None
            if abs(x1 - x0) >= 4 and abs(y1 - y0) >= 4:
                sw, sh = self.width(), self.height()
                ss = self._scaling
                reg = (
                    int(max(0, min(x0, x1)) / ss),
                    int(max(0, min(y0, y1)) / ss),
                    int(min(sw, max(x0, x1)) / ss),
                    int(min(sh, max(y0, y1)) / ss),
                    self._form,
                )
                self.region_drawn.emit(reg)
            self.update()
