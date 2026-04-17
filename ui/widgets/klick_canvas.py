from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor


class KlickCanvas(QLabel):
    """Zeigt ein Template-Bild und erlaubt das Setzen eines Klick-Punkts per Mausklick."""
    klick_gesetzt = pyqtSignal(float, float)

    def __init__(self, pixmap):
        super().__init__()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._rx: float | None = None
        self._ry: float | None = None

    def set_punkt(self, rx: float, ry: float):
        """Setzt einen vorhandenen Klick-Punkt (relative Koordinaten 0–100)."""
        self._rx = rx
        self._ry = ry
        self.update()

    def mousePressEvent(self, e):
        self._rx = round(e.pos().x() / self.width()  * 100, 1)
        self._ry = round(e.pos().y() / self.height() * 100, 1)
        self.klick_gesetzt.emit(self._rx, self._ry)
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._rx is not None and self._ry is not None:
            p = QPainter(self)
            p.setPen(QPen(QColor("#ff6600"), 2))
            px = int(self._rx / 100 * self.width())
            py = int(self._ry / 100 * self.height())
            p.drawLine(px - 8, py, px + 8, py)
            p.drawLine(px, py - 8, px, py + 8)
            p.end()
