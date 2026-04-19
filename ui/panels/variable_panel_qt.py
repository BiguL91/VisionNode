import time
import re
from lang import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QAction


# Farben pro Modus
MODUS_FARBEN = {
    "Timer": "#42a5f5",
    "Zahl":  "#ffca28",
    "Text":  "#aaaaaa",
}

# Schriftgrößen für Doppelklick-Wechsel
FONT_GROESSEN = [10, 9, 8]


class VariableBlock(QFrame):
    """Ein aufklappbarer Block für eine Gruppe von OCR-Variablen (z.B. ein Template)."""
    
    loeschen_requested = pyqtSignal(str)  # entry_name

    def __init__(self, key: str, display_name: str, farbe: str, eintraege: list, parent=None):
        """
        eintraege: list of (entry_name, anzeige_name, modus, kann_geloescht_werden)
        """
        super().__init__(parent)
        self.key = key
        self.display_name = display_name
        self.farbe = farbe
        self._aufgeklappt = True
        self._wert_labels: dict[str, QTableWidgetItem] = {}
        self._entry_modi: dict[str, str] = {}
        self._font_idx: dict[str, int] = {}
        self._is_matched = False

        self.setObjectName("collapsible_panel")
        self._setup_ui()
        self._eintraege_aufbauen(eintraege)

    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (24px Höhe wie Daten-Panel)
        self.header = QFrame()
        self.header.setObjectName("collapsible_header")
        self.header.setFixedHeight(24)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(6, 0, 6, 0)

        self.pfeil = QLabel("▼")
        self.pfeil.setObjectName("collapse_arrow")
        h_layout.addWidget(self.pfeil)

        self.lbl_title = QLabel(self.display_name)
        self.lbl_title.setObjectName("panel_title")
        self.lbl_title.setStyleSheet(f"color: {self.farbe};")
        h_layout.addWidget(self.lbl_title)
        
        # Match-Indikator (kleiner Punkt)
        self.match_indicator = QLabel(" ●")
        self.match_indicator.setVisible(False)
        self.match_indicator.setStyleSheet(f"color: {self.farbe}; font-size: 12px; font-weight: bold;")
        h_layout.addWidget(self.match_indicator)
        
        h_layout.addStretch()

        self.header.mousePressEvent = lambda e: self._toggle()
        root.addWidget(self.header)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        root.addWidget(self.table)

    def _on_cell_double_clicked(self, row, col):
        if col == 1:
            for k, it in self._wert_labels.items():
                if it.row() == row:
                    self._schrift_wechseln(k)
                    break

    def _toggle(self):
        self._aufgeklappt = not self._aufgeklappt
        self.table.setVisible(self._aufgeklappt)
        self.pfeil.setText("▼" if self._aufgeklappt else "▶")

    def _eintraege_aufbauen(self, eintraege: list):
        self.table.setRowCount(len(eintraege))
        for r, (en, an, modus, _) in enumerate(eintraege):
            self.add_entry_at_row(r, en, an, modus)
        self._update_table_height()

    def add_entry(self, entry_name: str, anzeige_name: str, modus: str):
        if entry_name in self._wert_labels:
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.add_entry_at_row(r, entry_name, anzeige_name, modus)
        self._update_table_height()

    def add_entry_at_row(self, r: int, entry_name: str, anzeige_name: str, modus: str):
        self._entry_modi[entry_name] = modus

        # Spalte 0: Name (10pt Standard)
        item_n = QTableWidgetItem(anzeige_name)
        item_n.setForeground(QColor("#cccccc"))
        font_n = QFont()
        font_n.setPointSize(10)
        item_n.setFont(font_n)
        item_n.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 0, item_n)
        
        # Spalte 1: Wert (10pt Standard, kein Consolas/Bold mehr)
        item_val = QTableWidgetItem("–")
        item_val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        font_v = QFont()
        font_v.setPointSize(FONT_GROESSEN[0])
        item_val.setFont(font_v)
        item_val.setForeground(QColor("#444444"))
        self.table.setItem(r, 1, item_val)
        
        self._wert_labels[entry_name] = item_val
        self._font_idx[entry_name] = 0

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item: return
        row = item.row()
        target_key = None
        for k, it in self._wert_labels.items():
            if it.row() == row:
                target_key = k
                break
        if not target_key: return
        menu = QMenu(self)
        act_del = QAction("✕ Löschen", self)
        act_del.triggered.connect(lambda: self.loeschen_requested.emit(target_key))
        menu.addAction(act_del)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _schrift_wechseln(self, name: str):
        idx = (self._font_idx.get(name, 0) + 1) % len(FONT_GROESSEN)
        self._font_idx[name] = idx
        item = self._wert_labels.get(name)
        if item:
            font = QFont()
            font.setPointSize(FONT_GROESSEN[idx])
            item.setFont(font)

    def wert_setzen(self, entry_name: str, wert: str, is_live: bool = False):
        item = self._wert_labels.get(entry_name)
        if not item: return
        if not wert: wert = "–"
        modus = self._entry_modi.get(entry_name, "Text")
        hat_wert = wert not in ("–", "-", "?", "")
        item.setText(str(wert))
        if not hat_wert:
            item.setForeground(QColor("#333333"))
        elif is_live:
            color = MODUS_FARBEN.get(modus, "#ffffff")
            item.setForeground(QColor(color))
        else:
            item.setForeground(QColor("#777777"))

    def set_matched(self, matched: bool):
        if self._is_matched == matched: return
        self._is_matched = matched
        self.match_indicator.setVisible(matched)

    def _update_table_height(self):
        h = self.table.rowCount() * self.table.verticalHeader().defaultSectionSize() + 2
        self.table.setMinimumHeight(h)
        self.table.setMaximumHeight(h)

    def entry_names(self) -> list[str]:
        return list(self._wert_labels.keys())


