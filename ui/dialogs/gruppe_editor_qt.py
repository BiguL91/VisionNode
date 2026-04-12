from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QCheckBox, QScrollArea,
    QWidget, QButtonGroup, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal


class BedingungsZeile(QFrame):
    """Eine einzelne State-Bedingung: [ComboBox Name] [Checkbox True] [✕]"""
    loeschen_requested = pyqtSignal(object)  # self

    def __init__(self, bekannte: list[str], state_name: str = "", state_val: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("bedingung_zeile")
        self.setStyleSheet("QFrame#bedingung_zeile { background: #1a1a1a; border-radius: 3px; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.addItems(bekannte)
        self.combo.setCurrentText(state_name)
        self.combo.setMinimumWidth(180)
        layout.addWidget(self.combo)

        self.check = QCheckBox("True")
        self.check.setChecked(state_val)
        layout.addWidget(self.check)

        layout.addStretch()

        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_danger")
        btn_del.setFixedSize(24, 24)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda: self.loeschen_requested.emit(self))
        layout.addWidget(btn_del)

    def get_name(self) -> str:
        return self.combo.currentText().strip()

    def get_wert(self) -> bool:
        return self.check.isChecked()


class BedingungsGruppe(QFrame):
    """Eine AND-Gruppe mit Connector (AND/OR) zum Vorgänger."""
    loeschen_requested = pyqtSignal(object)  # self

    def __init__(self, nr: int, gruppe_data: dict, bekannte: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("bedingung_gruppe")
        self.setStyleSheet("""
            QFrame#bedingung_gruppe {
                background: #222222;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
        """)

        self._bekannte = bekannte
        self._zeilen: list[BedingungsZeile] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Connector (AND/OR) — nur für Gruppen nr > 1 ──────────────────────
        self._conn_frame = QFrame()
        self._conn_frame.setStyleSheet("background: transparent;")
        conn_layout = QHBoxLayout(self._conn_frame)
        conn_layout.setContentsMargins(0, 6, 0, 4)
        conn_layout.setSpacing(6)

        lbl = QLabel("Verknüpfung:")
        lbl.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        conn_layout.addWidget(lbl)

        self._btn_and = QPushButton("AND")
        self._btn_or = QPushButton("OR")
        for btn in (self._btn_and, self._btn_or):
            btn.setCheckable(True)
            btn.setFixedWidth(50)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_and.setStyleSheet("QPushButton:checked { background: #1a3a5a; color: #55aaff; border-color: #55aaff; }")
        self._btn_or.setStyleSheet("QPushButton:checked { background: #3a2a00; color: #ffca28; border-color: #ffca28; }")

        self._btn_grp = QButtonGroup(self)
        self._btn_grp.setExclusive(True)
        self._btn_grp.addButton(self._btn_and)
        self._btn_grp.addButton(self._btn_or)

        conn_val = gruppe_data.get("connector") or "OR"
        if conn_val == "AND":
            self._btn_and.setChecked(True)
        else:
            self._btn_or.setChecked(True)

        conn_layout.addWidget(self._btn_and)
        conn_layout.addWidget(self._btn_or)
        conn_layout.addStretch()
        outer.addWidget(self._conn_frame)

        # ── Header ────────────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet("background: #252525; border-radius: 0px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 8, 4)

        lbl_nr = QLabel(f"  Gruppe {nr}")
        lbl_nr.setStyleSheet("color: #888888; font-size: 9px; font-weight: bold; background: transparent;")
        h_layout.addWidget(lbl_nr)
        h_layout.addStretch()

        btn_del_gruppe = QPushButton("Gruppe löschen")
        btn_del_gruppe.setObjectName("btn_danger")
        btn_del_gruppe.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_gruppe.clicked.connect(lambda: self.loeschen_requested.emit(self))
        h_layout.addWidget(btn_del_gruppe)

        outer.addWidget(header)

        # ── Zeilen-Container ─────────────────────────────────────────────────
        self._zeilen_container = QWidget()
        self._zeilen_container.setStyleSheet("background: #1a1a1a;")
        self._zeilen_layout = QVBoxLayout(self._zeilen_container)
        self._zeilen_layout.setContentsMargins(4, 4, 4, 0)
        self._zeilen_layout.setSpacing(2)
        outer.addWidget(self._zeilen_container)

        for sn, sv in gruppe_data.get("states", {}).items():
            self._zeile_hinzufuegen(sn, sv)

        # ── "+ Bedingung" Button ──────────────────────────────────────────────
        btn_add = QPushButton("+ Bedingung hinzufügen")
        btn_add.setObjectName("btn_icon")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet("text-align: left; padding: 4px 8px; background: #1a1a1a; color: #aaaaaa; border: none;")
        btn_add.clicked.connect(lambda: self._zeile_hinzufuegen())
        outer.addWidget(btn_add)

    def _zeile_hinzufuegen(self, state_name: str = "", state_val: bool = True):
        zeile = BedingungsZeile(self._bekannte, state_name, state_val)
        zeile.loeschen_requested.connect(self._zeile_entfernen)
        self._zeilen_layout.addWidget(zeile)
        self._zeilen.append(zeile)

    def _zeile_entfernen(self, zeile: BedingungsZeile):
        if zeile in self._zeilen:
            self._zeilen.remove(zeile)
        zeile.setParent(None)
        zeile.deleteLater()

    def set_connector_sichtbar(self, sichtbar: bool):
        self._conn_frame.setVisible(sichtbar)

    def get_connector(self) -> str | None:
        if self._btn_and.isChecked():
            return "AND"
        return "OR"

    def get_states(self) -> dict:
        result = {}
        for z in self._zeilen:
            n = z.get_name()
            if n:
                result[n] = z.get_wert()
        return result


class GruppeEditorQt(QDialog):
    """
    Konfiguriert Bedingungen (condition_states) für eine passive Gruppe.
    Ersetzt GruppeEditor (tkinter).

    Signals:
        gespeichert(gruppe_name, conditions)  — nach erfolgreichem Speichern
        geloescht(gruppe_name)               — nach Löschen der Konfiguration
    """
    gespeichert = pyqtSignal(str, list)
    geloescht = pyqtSignal(str)

    def __init__(self, gruppe_name: str, bekannte_states: list[str],
                 condition_states: list | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Gruppe konfigurieren: {gruppe_name}")
        self.setModal(True)
        self.setMinimumSize(520, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._gruppe_name = gruppe_name
        self._bekannte = sorted(bekannte_states)
        self._condition_states = self._migrate(condition_states or [])
        self._gruppen: list[BedingungsGruppe] = []

        self._setup_ui()

    @staticmethod
    def _migrate(raw) -> list:
        if not raw:
            return []
        if isinstance(raw, dict):
            return [{"connector": None, "states": raw}]
        if raw and isinstance(raw[0], dict) and ("states" in raw[0] or "connector" in raw[0]):
            return list(raw)
        return []

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        lbl_titel = QLabel(f'Bedingungen für Gruppe "{self._gruppe_name}"')
        lbl_titel.setStyleSheet("color: #ffca28; font-size: 11px; font-weight: bold;")
        root.addWidget(lbl_titel)

        lbl_info = QLabel(
            "Alle Templates in dieser Gruppe sind nur aktiv wenn diese Bedingungen erfüllt sind.\n"
            "AND innerhalb einer Gruppe, Gruppen können AND oder OR verknüpft werden."
        )
        lbl_info.setStyleSheet("color: #666666; font-size: 10px;")
        lbl_info.setWordWrap(True)
        root.addWidget(lbl_info)

        # ── Scroll-Bereich für Gruppen ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._gruppen_widget = QWidget()
        self._gruppen_layout = QVBoxLayout(self._gruppen_widget)
        self._gruppen_layout.setContentsMargins(0, 0, 0, 0)
        self._gruppen_layout.setSpacing(4)
        self._gruppen_layout.addStretch()

        scroll.setWidget(self._gruppen_widget)
        root.addWidget(scroll, stretch=1)

        # Gruppen laden
        daten = self._condition_states if self._condition_states else [{"connector": None, "states": {}}]
        for gd in daten:
            self._gruppe_hinzufuegen(gd)

        # ── "+ Neue Gruppe" ───────────────────────────────────────────────────
        btn_neue_gruppe = QPushButton("＋ Neue Gruppe hinzufügen")
        btn_neue_gruppe.setObjectName("btn_icon")
        btn_neue_gruppe.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_neue_gruppe.setStyleSheet(
            "background: #1a3a5a; color: #55aaff; padding: 5px 12px; border-radius: 4px;"
        )
        btn_neue_gruppe.clicked.connect(lambda: self._gruppe_hinzufuegen({"connector": "OR", "states": {}}))
        root.addWidget(btn_neue_gruppe)

        # ── Trennlinie + Buttons ──────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3a3a3a;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()

        btn_save = QPushButton(lang.t("btn_save"))
        btn_save.setObjectName("btn_primary")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._speichern)
        btn_row.addWidget(btn_save)

        btn_del_cfg = QPushButton("Konfiguration löschen")
        btn_del_cfg.setObjectName("btn_danger")
        btn_del_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_cfg.clicked.connect(self._loeschen)
        btn_row.addWidget(btn_del_cfg)

        btn_row.addStretch()

        btn_close = QPushButton(lang.t("btn_close"))
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

    def _gruppe_hinzufuegen(self, gruppe_data: dict):
        nr = len(self._gruppen) + 1
        gruppe = BedingungsGruppe(nr, gruppe_data, self._bekannte)
        gruppe.loeschen_requested.connect(self._gruppe_entfernen)
        gruppe.set_connector_sichtbar(nr > 1)

        # Vor dem Stretch einfügen
        idx = self._gruppen_layout.count() - 1
        self._gruppen_layout.insertWidget(idx, gruppe)
        self._gruppen.append(gruppe)

    def _gruppe_entfernen(self, gruppe: BedingungsGruppe):
        if gruppe in self._gruppen:
            self._gruppen.remove(gruppe)
        gruppe.setParent(None)
        gruppe.deleteLater()
        # Ersten Connector ausblenden
        if self._gruppen:
            self._gruppen[0].set_connector_sichtbar(False)

    def _sammeln(self) -> list[dict]:
        conditions = []
        for g in self._gruppen:
            states = g.get_states()
            if states:
                conditions.append({
                    "connector": g.get_connector(),
                    "states": states,
                })
        if conditions:
            conditions[0]["connector"] = None
        return conditions

    def _speichern(self):
        conditions = self._sammeln()
        self.gespeichert.emit(self._gruppe_name, conditions)
        self.accept()

    def _loeschen(self):
        antwort = QMessageBox.question(
            self,
            "Konfiguration löschen",
            f'Gruppen-Konfiguration für "{self._gruppe_name}" wirklich löschen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if antwort == QMessageBox.StandardButton.Yes:
            self.geloescht.emit(self._gruppe_name)
            self.accept()

    @staticmethod
    def ausfuehren(gruppe_name: str, bekannte_states: list[str],
                   condition_states: list | None = None, parent=None):
        """
        Convenience-Methode. Öffnet Dialog und gibt (conditions, geloescht) zurück
        oder None bei Abbruch.
        """
        dlg = GruppeEditorQt(gruppe_name, bekannte_states, condition_states, parent)
        result = {"conditions": None, "geloescht": False}
        dlg.gespeichert.connect(lambda n, c: result.update(conditions=c))
        dlg.geloescht.connect(lambda n: result.update(geloescht=True))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result
        return None
