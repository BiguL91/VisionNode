from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QCheckBox, QScrollArea,
    QWidget, QButtonGroup, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal


class GruppeEditorQt(QDialog):
    """
    Zentraler Editor für Zustands-Bedingungen (condition_states) 
    und zu setzende Zustände (set_states).
    Wird sowohl für Gruppen (main.py) als auch für einzelne Templates (template_editor_qt.py) genutzt.

    Signals:
        gespeichert(gruppe_name, conditions, set_states)  — nach erfolgreichem Speichern
        geloescht(gruppe_name)                            — nach Löschen der Konfiguration
    """
    gespeichert = pyqtSignal(str, list, dict)
    geloescht = pyqtSignal(str)

    def __init__(self, name: str, bekannte_states: list[str],
                 condition_states: list | None = None, 
                 set_states: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Zustände & Bedingungen: {name}")
        self.setModal(True)
        self.setMinimumSize(550, 650)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._name = name
        self._bekannte = sorted(bekannte_states)
        self._condition_states = self._migrate_condition_states(condition_states or [])
        self._set_states_data = set_states or {}
        
        # UI-Referenzen für das Sammeln
        self._gruppen_ui = []
        self._set_zeilen_ui = []

        self._setup_ui()

    @staticmethod
    def _migrate_condition_states(raw) -> list:
        if not raw: return []
        if isinstance(raw, dict): return [{"connector": None, "states": raw}]
        if raw and isinstance(raw[0], dict) and ("states" in raw[0] or "connector" in raw[0]):
            return list(raw)
        return []

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        lbl_titel = QLabel(f'Konfiguration für "{self._name}"')
        lbl_titel.setObjectName("dialog_header_title_gold_small")
        root.addWidget(lbl_titel)

        # ── Bereich 1: Bedingungen (Wann ist es aktiv?) ──────────────────────
        lbl_cond_header = QLabel("Bedingungen (Wann ist dieses Element aktiv?):")
        lbl_cond_header.setProperty("class", "lbl_header_dim")
        root.addWidget(lbl_cond_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setProperty("class", "bg_dark")

        self._gruppen_container = QWidget()
        self._gruppen_layout = QVBoxLayout(self._gruppen_container)
        self._gruppen_layout.setContentsMargins(0, 0, 0, 0)
        self._gruppen_layout.setSpacing(10)
        
        scroll.setWidget(self._gruppen_container)
        root.addWidget(scroll, stretch=3)

        # Gruppen laden
        daten = self._condition_states if self._condition_states else [{"connector": None, "states": {}}]
        for gd in daten:
            self._gruppe_bauen(gd)

        btn_neue_gruppe = QPushButton("＋ Neue Bedingungsgruppe hinzufügen")
        btn_neue_gruppe.setObjectName("btn_variant_save")
        btn_neue_gruppe.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_neue_gruppe.clicked.connect(lambda: self._gruppe_bauen({"connector": "OR", "states": {}}))
        root.addWidget(btn_neue_gruppe, alignment=Qt.AlignmentFlag.AlignLeft)

        # ── Trenner ──────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("class", "separator")
        root.addWidget(sep)

        # ── Bereich 2: Set-States (Was wird bei Erkennung gesetzt?) ───────────
        lbl_set_header = QLabel("Zustände setzen (Was passiert bei Erkennung?):")
        lbl_set_header.setProperty("class", "lbl_header_dim")
        root.addWidget(lbl_set_header)

        self._set_container = QWidget()
        self._set_layout = QVBoxLayout(self._set_container)
        self._set_layout.setContentsMargins(0, 0, 0, 0)
        self._set_layout.setSpacing(4)
        root.addWidget(self._set_container)

        # Bestehende Set-States laden
        for sn, sv in self._set_states_data.items():
            self._set_zeile_bauen(sn, sv)

        btn_add_set = QPushButton("+ Zustandsänderung hinzufügen")
        btn_add_set.setObjectName("btn_add_condition")
        btn_add_set.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_set.clicked.connect(lambda: self._set_zeile_bauen())
        root.addWidget(btn_add_set, alignment=Qt.AlignmentFlag.AlignLeft)

        root.addStretch(1)

        # ── Footer-Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_save = QPushButton(lang.t("btn_save"))
        btn_save.setObjectName("btn_new")
        btn_save.clicked.connect(self._speichern)
        
        btn_del_cfg = QPushButton("Konfiguration löschen")
        btn_del_cfg.setObjectName("btn_del_sm")
        btn_del_cfg.clicked.connect(self._loeschen)

        btn_close = QPushButton("Abbrechen")
        btn_close.clicked.connect(self.reject)

        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_del_cfg)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    # ── Bedingungs-Logik (AND/OR Gruppen) ────────────────────────────────────

    def _gruppe_bauen(self, gruppe_data: dict):
        wrapper = QFrame()
        wrapper.setObjectName("condition_group_wrapper")
        w_lay = QVBoxLayout(wrapper)
        w_lay.setContentsMargins(0, 0, 0, 0)
        w_lay.setSpacing(0)

        g = {"wrapper": wrapper, "zeilen": [], "connector_var": [gruppe_data.get("connector") or "OR"]}

        # Connector (AND/OR) - nur für Gruppen > 1
        conn_frame = QFrame()
        conn_lay = QHBoxLayout(conn_frame)
        conn_lay.setContentsMargins(0, 8, 0, 4)
        
        lbl = QLabel("Verknüpfung:")
        lbl.setProperty("class", "lbl_info")
        conn_lay.addWidget(lbl)

        btn_grp = QButtonGroup(self)
        for txt in ["AND", "OR"]:
            btn = QPushButton(txt)
            btn.setCheckable(True)
            btn.setFixedWidth(50)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName(f"btn_connector_{txt.lower()}")
            if txt == g["connector_var"][0]: btn.setChecked(True)
            btn.clicked.connect(lambda checked, t=txt, ref=g: ref["connector_var"].__setitem__(0, t))
            btn_grp.addButton(btn)
            conn_lay.addWidget(btn)
        conn_lay.addStretch()
        w_lay.addWidget(conn_frame)
        g["conn_frame"] = conn_frame

        # Haupt-Box
        box = QFrame()
        box.setObjectName("condition_group")
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(8, 8, 8, 8)
        box_lay.setSpacing(4)

        header = QHBoxLayout()
        nr = len(self._gruppen_ui) + 1
        lbl_nr = QLabel(f"Gruppe {nr}")
        lbl_nr.setProperty("class", "lbl_header_dim")
        header.addWidget(lbl_nr)
        header.addStretch()
        btn_del_g = QPushButton("Gruppe löschen")
        btn_del_g.setObjectName("btn_del_sm")
        btn_del_g.clicked.connect(lambda: self._gruppe_loeschen(g))
        header.addWidget(btn_del_g)
        box_lay.addLayout(header)

        zeilen_container = QWidget()
        zeilen_lay = QVBoxLayout(zeilen_container)
        zeilen_lay.setContentsMargins(0, 4, 0, 4)
        zeilen_lay.setSpacing(2)
        box_lay.addWidget(zeilen_container)
        g["zeilen_lay"] = zeilen_lay

        for sn, sv in gruppe_data.get("states", {}).items():
            self._zeile_bauen(g, sn, sv)

        btn_add_z = QPushButton("+ Bedingung")
        btn_add_z.setObjectName("btn_add_condition")
        btn_add_z.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_z.clicked.connect(lambda: self._zeile_bauen(g))
        box_lay.addWidget(btn_add_z, alignment=Qt.AlignmentFlag.AlignLeft)

        w_lay.addWidget(box)
        
        # Vor dem Stretch einfügen
        idx = max(0, self._gruppen_layout.count() - 1)
        self._gruppen_layout.insertWidget(idx, wrapper)
        self._gruppen_ui.append(g)
        self._refresh_connectors()

    def _zeile_bauen(self, g, name="", val=True):
        z = QWidget()
        z_lay = QHBoxLayout(z)
        z_lay.setContentsMargins(4, 2, 4, 2)
        z_lay.setSpacing(6)

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._bekannte)
        combo.setCurrentText(name)
        combo.setMinimumWidth(180)
        
        chk = QCheckBox("True")
        chk.setChecked(val)
        
        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_del_sm")

        z_lay.addWidget(combo)
        z_lay.addWidget(chk)
        z_lay.addStretch()
        z_lay.addWidget(btn_del)
        g["zeilen_lay"].addWidget(z)
        
        entry = (z, combo, chk)
        g["zeilen"].append(entry)
        btn_del.clicked.connect(lambda: (g["zeilen"].remove(entry), z.deleteLater()))

    def _gruppe_loeschen(self, g):
        if g in self._gruppen_ui:
            self._gruppen_ui.remove(g)
        g["wrapper"].deleteLater()
        self._refresh_connectors()

    def _refresh_connectors(self):
        for i, g in enumerate(self._gruppen_ui):
            g["conn_frame"].setVisible(i > 0)

    # ── Set-States Logik (Aktionen) ──────────────────────────────────────────

    def _set_zeile_bauen(self, name="", val=True):
        z = QWidget()
        z.setObjectName("condition_row")
        z_lay = QHBoxLayout(z)
        z_lay.setContentsMargins(8, 4, 8, 4)
        z_lay.setSpacing(6)

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._bekannte)
        combo.setCurrentText(name)
        combo.setMinimumWidth(180)
        
        chk = QCheckBox("True")
        chk.setChecked(val)
        
        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_del_sm")

        z_lay.addWidget(combo)
        z_lay.addWidget(chk)
        z_lay.addStretch()
        z_lay.addWidget(btn_del)
        self._set_layout.addWidget(z)
        
        entry = (z, combo, chk)
        self._set_zeilen_ui.append(entry)
        btn_del.clicked.connect(lambda: (self._set_zeilen_ui.remove(entry), z.deleteLater()))

    # ── Speichern / Löschen ──────────────────────────────────────────────────

    def _speichern(self):
        conditions = []
        for g in self._gruppen_ui:
            states = {}
            for (_, combo, chk) in g["zeilen"]:
                n = combo.currentText().strip()
                if n: states[n] = chk.isChecked()
            if states:
                conditions.append({
                    "connector": g["connector_var"][0],
                    "states": states,
                })
        if conditions:
            conditions[0]["connector"] = None

        set_states = {}
        for (_, combo, chk) in self._set_zeilen_ui:
            n = combo.currentText().strip()
            if n: set_states[n] = chk.isChecked()

        self.gespeichert.emit(self._name, conditions, set_states)
        self.accept()

    def _loeschen(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Konfiguration löschen")
        msg.setText(f'Zustands-Konfiguration für "{self._name}" wirklich löschen?')
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_nein)
        msg.exec()
        if msg.clickedButton() == btn_ja:
            self.geloescht.emit(self._name)
            self.accept()

    @staticmethod
    def ausfuehren(name: str, bekannte_states: list[str],
                   condition_states: list | None = None, 
                   set_states: dict | None = None,
                   parent=None):
        dlg = GruppeEditorQt(name, bekannte_states, condition_states, set_states, parent)
        result = {"conditions": None, "set_states": None, "geloescht": False}
        dlg.gespeichert.connect(lambda n, c, s: result.update(conditions=c, set_states=s))
        dlg.geloescht.connect(lambda n: result.update(geloescht=True))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result
        return None
