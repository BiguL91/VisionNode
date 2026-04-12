import time
from lang import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


# Farben pro Modus
MODUS_FARBEN = {
    "Timer": "#42a5f5",
    "Zahl":  "#ffca28",
    "Text":  "#aaaaaa",
}

# Schriftgrößen für Doppelklick-Wechsel
FONT_GROESSEN = [18, 13, 10]


class VariableGruppe(QFrame):
    """Eine Gruppe von OCR-Variablen mit farbigem Balken links."""

    loeschen_requested = pyqtSignal(str)  # entry_name

    def __init__(self, gruppen_name: str, farbe: str, eintraege: list, parent=None):
        """
        eintraege: list of (entry_name, anzeige_name, modus, kann_geloescht_werden)
        """
        super().__init__(parent)
        self.setObjectName("variable_gruppe")
        self._wert_labels: dict[str, QLabel] = {}
        self._font_idx: dict[str, int] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 4, 4)
        outer.setSpacing(0)

        # Farbbalken links
        self.balken = QFrame()
        self.balken.setFixedWidth(3)
        self.balken.setObjectName("gruppe_balken")
        self.balken.setStyleSheet(f"background-color: {farbe};") 
        outer.addWidget(self.balken)

        inner = QVBoxLayout()
        inner.setContentsMargins(6, 2, 0, 2)
        inner.setSpacing(2)
        outer.addLayout(inner)

        # Gruppen-Header
        kopf = QHBoxLayout()
        kopf.setContentsMargins(0, 0, 0, 2)
        lbl_name = QLabel(gruppen_name)
        lbl_name.setObjectName("gruppe_titel")
        lbl_name.setStyleSheet(f"color: {farbe};") 
        kopf.addWidget(lbl_name)
        kopf.addStretch()
        inner.addLayout(kopf)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setProperty("class", "separator")
        inner.addWidget(line)

        # Einträge
        for entry_name, anzeige_name, modus, kann_loeschen in eintraege:
            zeile = QHBoxLayout()
            zeile.setContentsMargins(0, 2, 0, 2)
            zeile.setSpacing(4)

            # Links: Modus + Name
            links = QVBoxLayout()
            links.setSpacing(0)
            lbl_modus = QLabel(f"[{modus}]")
            lbl_modus.setObjectName(f"lbl_modus_{modus.lower()}")
            lbl_anzeige = QLabel(anzeige_name)
            lbl_anzeige.setProperty("class", "lbl_dim")
            links.addWidget(lbl_modus)
            links.addWidget(lbl_anzeige)
            zeile.addLayout(links)
            zeile.addStretch()

            # Wert-Label (rechts, groß)
            wert_lbl = QLabel("–")
            wert_lbl.setObjectName("variable_wert")
            wert_lbl.setFont(QFont("Consolas", FONT_GROESSEN[0], QFont.Weight.Bold))
            wert_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            wert_lbl.mouseDoubleClickEvent = lambda e, n=entry_name: self._schrift_wechseln(n)
            zeile.addWidget(wert_lbl)
            self._wert_labels[entry_name] = wert_lbl
            self._font_idx[entry_name] = 0

            # Löschen-Button (optional)
            if kann_loeschen:
                btn_del = QPushButton("✕")
                btn_del.setObjectName("btn_del_sm")
                btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_del.clicked.connect(lambda _, n=entry_name: self.loeschen_requested.emit(n))
                zeile.addWidget(btn_del)

            inner.addLayout(zeile)

    def _schrift_wechseln(self, name: str):
        idx = (self._font_idx.get(name, 0) + 1) % len(FONT_GROESSEN)
        self._font_idx[name] = idx
        lbl = self._wert_labels.get(name)
        if lbl:
            lbl.setFont(QFont("Consolas", FONT_GROESSEN[idx], QFont.Weight.Bold))

    def wert_setzen(self, entry_name: str, wert: str):
        lbl = self._wert_labels.get(entry_name)
        if not lbl:
            return
        if not wert:
            wert = "–"
        hat_wert = wert != "–"
        lbl.setText(wert)
        lbl.setProperty("active", hat_wert)
        lbl.setStyle(lbl.style())

    def entry_names(self) -> list[str]:
        return list(self._wert_labels.keys())


