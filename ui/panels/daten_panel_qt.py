import time
from lang import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QGridLayout, QComboBox,
    QInputDialog, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from core.daten_manager import (
    datenbank_initialisieren, alle_listen, spalten_der_liste,
    zeilen_der_liste, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen,
    zuordnungen_der_liste, sekunden_formatieren, liste_erstellen, liste_loeschen
)


class ListenBlock(QFrame):
    """Ein einzelner aufklappbarer Listen-Block mit Tabelle."""

    def __init__(self, listen_dict: dict, bot_ref, parent=None):
        super().__init__(parent)
        self.l = listen_dict
        self.bot_ref = bot_ref
        self._aufgeklappt = True
        self._wert_labels: dict[tuple, QLabel] = {}  # (zeile_name, col_idx) → QLabel

        self.setObjectName("collapsible_panel")
        self._setup_ui()
        self._tabelle_zeichnen()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("collapsible_header")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(6, 4, 6, 4)

        self.pfeil = QLabel("▼")
        self.pfeil.setObjectName("collapse_arrow")
        h_layout.addWidget(self.pfeil)

        lbl = QLabel(self.l["name"])
        lbl.setObjectName("panel_title")
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        header.mousePressEvent = lambda e: self._toggle()
        root.addWidget(header)

        # Inhalt-Container
        self.inhalt = QWidget()
        inhalt_layout = QVBoxLayout(self.inhalt)
        inhalt_layout.setContentsMargins(4, 4, 4, 4)

        self.tabelle_widget = QWidget()
        self.tabelle_layout = QGridLayout(self.tabelle_widget)
        self.tabelle_layout.setSpacing(0)
        inhalt_layout.addWidget(self.tabelle_widget)

        root.addWidget(self.inhalt)

    def _toggle(self):
        self._aufgeklappt = not self._aufgeklappt
        self.inhalt.setVisible(self._aufgeklappt)
        self.pfeil.setText("▼" if self._aufgeklappt else "▶")

    def _tabelle_zeichnen(self):
        """Vollständiger Widget-Aufbau der Tabelle."""
        # Alte Widgets entfernen
        while self.tabelle_layout.count():
            item = self.tabelle_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._wert_labels.clear()

        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_berechnen()

        if not spalten:
            lbl = QLabel("Keine Spalten — Edit zum Konfigurieren.")
            lbl.setProperty("class", "lbl_dim")
            self.tabelle_layout.addWidget(lbl, 0, 0)
            return

        if not zeilen_namen:
            lbl = QLabel("(Keine Zeilen — Edit zum Konfigurieren)")
            lbl.setProperty("class", "lbl_dim")
            self.tabelle_layout.addWidget(lbl, 0, 0)
            return

        # Header
        lbl_zeile = QLabel("Zeile")
        lbl_zeile.setObjectName("daten_tab_header")
        lbl_zeile.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tabelle_layout.addWidget(lbl_zeile, 0, 0)

        for i, sp in enumerate(spalten):
            lbl = QLabel(sp["name"])
            lbl.setObjectName("daten_tab_header")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabelle_layout.addWidget(lbl, 0, i + 1)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setProperty("class", "separator")
        self.tabelle_layout.addWidget(line, 1, 0, 1, len(spalten) + 1)

        # Datenzeilen
        for r, z in enumerate(zeilen_namen):
            is_alt = r % 2 != 0
            row_idx = r + 2

            lbl_name = QLabel(z["name"])
            lbl_name.setObjectName("daten_tab_cell")
            lbl_name.setProperty("alt", is_alt)
            self.tabelle_layout.addWidget(lbl_name, row_idx, 0)

            for ci, sp in enumerate(spalten):
                ocr_var = zuordnungen.get((z["name"], sp["id"]))
                if not ocr_var:
                    ocr_var = sp.get("ocr_var")
                    if ocr_var and "{row}" in ocr_var:
                        ocr_var = ocr_var.replace("{row}", z["name"])

                entry = ocr_werte.get(ocr_var, ("—", 0)) if ocr_var else ("—", 0)
                wert = entry[0]
                anzeige = self._format_wert(wert, sp.get("format", "standard"))
                ist_berech = ocr_var in berech_namen

                lbl = QLabel(anzeige)
                lbl.setObjectName("daten_tab_cell")
                lbl.setProperty("alt", is_alt)
                lbl.setProperty("highlight", ist_berech)
                lbl.setFont(QFont("Consolas", 8))
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabelle_layout.addWidget(lbl, row_idx, ci + 1)
                self._wert_labels[(z["name"], ci)] = lbl

    def werte_aktualisieren(self):
        """Nur Werte aktualisieren, kein Rebuild."""
        if not self._aufgeklappt:
            return
        if not self._wert_labels:
            self._tabelle_zeichnen()
            return

        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_berechnen()
        for r, z in enumerate(zeilen_namen):
            for ci, sp in enumerate(spalten):
                ocr_var = zuordnungen.get((z["name"], sp["id"]))
                if not ocr_var:
                    ocr_var = sp.get("ocr_var")
                    if ocr_var and "{row}" in ocr_var:
                        ocr_var = ocr_var.replace("{row}", z["name"])
                entry = ocr_werte.get(ocr_var, ("—", 0)) if ocr_var else ("—", 0)
                anzeige = self._format_wert(entry[0], sp.get("format", "standard"))
                lbl = self._wert_labels.get((z["name"], ci))
                if lbl:
                    lbl.setText(anzeige)

    def _werte_berechnen(self):
        spalten       = spalten_der_liste(self.l["id"])
        zeilen_namen  = zeilen_der_liste(self.l["id"])
        transformationen = transformationen_der_liste(self.l["id"])
        berechnungen  = berechnungen_der_liste(self.l["id"])
        db_cache      = cache_lesen(self.l["id"])
        ocr_werte     = dict(db_cache)

        ocr_roh_live = {}
        if self.bot_ref and hasattr(self.bot_ref, "app"):
            ocr_roh_live.update(self.bot_ref.app.state.ocr_values)
            ocr_roh_live.update(self.bot_ref.app.state.template_ocr_values)

        ausgabe_namen = {t["name"] for t in transformationen} | {b["name"] for b in berechnungen}
        jetzt = time.time()
        neue_cache_werte = {}

        for name, val in ocr_roh_live.items():
            if name in ausgabe_namen:
                continue
            if val not in (None, "", "—"):
                ocr_werte[name] = (val, jetzt)
                neue_cache_werte[name] = val

        for t in transformationen:
            rohwert = ocr_roh_live.get(t["ocr_var"])
            if rohwert not in (None, "", "—"):
                wert = transformation_anwenden(rohwert, t["typ"])
                if wert not in ("", "—", "?"):
                    ocr_werte[t["name"]] = (wert, jetzt)
                    neue_cache_werte[t["name"]] = wert
                    if t["typ"] == "timer":
                        try:
                            neue_cache_werte[f"Timer.{t['name']}._deadline"] = str(jetzt + float(wert))
                        except (ValueError, TypeError):
                            pass
            elif t["typ"] == "timer":
                de = db_cache.get(f"Timer.{t['name']}._deadline")
                if de and de[0] not in (None, "", "—", "?"):
                    try:
                        rest = max(0, int(float(de[0]) - jetzt))
                        ocr_werte[t["name"]] = (str(rest), jetzt)
                        neue_cache_werte[t["name"]] = str(rest)
                    except (ValueError, TypeError):
                        pass

        berech_sortiert = (
            [b for b in berechnungen if b.get("typ") == "zwischen"] +
            [b for b in berechnungen if b.get("typ") != "zwischen"]
        )
        for b in berech_sortiert:
            ergebnis = berechnung_auswerten(b["formel_json"], ocr_werte, self.l["update_intervall"])
            if ergebnis not in ("?", "—") and b["formel_json"]:
                ocr_werte[b["name"]] = (ergebnis, jetzt)
                neue_cache_werte[b["name"]] = ergebnis

        for var_name, wert in neue_cache_werte.items():
            cache_schreiben(self.l["id"], var_name, wert)

        berech_namen  = {b["name"] for b in berechnungen}
        zuordnungen   = zuordnungen_der_liste(self.l["id"])
        return ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen

    def _format_wert(self, wert, format_typ):
        if wert in (None, "", "—", "?"):
            return str(wert) if wert else "—"
        try:
            num = float(str(wert).replace(",", "."))
        except (ValueError, TypeError):
            return str(wert)
        if format_typ == "K/M/B":
            if abs(num) >= 1e9: return f"{num/1e9:.1f}B"
            if abs(num) >= 1e6: return f"{num/1e6:.1f}M"
            if abs(num) >= 1e3: return f"{num/1e3:.1f}K"
            return str(round(num, 1))
        if format_typ == "0 (Ganzzahl)":   return str(int(round(num)))
        if format_typ == ".2 (2 Nachkomma)": return f"{num:.2f}"
        if format_typ == "timer":            return sekunden_formatieren(num)
        return str(int(num)) if num == int(num) else str(round(num, 1))


