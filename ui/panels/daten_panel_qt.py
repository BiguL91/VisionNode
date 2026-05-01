import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QGridLayout, QComboBox,
    QInputDialog, QSizePolicy, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QByteArray
from PyQt6.QtGui import QFont, QColor, QAction

from core.bot_state import BotState
from core.event_bus import bus
from core.daten_manager import (
    datenbank_initialisieren, alle_listen, spalten_der_liste,
    zeilen_der_liste, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen,
    zuordnungen_der_liste, sekunden_formatieren, liste_erstellen, liste_loeschen
)


class BaseListenBlock(QFrame):
    """Basisklasse für aufklappbare Listen-Blöcke."""
    edit_requested = pyqtSignal(dict)

    def __init__(self, listen_dict: dict, bot_ref, parent=None):
        super().__init__(parent)
        self.l = listen_dict
        self.bot_ref = bot_ref
        self._aufgeklappt = True
        self._is_loading = False

        self.setObjectName("collapsible_panel")
        self._setup_ui()
        self._tabelle_zeichnen()

    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

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

        # Name anpassen (Timer -> Globale Var.)
        display_name = self.l["name"]
        if self.l.get("typ") == "timer" and display_name == "Timer":
            display_name = "Globale Var."
            
        lbl = QLabel(display_name)
        lbl.setObjectName("panel_title")
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        header.mousePressEvent = lambda e: self._toggle()
        
        # Kontextmenü für den Header
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        
        root.addWidget(header)

        # Tabelle
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.table.horizontalHeader().setFixedHeight(24)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        
        # Kontextmenü
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        # Spaltenbreiten speichern
        self.table.horizontalHeader().sectionResized.connect(self._save_header_state)
        
        # Performance & Style
        self.table.setProperty("class", "daten_tabelle")
        root.addWidget(self.table)

    def _show_header_context_menu(self, pos):
        """Rechtsklick-Menü für den Titel-Balken."""
        menu = QMenu(self)
        menu.setObjectName("context_menu")
        
        act_edit = QAction("✎ Liste bearbeiten...", self)
        act_edit.triggered.connect(lambda: self.edit_requested.emit(self.l))
        menu.addAction(act_edit)
        
        menu.addSeparator()
        
        act_toggle = QAction("▲/▼ Auf/Zuklappen", self)
        act_toggle.triggered.connect(self._toggle)
        menu.addAction(act_toggle)
        
        menu.exec(self.sender().mapToGlobal(pos))

    def _show_context_menu(self, pos):
        """Zeigt ein Rechtsklick-Menü für die Tabelle an."""
        menu = QMenu(self)
        menu.setObjectName("context_menu")
        
        act_edit = QAction("✎ Liste bearbeiten...", self)
        act_edit.triggered.connect(lambda: self.edit_requested.emit(self.l))
        menu.addAction(act_edit)
        
        menu.addSeparator()
        
        act_reset_header = QAction("↺ Spaltenbreiten zurücksetzen", self)
        def reset_header():
            cache_schreiben(self.l["id"], "UI.header_state", "")
            self._tabelle_zeichnen()
        act_reset_header.triggered.connect(reset_header)
        menu.addAction(act_reset_header)
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _save_header_state(self):
        """Speichert den aktuellen Zustand des Tabellen-Headers (Breiten, etc.) in der DB."""
        if self._is_loading: return
        state = self.table.horizontalHeader().saveState()
        cache_schreiben(self.l["id"], "UI.header_state", state.toHex().data().decode())

    def _restore_header_state(self):
        """Stellt den gespeicherten Zustand des Tabellen-Headers aus der DB wieder her."""
        saved = cache_lesen(self.l["id"]).get("UI.header_state")
        if saved:
            state_hex = saved[0]
            self.table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode()))

    def _toggle(self):
        self._aufgeklappt = not self._aufgeklappt
        self.table.setVisible(self._aufgeklappt)
        self.pfeil.setText("▼" if self._aufgeklappt else "▶")
        if self._aufgeklappt:
            self._tabelle_zeichnen()

    def _tabelle_zeichnen(self):
        pass

    def werte_aktualisieren(self):
        pass

    def _werte_abrufen(self):
        """Holt die bereits verarbeiteten Werte aus dem Cache (DataWorker hat gerechnet)."""
        spalten       = spalten_der_liste(self.l["id"])
        zeilen_namen  = zeilen_der_liste(self.l["id"])
        berechnungen  = berechnungen_der_liste(self.l["id"])
        db_cache      = cache_lesen(self.l["id"])
        
        # Wir nutzen einfach den Cache als Basis für die Anzeige
        ocr_werte     = dict(db_cache)
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


