import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QStackedWidget, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal


class KartenButton(QFrame):
    """Klickbare Karte mit Icon, Label und Beschreibung."""
    clicked = pyqtSignal()

    def __init__(self, icon: str, label: str, farbe: str, beschreibung: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            KartenButton { background: #2a2a2a; border-radius: 6px; border: 1px solid #3a3a3a; }
            KartenButton:hover { background: #333333; border-color: #4a4a4a; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        kopf = QHBoxLayout()
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet(f"color: {farbe}; font-size: 16px; background: transparent;")
        lbl_name = QLabel(label)
        lbl_name.setStyleSheet(f"color: {farbe}; font-size: 12px; font-weight: bold; background: transparent;")
        kopf.addWidget(lbl_icon)
        kopf.addWidget(lbl_name)
        kopf.addStretch()
        layout.addLayout(kopf)

        lbl_desc = QLabel(beschreibung)
        lbl_desc.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class TypDialog(QDialog):
    """
    3-stufiger Auswahlsdialog:
    Stufe 1: Kategorie (Workflow / State)
    Stufe 2: Typ (Aktive Gruppe / Passive Gruppe / Template)
    Stufe 3: Passive Gruppen-Art (Master / Untergeordnet)
    """

    KATEGORIEN = [
        {"key": "workflow", "label": "Workflow Template", "icon": "⚙",
         "farbe": "#55ff88",
         "beschreibung": "Führt Aktionen aus (Klicks, Abläufe).\nWird im Workflow-Panel angezeigt."},
        {"key": "state", "label": "State Template", "icon": "🚩",
         "farbe": "#ff7043",
         "beschreibung": "Erkennt einen Spielzustand und setzt einen Game-State.\nWird im State-Panel angezeigt."},
    ]

    TYPEN = [
        {"key": "aktiv_gruppe", "label": "Aktive Gruppe", "icon": "★",
         "farbe": "#ffca28",
         "beschreibung": "Hat ein Bild, erkennt sich selbst als Gruppe.\nKind-Templates können zugeordnet werden."},
        {"key": "passiv_gruppe", "label": "Passive Gruppe", "icon": "📦",
         "farbe": "#7a9abf",
         "beschreibung": "Kein Bild, nur Bedingungen.\nOrganisiert andere Templates/Gruppen."},
        {"key": "template", "label": "Template", "icon": "◻",
         "farbe": "#cccccc",
         "beschreibung": "Normales Erkennungs-Template.\nGehört zu einer Gruppe."},
    ]

    PASSIV_ARTEN = [
        {"key": "master", "label": "Master Gruppe", "icon": "◈",
         "farbe": "#7a9abf",
         "beschreibung": "Eigenständige Gruppe ohne übergeordnete Gruppe.\nTop-Level-Organisationseinheit."},
        {"key": "untergeordnet", "label": "Untergeordnete Gruppe", "icon": "↳",
         "farbe": "#9abf7a",
         "beschreibung": "Gehört zu einer bestehenden Gruppe.\nWird ihr untergeordnet zugewiesen."},
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neues Element erstellen")
        self.setModal(True)
        self.setFixedWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._kategorie: str | None = None
        self._typ: str | None = None
        self._ergebnis: tuple | None = None  # (typ, kategorie[, extra])

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.stack.addWidget(self._seite_bauen(
            titel="Welche Kategorie?",
            items=self.KATEGORIEN,
            on_click=self._kategorie_gewaehlt,
            zurueck=None,
            zurueck_label=None,
        ))

    def _seite_bauen(self, titel, items, on_click, zurueck, zurueck_label) -> QWidget:
        seite = QWidget()
        layout = QVBoxLayout(seite)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header
        kopf = QHBoxLayout()
        if zurueck is not None:
            btn_back = QPushButton("← Zurück")
            btn_back.setObjectName("btn_icon")
            btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_back.clicked.connect(zurueck)
            kopf.addWidget(btn_back)
        kopf.addStretch()
        if zurueck_label:
            lbl = QLabel(zurueck_label)
            lbl.setStyleSheet("color: #666666; font-size: 10px;")
            kopf.addWidget(lbl)
        if zurueck is not None:
            layout.addLayout(kopf)

        lbl_titel = QLabel(titel)
        lbl_titel.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        layout.addWidget(lbl_titel)

        for item in items:
            karte = KartenButton(
                icon=item["icon"], label=item["label"],
                farbe=item["farbe"], beschreibung=item["beschreibung"]
            )
            karte.clicked.connect(lambda key=item["key"]: on_click(key))
            layout.addWidget(karte)

        layout.addStretch()

        btn_cancel = QPushButton(lang.t("btn_cancel"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

        return seite

    def _kategorie_gewaehlt(self, kategorie: str):
        self._kategorie = kategorie
        kat_label = next(k["icon"] + " " + k["label"] for k in self.KATEGORIEN if k["key"] == kategorie)

        seite2 = self._seite_bauen(
            titel="Welchen Typ?",
            items=self.TYPEN,
            on_click=self._typ_gewaehlt,
            zurueck=lambda: self.stack.setCurrentIndex(0),
            zurueck_label=kat_label,
        )
        if self.stack.count() > 1:
            self.stack.removeWidget(self.stack.widget(1))
        if self.stack.count() > 2:
            self.stack.removeWidget(self.stack.widget(2))
        self.stack.addWidget(seite2)
        self.stack.setCurrentIndex(1)

    def _typ_gewaehlt(self, typ: str):
        self._typ = typ
        if typ == "passiv_gruppe":
            seite3 = self._seite_bauen(
                titel="Welche Art?",
                items=self.PASSIV_ARTEN,
                on_click=self._passiv_art_gewaehlt,
                zurueck=lambda: self.stack.setCurrentIndex(1),
                zurueck_label="📦 Passive Gruppe",
            )
            while self.stack.count() > 2:
                self.stack.removeWidget(self.stack.widget(2))
            self.stack.addWidget(seite3)
            self.stack.setCurrentIndex(2)
        else:
            self._ergebnis = (typ, self._kategorie)
            self.accept()

    def _passiv_art_gewaehlt(self, art: str):
        self._ergebnis = (self._typ, self._kategorie, {"art": art})
        self.accept()

    def ergebnis(self):
        """Gibt (typ, kategorie[, extra]) zurück oder None bei Abbruch."""
        return self._ergebnis

    @staticmethod
    def ausfuehren(parent=None):
        """Convenience: Dialog öffnen und Ergebnis zurückgeben."""
        dlg = TypDialog(parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.ergebnis()
        return None
