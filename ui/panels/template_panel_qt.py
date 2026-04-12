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
            self.btn_ocr    = QPushButton("🔤 OCR")
            self.btn_ocr.setObjectName("btn_sm")
            self.btn_klick  = QPushButton("🖱 Klick")
            self.btn_klick.setObjectName("btn_sm")
            self.btn_gruppe = QPushButton("📦 Grupp")
            self.btn_gruppe.setObjectName("btn_sm")

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
        """Baut die Liste neu auf."""
        self.liste.clear()
        self._last_gruppe = None

        templates_mit_ocr = {v.get("template") for v in ocr_konfig.values()}

        # Varianten zählen
        varianten_count: dict[str, int] = defaultdict(int)
        for t_name in templates.keys():
            varianten_count[t_name.split("__")[0]] += 1

        # Nach Gruppen sortieren
        nach_gruppen: dict[str, list] = defaultdict(list)
        for name, t in templates.items():
            if name.startswith("_") or "__" in name:
                continue
            tpl_s = settings.get(name, {})
            kategorie = tpl_s.get("kategorie", "workflow")
            if self.filter_modus == "state" and kategorie != "state":
                continue
            if self.filter_modus == "workflow" and kategorie != "workflow":
                continue
            g = (t["gruppe"] or "").strip().replace("\\", "/")
            nach_gruppen[g].append(name)

        aktive_gruppen = set(nach_gruppen.keys()) - {""}
        passive_gruppen = set(passive_gruppen_func(self.filter_modus))
        alle_gruppen_set = aktive_gruppen | passive_gruppen
        alle_gruppen = sorted(
            alle_gruppen_set | {""} if "" in nach_gruppen else alle_gruppen_set,
            key=lambda x: (x != "", x.lower())
        )

        def mark(name):
            s = settings.get(name, {})
            m = ""
            if s.get("kategorie") == "state" or s.get("set_states"): m += " 🚩"
            if name in templates_mit_ocr: m += " 🔤"
            if name in klick_konfig: m += " 🖱"
            if s.get("scan_regions"): m += " 🎯"
            return m

        if not alle_gruppen:
            self._item("  (Keine Einträge)", "#555555")
            return

        from PyQt6.QtCore import QSize
        for i, gruppe in enumerate(alle_gruppen):
            # Trennlinie VOR jeder Gruppe (außer der ersten)
            if i > 0:
                sep = QListWidgetItem("──────────────────────────")
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setForeground(QColor("#333333"))
                sep.setSizeHint(QSize(0, 12))  # Sehr flache Trennlinie
                sep.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.liste.addItem(sep)

            if not gruppe:
                self._item("[Global]", "#888888", gruppe_key="")
                for name in sorted(nach_gruppen[""]):
                    v = f" ({varianten_count[name]})" if varianten_count[name] > 1 else ""
                    self._item(f"  {name}{v}{mark(name)}", "#cccccc")
            else:
                kurzname = gruppe.split("/")[-1]
                tiefe    = gruppe.count("/")
                basis_einzug = "    " * tiefe
                praefix = ("    " * (tiefe - 1) + "    └─ ") if tiefe > 0 else ""

                hat_master = kurzname in [t.split("/")[-1] for t in nach_gruppen.get(gruppe, [])]
                ist_passiv = gruppe in passive_gruppen
                hat_cfg = (kurzname in settings and isinstance(settings[kurzname], dict)
                           and bool(settings[kurzname].get("condition_states")))
                cfg_mark = " ⚙" if hat_cfg else ""

                if hat_master:
                    v = f" ({varianten_count[gruppe]})" if varianten_count[gruppe] > 1 else ""
                    self._item(f"{praefix}★ [{kurzname}]{v}{mark(gruppe)}{cfg_mark}",
                               "#ffca28", gruppe_key=gruppe)
                elif ist_passiv:
                    self._item(f"{praefix}📦 [{kurzname}]{mark(kurzname)}{cfg_mark}",
                               "#7a9abf", gruppe_key=gruppe)
                else:
                    self._item(f"{praefix}📁 [{kurzname}]{mark(kurzname)}{cfg_mark}",
                               "#888888", gruppe_key=gruppe)

                for name in sorted(nach_gruppen.get(gruppe, [])):
                    if name == gruppe:
                        continue
                    v = f" ({varianten_count[name]})" if varianten_count[name] > 1 else ""
                    self._item(f"{basis_einzug}    └─ {name}{v}{mark(name)}", "#cccccc")

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
