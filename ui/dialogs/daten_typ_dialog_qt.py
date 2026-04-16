from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal


class KartenButton(QFrame):
    """Klickbare Karte mit Icon, Label und Beschreibung."""
    clicked = pyqtSignal()

    def __init__(self, icon: str, label: str, type_key: str, beschreibung: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("karten_button")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        kopf = QHBoxLayout()
        lbl_icon = QLabel(icon)
        lbl_icon.setObjectName("karte_icon")
        lbl_icon.setProperty("type", type_key)
        lbl_name = QLabel(label)
        lbl_name.setObjectName("karte_titel")
        lbl_name.setProperty("type", type_key)
        kopf.addWidget(lbl_icon)
        kopf.addWidget(lbl_name)
        kopf.addStretch()
        layout.addLayout(kopf)

        lbl_desc = QLabel(beschreibung)
        lbl_desc.setProperty("class", "lbl_dim")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DatenTypDialog(QDialog):
    """Auswahldialog für den Typ einer neuen Daten-Liste."""

    TYPEN = [
        {"key": "daten", "label": "Standard Daten-Liste", "icon": "📊",
         "beschreibung": "Klassische Tabelle mit Spalten, Zeilen, OCR-Mapping und Berechnungen."},
        {"key": "timer", "label": "Globale Timer Liste", "icon": "⏳",
         "beschreibung": "Verwaltung von Countdowns, die im Workflow gesetzt und im FUP abgefragt werden können."},
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neues Element erstellen")
        self.setModal(True)
        self.setFixedWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._ergebnis: str | None = None  # "daten" | "timer"
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        lbl_titel = QLabel("Was möchtest du erstellen?")
        lbl_titel.setObjectName("dialog_titel_gross")
        root.addWidget(lbl_titel)

        for item in self.TYPEN:
            karte = KartenButton(
                icon=item["icon"], label=item["label"],
                type_key=item["key"], beschreibung=item["beschreibung"]
            )
            karte.clicked.connect(lambda k=item["key"]: self._gewaehlt(k))
            root.addWidget(karte)

        root.addStretch()

        btn_cancel = QPushButton(lang.t("btn_cancel"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        root.addWidget(btn_cancel)

    def _gewaehlt(self, key: str):
        self._ergebnis = key
        self.accept()

    def ergebnis(self):
        return self._ergebnis

    @staticmethod
    def ausfuehren(parent=None):
        dlg = DatenTypDialog(parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.ergebnis()
        return None
