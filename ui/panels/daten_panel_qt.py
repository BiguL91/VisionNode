import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QGridLayout, QComboBox,
    QInputDialog, QSizePolicy, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QAction

from core.daten_manager import (
    datenbank_initialisieren, alle_listen, spalten_der_liste,
    zeilen_der_liste, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen,
    zuordnungen_der_liste, sekunden_formatieren, liste_erstellen, liste_loeschen
)


class ListenBlock(QFrame):
    """Ein einzelner aufklappbarer Listen-Block mit QTableWidget."""

    def __init__(self, listen_dict: dict, bot_ref, parent=None):
        super().__init__(parent)
        self.l = listen_dict
        self.bot_ref = bot_ref
        self._aufgeklappt = True

        self.setObjectName("collapsible_panel")
        self._setup_ui()
        self._tabelle_zeichnen()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
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

        # Tabelle
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        
        # Performance & Style
        self.table.setProperty("class", "daten_tabelle")
        
        root.addWidget(self.table)

    def _toggle(self):
        self._aufgeklappt = not self._aufgeklappt
        self.table.setVisible(self._aufgeklappt)
        self.pfeil.setText("▼" if self._aufgeklappt else "▶")
        if self._aufgeklappt:
            self._tabelle_zeichnen()

    def _tabelle_zeichnen(self):
        """Initialer Aufbau der Tabelle."""
        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_berechnen()

        if self.l.get("typ") == "timer":
            self.table.setColumnCount(2)
            self.table.setRowCount(len(zeilen_namen))
            self.table.setHorizontalHeaderLabels(["Name", "Wert"])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            
            for r, z in enumerate(zeilen_namen):
                full_name = z["name"]
                display_name = full_name
                if full_name.startswith("[T] "): display_name = full_name[4:]
                elif full_name.startswith("[W] "): display_name = full_name[4:]
                
                self.table.setItem(r, 0, QTableWidgetItem(display_name))
                item_val = QTableWidgetItem("—")
                item_val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 1, item_val)
        else:
            if not spalten:
                self.table.setColumnCount(1)
                self.table.setRowCount(1)
                self.table.setHorizontalHeaderLabels(["Info"])
                self.table.setItem(0, 0, QTableWidgetItem("Keine Spalten konfiguriert."))
                return

            self.table.setColumnCount(len(spalten) + 1)
            self.table.setRowCount(len(zeilen_namen))
            headers = ["Zeile"] + [s["name"] for s in spalten]
            self.table.setHorizontalHeaderLabels(headers)
            
            for r, z in enumerate(zeilen_namen):
                self.table.setItem(r, 0, QTableWidgetItem(z["name"]))
                for ci, sp in enumerate(spalten):
                    item = QTableWidgetItem("—")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(r, ci + 1, item)

        self.werte_aktualisieren()
        # Höhe an Inhalt anpassen (Kompakt-Modus)
        h = self.table.horizontalHeader().height() + (self.table.rowCount() * self.table.verticalHeader().defaultSectionSize()) + 2
        self.table.setMinimumHeight(min(h, 400))
        self.table.setMaximumHeight(h)

    def werte_aktualisieren(self):
        """Nur Werte in der bestehenden Tabelle updaten."""
        if not self._aufgeklappt or self.table.rowCount() == 0:
            return

        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_berechnen()
        
        if self.l.get("typ") == "timer":
            for r, z in enumerate(zeilen_namen):
                full_name = z["name"]
                is_timer = not full_name.startswith("[W] ")
                val = ocr_werte.get(full_name, ("—", 0))[0]
                anzeige = sekunden_formatieren(val) if is_timer and val not in ("—", "?") else str(val)
                
                item = self.table.item(r, 1)
                if item:
                    item.setText(anzeige)
                    if is_timer: item.setForeground(QColor("#42a5f5"))
        else:
            for r, z in enumerate(zeilen_namen):
                for ci, sp in enumerate(spalten):
                    ocr_var = zuordnungen.get((z["name"], sp["id"]))
                    if not ocr_var:
                        ocr_var = sp.get("ocr_var")
                        if ocr_var and "{row}" in ocr_var:
                            ocr_var = ocr_var.replace("{row}", z["name"])

                    entry = ocr_werte.get(ocr_var, ("—", 0)) if ocr_var else ("—", 0)
                    wert = entry[0]
                    anzeige = self._format_wert(wert, sp.get("format", "standard"))
                    
                    item = self.table.item(r, ci + 1)
                    if item:
                        item.setText(anzeige)
                        if ocr_var in berech_namen:
                            item.setForeground(QColor("#4fc3f7"))
                        elif sp.get("typ") == "timer":
                            item.setForeground(QColor("#e91e63"))
                        else:
                            item.setForeground(QColor("#cccccc"))

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

        # 1. Timer-Logik für Timer-Listen
        if self.l.get("typ") == "timer":
            for z in zeilen_namen:
                t_name = z["name"]
                de_key = f"Timer.{t_name}._deadline"
                de_entry = db_cache.get(de_key)
                if de_entry and de_entry[0] not in (None, "", "—", "?"):
                    try:
                        rest = max(0, int(float(de_entry[0]) - jetzt))
                        ocr_werte[t_name] = (str(rest), jetzt)
                        neue_cache_werte[t_name] = str(rest)
                    except (ValueError, TypeError):
                        pass

        # 2. Live-OCR zu Cache
        for name, val in ocr_roh_live.items():
            if name in ausgabe_namen:
                continue
            if val not in (None, "", "—"):
                ocr_werte[name] = (val, jetzt)
                neue_cache_werte[name] = val

        # 3. Transformationen
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

        # 4. Berechnungen
        berech_sortiert = (
            [b for b in berechnungen if b.get("typ") == "zwischen"] +
            [b for b in berechnungen if b.get("typ") != "zwischen"]
        )
        for b in berech_sortiert:
            ergebnis = berechnung_auswerten(b["formel_json"], ocr_werte, self.l["update_intervall"])
            if ergebnis not in ("?", "—") and b["formel_json"]:
                ocr_werte[b["name"]] = (ergebnis, jetzt)
                neue_cache_werte[b["name"]] = ergebnis

        # 5. Cache wegschreiben
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


