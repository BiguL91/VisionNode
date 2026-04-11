"""
Legende-Dialog (Qt). Ersetzt _legende_zeigen() aus main.py.
"""
import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PyQt6.QtCore import Qt


_EINTRAEGE = [
    ("TYPEN", None, None),
    ("★  [Name]",   "#ffca28", "Aktive Gruppe — hat Bild, erkennt sich selbst als Gruppe"),
    ("📦 [Name]",   "#7a9abf", "Passive Gruppe — kein Bild, nur Bedingungen"),
    ("📁 [Name]",   "#888888", "Ordner — Gruppe ohne eigenes Master-Template"),
    ("    └─ Name", "#cccccc", "Kind-Template — gehört zur übergeordneten Gruppe"),
    ("", None, None),
    ("MARKIERUNGEN", None, None),
    ("🚩", "#ff7043", "State Template — setzt einen Game-State wenn erkannt"),
    ("🔤", "#55aaff", "OCR konfiguriert"),
    ("🖱",  "#ff6600", "Klick-Zone konfiguriert"),
    ("🎯",  "#ffca28", "Scan-Bereich (ROI) konfiguriert"),
    ("⚙",  "#aaaaaa", "Gruppen-Bedingungen konfiguriert"),
    ("(2)", "#888888", "Anzahl der Varianten (z.B. Name__2, Name__3)"),
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
        lbl_titel.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_titel)
        layout.addSpacing(6)

        for symbol, farbe, beschreibung in _EINTRAEGE:
            if beschreibung is None:
                if symbol:
                    # Kategorie-Header
                    lbl = QLabel(symbol)
                    lbl.setStyleSheet("color: #555555; font-size: 8px; font-weight: bold;")
                    layout.addSpacing(6)
                    layout.addWidget(lbl)
                else:
                    # Trennlinie
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setStyleSheet("color: #3a3a3a;")
                    layout.addSpacing(4)
                    layout.addWidget(sep)
                    layout.addSpacing(4)
                continue

            zeile = QHBoxLayout()
            zeile.setSpacing(8)

            lbl_sym = QLabel(symbol)
            lbl_sym.setFixedWidth(90)
            lbl_sym.setStyleSheet(f"color: {farbe}; font-size: 10px;")
            zeile.addWidget(lbl_sym)

            lbl_desc = QLabel(beschreibung)
            lbl_desc.setStyleSheet("color: #888888; font-size: 9px;")
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
