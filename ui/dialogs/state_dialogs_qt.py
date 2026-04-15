"""
Kleine State-Variable Dialoge (Qt).
Ersetzt die inline-Toplevel-Dialoge aus main.py.

Klassen:
    StateHinzufuegenDialog  — neue State-Variable anlegen
    StateUmbenennenDialog   — bestehende State-Variable umbenennen
"""
from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal


class StateHinzufuegenDialog(QDialog):
    """
    Kleiner Dialog: Name eingeben + optionaler Startwert TRUE.

    Signal:
        hinzugefuegt(name: str, startwert: bool)
    """
    hinzugefuegt = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(lang.t("state_add_title"))
        self.setModal(True)
        self.setFixedSize(300, 180)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        lbl = QLabel(lang.t("state_add_label"))
        lbl.setProperty("class", "lbl_dim")
        layout.addWidget(lbl)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("z.B. is_kampf_aktiv")
        self._entry.returnPressed.connect(self._bestaetigen)
        layout.addWidget(self._entry)

        self._check = QCheckBox(lang.t("state_add_start_true"))
        layout.addWidget(self._check)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_add = QPushButton(lang.t("btn_add"))
        btn_add.setObjectName("btn_new")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._bestaetigen)
        btn_row.addWidget(btn_add)

        btn_cancel = QPushButton(lang.t("btn_cancel"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        layout.addLayout(btn_row)
        self._entry.setFocus()

    def _bestaetigen(self):
        name = self._entry.text().strip()
        if not name:
            return
        self.hinzugefuegt.emit(name, self._check.isChecked())
        self.accept()

    @staticmethod
    def ausfuehren(parent=None) -> tuple[str, bool] | None:
        """Gibt (name, startwert) zurück oder None bei Abbruch."""
        result = {}
        dlg = StateHinzufuegenDialog(parent)
        dlg.hinzugefuegt.connect(lambda n, v: result.update(name=n, wert=v))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result.get("name"), result.get("wert", False)
        return None


class StateEditorDialog(QDialog):
    """
    Dialog zum Bearbeiten einer State-Variable (Name und Wert).

    Signal:
        gespeichert(alter_name: str, neuer_name: str, wert: bool)
    """
    gespeichert = pyqtSignal(str, str, bool)

    def __init__(self, name: str, wert: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("State-Variable bearbeiten")
        self.setModal(True)
        self.setFixedSize(300, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._alter_name = name
        self._wert = wert
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        lbl = QLabel(lang.t("state_rename_label"))
        lbl.setProperty("class", "lbl_dim")
        layout.addWidget(lbl)

        self._entry = QLineEdit(self._alter_name)
        self._entry.selectAll()
        self._entry.returnPressed.connect(self._bestaetigen)
        layout.addWidget(self._entry)

        self._check = QCheckBox("Aktiv (TRUE)")
        self._check.setChecked(self._wert)
        layout.addWidget(self._check)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_save = QPushButton("Speichern")
        btn_save.setObjectName("btn_new")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._bestaetigen)
        btn_row.addWidget(btn_save)

        btn_cancel = QPushButton(lang.t("btn_cancel"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        layout.addLayout(btn_row)
        self._entry.setFocus()

    def _bestaetigen(self):
        neuer_name = self._entry.text().strip()
        neuer_wert = self._check.isChecked()
        if not neuer_name:
            return
        self.gespeichert.emit(self._alter_name, neuer_name, neuer_wert)
        self.accept()

    @staticmethod
    def ausfuehren(name: str, wert: bool, parent=None) -> tuple[str, str, bool] | None:
        """Gibt (alter_name, neuer_name, neuer_wert) zurück oder None bei Abbruch."""
        result = {}
        dlg = StateEditorDialog(name, wert, parent)
        dlg.gespeichert.connect(lambda a, n, v: result.update(alt=a, neu=n, wert=v))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result.get("alt"), result.get("neu"), result.get("wert")
        return None
