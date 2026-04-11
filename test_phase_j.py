"""
Phase J Test — Alle kleinen Dialoge
Öffnet einen simplen Launcher mit Buttons zum Testen jedes Dialogs.
"""
import sys
import style
import lang
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt

from ui.dialogs.typ_dialog_qt       import TypDialog
from ui.dialogs.gruppe_editor_qt    import GruppeEditorQt
from ui.dialogs.roi_editor_qt       import ROIEditorQt
from ui.dialogs.state_dialogs_qt    import StateHinzufuegenDialog, StateUmbenennenDialog
from ui.dialogs.legende_dialog_qt   import LegendDialog


MOCK_STATES = ["is_kampf", "is_menu", "is_pause", "is_lade_screen", "has_gold"]

MOCK_CONDITIONS = [
    {"connector": None,  "states": {"is_kampf": True, "has_gold": False}},
    {"connector": "OR",  "states": {"is_menu": False}},
]


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase J Test — Kleine Dialoge")
        self.resize(460, 380)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        lbl = QLabel("Phase J — Dialog Launcher")
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

        def row(label, fn):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(fn)
            root.addWidget(btn)

        row("1 · TypDialog — 3-stufige Auswahl",      self._test_typ_dialog)
        row("2 · GruppeEditorQt — AND/OR Bedingungen", self._test_gruppe_editor)
        row("3 · ROIEditorQt — Scannbereiche zeichnen",self._test_roi_editor)
        row("4 · StateHinzufuegenDialog",              self._test_state_add)
        row("5 · StateUmbenennenDialog",               self._test_state_rename)
        row("6 · LegendDialog — Symbol-Legende",       self._test_legende)

        root.addStretch()

    def _show(self, text: str):
        self._log.setText(text)

    def _test_typ_dialog(self):
        ergebnis = TypDialog.ausfuehren(self)
        self._show(f"TypDialog → {ergebnis}")

    def _test_gruppe_editor(self):
        dlg = GruppeEditorQt(
            gruppe_name="Haupt-Kampf",
            bekannte_states=MOCK_STATES,
            condition_states=MOCK_CONDITIONS,
            parent=self
        )
        dlg.gespeichert.connect(lambda n, c: self._show(f"Gespeichert [{n}]: {c}"))
        dlg.geloescht.connect(lambda n: self._show(f"Konfiguration gelöscht: {n}"))
        dlg.exec()

    def _test_roi_editor(self):
        from PIL import Image
        import numpy as np

        def mock_snap():
            # Einfaches 640×360 Testbild (dunkelgrau mit weißem Rand)
            arr = np.full((360, 640, 3), 40, dtype=np.uint8)
            arr[0, :] = arr[-1, :] = arr[:, 0] = arr[:, -1] = 180
            return Image.fromarray(arr)

        dlg = ROIEditorQt(
            t_name="Test-Template",
            initial_regions=[(50, 50, 200, 150), (300, 100, 500, 250)],
            get_live_snap_func=mock_snap,
            parent=self
        )
        dlg.regionen_geaendert.connect(lambda r: self._show(f"Regionen: {r}"))
        dlg.show()

    def _test_state_add(self):
        result = StateHinzufuegenDialog.ausfuehren(self)
        self._show(f"StateHinzufügen → {result}")

    def _test_state_rename(self):
        result = StateUmbenennenDialog.ausfuehren("is_kampf", self)
        self._show(f"StateUmbenennen → {result}")

    def _test_legende(self):
        LegendDialog.zeigen(self)
        self._show("Legende geschlossen.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