class NormalListenBlock(BaseListenBlock):
    """Matrix-Ansicht: Zeilen x Spalten."""

    def _tabelle_zeichnen(self):
        self._is_loading = True
        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_abrufen()

        if not spalten:
            self.table.setColumnCount(1)
            self.table.setRowCount(1)
            self.table.setHorizontalHeaderLabels(["Info"])
            self.table.setItem(0, 0, QTableWidgetItem("Keine Spalten konfiguriert."))
            self._is_loading = False
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

        self._restore_header_state()
        self.werte_aktualisieren()
        self._is_loading = False

        h = 24 + (self.table.rowCount() * self.table.verticalHeader().defaultSectionSize()) + 2
        self.table.setMinimumHeight(min(h, 400))
        self.table.setMaximumHeight(h)

    def werte_aktualisieren(self):
        if not self._aufgeklappt or self.table.rowCount() == 0:
            return

        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_abrufen()
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


class GlobalListenBlock(BaseListenBlock):
    """Einfache Listen-Ansicht für Globale Variablen (Timer, etc.)."""

    def _tabelle_zeichnen(self):
        self._is_loading = True
        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_abrufen()

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

        self._restore_header_state()
        self.werte_aktualisieren()
        self._is_loading = False

        h = 24 + (self.table.rowCount() * self.table.verticalHeader().defaultSectionSize()) + 2
        self.table.setMinimumHeight(min(h, 400))
        self.table.setMaximumHeight(h)

    def werte_aktualisieren(self):
        if not self._aufgeklappt or self.table.rowCount() == 0:
            return

        ocr_werte, spalten, zeilen_namen, berech_namen, zuordnungen = self._werte_abrufen()
        for r, z in enumerate(zeilen_namen):
            full_name = z["name"]
            is_timer = not full_name.startswith("[W] ")
            val = ocr_werte.get(full_name, ("—", 0))[0]
            anzeige = sekunden_formatieren(val) if is_timer and val not in ("—", "?") else str(val)
            
            item = self.table.item(r, 1)
            if item:
                item.setText(anzeige)
                if is_timer: item.setForeground(QColor("#42a5f5"))


from ui.dialogs.daten_typ_dialog_qt import DatenTypDialog

