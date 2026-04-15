"""
Daten-Listen-Editor (Qt). Ersetzt DatenListeEditor (tkinter).

Tabs: OCR-Transform | Berechnung | Struktur | Mapping
"""
import time
from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QScrollArea, QFrame,
    QLabel, QLineEdit, QComboBox, QPushButton, QSpinBox,
    QMessageBox, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from core.daten_manager import (
    spalten_der_liste, spalte_hinzufuegen, spalte_aktualisieren, spalte_loeschen,
    zeilen_der_liste, zeile_hinzufuegen, zeile_umbenennen, zeile_loeschen, zeile_verschieben,
    liste_umbenennen, liste_intervall_setzen, liste_loeschen,
    transformationen_der_liste, transformation_hinzufuegen,
    transformation_aktualisieren, transformation_loeschen, transformation_anwenden,
    berechnungen_der_liste, berechnung_hinzufuegen, berechnung_aktualisieren,
    berechnung_loeschen, berechnung_auswerten, cache_lesen,
    zuordnungen_der_liste, zuordnung_speichern, variable_umbenennen,
    spalte_verschieben, sekunden_formatieren,
)


# ── Formel-Builder ─────────────────────────────────────────────────────────────
class FormelBuilder(QWidget):
    """Horizontaler Editor für Formeln: [var/zahl] [op] [var/zahl] ..."""
    changed = pyqtSignal()

    def __init__(self, formel: list, optionen: list[str], b_typ: str = "ausgabe", parent=None):
        super().__init__(parent)
        self._formel = formel
        self._optionen = optionen
        self._b_typ = b_typ
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._aufbauen()

    def _aufbauen(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        i = 0
        while i < len(self._formel):
            teil = self._formel[i]

            if i == 0:
                self._slot_widget(teil, i)
                i += 1

            elif "op" in teil:
                # Operator-Dropdown
                op_combo = QComboBox()
                op_combo.addItems(["+", "-", "*", "/"])
                op_combo.setCurrentText(teil.get("op", "+"))
                op_combo.setFixedWidth(50)
                op_combo.setObjectName("formula_operator")
                idx = i
                op_combo.currentTextChanged.connect(lambda v, ix=idx: self._op_geaendert(ix, v))
                self._layout.addWidget(op_combo)

                if i + 1 < len(self._formel):
                    self._slot_widget(self._formel[i + 1], i + 1)
                    # Löschen-Button
                    btn_del = QPushButton("–")
                    btn_del.setObjectName("btn_del_sm")
                    btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_del.clicked.connect(lambda _, ix=i: self._operand_loeschen(ix))
                    self._layout.addWidget(btn_del)
                    i += 2
                    continue
                i += 1

            else:
                i += 1

        # +Var / +Zahl Buttons
        btn_var = QPushButton("+ Var")
        btn_var.setObjectName("btn_add_var")
        btn_var.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_var.clicked.connect(lambda: self._operand_hinzufuegen("var"))
        self._layout.addWidget(btn_var)

        btn_zahl = QPushButton("+ Zahl")
        btn_zahl.setObjectName("btn_add_num")
        btn_zahl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_zahl.clicked.connect(lambda: self._operand_hinzufuegen("zahl"))
        self._layout.addWidget(btn_zahl)

        self._layout.addStretch()

    def _slot_widget(self, teil: dict, idx: int):
        if "var" in teil:
            combo = QComboBox()
            combo.addItems([""] + self._optionen)
            combo.setCurrentText(teil.get("var", ""))
            combo.setMinimumWidth(160)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.currentTextChanged.connect(lambda v, ix=idx: self._var_geaendert(ix, v))
            self._layout.addWidget(combo)
        elif "zahl" in teil:
            entry = QLineEdit(str(teil.get("zahl", "")))
            entry.setFixedWidth(70)
            entry.setObjectName("formula_number_entry")
            entry.textChanged.connect(lambda v, ix=idx: self._zahl_geaendert(ix, v))
            self._layout.addWidget(entry)

    def _var_geaendert(self, idx: int, val: str):
        if idx < len(self._formel):
            self._formel[idx]["var"] = val
            self.changed.emit()

    def _zahl_geaendert(self, idx: int, val: str):
        if idx < len(self._formel):
            self._formel[idx]["zahl"] = val
            # kein rebuilt — sonst verliert Entry den Fokus

    def _op_geaendert(self, idx: int, val: str):
        if idx < len(self._formel):
            self._formel[idx]["op"] = val
            self.changed.emit()

    def _operand_hinzufuegen(self, slot_typ: str):
        self._formel.append({"op": "+"})
        self._formel.append({"var": ""} if slot_typ == "var" else {"zahl": ""})
        self._aufbauen()
        self.changed.emit()

    def _operand_loeschen(self, idx: int):
        if 0 <= idx and idx + 1 < len(self._formel):
            del self._formel[idx:idx + 2]
        self._aufbauen()
        self.changed.emit()


# ── Transform-Block ────────────────────────────────────────────────────────────
class TransformBlock(QFrame):
    loeschen_requested = pyqtSignal(int)

    def __init__(self, t: dict, ocr_vars_struk: dict, ocr_state_func, db_cache: dict, parent=None):
        """
        ocr_vars_struk: { Kategorie: { Gruppe: { Template: [ (Anzeige, Tech), ... ] } } }
        Gruppe kann "" sein (Templates ohne Container), dann wird die Gruppe-Ebene übersprungen.
        """
        super().__init__(parent)
        self._t = t
        self._ocr_vars_struk = ocr_vars_struk
        self._ocr_state_func = ocr_state_func
        self._db_cache = db_cache
        self._selected_tech = t.get("ocr_var", "")
        self.setObjectName("editor_block")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Zeile 1: Name | OCR-Var (Button) | Typ | ✕
        z1 = QHBoxLayout()

        z1.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(t["name"])
        self._name_edit.setMinimumWidth(120)
        self._name_edit.editingFinished.connect(self._name_speichern)
        z1.addWidget(self._name_edit)

        z1.addWidget(QLabel("OCR-Var:"))
        self._ocr_btn = QPushButton("Wählen...")
        self._ocr_btn.setMinimumWidth(220)
        self._ocr_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ocr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ocr_btn.clicked.connect(self._ocr_menue_zeigen)
        self._ocr_btn_aktualisieren()
        z1.addWidget(self._ocr_btn)

        z1.addWidget(QLabel("Typ:"))
        self._typ_combo = QComboBox()
        self._typ_combo.addItems(["einheit_zu_zahl", "timer", "text"])
        self._typ_combo.setCurrentText(t.get("typ", "einheit_zu_zahl"))
        self._typ_combo.currentTextChanged.connect(self._typ_speichern)
        z1.addWidget(self._typ_combo)

        z1.addStretch()
        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_del_sm")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda: self.loeschen_requested.emit(t["id"]))
        z1.addWidget(btn_del)
        layout.addLayout(z1)

        # Zeile 2: Rohwert → Ausgabe (Live)
        z2 = QHBoxLayout()
        z2.addWidget(QLabel("Rohwert:"))
        self._roh_lbl = QLabel("—")
        self._roh_lbl.setObjectName("live_value_raw")
        z2.addWidget(self._roh_lbl)
        z2.addWidget(QLabel("→"))
        z2.addWidget(QLabel("Ausgabe:"))
        self._aus_lbl = QLabel("—")
        self._aus_lbl.setObjectName("live_value_output")
        z2.addWidget(self._aus_lbl)
        z2.addStretch()
        layout.addLayout(z2)

        self._live_update()
        self._typ_combo.currentTextChanged.connect(lambda _: self._live_update())

    def _ocr_btn_aktualisieren(self):
        """Sucht den Anzeige-Namen für den technischen Key."""
        if not self._selected_tech:
            self._ocr_btn.setText("(Keine)")
            return
        
        # Einfach den technischen Key anzeigen, da dieser nun der "ganze Name" ist
        self._ocr_btn.setText(self._selected_tech)

    def _ocr_menue_zeigen(self):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        # "(Keine)" Option
        a_none = menu.addAction("(Keine)")
        a_none.triggered.connect(lambda: self._ocr_auswaehlen(""))
        menu.addSeparator()

        for kat, gruppen in self._ocr_vars_struk.items():
            kat_menu = menu.addMenu(kat.upper())
            for grp, templates in gruppen.items():
                # Gruppe-Ebene nur einziehen wenn ein Container-Name vorhanden
                grp_menu = kat_menu.addMenu(grp) if grp else kat_menu
                for tn, vars in templates.items():
                    tpl_menu = grp_menu.addMenu(tn)
                    for disp, tech in vars:
                        a = tpl_menu.addAction(disp)
                        a.triggered.connect(lambda _, t=tech: self._ocr_auswaehlen(t))

        menu.exec(self._ocr_btn.mapToGlobal(self._ocr_btn.rect().bottomLeft()))

    def _ocr_auswaehlen(self, tech_name):
        self._selected_tech = tech_name
        transformation_aktualisieren(self._t["id"], ocr_var=tech_name)
        self._ocr_btn_aktualisieren()
        self._live_update()

    def _live_update(self):
        ocr_name = self._selected_tech
        rohwert = "—"
        if ocr_name and self._ocr_state_func:
            rohwert = self._ocr_state_func(ocr_name) or "—"
        roh_str = str(rohwert)
        if self._roh_lbl.text() != roh_str:
            self._roh_lbl.setText(roh_str)

        typ = self._typ_combo.currentText()
        if rohwert not in (None, "", "—"):
            sek = transformation_anwenden(rohwert, typ)
            ausgabe = sekunden_formatieren(sek) if typ == "timer" and sek not in ("—", "?", "") else sek
        else:
            entry = self._db_cache.get(self._t["name"], ("—", 0))
            sek = entry[0]
            ausgabe = sekunden_formatieren(sek) if typ == "timer" and sek not in ("—", "?", "", None) else sek
        aus_str = str(ausgabe)
        if self._aus_lbl.text() != aus_str:
            self._aus_lbl.setText(aus_str)

    def _name_speichern(self):
        transformation_aktualisieren(self._t["id"], name=self._name_edit.text().strip())

    def _typ_speichern(self, val: str):
        transformation_aktualisieren(self._t["id"], typ=val)


# ── Berechnungs-Block ──────────────────────────────────────────────────────────
class BerechnungsBlock(QFrame):
    loeschen_requested = pyqtSignal(int)

    def __init__(self, b: dict, vars_func, werte_func, liste_id: str, parent=None):
        super().__init__(parent)
        self._b = b
        self._vars_func = vars_func
        self._werte_func = werte_func
        self._liste_id = liste_id
        self.setObjectName("editor_block")

        formel = b["formel_json"] if b["formel_json"] else [{"var": ""}]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Kopf: Name | = Ergebnis | ✕
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(b["name"])
        self._name_edit.setMinimumWidth(160)
        self._name_edit.editingFinished.connect(self._name_speichern)
        kopf.addWidget(self._name_edit)

        self._ergebnis_lbl = QLabel("= —")
        self._ergebnis_lbl.setObjectName("live_value_output_small")
        kopf.addWidget(self._ergebnis_lbl)
        kopf.addStretch()

        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_del_sm")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda: self.loeschen_requested.emit(b["id"]))
        kopf.addWidget(btn_del)
        layout.addLayout(kopf)

        # Formel-Builder
        self._formel_builder = FormelBuilder(formel, self._vars_func(), b.get("typ", "ausgabe"))
        self._formel_builder.changed.connect(self._formel_geaendert)
        layout.addWidget(self._formel_builder)

        self._ergebnis_aktualisieren()

    def _formel_geaendert(self):
        berechnung_aktualisieren(self._b["id"], formel_json=self._b["formel_json"])
        self._ergebnis_aktualisieren()

    def _ergebnis_aktualisieren(self):
        """Berechnet Werte selbst – nur für manuelle Aufrufe (z.B. nach Formel-Änderung)."""
        werte = self._werte_func()
        self._ergebnis_mit_werten(werte)

    def _ergebnis_mit_werten(self, werte: dict):
        """Setzt das Ergebnis mit bereits berechneten Werten – für den Live-Tick."""
        ergebnis = berechnung_auswerten(self._b["formel_json"], werte, 30)
        neu = f"= {ergebnis}"
        if self._ergebnis_lbl.text() != neu:
            self._ergebnis_lbl.setText(neu)

    def _name_speichern(self):
        neuer = self._name_edit.text().strip()
        alter = self._b["name"]
        if neuer and neuer != alter:
            berechnung_aktualisieren(self._b["id"], name=neuer)
            variable_umbenennen(self._liste_id, alter, neuer)
            self._b["name"] = neuer


# ── Haupt-Dialog ───────────────────────────────────────────────────────────────
class DatenListeEditorQt(QDialog):
    """
    Daten-Listen-Editor (Qt). Ersetzt DatenListeEditor (tkinter).

    Signals:
        gespeichert()   — nach Speichern
        geloescht()     — nach Listen-Löschung
    """
    gespeichert = pyqtSignal()
    geloescht = pyqtSignal()

    def __init__(self, liste: dict, ocr_state_func=None, on_gespeichert=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Liste bearbeiten: {liste['name']}")
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setMinimumHeight(600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._liste = liste
        self._ocr_state_func = ocr_state_func   # func(ocr_name) → str|None
        self._on_gespeichert = on_gespeichert

        self._transformationen = transformationen_der_liste(liste["id"])
        self._berechnungen     = berechnungen_der_liste(liste["id"])
        self._zeilen           = zeilen_der_liste(liste["id"])
        self._spalten          = spalten_der_liste(liste["id"])
        self._ocr_vars         = {}              # Struktur: { Kat: { Tpl: [ (Disp, Tech) ] } }
        self._db_cache         = cache_lesen(liste["id"])
        self._transform_blocks: list[TransformBlock]   = []
        self._berech_blocks:    list[BerechnungsBlock] = []

        self._live_timer = QTimer(self)
        self._live_timer.setInterval(1000)
        self._live_timer.timeout.connect(self._live_tick)

        self._setup_ui()

    # ── OCR-Vars ───────────────────────────────────────────────────────────────

    def _ocr_vars_laden(self) -> dict:
        return self._ocr_vars   # wird von außen gesetzt

    def set_ocr_vars(self, vars_struk: dict):
        """Erwartet Struktur: { Kategorie: { Gruppe: { Template: [ (AnzeigeName, TechnischerName) ] } } }."""
        self._ocr_vars = vars_struk
        self._transform_neu_aufbauen()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Kopf ──────────────────────────────────────────────────────────────
        kopf = QFrame()
        kopf.setObjectName("dialog_header_frame")
        kl = QHBoxLayout(kopf)
        kl.setContentsMargins(10, 6, 10, 6)

        kl.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(self._liste["name"])
        self._name_edit.setMinimumWidth(180)
        kl.addWidget(self._name_edit)

        kl.addStretch()
        root.addWidget(kopf)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._transform_tab(), "OCR Transform")
        self._tabs.addTab(self._berechnung_tab(), "Berechnung")
        self._tabs.addTab(self._struktur_tab(), "Struktur")
        self._tabs.addTab(self._mapping_tab(), "Mapping")
        self._tabs.currentChanged.connect(self._tab_gewechselt)
        root.addWidget(self._tabs, stretch=1)

        # ── Buttons ───────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("class", "separator")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_del_liste = QPushButton("✕ Liste löschen")
        btn_del_liste.setObjectName("btn_del_sm")
        btn_del_liste.clicked.connect(self._liste_loeschen)
        btn_row.addWidget(btn_del_liste)
        btn_row.addStretch()

        btn_close = QPushButton(lang.t("btn_close"))
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        btn_save = QPushButton("✔ " + lang.t("btn_save"))
        btn_save.setObjectName("btn_new")
        btn_save.clicked.connect(self._speichern)
        btn_row.addWidget(btn_save)

        root.addLayout(btn_row)

    def _tab_gewechselt(self, index):
        """Aktualisiert Tab-Inhalte beim Wechsel."""
        if index == 1:  # Berechnung
            self._berech_neu_aufbauen()
        elif index == 3:  # Mapping
            self._mapping_neu_aufbauen()

    # ── Tab: OCR Transform ─────────────────────────────────────────────────────

    def _transform_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 8, 4, 4)

        btn_add = QPushButton("+ Transformation hinzufügen")
        btn_add.setObjectName("btn_sm")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._transformation_hinzufuegen)
        layout.addWidget(btn_add)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._transform_container = QWidget()
        self._transform_layout = QVBoxLayout(self._transform_container)
        self._transform_layout.setContentsMargins(0, 0, 0, 0)
        self._transform_layout.setSpacing(4)
        self._transform_layout.addStretch()
        scroll.setWidget(self._transform_container)
        layout.addWidget(scroll)

        self._transform_neu_aufbauen()
        return w

    def _transform_neu_aufbauen(self):
        while self._transform_layout.count() > 1:
            item = self._transform_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._transformationen = transformationen_der_liste(self._liste["id"])
        # Reverse-Lookup aufbauen: tech_name → (kategorie, gruppe, template)
        _var_lookup: dict[str, tuple[str, str, str]] = {}
        for kat, gruppen in self._ocr_vars.items():
            for grp, templates in gruppen.items():
                for tn, vars in templates.items():
                    for _disp, tech in vars:
                        _var_lookup[tech] = (kat, grp, tn)
        # Nach Workflow/State → Gruppe/Container → Template → Var sortieren
        self._transformationen.sort(key=lambda x: (
            *_var_lookup.get(x.get("ocr_var", ""), ("zzz", "zzz", "zzz")),
            x.get("ocr_var", ""),
        ))
        
        self._db_cache = cache_lesen(self._liste["id"])

        self._transform_blocks = []
        if not self._transformationen:
            lbl = QLabel("Keine Transformationen definiert.")
            lbl.setProperty("class", "lbl_dim")
            self._transform_layout.insertWidget(0, lbl)
            return

        for i, t in enumerate(self._transformationen):
            block = TransformBlock(t, self._ocr_vars, self._ocr_state_func, self._db_cache)
            block.loeschen_requested.connect(self._transformation_loeschen)
            self._transform_layout.insertWidget(i, block)
            self._transform_blocks.append(block)

    def _transformation_hinzufuegen(self):
        transformation_hinzufuegen(self._liste["id"], "neu_transform", "", "einheit_zu_zahl")
        self._transform_neu_aufbauen()

    def _transformation_loeschen(self, trans_id: int):
        transformation_loeschen(trans_id)
        self._transformationen = [t for t in self._transformationen if t["id"] != trans_id]
        self._transform_neu_aufbauen()

    # ── Tab: Berechnung ────────────────────────────────────────────────────────

    def _berechnung_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._berech_container = QWidget()
        self._berech_layout = QVBoxLayout(self._berech_container)
        self._berech_layout.setContentsMargins(0, 0, 0, 0)
        self._berech_layout.setSpacing(4)
        self._berech_layout.addStretch()
        scroll.setWidget(self._berech_container)
        layout.addWidget(scroll)

        self._berech_neu_aufbauen()
        return w

    def _berech_vars(self, nur_zwischen: bool = False) -> list[str]:
        self._transformationen = transformationen_der_liste(self._liste["id"])
        self._berechnungen = berechnungen_der_liste(self._liste["id"])
        namen = [t["name"] for t in self._transformationen if t.get("name")]
        namen += [b["name"] for b in self._berechnungen if b.get("name") and b.get("typ") == "zwischen"]
        if not nur_zwischen:
            namen += [b["name"] for b in self._berechnungen if b.get("name") and b.get("typ") == "ausgabe"]
        return namen + ["zeit_h", "zeit_m", "zeit_s"]

    def _berech_werte(self) -> dict:
        self._db_cache = cache_lesen(self._liste["id"])
        werte = dict(self._db_cache)
        jetzt = time.time()
        for t in self._transformationen:
            rohwert = self._ocr_state_func(t["ocr_var"]) if self._ocr_state_func and t.get("ocr_var") else None
            if rohwert not in (None, "", "—"):
                aus = transformation_anwenden(rohwert, t["typ"])
                if aus not in (None, "", "—", "?"):
                    werte[t["name"]] = (aus, jetzt)
        between = [b for b in self._berechnungen if b.get("typ") == "zwischen"]
        rest = [b for b in self._berechnungen if b.get("typ") != "zwischen"]
        for b in between + rest:
            er = berechnung_auswerten(b["formel_json"], werte, self._liste.get("update_intervall", 30))
            if er not in ("?", "—") and b["formel_json"]:
                werte[b["name"]] = (er, jetzt)
        return werte

    def _berech_sektion(self, titel: str, farbe: str, blocks: list, typ: str):
        header = QFrame()
        header.setObjectName("calculation_header")
        header.setProperty("type", typ) # "zwischen" | "ausgabe"
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel(titel)
        lbl.setObjectName("calculation_header_title")
        lbl.setProperty("type", typ)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        btn_add = QPushButton("+ Hinzufügen")
        btn_add.setObjectName("btn_calculation_add")
        btn_add.setProperty("type", typ)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(lambda: self._berechnung_hinzufuegen(typ))
        h_layout.addWidget(btn_add)
        self._berech_layout.insertWidget(self._berech_layout.count() - 1, header)

        for b in blocks:
            block = BerechnungsBlock(
                b,
                lambda nz=typ: self._berech_vars(nz == "zwischen"),
                self._berech_werte,
                self._liste["id"]
            )
            block.loeschen_requested.connect(self._berechnung_loeschen)
            self._berech_layout.insertWidget(self._berech_layout.count() - 1, block)
            self._berech_blocks.append(block)

    def _berech_neu_aufbauen(self):
        self._berech_blocks = []
        while self._berech_layout.count() > 1:
            item = self._berech_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._berechnungen = berechnungen_der_liste(self._liste["id"])
        zwischen = [b for b in self._berechnungen if b.get("typ") == "zwischen"]
        ausgabe  = [b for b in self._berechnungen if b.get("typ") != "zwischen"]

        self._berech_sektion("ZWISCHENBERECHNUNG", "#4caf50", zwischen, "zwischen")
        self._berech_sektion("AUSGABE", "#4fc3f7", ausgabe, "ausgabe")

    def _berechnung_hinzufuegen(self, typ: str = "ausgabe"):
        name = "neue_zwischen" if typ == "zwischen" else "neue_ausgabe"
        berechnung_hinzufuegen(self._liste["id"], name, typ=typ)
        self._berech_neu_aufbauen()

    def _berechnung_loeschen(self, bid: int):
        berechnung_loeschen(bid)
        self._berechnungen = [b for b in self._berechnungen if b["id"] != bid]
        self._berech_neu_aufbauen()

    # ── Tab: Struktur ──────────────────────────────────────────────────────────

    def _struktur_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(12)

        # Zeilen
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        lbl_z = QLabel("ZEILEN")
        lbl_z.setProperty("class", "lbl_header_dim")
        ll.addWidget(lbl_z)
        btn_z = QPushButton("+ Zeile")
        btn_z.setObjectName("btn_sm")
        btn_z.clicked.connect(self._zeile_hinzufuegen)
        ll.addWidget(btn_z)
        sc_z = QScrollArea()
        sc_z.setWidgetResizable(True)
        sc_z.setFrameShape(QFrame.Shape.NoFrame)
        self._zeilen_widget = QWidget()
        self._zeilen_layout = QVBoxLayout(self._zeilen_widget)
        self._zeilen_layout.setContentsMargins(0, 0, 0, 0)
        self._zeilen_layout.setSpacing(2)
        self._zeilen_layout.addStretch()
        sc_z.setWidget(self._zeilen_widget)
        ll.addWidget(sc_z)
        layout.addWidget(links)

        # Spalten
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        lbl_s = QLabel("SPALTEN")
        lbl_s.setProperty("class", "lbl_header_dim")
        rl.addWidget(lbl_s)
        btn_s = QPushButton("+ Spalte")
        btn_s.setObjectName("btn_sm")
        btn_s.clicked.connect(self._spalte_hinzufuegen)
        rl.addWidget(btn_s)
        sc_s = QScrollArea()
        sc_s.setWidgetResizable(True)
        sc_s.setFrameShape(QFrame.Shape.NoFrame)
        self._spalten_widget = QWidget()
        self._spalten_layout = QVBoxLayout(self._spalten_widget)
        self._spalten_layout.setContentsMargins(0, 0, 0, 0)
        self._spalten_layout.setSpacing(2)
        self._spalten_layout.addStretch()
        sc_s.setWidget(self._spalten_widget)
        rl.addWidget(sc_s)
        layout.addWidget(rechts)

        self._zeilen_neu_aufbauen()
        self._spalten_neu_aufbauen()
        return w

    def _zeile_widget_erstellen(self, z: dict):
        row = QFrame()
        row.setObjectName("structure_row")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(4, 2, 4, 2)
        entry = QLineEdit(z["name"])
        entry.editingFinished.connect(lambda zid=z["id"], e=entry: self._zeile_speichern(zid, e.text()))
        rl.addWidget(entry)

        btn_up = QPushButton("▲")
        btn_up.setObjectName("btn_move_sm")
        btn_up.setFixedWidth(24)
        btn_up.clicked.connect(lambda _, zid=z["id"]: self._zeile_verschieben(zid, -1))
        rl.addWidget(btn_up)

        btn_down = QPushButton("▼")
        btn_down.setObjectName("btn_move_sm")
        btn_down.setFixedWidth(24)
        btn_down.clicked.connect(lambda _, zid=z["id"]: self._zeile_verschieben(zid, 1))
        rl.addWidget(btn_down)

        btn = QPushButton("✕")
        btn.setObjectName("btn_del_sm")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _, zid=z["id"]: self._zeile_loeschen(zid))
        rl.addWidget(btn)
        return row

    def _zeilen_neu_aufbauen(self):
        while self._zeilen_layout.count() > 1:
            item = self._zeilen_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._zeilen = zeilen_der_liste(self._liste["id"])
        for i, z in enumerate(self._zeilen):
            self._zeilen_layout.insertWidget(i, self._zeile_widget_erstellen(z))

    def _zeile_hinzufuegen(self):
        zeile_hinzufuegen(self._liste["id"], "Neu")
        self._zeilen_neu_aufbauen()

    def _zeile_loeschen(self, zid: str):
        zeile_loeschen(zid)
        self._zeilen = [z for z in self._zeilen if z["id"] != zid]
        self._zeilen_neu_aufbauen()

    def _zeile_verschieben(self, zid: int, richtung: int):
        zeile_verschieben(zid, richtung)
        self._zeilen_neu_aufbauen()

    def _zeile_speichern(self, zid: str, neuer: str):
        neuer = neuer.strip()
        if neuer:
            zeile_umbenennen(zid, neuer)

    def _spalte_widget_erstellen(self, sp: dict):
        row = QFrame()
        row.setObjectName("structure_row")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(4, 2, 4, 2)
        rl.setSpacing(4)

        name_e = QLineEdit(sp["name"])
        name_e.setMinimumWidth(120)
        name_e.editingFinished.connect(lambda sid=sp["id"], e=name_e: spalte_aktualisieren(sid, name=e.text().strip()))
        rl.addWidget(name_e)

        typ_c = QComboBox()
        typ_c.addItems(["zahl", "text"])
        typ_c.setCurrentText(sp.get("typ", "zahl"))
        typ_c.setFixedWidth(65)
        typ_c.currentTextChanged.connect(lambda v, sid=sp["id"]: spalte_aktualisieren(sid, typ=v))
        rl.addWidget(typ_c)

        fmt_c = QComboBox()
        fmt_c.addItems(["standard", "K/M/B", "0 (Ganzzahl)", ".2 (2 Nachkomma)", "timer"])
        fmt_c.setCurrentText(sp.get("format") or "standard")
        fmt_c.setMinimumWidth(130)
        fmt_c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        fmt_c.currentTextChanged.connect(lambda v, sid=sp["id"]: spalte_aktualisieren(sid, format=v))
        rl.addWidget(fmt_c)

        btn_up = QPushButton("▲")
        btn_up.setObjectName("btn_move_sm")
        btn_up.setFixedWidth(24)
        btn_up.clicked.connect(lambda _, sid=sp["id"]: self._spalte_verschieben(sid, -1))
        rl.addWidget(btn_up)

        btn_down = QPushButton("▼")
        btn_down.setObjectName("btn_move_sm")
        btn_down.setFixedWidth(24)
        btn_down.clicked.connect(lambda _, sid=sp["id"]: self._spalte_verschieben(sid, 1))
        rl.addWidget(btn_down)

        btn = QPushButton("✕")
        btn.setObjectName("btn_del_sm")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _, sid=sp["id"]: self._spalte_loeschen(sid))
        rl.addWidget(btn)
        return row

    def _spalten_neu_aufbauen(self):
        while self._spalten_layout.count() > 1:
            item = self._spalten_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._spalten = spalten_der_liste(self._liste["id"])
        for i, sp in enumerate(self._spalten):
            self._spalten_layout.insertWidget(i, self._spalte_widget_erstellen(sp))

    def _spalte_hinzufuegen(self):
        spalte_hinzufuegen(self._liste["id"], "Neu", typ="zahl")
        self._spalten_neu_aufbauen()

    def _spalte_loeschen(self, sid: str):
        spalte_loeschen(sid)
        self._spalten = [s for s in self._spalten if s["id"] != sid]
        self._spalten_neu_aufbauen()

    def _spalte_verschieben(self, sid: int, richtung: int):
        spalte_verschieben(sid, richtung)
        self._spalten_neu_aufbauen()

    # ── Tab: Mapping ───────────────────────────────────────────────────────────

    def _mapping_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 8, 4, 4)

        info = QLabel("Spezifische Zuordnung: Welcher Wert für welche Zelle?")
        info.setProperty("class", "lbl_info")
        layout.addWidget(info)

        self._mapping_table = QTableWidget()
        self._mapping_table.setObjectName("mapping_table")
        # ResizeMode.ResizeToContents stellt sicher, dass alles sichtbar ist
        header = self._mapping_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._mapping_table)

        self._mapping_neu_aufbauen()
        return w

    def _mapping_neu_aufbauen(self):
        self._zeilen = zeilen_der_liste(self._liste["id"])
        self._spalten = spalten_der_liste(self._liste["id"])
        self._transformationen = transformationen_der_liste(self._liste["id"])
        self._berechnungen = berechnungen_der_liste(self._liste["id"])
        zuordnungen = zuordnungen_der_liste(self._liste["id"])

        optionen = [""] \
            + [t["name"] for t in self._transformationen if t.get("name")] \
            + [b["name"] for b in self._berechnungen if b.get("name")]

        tbl = self._mapping_table
        tbl.clear()
        tbl.setRowCount(len(self._zeilen))
        tbl.setColumnCount(len(self._spalten))
        tbl.setVerticalHeaderLabels([z["name"] for z in self._zeilen])
        tbl.setHorizontalHeaderLabels([s["name"] for s in self._spalten])

        for r, zeile in enumerate(self._zeilen):
            for c, sp in enumerate(self._spalten):
                val = zuordnungen.get((zeile["name"], sp["id"]), "")
                combo = QComboBox()
                combo.addItems(optionen)
                combo.setCurrentText(val)
                combo.currentTextChanged.connect(
                    lambda v, zn=zeile["name"], sid=sp["id"]: zuordnung_speichern(self._liste["id"], zn, sid, v)
                )
                tbl.setCellWidget(r, c, combo)

    # ── Speichern / Löschen ────────────────────────────────────────────────────

    def _speichern(self):
        neuer_name = self._name_edit.text().strip()
        if neuer_name and neuer_name != self._liste["name"]:
            liste_umbenennen(self._liste["id"], neuer_name)
            self._liste["name"] = neuer_name
            self.setWindowTitle(f"Liste bearbeiten: {neuer_name}")

        self.gespeichert.emit()
        if self._on_gespeichert:
            self._on_gespeichert()
        # Dialog bleibt offen (nur Schließen-Button oder X beendet)

    # ── Live-Tick ──────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if self._ocr_state_func:
            self._live_timer.start()

    def closeEvent(self, event):
        self._live_timer.stop()
        super().closeEvent(event)

    def _live_tick(self):
        """Aktualisiert Roh-/Ausgabe-Werte in Transform- und Berechnungs-Blöcken."""
        idx = self._tabs.currentIndex()
        if idx == 0:  # OCR Transform
            for block in self._transform_blocks:
                block._live_update()
        elif idx == 1:  # Berechnung
            if self._berech_blocks:
                werte = self._berech_werte()  # einmal DB-Read für alle Blöcke
                for block in self._berech_blocks:
                    block._ergebnis_mit_werten(werte)

    # ── Listen-Aktionen ────────────────────────────────────────────────────────

    def _liste_loeschen(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Liste löschen")
        msg.setText(f"Liste '{self._liste['name']}' wirklich löschen?\nAlle Daten gehen verloren.")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_nein)
        msg.exec()
        
        if msg.clickedButton() == btn_ja:
            liste_loeschen(self._liste["id"])
            self.geloescht.emit()
            if self._on_gespeichert:
                self._on_gespeichert()
            self.accept()
