"""
Phase K Test — Mittlere Dialoge
Launcher zum manuellen Testen von Logic-Editor, Settings und Daten-Editor.
"""
import sys
import uuid
import style
import lang
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt

from ui.dialogs.logic_editor_qt    import LogicEditorDialogQt
from ui.dialogs.settings_dialog_qt import SettingsDialog
from ui.dialogs.daten_editor_qt    import DatenListeEditorQt


MOCK_GRAPH = {
    "nodes": [
        {"id": "n1", "typ": "l_var",    "x": 50,  "y": 100, "variable": "state::is_kampf"},
        {"id": "n2", "typ": "l_const",  "x": 50,  "y": 220, "wert": "1"},
        {"id": "n3", "typ": "l_and",    "x": 280, "y": 150},
        {"id": "n4", "typ": "l_result", "x": 500, "y": 200},
    ],
    "connections": [
        {"von": "n1", "port_von": "out", "zu": "n3", "port_zu": "in1"},
        {"von": "n2", "port_von": "out", "zu": "n3", "port_zu": "in2"},
        {"von": "n3", "port_von": "out", "zu": "n4", "port_zu": "in"},
    ],
}

MOCK_SETTINGS = {
    "display_fps": 30,
    "ocr_intervall": 0.5,
    "matching_skalierung": 0.5,
    "log_variablen": True,
    "log_workflow": True,
}


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase K Test — Mittlere Dialoge")
        self.resize(420, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        lbl = QLabel("Phase K — Dialog Launcher")
        lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        root.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3a3a3a;")
        root.addWidget(sep)

        self._log = QLabel("— Ergebnis erscheint hier —")
        self._log.setStyleSheet("color: #666666; font-size: 10px;")
        self._log.setWordWrap(True)
        root.addWidget(self._log)

        def btn(label, fn):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            root.addWidget(b)

        btn("1 · LogicEditorDialogQt — FUP Node-Editor",  self._test_logic)
        btn("2 · SettingsDialog — Einstellungen",          self._test_settings)
        btn("3 · DatenListeEditorQt — Daten-Listen-Editor",self._test_daten)

        root.addStretch()

    def _show(self, text: str):
        self._log.setText(str(text))

    def _test_logic(self):
        import copy
        dlg = LogicEditorDialogQt(
            name="Test-Netzwerk",
            graph=copy.deepcopy(MOCK_GRAPH),
            game_states={"is_kampf": True, "is_menu": False},
            templates=["Gegner", "Item", "Hauptmenü"],
            ocr_vars={"global": {"health": ""}, "template": {"Item_count": ""}},
            parent=self
        )
        dlg.gespeichert.connect(lambda g: self._show(f"Logic gespeichert: {len(g['nodes'])} Nodes"))
        dlg.exec()

    def _test_settings(self):
        result = SettingsDialog.ausfuehren(MOCK_SETTINGS, self)
        self._show(f"Settings → {result}")

    def _test_daten(self):
        # Daten-Editor benötigt eine echte Liste aus der DB.
        # Wir versuchen die erste Liste zu laden, oder zeigen Hinweis.
        try:
            from core.daten_manager import alle_listen
            listen = alle_listen()
            if not listen:
                self._show("Keine Daten-Listen vorhanden — erst im Bot eine Liste anlegen.")
                return
            liste = listen[0]
            dlg = DatenListeEditorQt(liste, parent=self)
            dlg.gespeichert.connect(lambda: self._show(f"Gespeichert: {liste['name']}"))
            dlg.geloescht.connect(lambda: self._show("Liste gelöscht."))
            dlg.exec()
        except Exception as e:
            self._show(f"Fehler beim Laden der Listen: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