class VariablePanel(QWidget):
    feste_region_loeschen = pyqtSignal(str)
    template_ocr_loeschen  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bloecke: dict[str, VariableBlock] = {}
        self._reihenfolge: list[str] = []
        self._nur_aktive = False
        self._letzte_ocr_konfig_keys: set | None = None
        self._ocr_letzter_wert_zeit: dict[str, float] = {}
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setObjectName("panel_header_lite")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("OCR VARIABLEN")
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
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(4, 4, 4, 4)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll)

    def aktualisieren(self, regionen: dict, ocr_konfig: dict, template_farbe_func, is_smart_func=None):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._bloecke.clear()
        self._reihenfolge.clear()
        self._letzte_ocr_konfig_keys = set(ocr_konfig.keys())
        hat = False
        if regionen:
            hat = True
            eintraege = [(n, n, r.get("modus", "Text"), True) for n, r in regionen.items()]
            block = self._block_hinzufuegen("_feste_", "Feste Regionen", "#888888", eintraege)
            block.loeschen_requested.connect(self.feste_region_loeschen)
        grp: dict[str, list] = {}
        for en, k in ocr_konfig.items():
            tn = k.get("template", en)
            if tn not in grp: grp[tn] = []
            if is_smart_func and is_smart_func(tn): continue
            display_name = en
            if "_" in en:
                prefix = f"{tn}_"
                if en.startswith(prefix): display_name = en[len(prefix):]
                else:
                    teile = en.split("_", 1)
                    if len(teile) > 1: display_name = teile[1]
            grp[tn].append((en, display_name, k.get("modus", "Text"), True))
        for tn, eintraege in sorted(grp.items()):
            hat = True
            farbe = template_farbe_func(tn)
            block = self._block_hinzufuegen(tn, tn, farbe, eintraege)
            block.loeschen_requested.connect(self.template_ocr_loeschen)
        if not hat:
            lbl = QLabel("(Keine Variablen)")
            lbl.setProperty("class", "lbl_empty_hint")
            self.list_layout.insertWidget(0, lbl)

    def werte_aktualisieren(self, ocr_werte: dict, aktuelle_matches: set, ocr_konfig: dict):
        jetzt = time.time()
        aktuelle_keys = set(ocr_konfig.keys())
        if self._letzte_ocr_konfig_keys is not None and aktuelle_keys != self._letzte_ocr_konfig_keys:
            return 
        for full_key, wert in ocr_werte.items():
            if "_" in full_key:
                m = re.search(r"^(.*)_(\d+)$", full_key)
                if m:
                    base_name, idx = m.groups()
                    if base_name in ocr_konfig:
                        k = ocr_konfig[base_name]
                        tn = k.get("template", base_name)
                        if tn in self._bloecke:
                            prefix = f"{tn}_"
                            short_name = base_name[len(prefix):] if base_name.startswith(prefix) else base_name
                            display_name = f"{short_name} [{idx}]"
                            self._bloecke[tn].add_entry(full_key, display_name, k.get("modus", "Text"))
        for key, block in self._bloecke.items():
            is_m = key in aktuelle_matches
            block.set_matched(is_m)
            for entry_name in block.entry_names():
                val = ocr_werte.get(entry_name, "–") or "–"
                is_live = False
                if val not in ("–", "-", "?", ""):
                    if is_m:
                        self._ocr_letzter_wert_zeit[entry_name] = jetzt
                        is_live = True
                    else:
                        last_t = self._ocr_letzter_wert_zeit.get(entry_name, 0)
                        is_live = (jetzt - last_t < 1.5)
                block.wert_setzen(entry_name, val, is_live=is_live)
        for tn in self._reihenfolge:
            block = self._bloecke.get(tn)
            if block:
                block.setVisible(self._sichtbar(tn, aktuelle_matches, jetzt))

    def set_nur_aktive(self, val: bool):
        self._nur_aktive = val

    def _block_hinzufuegen(self, key: str, name: str, farbe: str, eintraege: list) -> VariableBlock:
        block = VariableBlock(key, name, farbe, eintraege)
        self.list_layout.insertWidget(self.list_layout.count() - 1, block)
        self._bloecke[key] = block
        self._reihenfolge.append(key)
        return block

    def _sichtbar(self, tn: str, aktuelle_matches: set, jetzt: float) -> bool:
        if tn == "_feste_": return True
        if not self._nur_aktive: return True
        if tn in aktuelle_matches: return True
        block = self._bloecke.get(tn)
        if not block: return False
        return any(jetzt - self._ocr_letzter_wert_zeit.get(en, 0) < 2.5 for en in block.entry_names())
