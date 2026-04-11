"""
Test: Zustands-Panel in PyQt6
Standalone — läuft ohne Bot/Backend.
Nutzt style.py + lang.py Infrastruktur.
"""
import sys
import style
import lang
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt


# ── State-Zeile ────────────────────────────────────────────────────────────────
class StateRow(QFrame):
    def __init__(self, name: str, value: bool, on_select, on_toggle):
        super().__init__()
        self.name = name
        self.value = value
        self._on_select = on_select
        self._on_toggle = on_toggle

        self.setProperty("selected", False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        layout.addWidget(self.name_label, stretch=1)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedWidth(60)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._do_toggle)
        layout.addWidget(self.toggle_btn)

        self._update_toggle()

    def _update_toggle(self):
        self.toggle_btn.setText("TRUE" if self.value else "FALSE")
        self.toggle_btn.setObjectName("toggle_true" if self.value else "toggle_false")
        self.toggle_btn.setStyle(self.toggle_btn.style())

    def _do_toggle(self):
        self.value = not self.value
        self._update_toggle()
        self._on_toggle(self.name, self.value)

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        color = "#0d47a1" if selected else "transparent"
        self.setStyleSheet(f"StateRow {{ background-color: {color}; border-radius: 4px; }}")

    def mousePressEvent(self, event):
        self._on_select(self.name)
        super().mousePressEvent(event)


# ── Zustands-Panel ─────────────────────────────────────────────────────────────
class StatePanel(QWidget):
    def __init__(self, game_states: dict):
        super().__init__()
        self.game_states = game_states
        self.ausgewaehlt = None
        self.rows: dict[str, StateRow] = {}
        self.nur_aktive = False

        self._setup_ui()
        self._rebuild()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(4, 4, 4, 4)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        root_layout.addWidget(self.scroll)

        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(4, 4, 4, 4)

        self.btn_umbenennen = QPushButton(lang.t("btn_rename"))
        self.btn_umbenennen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_umbenennen.clicked.connect(self._umbenennen)
        self.btn_umbenennen.setEnabled(False)

        self.btn_loeschen = QPushButton(lang.t("btn_delete"))
        self.btn_loeschen.setObjectName("btn_danger")
        self.btn_loeschen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_loeschen.clicked.connect(self._loeschen)
        self.btn_loeschen.setEnabled(False)

        btn_bar.addWidget(self.btn_umbenennen)
        btn_bar.addWidget(self.btn_loeschen)
        btn_bar.addStretch()
        root_layout.addLayout(btn_bar)

    def _rebuild(self):
        for row in self.rows.values():
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()

        keys = sorted(k for k, v in self.game_states.items()
                      if not self.nur_aktive or v)

        if not keys:
            key = "state_only_active_empty" if self.nur_aktive else "state_no_states"
            placeholder = QLabel(lang.t(key))
            placeholder.setStyleSheet("color: #555555; padding: 8px;")
            self.list_layout.insertWidget(0, placeholder)
            return

        for i, name in enumerate(keys):
            row = StateRow(
                name=name,
                value=self.game_states[name],
                on_select=self._auswahl_setzen,
                on_toggle=self._on_toggle,
            )
            if name == self.ausgewaehlt:
                row.set_selected(True)
            self.list_layout.insertWidget(i, row)
            self.rows[name] = row

    def _auswahl_setzen(self, name: str):
        if self.ausgewaehlt and self.ausgewaehlt in self.rows:
            self.rows[self.ausgewaehlt].set_selected(False)
        self.ausgewaehlt = name
        if name in self.rows:
            self.rows[name].set_selected(True)
        self.btn_umbenennen.setEnabled(True)
        self.btn_loeschen.setEnabled(True)

    def _on_toggle(self, name: str, new_value: bool):
        self.game_states[name] = new_value

    def _umbenennen(self):
        if not self.ausgewaehlt:
            return
        neuer_name, ok = QInputDialog.getText(
            self, lang.t("state_rename_title"),
            lang.t("state_rename_label"),
            text=self.ausgewaehlt
        )
        if ok and neuer_name and neuer_name != self.ausgewaehlt:
            val = self.game_states.pop(self.ausgewaehlt)
            self.game_states[neuer_name] = val
            self.ausgewaehlt = neuer_name
            self._rebuild()

    def _loeschen(self):
        if not self.ausgewaehlt:
            return
        antwort = QMessageBox.question(
            self, lang.t("btn_delete"),
            lang.t("state_delete_confirm", name=self.ausgewaehlt),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if antwort == QMessageBox.StandardButton.Yes:
            del self.game_states[self.ausgewaehlt]
            self.ausgewaehlt = None
            self.btn_umbenennen.setEnabled(False)
            self.btn_loeschen.setEnabled(False)
            self._rebuild()

    def set_nur_aktive(self, val: bool):
        if self.nur_aktive != val:
            self.nur_aktive = val
            self._rebuild()


# ── Testfenster ────────────────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{lang.t('app_title')} — {lang.t('panel_state_vars')} Test")
        self.resize(300, 450)

        self.game_states = {
            "im_hauptmenue": True,
            "kampf_aktiv": False,
            "inventar_offen": False,
            "gegner_sichtbar": True,
            "quest_abgeschlossen": False,
            "dialog_aktiv": True,
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 6, 6, 4)

        title = QLabel(lang.t("panel_state_vars"))
        title.setObjectName("panel_title")

        btn_nur_aktive = QPushButton(lang.t("btn_only_active"))
        btn_nur_aktive.setCheckable(True)
        btn_nur_aktive.setCursor(Qt.CursorShape.PointingHandCursor)

        self.panel = StatePanel(self.game_states)
        btn_nur_aktive.toggled.connect(self.panel.set_nur_aktive)

        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(btn_nur_aktive)

        layout.addLayout(toolbar)
        layout.addWidget(self.panel)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
