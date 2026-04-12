import re
from lang import lang
from collections import defaultdict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


class TemplatePanel(QWidget):
    # Signals → Bot-Controller
    neu_laden_requested       = pyqtSignal()
    bearbeiten_requested      = pyqtSignal(str)          # template_name
    loeschen_requested        = pyqtSignal(str)          # template_name
    ocr_konfigurieren_requested = pyqtSignal(str)        # template_name
    klick_konfigurieren_requested = pyqtSignal(str)      # template_name
    gruppe_konfigurieren_requested = pyqtSignal(str)     # gruppen_name

    def __init__(self, filter_modus: str = "all", show_buttons: bool = True, parent=None):
        super().__init__(parent)
        self.filter_modus = filter_modus
        self.show_buttons = show_buttons
        self._last_gruppe: str | None = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.liste = QListWidget()
        self.liste.setObjectName("template_liste")
        self.liste.currentRowChanged.connect(self._on_select)
        self.liste.itemDoubleClicked.connect(self._on_doppelklick)
        layout.addWidget(self.liste)

        if self.show_buttons:
            self.buttons_widget = QWidget()
            btn_layout = QVBoxLayout(self.buttons_widget)
            btn_layout.setContentsMargins(0, 4, 0, 4)
            btn_layout.setSpacing(4)

            self.btn_neu_laden  = QPushButton("+ Neu")
            self.btn_neu_laden.setObjectName("btn_new_sm")
            self.btn_bearbeiten = QPushButton("✎ Bearbeiten")
            self.btn_bearbeiten.setObjectName("btn_sm")
            self.btn_loeschen   = QPushButton("✕ Lösch")
            self.btn_loeschen.setObjectName("btn_del_sm")
            self.btn_ocr    = QPushButton(f"🔤 {lang.t('btn_ocr')}")
            self.btn_ocr.setObjectName("btn_ocr_action")
            self.btn_klick  = QPushButton(f"🖱 {lang.t('btn_click')}")
            self.btn_klick.setObjectName("btn_klick_action")
            self.btn_gruppe = QPushButton(f"🚩 {lang.t('tab_states')}")
            self.btn_gruppe.setObjectName("btn_states_action")

            zeile1 = QHBoxLayout()
            zeile1.setSpacing(4)
            for btn in [self.btn_neu_laden, self.btn_bearbeiten, self.btn_loeschen]:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                zeile1.addWidget(btn)

            zeile2 = QHBoxLayout()
            zeile2.setSpacing(4)
            for btn in [self.btn_ocr, self.btn_klick, self.btn_gruppe]:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                zeile2.addWidget(btn)

            btn_layout.addLayout(zeile1)
            btn_layout.addLayout(zeile2)
            layout.addWidget(self.buttons_widget)

            self.btn_neu_laden.clicked.connect(self.neu_laden_requested)
            self.btn_bearbeiten.clicked.connect(self._bearbeiten)
            self.btn_loeschen.clicked.connect(self._loeschen)
            self.btn_ocr.clicked.connect(self._ocr)
            self.btn_klick.clicked.connect(self._klick)
            self.btn_gruppe.clicked.connect(self._gruppe)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def aktualisieren(self, templates: dict, settings: dict,
                      ocr_konfig: dict, klick_konfig: dict,
                      template_farbe_func, passive_gruppen_func):
        """Baut die Liste als echte Hierarchie neu auf."""
        self.liste.clear()
        self._last_gruppe = None

        templates_mit_ocr = {v.get("template") for v in ocr_konfig.values()}

        # 1. Hilfsfunktion für Vollpfad-Berechnung
        def get_vollpfad(name):
            s = settings.get(name, {})
            parent = s.get("gruppe", "")
            if not parent or parent == name:
                return name
            return f"{parent}/{name}"

        # 2. Daten sammeln und Baum strukturieren
        # baum: { vollpfad_parent: [namen_der_kinder] }
        baum = defaultdict(list)
        name_to_vollpfad = {}

        # Alle Templates (Master) sammeln
        for name in templates.keys():
            if name.startswith("_") or "__" in name:
                continue
            s = settings.get(name, {})
            kat = s.get("kategorie", "workflow")
            if self.filter_modus != "all" and kat != self.filter_modus:
                continue
            
            vp = get_vollpfad(name)
            name_to_vollpfad[name] = vp
            
            parent_pfad = s.get("gruppe", "")
            # CLEANUP: Wenn gruppe == name, ist es ein Root-Master
            if parent_pfad == name: 
                parent_pfad = ""
            
            baum[parent_pfad].append(name)

        # Alle passiven Gruppen sammeln
        passiv_keys = passive_gruppen_func(self.filter_modus)
        for p_name in passiv_keys:
            vp = get_vollpfad(p_name)
            name_to_vollpfad[p_name] = vp
            
            s = settings.get(p_name, {})
            parent_pfad = s.get("gruppe", "")
            # CLEANUP: Wenn gruppe == name, ist es ein Root-Master
            if parent_pfad == p_name:
                parent_pfad = ""
                
            if p_name not in baum[parent_pfad]:
                baum[parent_pfad].append(p_name)

        # Varianten zählen
        varianten_count: dict[str, int] = defaultdict(int)
        for t_name in templates.keys():
            varianten_count[t_name.split("__")[0]] += 1

        def mark(name):
            s = settings.get(name, {})
            m = ""
            if s.get("kategorie") == "state" or s.get("set_states"): m += " 🚩"
            if name in templates_mit_ocr: m += " 🔤"
            if name in klick_konfig: m += " 🖱"
            if s.get("scan_regions"): m += " 🎯"
            return m

        # 3. Rekursive Render-Funktion
        from PyQt6.QtCore import QSize
        
        def render_node(node_name, tiefe=0):
            praefix = "    " * (tiefe - 1) + "    └─ " if tiefe > 0 else ""
            
            s = settings.get(node_name, {})
            typ = s.get("typ", "template")
            kurzname = node_name
            vollpfad = name_to_vollpfad.get(node_name, node_name)
            
            # Icon und Farbe bestimmen
            farbe = "#cccccc"
            icon = ""
            cfg_mark = " ⚙" if s.get("condition_states") else ""
            
            if typ == "aktiv_gruppe":
                icon = "★ "
                farbe = "#ffca28"
            elif typ == "passiv_gruppe":
                icon = "📦 "
                farbe = "#7a9abf"
            elif node_name in templates: # Normales Template
                farbe = "#cccccc"
            else: # Unbekannter Ordner/Gruppe
                icon = "📁 "
                farbe = "#888888"

            # Item hinzufügen
            v = f" ({varianten_count[node_name]})" if varianten_count[node_name] > 1 else ""
            label = f"{praefix}{icon}[{kurzname}]{v}{mark(node_name)}{cfg_mark}" if icon else f"{praefix}{kurzname}{v}{mark(node_name)}{cfg_mark}"
            
            self._item(label, farbe, gruppe_key=node_name if typ in ("aktiv_gruppe", "passiv_gruppe") else None)

            # Kinder rendern (Templates die diesen Vollpfad als 'gruppe' haben)
            kinder = sorted(baum.get(vollpfad, []), key=lambda x: (settings.get(x, {}).get("typ") != "template", x.lower()))
            for kind in kinder:
                if kind == node_name:
                    continue
                render_node(kind, tiefe + 1)

        # 4. Startpunkt: Root-Elemente (parent_pfad == "")
        root_items = sorted(baum.get("", []), key=lambda x: (settings.get(x, {}).get("typ") == "template", x.lower()))
        
        if not root_items:
            self._item("  (Keine Einträge)", "#555555")
            return

        for i, root_name in enumerate(root_items):
            if i > 0:
                sep = QListWidgetItem("──────────────────────────")
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setForeground(QColor("#333333"))
                sep.setSizeHint(QSize(0, 12))
                sep.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.liste.addItem(sep)
            
            render_node(root_name, tiefe=0)


    def get_auswahl_name(self) -> str | None:
        item = self.liste.currentItem()
        if not item:
            return None
        text = item.text()
        clean = text.strip()
        for icon in ["🚩", "🔤", "🖱", "★", "📁", "📦", "└─", "⚙", "🎯"]:
            clean = clean.replace(icon, "")
        clean = clean.strip()
        clean = re.sub(r"\s\(\d+\)$", "", clean).strip()
        m = re.search(r"\[(.+?)\]", clean)
        if m:
            return m.group(1)
        if not clean or clean in ("[Global]", "(Keine Einträge)"):
            return None
        return clean

    # ── Intern ────────────────────────────────────────────────────────────────

    def _item(self, text: str, farbe: str, gruppe_key: str | None = None):
        from PyQt6.QtCore import QSize
        item = QListWidgetItem(text)
        item.setForeground(QColor(farbe))
        item.setSizeHint(QSize(0, 20))  # Kompaktere Zeilenhöhe
        if gruppe_key is not None:
            item.setData(Qt.ItemDataRole.UserRole, gruppe_key)
        self.liste.addItem(item)

    def _on_select(self):
        item = self.liste.currentItem()
        if not item:
            return
        gruppe_key = item.data(Qt.ItemDataRole.UserRole)
        if gruppe_key is not None:
            self._last_gruppe = gruppe_key if gruppe_key else None
        else:
            name = self.get_auswahl_name()
            self._last_gruppe = None  # wird vom Controller gesetzt falls nötig

    def _on_doppelklick(self, item: QListWidgetItem):
        if "📦" in item.text():
            self._gruppe()

    def _bearbeiten(self):
        name = self.get_auswahl_name()
        if name:
            self.bearbeiten_requested.emit(name)

    def _loeschen(self):
        name = self.get_auswahl_name()
        if name:
            self.loeschen_requested.emit(name)

    def _ocr(self):
        name = self.get_auswahl_name()
        if name:
            self.ocr_konfigurieren_requested.emit(name)

    def _klick(self):
        name = self.get_auswahl_name()
        if name:
            self.klick_konfigurieren_requested.emit(name)

    def _gruppe(self):
        if self._last_gruppe:
            self.gruppe_konfigurieren_requested.emit(self._last_gruppe)
