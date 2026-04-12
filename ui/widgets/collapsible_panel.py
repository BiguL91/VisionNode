"""
CollapsiblePanel — ersetzt _panel_erstellen() aus PanelsMixin.

Verwendung:
    panel = CollapsiblePanel("WORKFLOWS", expanded=True)
    panel.content_layout.addWidget(irgendwas)
    layout.addWidget(panel)
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal


class CollapsiblePanel(QWidget):
    toggled = pyqtSignal(bool)  # True = aufgeklappt

    def __init__(self, title: str, expanded: bool = True,
                 stretch: bool = False, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._stretch = stretch

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self._header = QFrame()
        self._header.setObjectName("collapsible_header")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFixedHeight(26)

        h_layout = QHBoxLayout(self._header)
        h_layout.setContentsMargins(6, 0, 6, 0)
        h_layout.setSpacing(4)

        self._arrow = QLabel("▼" if expanded else "▶")
        self._arrow.setObjectName("collapse_arrow")
        self._arrow.setFixedWidth(14)
        h_layout.addWidget(self._arrow)

        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("panel_title")
        h_layout.addWidget(self._title_lbl)
        h_layout.addStretch()

        self._header.mousePressEvent = lambda e: self._toggle()
        root.addWidget(self._header)

        # ── Inhalt ────────────────────────────────────────────────────────────
        self._content = QWidget()
        self._content.setObjectName("collapsible_content")
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(6, 4, 6, 4)
        self.content_layout.setSpacing(4)

        if stretch:
            self._content.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        root.addWidget(self._content)
        self._content.setVisible(expanded)

        self._update_size_policy()

    def _update_size_policy(self):
        """Passt die SizePolicy an den Klapp-Zustand an."""
        if self._expanded:
            if self._stretch:
                self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            else:
                self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                self._content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")
        self._update_size_policy()
        self.toggled.emit(self._expanded)

    def set_expanded(self, val: bool):
        if val != self._expanded:
            self._toggle()

    def set_header_extra(self, widget: QWidget):
        """Fügt ein Extra-Widget rechts im Header ein (z.B. 'Nur Aktive' Button)."""
        layout = self._header.layout()
        layout.addWidget(widget)

    def is_expanded(self) -> bool:
        return self._expanded
