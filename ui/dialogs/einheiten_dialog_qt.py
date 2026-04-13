from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QLineEdit, QPushButton, QFrame, QSizePolicy,
    QSpacerItem, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from core.daten_manager import _einheiten_laden, _einheiten_speichern

class EinheitenDialogQt(QDialog):
    """Dialog zur Verwaltung globaler Einheiten und Faktoren (Mio, Tsd, etc.)."""
    
    gespeichert = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Globale Einheiten & Faktoren")
        self.setMinimumWidth(450)
        self.setMinimumHeight(550)
        self.setObjectName("dialog_standard")

        self.aktuelle_einheiten = _einheiten_laden()
        self._setup_ui()
        self._liste_aktualisieren()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Info
        header_lbl = QLabel("Zuweisung: Kürzel → Multiplikator")
        header_lbl.setObjectName("dialog_header_title_gold")
        layout.addWidget(header_lbl)

        info_lbl = QLabel("Beispiel: 'Mio.' → 1.000.000 oder 'Tsd.' → 1.000")
        info_lbl.setProperty("class", "lbl_info")
        layout.addWidget(info_lbl)

        # Scrollbare Liste
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("units_scroll_area")
        
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(10, 10, 10, 10)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        
        scroll.setWidget(self.list_container)
        layout.addWidget(scroll, stretch=1)

        # Eingabebereich
        eingabe_frame = QFrame()
        eingabe_frame.setObjectName("dialog_footer_input_frame")
        eingabe_layout = QGridLayout(eingabe_frame)
        eingabe_layout.setContentsMargins(10, 10, 10, 10)
        eingabe_layout.setSpacing(10)

        eingabe_layout.addWidget(QLabel("Kürzel:"), 0, 0)
        eingabe_layout.addWidget(QLabel("Faktor:"), 0, 1)

        self.k_edit = QLineEdit()
        self.k_edit.setPlaceholderText("z.B. Mio")
        self.k_edit.setMinimumHeight(30)
        eingabe_layout.addWidget(self.k_edit, 1, 0)

        self.f_edit = QLineEdit()
        self.f_edit.setPlaceholderText("z.B. 1000000")
        self.f_edit.setMinimumHeight(30)
        eingabe_layout.addWidget(self.f_edit, 1, 1)

        btn_add = QPushButton("+ Hinzufügen / Update")
        btn_add.setObjectName("btn_new")
        btn_add.setMinimumHeight(35)
        btn_add.clicked.connect(self._hinzufuegen)
        eingabe_layout.addWidget(btn_add, 2, 0, 1, 2)

        layout.addWidget(eingabe_frame)

        # Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setMinimumWidth(100)
        btn_cancel.setMinimumHeight(35)
        footer_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Speichern")
        btn_save.setObjectName("btn_new")
        btn_save.setMinimumWidth(120)
        btn_save.setMinimumHeight(35)
        btn_save.clicked.connect(self._speichern)
        footer_layout.addWidget(btn_save)

        layout.addLayout(footer_layout)

    def _liste_aktualisieren(self):
        # Alte Widgets entfernen (außer dem Stretch ganz unten)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for k, v in sorted(self.aktuelle_einheiten.items()):
            row = QFrame()
            row.setObjectName("unit_list_row")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 5, 10, 5)

            lbl_k = QLabel(k)
            lbl_k.setObjectName("unit_label_key")
            lbl_k.setFixedWidth(120)
            row_layout.addWidget(lbl_k)

            # Formatieren mit Tausender-Punkten
            try:
                val_str = f"× {v:,.0f}".replace(",", ".")
            except Exception:
                val_str = f"× {v}"
                
            lbl_v = QLabel(val_str)
            lbl_v.setObjectName("unit_label_value")
            row_layout.addWidget(lbl_v)
            row_layout.addStretch()

            btn_del = QPushButton("✕")
            btn_del.setObjectName("btn_del_sm")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.clicked.connect(lambda checked, key=k: self._loeschen(key))
            row_layout.addWidget(btn_del)

            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _hinzufuegen(self):
        k = self.k_edit.text().strip().upper().rstrip(".")
        f_raw = self.f_edit.text().strip().replace(".", "").replace(",", "")
        
        if not k:
            QMessageBox.warning(self, "Eingabe fehlt", "Bitte geben Sie ein Kürzel ein.")
            return
        
        if not f_raw.isdigit():
            QMessageBox.warning(self, "Ungültiger Faktor", "Der Faktor muss eine Zahl sein.")
            return

        self.aktuelle_einheiten[k] = int(f_raw)
        self.k_edit.clear()
        self.f_edit.clear()
        self._liste_aktualisieren()

    def _loeschen(self, key):
        if key in self.aktuelle_einheiten:
            del self.aktuelle_einheiten[key]
            self._liste_aktualisieren()

    def _speichern(self):
        _einheiten_speichern(self.aktuelle_einheiten)
        self.gespeichert.emit()
        self.accept()
