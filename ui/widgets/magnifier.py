from __future__ import annotations
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap, QPen, QColor, QRegion

class OCRMagnifier(QLabel):
    """Eine Lupe als separates, rahmenloses Fenster."""
    def __init__(self, size=160, zoom=4):
        super().__init__(None)  # Top-Level
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._size = size
        self._zoom = zoom
        self.setFixedSize(size, size)
        self.setObjectName("ocr_magnifier")
        self.setMask(QRegion(0, 0, size, size, QRegion.RegionType.Ellipse))
        self._pm = QPixmap()

    def update_view(self, pixmap, global_pos):
        self._pm = pixmap
        self.update()
        self.move(global_pos.x() + 25, global_pos.y() + 25)
        if not self.isVisible():
            self.show()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self._pm.isNull():
            p.drawPixmap(self.rect(), self._pm)
        m = self._size // 2
        # Gestrichelte Linien für das Fadenkreuz
        p.setPen(QPen(QColor(255, 255, 255, 150), 1, Qt.PenStyle.DashLine))
        p.drawLine(0, m, self._size, m)
        p.drawLine(m, 0, m, self._size)
        p.end()
