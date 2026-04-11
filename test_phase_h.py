"""
Phase H Test — Log + State Panel
Simuliert einen Bot-Tick alle 2s: States toggeln, Log-Einträge kommen rein.
"""
import sys
import style
import lang
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSplitter
)
from PyQt6.QtCore import Qt, QTimer

from ui.panels.log_panel_qt import LogPanel
from ui.panels.state_panel_qt import StatePanel


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase H Test — Log + State Panel")
        self.resize(640, 500)

        # Mock game_states
        self.game_states = {
            "im_hauptmenue": True,
            "kampf_aktiv": False,
            "inventar_offen": False,
            "gegner_sichtbar": True,
            "quest_abgeschlossen": False,
            "dialog_aktiv": True,
        }
        self._tick = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        lbl = QLabel("Phase H — Log + State Panel Test")
        lbl.setObjectName("panel_title")
        toolbar.addWidget(lbl)
        toolbar.addStretch()

        btn_nur_aktive = QPushButton(lang.t("btn_only_active"))
        btn_nur_aktive.setCheckable(True)
        btn_nur_aktive.setCursor(Qt.CursorShape.PointingHandCursor)
        toolbar.addWidget(btn_nur_aktive)

        btn_tick = QPushButton("▶ Tick simulieren")
        btn_tick.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_tick.clicked.connect(self._simulate_tick)
        toolbar.addWidget(btn_tick)

        layout.addLayout(toolbar)

        # Splitter: State (links) | Log (rechts)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # State Panel
        state_container = QWidget()
        sc_layout = QVBoxLayout(state_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.addWidget(QLabel("STATE VARIABLEN"))
        self.state_panel = StatePanel()
        self.state_panel.aktualisieren(self.game_states)
        self.state_panel.rename_requested.connect(self._on_rename)
        self.state_panel.delete_requested.connect(self._on_delete)
        self.state_panel.toggle_requested.connect(self._on_toggle)
        sc_layout.addWidget(self.state_panel)
        splitter.addWidget(state_container)

        # Log Panel
        log_container = QWidget()
        lc_layout = QVBoxLayout(log_container)
        lc_layout.setContentsMargins(0, 0, 0, 0)
        lc_layout.addWidget(QLabel("LOG"))
        self.log_panel = LogPanel()
        lc_layout.addWidget(self.log_panel)
        splitter.addWidget(log_container)

        splitter.setSizes([280, 360])
        layout.addWidget(splitter)

        btn_nur_aktive.toggled.connect(self._on_nur_aktive)

        # Auto-Tick alle 3s
        self._timer = QTimer()
        self._timer.timeout.connect(self._simulate_tick)
        self._timer.start(3000)

        self.log_panel.log("Test gestartet.")
        self.log_panel.log("Auto-Tick alle 3 Sekunden.")

    def _simulate_tick(self):
        self._tick += 1
        import random
        key = random.choice(list(self.game_states.keys()))
        self.game_states[key] = not self.game_states[key]
        self.log_panel.log(f"[Tick {self._tick}] {key} → {self.game_states[key]}")
        self.state_panel.werte_aktualisieren(self.game_states)

    def _on_nur_aktive(self, val: bool):
        self.state_panel.set_nur_aktive(val)
        self.state_panel.aktualisieren(self.game_states)

    def _on_rename(self, alter_name: str):
        from PyQt6.QtWidgets import QInputDialog
        neuer_name, ok = QInputDialog.getText(
            self, lang.t("state_rename_title"),
            lang.t("state_rename_label"), text=alter_name
        )
        if ok and neuer_name and neuer_name != alter_name:
            val = self.game_states.pop(alter_name)
            self.game_states[neuer_name] = val
            self.log_panel.log(f"Umbenannt: {alter_name} → {neuer_name}")
            self.state_panel.aktualisieren(self.game_states)
            self.state_panel.set_auswahl(neuer_name)

    def _on_delete(self, name: str):
        del self.game_states[name]
        self.log_panel.log(f"Gelöscht: {name}")
        self.state_panel.aktualisieren(self.game_states)

    def _on_toggle(self, name: str, value: bool):
        self.game_states[name] = value
        self.log_panel.log(f"Toggle: {name} → {value}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