class VariablePanel(QWidget):
    # Signals
    feste_region_loeschen = pyqtSignal(str)       # region_name
    template_ocr_loeschen  = pyqtSignal(str)      # entry_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gruppen: dict[str, VariableGruppe] = {}  # gruppen_name → Widget
        self._reihenfolge: list[str] = []
        self._nur_aktive = False
        self._letzte_ocr_konfig_keys: set | None = None
        self._ocr_letzter_wert_zeit: dict[str, float] = {}

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(4, 4, 4, 4)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def aktualisieren(self, regionen: dict, ocr_konfig: dict, template_farbe_func):
        """Vollständiger Rebuild — nur bei strukturellen Änderungen."""
        # Alte Gruppen entfernen
        for g in self._gruppen.values():
            self.list_layout.removeWidget(g)
            g.deleteLater()
        self._gruppen.clear()
        self._reihenfolge.clear()
        self._letzte_ocr_konfig_keys = set(ocr_konfig.keys())

        hat = False

        # 1. Feste Regionen
        if regionen:
            hat = True
            eintraege = [
                (n, n, r.get("modus", "Text"), True)
                for n, r in regionen.items()
            ]
            gruppe = self._gruppe_hinzufuegen("_feste_", "Feste Regionen", "#888888", eintraege)
            gruppe.loeschen_requested.connect(self.feste_region_loeschen)

        # 2. Template OCR
        grp: dict[str, list] = {}
        for en, k in ocr_konfig.items():
            tn = k.get("template", en)
            grp.setdefault(tn, []).append((en, en, k.get("modus", "Text"), True))

        for tn, eintraege in grp.items():
            hat = True
            farbe = template_farbe_func(tn)
            gruppe = self._gruppe_hinzufuegen(tn, tn, farbe, eintraege)
            gruppe.loeschen_requested.connect(self.template_ocr_loeschen)

        if not hat:
            lbl = QLabel("(Keine Variablen)")
            lbl.setProperty("class", "lbl_empty_hint")
            self.list_layout.insertWidget(0, lbl)

    def werte_aktualisieren(self, ocr_werte: dict, aktuelle_matches: set,
                             ocr_konfig: dict, nur_aktive: bool):
        """Surgical Update — nur Werte und Sichtbarkeit."""
        jetzt = time.time()
        self._nur_aktive = nur_aktive

        # Strukturcheck
        aktuelle_keys = set(ocr_konfig.keys())
        if self._letzte_ocr_konfig_keys is not None and aktuelle_keys != self._letzte_ocr_konfig_keys:
            return  # Rebuild nötig → Signal nach außen geben oder direkt aktualisieren()

        # Zeitstempel für aktive Werte merken
        for n, v in ocr_werte.items():
            if v and v not in ("", "—", "-", "?"):
                self._ocr_letzter_wert_zeit[n] = jetzt

        # Werte setzen
        for gname, gruppe in self._gruppen.items():
            for entry_name in gruppe.entry_names():
                val = ocr_werte.get(entry_name, "–") or "–"
                gruppe.wert_setzen(entry_name, val)

        # Sichtbarkeit
        self._sichtbarkeit_aktualisieren(aktuelle_matches, jetzt)

    def set_nur_aktive(self, val: bool):
        self._nur_aktive = val

    # ── Intern ────────────────────────────────────────────────────────────────

    def _gruppe_hinzufuegen(self, key: str, name: str, farbe: str,
                             eintraege: list) -> VariableGruppe:
        gruppe = VariableGruppe(name, farbe, eintraege)
        insert_pos = self.list_layout.count() - 1  # vor dem Stretch
        self.list_layout.insertWidget(insert_pos, gruppe)
        self._gruppen[key] = gruppe
        self._reihenfolge.append(key)
        return gruppe

    def _sichtbar(self, tn: str, aktuelle_matches: set, jetzt: float) -> bool:
        if tn == "_feste_":
            return True
        if not self._nur_aktive:
            return True
        if tn not in aktuelle_matches:
            return False
        gruppe = self._gruppen.get(tn)
        if not gruppe:
            return False
        return any(
            jetzt - self._ocr_letzter_wert_zeit.get(en, 0) < 2.0
            for en in gruppe.entry_names()
        )

    def _sichtbarkeit_aktualisieren(self, aktuelle_matches: set, jetzt: float):
        for tn in self._reihenfolge:
            gruppe = self._gruppen.get(tn)
            if gruppe:
                gruppe.setVisible(self._sichtbar(tn, aktuelle_matches, jetzt))