class DatenPanel(QWidget):
    liste_bearbeiten_requested = pyqtSignal(dict)   # listen_dict
    einheiten_requested        = pyqtSignal()

    def __init__(self, bot_ref=None, parent=None):
        super().__init__(parent)
        self.bot_ref = bot_ref
        self._listen_cache: list = []
        self._bloecke: dict[int, ListenBlock] = {}  # listen_id → Block

        datenbank_initialisieren()
        self._setup_ui()
        self._alles_aufbauen()

        # Auto-Update Timer
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._auto_update)
        self._update_timer.start(1000)

        # Transform-Loop
        self._transform_timer = QTimer(self)
        self._transform_timer.timeout.connect(self._transform_tick)
        self._transform_timer.start(800)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # Zeile 1: Dropdown
        zeile1 = QHBoxLayout()
        zeile1.setContentsMargins(4, 4, 4, 0)
        zeile1.setSpacing(4)

        self.dropdown = QComboBox()
        self.dropdown.setCursor(Qt.CursorShape.PointingHandCursor)
        zeile1.addWidget(self.dropdown)

        root.addLayout(zeile1)

        # Zeile 2: Buttons (strecken sich)
        zeile2 = QHBoxLayout()
        zeile2.setContentsMargins(4, 0, 4, 0)
        zeile2.setSpacing(4)

        self.btn_neu = QPushButton("+ Neu")
        self.btn_neu.setObjectName("btn_new_sm")
        self.btn_neu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_neu.clicked.connect(self._neue_liste)

        self.btn_edit = QPushButton("✎ Bearbeiten")
        self.btn_edit.setObjectName("btn_sm")
        self.btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit.clicked.connect(self._liste_bearbeiten)

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setObjectName("btn_del_sm")
        self.btn_delete.setToolTip("Liste löschen")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self._liste_loeschen_dialog)

        self.btn_einheiten = QPushButton("⚖️ Einheiten")
        self.btn_einheiten.setObjectName("btn_sm")
        self.btn_einheiten.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_einheiten.clicked.connect(self.einheiten_requested)

        for btn in [self.btn_neu, self.btn_edit, self.btn_delete, self.btn_einheiten]:
            zeile2.addWidget(btn)

        root.addLayout(zeile2)

        # Scrollbarer Bereich
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def listen_neu_laden(self):
        self._alles_aufbauen()

    # ── Intern ────────────────────────────────────────────────────────────────

    def _alles_aufbauen(self):
        while self.container_layout.count() > 1:  # Stretch bleibt
            item = self.container_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._bloecke.clear()

        self._listen_cache = alle_listen()
        self._dropdown_aktualisieren()

        if not self._listen_cache:
            lbl = QLabel("Keine Listen vorhanden.")
            lbl.setProperty("class", "lbl_empty_hint")
            self.container_layout.insertWidget(0, lbl)
            return

        for i, l in enumerate(self._listen_cache):
            block = ListenBlock(l, self.bot_ref)
            self.container_layout.insertWidget(i, block)
            self._bloecke[l["id"]] = block

    def _dropdown_aktualisieren(self):
        self.dropdown.clear()
        for l in self._listen_cache:
            self.dropdown.addItem(l["name"], l["id"])

    def _neue_liste(self):
        name, ok = QInputDialog.getText(self, "Neue Liste", "Name der Liste:")
        if ok and name.strip():
            liste_erstellen(name.strip())
            self._alles_aufbauen()
            idx = self.dropdown.findText(name.strip())
            if idx >= 0:
                self.dropdown.setCurrentIndex(idx)

    def _liste_bearbeiten(self):
        listen_id = self.dropdown.currentData()
        if listen_id is None:
            return
        l = next((x for x in self._listen_cache if x["id"] == listen_id), None)
        if l:
            self.liste_bearbeiten_requested.emit(l)

    def _liste_loeschen_dialog(self):
        listen_id = self.dropdown.currentData()
        if listen_id is None:
            return
        listen_name = self.dropdown.currentText()
        antwort = QMessageBox.question(
            self, "Liste löschen",
            f"Möchtest du die Liste '{listen_name}' wirklich unwiderruflich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if antwort == QMessageBox.StandardButton.Yes:
            liste_loeschen(listen_id)
            self._alles_aufbauen()

    def _auto_update(self):
        for block in self._bloecke.values():
            block.werte_aktualisieren()
        # Timer-Intervall aus Min-Intervall aller Listen
        if self._listen_cache:
            min_iv = min(l["update_intervall"] for l in self._listen_cache)
            self._update_timer.setInterval(max(500, min_iv * 1000))

    def _transform_tick(self):
        if not self.bot_ref or not hasattr(self.bot_ref, "app"):
            return
        ocr_roh = {}
        ocr_roh.update(self.bot_ref.app.state.ocr_values)
        ocr_roh.update(self.bot_ref.app.state.template_ocr_values)
        if not ocr_roh:
            return
        jetzt = time.time()
        for l in self._listen_cache:
            for t in transformationen_der_liste(l["id"]):
                rohwert = ocr_roh.get(t["ocr_var"])
                if rohwert not in (None, "", "—"):
                    wert = transformation_anwenden(rohwert, t["typ"])
                    if wert not in ("", "—", "?"):
                        cache_schreiben(l["id"], t["name"], wert)
                        if t["typ"] == "timer":
                            try:
                                cache_schreiben(l["id"], f"Timer.{t['name']}._deadline",
                                               str(jetzt + float(wert)))
                            except (ValueError, TypeError):
                                pass