class DatenPanel(QWidget):
    liste_bearbeiten_requested = pyqtSignal(dict)
    timer_bearbeiten_requested = pyqtSignal(dict)
    einheiten_requested        = pyqtSignal()
    geandert                   = pyqtSignal()

    def __init__(self, bot_ref=None, filter_typ="all", parent=None):
        """
        filter_typ: "all", "timer" oder "daten"
        """
        super().__init__(parent)
        self.bot_ref = bot_ref
        self.filter_typ = filter_typ
        self._listen_cache: list = []
        self._bloecke: dict[int, BaseListenBlock] = {}
        self._sichtbare_listen: set[int] = set() # listen_id

        datenbank_initialisieren()
        self._setup_ui()
        self._alles_aufbauen()

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._auto_update)
        self._update_timer.start(2000) # Reiner Polling-Fallback für Timer-Animationen

        # Event Bus Integration
        bus.subscribe("data.updated", self._on_data_updated)

    def _on_data_updated(self, event):
        """Wird vom DataWorker gerufen, wenn neue Berechnungen vorliegen."""
        # Wir nutzen ein QTimer.singleShot, um den UI-Thread nicht direkt zu blockieren
        QTimer.singleShot(0, self._auto_update)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("panel_header_lite")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(8, 4, 8, 4)
        
        title = "DATEN-LISTEN"
        if self.filter_typ == "timer": title = "GLOBALE VARIABLEN"
        elif self.filter_typ == "daten": title = "DATEN-LISTEN"
        
        lbl = QLabel(title)
        lbl.setProperty("class", "lbl_dim")
        h_lay.addWidget(lbl)
        h_lay.addStretch()

        # Filter Button
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
            # Nur Listen anzeigen, die zum Filter passen
            if self.filter_typ == "timer" and l.get("typ") != "timer": continue
            if self.filter_typ == "daten" and l.get("typ") == "timer": continue
            
            name = l["name"]
            if l.get("typ") == "timer" and name == "Timer": name = "Globale Var."
            
            act = QAction(name, menu)
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
        # Filter anwenden
        if self.filter_typ == "timer":
            listen = [l for l in listen if l.get("typ") == "timer"]
        elif self.filter_typ == "daten":
            listen = [l for l in listen if l.get("typ") != "timer"]
            
        listen.sort(key=lambda x: (x.get("typ", "daten"), x["name"]))
        self._listen_cache = listen
        
        if not self._sichtbare_listen:
            self._sichtbare_listen = {l["id"] for l in listen}

        if not self._listen_cache:
            lbl = QLabel("Keine Listen vorhanden.")
            lbl.setProperty("class", "lbl_empty_hint")
            self.container_layout.insertWidget(0, lbl)
            return

        for i, l in enumerate(self._listen_cache):
            if l.get("typ") == "timer":
                block = GlobalListenBlock(l, self.bot_ref)
            else:
                block = NormalListenBlock(l, self.bot_ref)
            
            block.edit_requested.connect(self._on_block_edit_requested)
            self.container_layout.insertWidget(i, block)
            self._bloecke[l["id"]] = block
        
        self._aktualisiere_sichtbarkeit()
        self.geandert.emit()

    def _on_block_edit_requested(self, listen_dict: dict):
        """Wird aufgerufen, wenn im Block 'Bearbeiten' gewählt wurde."""
        if listen_dict.get("typ") == "timer":
            self.timer_bearbeiten_requested.emit(listen_dict)
        else:
            self.liste_bearbeiten_requested.emit(listen_dict)

    def _neue_liste(self):
        typ = DatenTypDialog.ausfuehren(self)
        if not typ: return
        name, ok = QInputDialog.getText(self, "Neue Liste", "Name:")
        if ok and name.strip():
            new_id = liste_erstellen(name.strip(), typ=typ)
            self._sichtbare_listen.add(new_id)
            self._alles_aufbauen()

    def _liste_bearbeiten(self):
        # Nur sichtbare IDs sammeln
        sichtbare_ids = [l["id"] for l in self._listen_cache if l["id"] in self._sichtbare_listen]
        
        if len(sichtbare_ids) == 1:
            lid = sichtbare_ids[0]
        else:
            namen = []
            for l in self._listen_cache:
                if l["id"] in self._sichtbare_listen:
                    n = l["name"]
                    if l.get("typ") == "timer" and n == "Timer": n = "Globale Var."
                    namen.append(n)
            
            if not namen: return
            name, ok = QInputDialog.getItem(self, "Bearbeiten", "Welche Liste?", namen, 0, False)
            if not ok: return
            
            lid = None
            for l in self._listen_cache:
                n = l["name"]
                if l.get("typ") == "timer" and n == "Timer": n = "Globale Var."
                if n == name:
                    lid = l["id"]
                    break
            if lid is None: return
            
        l = next((x for x in self._listen_cache if x["id"] == lid), None)
        if l:
            if l.get("typ") == "timer":
                self.timer_bearbeiten_requested.emit(l)
            else:
                self.liste_bearbeiten_requested.emit(l)

    def _liste_loeschen_dialog(self):
        namen = []
        for l in self._listen_cache:
            if l["id"] in self._sichtbare_listen:
                n = l["name"]
                if l.get("typ") == "timer" and n == "Timer": n = "Globale Var."
                namen.append(n)
                
        if not namen: return
        name, ok = QInputDialog.getItem(self, "Löschen", "Welche Liste?", namen, 0, False)
        if not ok: return
        
        lid = None
        for l in self._listen_cache:
            n = l["name"]
            if l.get("typ") == "timer" and n == "Timer": n = "Globale Var."
            if n == name:
                lid = l["id"]
                break
        if lid is None: return

        if QMessageBox.question(self, "Löschen", f"Liste '{name}' wirklich löschen?") == QMessageBox.StandardButton.Yes:
            liste_loeschen(lid)
            if lid in self._sichtbare_listen: self._sichtbare_listen.remove(lid)
            self._alles_aufbauen()

    def _auto_update(self):
        for lid in self._sichtbare_listen:
            if lid in self._bloecke:
                self._bloecke[lid].werte_aktualisieren()
