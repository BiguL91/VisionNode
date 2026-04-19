from lang import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal


class StateRow(QFrame):
    selected = pyqtSignal(str)
    toggled = pyqtSignal(str, bool)
    double_clicked = pyqtSignal(str)

    def __init__(self, name: str, value: bool, parent=None):
        super().__init__(parent)
        self.name = name
        self.value = value

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.name_label = QLabel(name)
        self.name_label.setObjectName("state_name")
        layout.addWidget(self.name_label, stretch=1)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedWidth(60)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._do_toggle)
        layout.addWidget(self.toggle_btn)

        self._update_toggle()
        self.set_selected(False)

    def _update_toggle(self):
        self.toggle_btn.setText("TRUE" if self.value else "FALSE")
        self.toggle_btn.setObjectName("toggle_true" if self.value else "toggle_false")
        self.toggle_btn.setStyle(self.toggle_btn.style())

    def _do_toggle(self):
        self.value = not self.value
        self._update_toggle()
        self.toggled.emit(self.name, self.value)

    def update_value(self, value: bool):
        """Aktualisiert nur den Wert ohne Rebuild."""
        if self.value != value:
            self.value = value
            self._update_toggle()

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.setStyle(self.style())

    def mousePressEvent(self, event):
        self.selected.emit(self.name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.name)
        super().mouseDoubleClickEvent(event)


class StatePanel(QWidget):
    # Signals für den Bot-Controller
    add_requested    = pyqtSignal()
    rename_requested = pyqtSignal(str)       # alter Name
    delete_requested = pyqtSignal(str)       # Name
    toggle_requested = pyqtSignal(str, bool) # Name, neuer Wert

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ausgewaehlt: str | None = None
        self.rows: dict[str, StateRow] = {}
        self.nur_aktive = False
        self._last_keys: set[str] = set()

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header mit "Nur Aktive" Button
        header = QWidget()
        header.setObjectName("panel_header_lite")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(8, 4, 8, 4)
        
        lbl = QLabel("STATE VARIABLEN")
        lbl.setProperty("class", "lbl_dim")
        h_lay.addWidget(lbl)
        h_lay.addStretch()

        self._btn_nur_aktive = QPushButton("Nur Aktive")
        self._btn_nur_aktive.setCheckable(True)
        self._btn_nur_aktive.setObjectName("btn_sm")
        self._btn_nur_aktive.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_nur_aktive.toggled.connect(self.set_nur_aktive)
        h_lay.addWidget(self._btn_nur_aktive)
        
        root.addWidget(header)

        # Scroll-Liste
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(4, 4, 4, 4)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, stretch=1)

        # Button-Leiste
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 2, 0, 0)
        btn_bar.setSpacing(4)

        self.btn_add = QPushButton("+ Neu")
        self.btn_add.setObjectName("btn_new_sm")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.add_requested)

        self.btn_rename = QPushButton(lang.t("btn_rename"))
        self.btn_rename.setObjectName("btn_sm")
        self.btn_rename.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rename.setEnabled(False)
        self.btn_rename.clicked.connect(self._umbenennen)

        self.btn_delete = QPushButton(lang.t("btn_delete"))
        self.btn_delete.setObjectName("btn_del_sm")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._loeschen)

        for btn in [self.btn_add, self.btn_rename, self.btn_delete]:
            btn_bar.addWidget(btn)
        root.addLayout(btn_bar)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def aktualisieren(self, game_states: dict):
        """Vollständiger Rebuild der Liste."""
        keys = sorted(k for k, v in game_states.items()
                      if not self.nur_aktive or v)
        self._last_keys = set(keys)

        # Alle Widgets (Zeilen + leere Labels) entfernen
        while self.list_layout.count() > 1:  # Stretch bleibt
            item = self.list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.rows.clear()

        if not keys:
            key = "state_only_active_empty" if self.nur_aktive else "state_no_states"
            lbl = QLabel(lang.t(key))
            lbl.setProperty("class", "lbl_empty_hint")
            self.list_layout.insertWidget(0, lbl)
            return

        for i, name in enumerate(keys):
            row = StateRow(name=name, value=game_states[name])
            row.selected.connect(self._auswahl_setzen)
            row.toggled.connect(self.toggle_requested)
            row.double_clicked.connect(lambda: self.rename_requested.emit(self.ausgewaehlt))
            if name == self.ausgewaehlt:
                row.set_selected(True)
            self.list_layout.insertWidget(i, row)
            self.rows[name] = row

    def werte_aktualisieren(self, game_states: dict):
        """Surgical Update: nur Werte ändern, kein Rebuild."""
        current_keys = set(k for k, v in game_states.items()
                           if not self.nur_aktive or v)

        # Struktur hat sich geändert → Rebuild
        if current_keys != self._last_keys:
            self.aktualisieren(game_states)
            return

        for name, row in self.rows.items():
            if name in game_states:
                row.update_value(game_states[name])

    def set_nur_aktive(self, val: bool):
        if self.nur_aktive != val:
            self.nur_aktive = val

    def set_auswahl(self, name: str | None):
        """Setzt Auswahl von außen (z.B. nach Umbenennen)."""
        self._auswahl_setzen(name)

    # ── Interne Slots ──────────────────────────────────────────────────────────

    def _auswahl_setzen(self, name: str | None):
        if self.ausgewaehlt and self.ausgewaehlt in self.rows:
            self.rows[self.ausgewaehlt].set_selected(False)
        self.ausgewaehlt = name
        if name and name in self.rows:
            self.rows[name].set_selected(True)
        has_sel = name is not None
        self.btn_rename.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _umbenennen(self):
        if self.ausgewaehlt:
            self.rename_requested.emit(self.ausgewaehlt)

    def _loeschen(self):
        if self.ausgewaehlt:
            self.delete_requested.emit(self.ausgewaehlt)
