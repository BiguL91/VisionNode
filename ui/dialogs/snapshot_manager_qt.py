from __future__ import annotations
import os
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
    QLabel, QPushButton, QMessageBox, QSplitter, QFrame,
    QSizePolicy, QLineEdit
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
        self.setMinimumSize(100, 100)

    def set_frame(self, frame_np):
        if frame_np is None:
            self._pixmap = None
        elif isinstance(frame_np, np.ndarray):
            h, w = frame_np.shape[:2]
            rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self._pixmap = QPixmap.fromImage(qimg)
        elif isinstance(frame_np, QPixmap):
            self._pixmap = frame_np
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap and not self._pixmap.isNull():
            sz = self._pixmap.size()
            sz.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            x = (self.width() - sz.width()) // 2
            y = (self.height() - sz.height()) // 2
            painter.drawPixmap(QRect(x, y, sz.width(), sz.height()), self._pixmap)
        else:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Kein Bild")

class SnapshotManagerDialog(QDialog):
    """Dialog zum Verwalten oder Auswählen (Picker-Modus) von Snapshots."""
    bild_gewaehlt = pyqtSignal(str) # Pfad des gewählten Bildes (nur im Picker-Modus)

    def __init__(self, parent=None, picker_mode=False):
        super().__init__(parent)
        self.picker_mode = picker_mode
        self.setWindowTitle("Snapshots auswählen" if picker_mode else "Snapshots verwalten")
        self.setObjectName("snapshot_manager_dialog")
        self.setMinimumSize(950, 650)
        
        self.snapshot_dir = "snapshots"
        self._selected_path = None
        
        self._setup_ui()
        self._liste_aktualisieren()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        header_text = "Snapshot zur Bearbeitung wählen" if self.picker_mode else "Gespeicherte Snapshots"
        header = QLabel(header_text)
        header.setObjectName("dialog_header_title_gold_small")
        layout.addWidget(header)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Links: Liste
        left_widget = QFrame()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.liste = QListWidget()
        self.liste.currentRowChanged.connect(self._on_selection_changed)
        self.liste.itemDoubleClicked.connect(self._on_double_click)
        left_layout.addWidget(self.liste)
        
        self.splitter.addWidget(left_widget)
        
        # Rechts: Vorschau & Kontrolle
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        self.preview_label = ScalablePreviewLabel()
        self.preview_label.setStyleSheet("background-color: #0a0a0a; border: 1px solid #3d3d3d;")
        right_layout.addWidget(self.preview_label, stretch=1)
        
        # Untere Leiste (Kontext-abhängig)
        self.controls_stack = QFrame()
        ctrl_layout = QVBoxLayout(self.controls_stack)
        ctrl_layout.setContentsMargins(0, 5, 0, 0)

        if self.picker_mode:
            # Picker Modus: Großer "Verwenden" Button
            self.btn_use = QPushButton("🚀 Dieses Bild in den ROI Editor laden")
            self.btn_use.setObjectName("btn_new")
            self.btn_use.setFixedHeight(40)
            self.btn_use.clicked.connect(self._auswaehlen)
            ctrl_layout.addWidget(self.btn_use)
        else:
            # Manager Modus: Umbenennen & Löschen
            rename_row = QHBoxLayout()
            rename_row.addWidget(QLabel("Name:"))
            self.name_edit = QLineEdit()
            rename_row.addWidget(self.name_edit)
            self.btn_rename = QPushButton("Umbenennen")
            self.btn_rename.clicked.connect(self._umbenennen)
            rename_row.addWidget(self.btn_rename)
            ctrl_layout.addLayout(rename_row)
            
            btn_row = QHBoxLayout()
            self.btn_delete = QPushButton("✕ Snapshot löschen")
            self.btn_delete.setObjectName("btn_del_sm")
            self.btn_delete.clicked.connect(self._loeschen)
            btn_row.addWidget(self.btn_delete)
            btn_row.addStretch()
            self.btn_close = QPushButton("Schließen")
            self.btn_close.clicked.connect(self.accept)
            btn_row.addWidget(self.btn_close)
            ctrl_layout.addLayout(btn_row)

        right_layout.addWidget(self.controls_stack)
        
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, stretch=1)

    def _on_double_click(self):
        if self.picker_mode:
            self._auswaehlen()

    def _auswaehlen(self):
        if self._selected_path:
            self.bild_gewaehlt.emit(self._selected_path)
            self.accept()

    def _on_selection_changed(self, row):
        if row < 0:
            self.preview_label.set_frame(None)
            self._selected_path = None
            if not self.picker_mode: self.name_edit.clear()
            return
            
        filename = self.liste.item(row).text()
        self._selected_path = os.path.join(self.snapshot_dir, filename)
        
        if not self.picker_mode:
            self.name_edit.setText(os.path.splitext(filename)[0])
        
        if cv2:
            frame = cv2.imread(self._selected_path)
            self.preview_label.set_frame(frame)
        else:
            self.preview_label.set_frame(QPixmap(self._selected_path))

    def _liste_aktualisieren(self):
        self.liste.clear()
        if not os.path.exists(self.snapshot_dir): return
        files = [f for f in os.listdir(self.snapshot_dir) if f.lower().endswith(".png")]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(self.snapshot_dir, x)), reverse=True)
        for f in files:
            self.liste.addItem(f)
        if self.liste.count() > 0:
            self.liste.setCurrentRow(0)

    def _umbenennen(self):
        current_item = self.liste.currentItem()
        if not current_item: return
        alter_name = current_item.text()
        neuer_name_base = self.name_edit.text().strip()
        if not neuer_name_base: return
        neuer_name = f"{neuer_name_base}.png"
        if alter_name == neuer_name: return
        alt_pfad = os.path.join(self.snapshot_dir, alter_name)
        neu_pfad = os.path.join(self.snapshot_dir, neuer_name)
        if os.path.exists(neu_pfad):
            QMessageBox.warning(self, "Fehler", f"Name existiert bereits.")
            return
        try:
            os.rename(alt_pfad, neu_pfad)
            self._liste_aktualisieren()
            items = self.liste.findItems(neuer_name, Qt.MatchFlag.MatchExactly)
            if items: self.liste.setCurrentItem(items[0])
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler: {e}")

    def _loeschen(self):
        current_item = self.liste.currentItem()
        if not current_item: return
        filename = current_item.text()
        pfad = os.path.join(self.snapshot_dir, filename)
        ret = QMessageBox.question(self, "Löschen", f"Snapshot '{filename}' löschen?", 
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            try:
                os.remove(pfad)
                self._liste_aktualisieren()
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Fehler: {e}")
