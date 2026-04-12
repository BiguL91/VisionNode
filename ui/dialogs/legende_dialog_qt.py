"""
Legende-Dialog (Qt). Ersetzt _legende_zeigen() aus main.py.
"""
from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PyQt6.QtCore import Qt


_EINTRAEGE = [
    ("TYPEN", None, None),
    ("★  [Name]",   "aktiv_gruppe", "Aktive Gruppe — hat Bild, erkennt sich selbst als Gruppe"),
    ("📦 [Name]",   "passiv_gruppe", "Passive Gruppe — kein Bild, nur Bedingungen"),
    ("📁 [Name]",   "folder",        "Ordner — Gruppe ohne eigenes Master-Template"),
    ("    └─ Name", "template",      "Kind-Template — gehört zur übergeordneten Gruppe"),
    ("", None, None),
    ("MARKIERUNGEN", None, None),
    ("🚩", "state",  "State Template — setzt einen Game-State wenn erkannt"),
    ("🔤", "ocr",    "OCR konfiguriert"),
    ("🖱",  "klick",  "Klick-Zone konfiguriert"),
    ("🎯",  "roi",    "Scan-Bereich (ROI) konfiguriert"),
    ("⚙",  "logic",  "Gruppen-Bedingungen konfiguriert"),
    ("(2)", "folder", "Anzahl der Varianten (z.B. Name__2, Name__3)"),
]


class LegendDialog(QDialog):
    """Symbol-Legende für das Template-Panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(lang.t("legend_title"))
        self.setModal(True)
        self.setFixedWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(2)

        lbl_titel = QLabel("Symbol-Legende")
        lbl_titel.setObjectName("dialog_titel_gross")
        layout.addWidget(lbl_titel)
        layout.addSpacing(6)

        for symbol, type_key, beschreibung in _EINTRAEGE:
            if beschreibung is None:
                if symbol:
                    # Kategorie-Header
                    lbl = QLabel(symbol)
                    lbl.setProperty("class", "lbl_header_dim")
                    layout.addSpacing(6)
                    layout.addWidget(lbl)
                else:
                    # Trennlinie
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setProperty("class", "separator")
                    layout.addSpacing(4)
                    layout.addWidget(sep)
                    layout.addSpacing(4)
                continue

            zeile = QHBoxLayout()
            zeile.setSpacing(8)

            lbl_sym = QLabel(symbol)
            lbl_sym.setFixedWidth(90)
            lbl_sym.setObjectName("legend_symbol")
            lbl_sym.setProperty("type", type_key)
            zeile.addWidget(lbl_sym)

            lbl_desc = QLabel(beschreibung)
            lbl_desc.setProperty("class", "lbl_info")
            lbl_desc.setWordWrap(True)
            zeile.addWidget(lbl_desc, stretch=1)

            layout.addLayout(zeile)

        layout.addSpacing(10)

        btn_close = QPushButton(lang.t("btn_close"))
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def zeigen(parent=None):
        """Convenience: Dialog anzeigen."""
        dlg = LegendDialog(parent)
        dlg.exec()
