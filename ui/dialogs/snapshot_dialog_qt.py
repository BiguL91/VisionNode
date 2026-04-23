from __future__ import annotations
import os
import time
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter

try:
    import cv2
except ImportError:
    cv2 = None

from ui.widgets.vorschau_label import _frame_to_qpixmap

class ScalablePreviewLabel(QLabel):
    """Ein Label, das sein Pixmap immer proportional auf die volle verfügbare Größe skaliert."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100) # Erlaubt das Verkleinern/Vergrößern

    def set_frame(self, frame_np):
        if frame_np is None:
            self._pixmap = None
        else:
            # Einmalig in QPixmap wandeln (volle Auflösung)
            h, w = frame_np.shape[:2]
            rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self._pixmap = QPixmap.fromImage(qimg)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap and not self._pixmap.isNull():
            # Berechne Skalierung unter Beibehaltung des Seitenverhältnisses
            sz = self._pixmap.size()
            sz.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            
            # Zentrieren
            x = (self.width() - sz.width()) // 2
            y = (self.height() - sz.height()) // 2
            
            painter.drawPixmap(QRect(x, y, sz.width(), sz.height()), self._pixmap)
        else:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Kein Bild")

class SnapshotDialog(QDialog):
    """Dialog zur Anzeige und Benennung eines Snapshots."""
    gespeichert = pyqtSignal(str, object) # Pfad, Frame

    def __init__(self, frame_np, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snapshot speichern")
        self.setObjectName("snapshot_dialog")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self.frame = frame_np
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Titel
        header = QLabel("Snapshot Vorschau")
        header.setObjectName("dialog_header_title_gold_small")
        layout.addWidget(header)

        # Bild-Vorschau (Nutzt das neue ScalablePreviewLabel)
        self.preview_label = ScalablePreviewLabel()
        self.preview_label.setStyleSheet("background-color: #111111; border: 1px solid #3d3d3d;")
        layout.addWidget(self.preview_label, stretch=1)
        self.preview_label.set_frame(self.frame)

        # Name Eingabe
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Dateiname:"))
        
        default_name = f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}"
        self.name_edit = QLineEdit(default_name)
        self.name_edit.setPlaceholderText("z.B. Hauptmenü_Offen")
        self.name_edit.selectAll()
        input_row.addWidget(self.name_edit)
        input_row.addWidget(QLabel(".png"))
        layout.addLayout(input_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Speichern")
        self.save_btn.setObjectName("btn_new")
        self.save_btn.clicked.connect(self._speichern)
        btn_row.addWidget(self.save_btn)

        layout.addLayout(btn_row)

        self.name_edit.setFocus()
        self.name_edit.returnPressed.connect(self._speichern)

    def _speichern(self):
        name = self.name_edit.text().strip()
        if not name: return

        os.makedirs("snapshots", exist_ok=True)
        safe_name = "".join([c for c in name if c.isalnum() or c in (" ", "_", "-")]).strip()
        pfad = os.path.join("snapshots", f"{safe_name}.png")

        if cv2 and self.frame is not None:
            cv2.imwrite(pfad, self.frame)
            self.gespeichert.emit(pfad, self.frame)
            self.accept()