from ui.dialogs.daten_typ_dialog_qt import DatenTypDialog

class DatenPanel(QWidget):
    liste_bearbeiten_requested = pyqtSignal(dict)
    timer_bearbeiten_requested = pyqtSignal(dict)
    einheiten_requested        = pyqtSignal()
    geandert                   = pyqtSignal()

    def __init__(self, bot_ref=None, parent=None):
        super().__init__(parent)
        self.bot_ref = bot_ref
        self._listen_cache: list = []
        self._bloecke: dict[int, ListenBlock] = {}
        self._sichtbare_listen: set[int] = set() # listen_id

        datenbank_initialisieren()
        self._setup_ui()
        self._alles_aufbauen()

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._auto_update)
        self._update_timer.start(1000)

        self._transform_timer = QTimer(self)
        self._transform_timer.timeout.connect(self._transform_tick)
        self._transform_timer.start(800)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("panel_header_lite")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(8, 4, 8, 4)
        
        lbl = QLabel("DATEN-LISTEN")
        lbl.setProperty("class", "lbl_dim")
        h_lay.addWidget(lbl)
        h_lay.addStretch()

        # Filter Button (Dropdown Ersatz)
        self.btn_filter = QPushButton("Auswahl ▼")
        self.btn_filter.setObjectName("btn_sm")
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.clicked.connect(self._show_filter_menu)
        h_lay.addWidget(self.btn_filter)
        
        root.addWidget(header)

        # Buttons
        zeile2 = QHBoxLayout()
        zeile2.setContentsMargins(4, 4, 4, 4)
        zeile2.setSpacing(4)

        self.btn_neu = QPushButton("+ Neu")
        self.btn_neu.setObjectName("btn_new_sm")
        self.btn_neu.clicked.connect(self._neue_liste)

        self.btn_einheiten = QPushButton("⚖️ Einheiten")
        self.btn_einheiten.setObjectName("btn_sm")
        self.btn_einheiten.clicked.connect(self.einheiten_requested.emit)

        for btn in [self.btn_neu, self.btn_einheiten]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            zeile2.addWidget(btn)
        zeile2.addStretch()
        root.addLayout(zeile2)

        # Scrollbarer Bereich
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, stretch=1)

    def _show_filter_menu(self):
        menu = QMenu(self)
        for l in self._listen_cache:
            act = QAction(l["name"], menu)
            act.setCheckable(True)
            act.setChecked(l["id"] in self._sichtbare_listen)
            act.triggered.connect(lambda *args, lid=l["id"]: self._toggle_liste(lid))
            menu.addAction(act)
        
        menu.addSeparator()
        act_edit = menu.addAction("✎ Liste bearbeiten...")
        act_edit.triggered.connect(self._liste_bearbeiten)
        act_del = menu.addAction("✕ Liste löschen...")
        act_del.triggered.connect(self._liste_loeschen_dialog)
        
        self.btn_filter.setMenu(menu)
        menu.exec(self.btn_filter.mapToGlobal(self.btn_filter.rect().bottomLeft()))
        self.btn_filter.setMenu(None)

    def _toggle_liste(self, lid):
        if lid in self._sichtbare_listen:
            self._sichtbare_listen.remove(lid)
        else:
            self._sichtbare_listen.add(lid)
        self._aktualisiere_sichtbarkeit()

    def _aktualisiere_sichtbarkeit(self):
        for lid, block in self._bloecke.items():
            block.setVisible(lid in self._sichtbare_listen)

    def listen_neu_laden(self):
        self._alles_aufbauen()

    def _alles_aufbauen(self):
        while self.container_layout.count() > 1:
            item = self.container_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._bloecke.clear()

        listen = alle_listen()
        listen.sort(key=lambda x: (x.get("typ", "daten"), x["name"]))
        self._listen_cache = listen
        
        # Standardmäßig alle anzeigen, wenn Set leer
        if not self._sichtbare_listen:
            self._sichtbare_listen = {l["id"] for l in listen}

        if not self._listen_cache:
            lbl = QLabel("Keine Listen vorhanden.")
            lbl.setProperty("class", "lbl_empty_hint")
            self.container_layout.insertWidget(0, lbl)
            return

        for i, l in enumerate(self._listen_cache):
            block = ListenBlock(l, self.bot_ref)
            self.container_layout.insertWidget(i, block)
            self._bloecke[l["id"]] = block
        
        self._aktualisiere_sichtbarkeit()
        self.geandert.emit()

    def _neue_liste(self):
        typ = DatenTypDialog.ausfuehren(self)
        if not typ: return
        name, ok = QInputDialog.getText(self, "Neue Liste", "Name:")
        if ok and name.strip():
            new_id = liste_erstellen(name.strip(), typ=typ)
            self._sichtbare_listen.add(new_id)
            self._alles_aufbauen()

    def _liste_bearbeiten(self):
        # Wenn nur eine Liste sichtbar ist, diese direkt bearbeiten. Sonst fragen.
        if len(self._sichtbare_listen) == 1:
            lid = list(self._sichtbare_listen)[0]
        else:
            namen = [l["name"] for l in self._listen_cache if l["id"] in self._sichtbare_listen]
            if not namen: return
            name, ok = QInputDialog.getItem(self, "Bearbeiten", "Welche Liste?", namen, 0, False)
            if not ok: return
            lid = next(l["id"] for l in self._listen_cache if l["name"] == name)
            
        l = next((x for x in self._listen_cache if x["id"] == lid), None)
        if l:
            if l.get("typ") == "timer":
                self.timer_bearbeiten_requested.emit(l)
            else:
                self.liste_bearbeiten_requested.emit(l)

    def _liste_loeschen_dialog(self):
        namen = [l["name"] for l in self._listen_cache if l["id"] in self._sichtbare_listen]
        if not namen: return
        name, ok = QInputDialog.getItem(self, "Löschen", "Welche Liste?", namen, 0, False)
        if not ok: return
        lid = next(l["id"] for l in self._listen_cache if l["name"] == name)

        if QMessageBox.question(self, "Löschen", f"Liste '{name}' wirklich löschen?") == QMessageBox.StandardButton.Yes:
            liste_loeschen(lid)
            if lid in self._sichtbare_listen: self._sichtbare_listen.remove(lid)
            self._alles_aufbauen()

    def _auto_update(self):
        for lid in self._sichtbare_listen:
            if lid in self._bloecke:
                self._bloecke[lid].werte_aktualisieren()

    def _transform_tick(self):
        if not self.bot_ref or not hasattr(self.bot_ref, "app"): return
        ocr_roh = {**self.bot_ref.app.state.ocr_values, **self.bot_ref.app.state.template_ocr_values}
        if not ocr_roh: return
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
                                cache_schreiben(l["id"], f"Timer.{t['name']}._deadline", str(jetzt + float(wert)))
                            except (ValueError, TypeError): pass
