"""
Phase I Test — Alle mittleren Panels + CollapsiblePanel
Imports prüfen, Panels instanziieren, Testfenster öffnen.
"""
import sys
import style
import lang
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QSplitter, QScrollArea
)
from PyQt6.QtCore import Qt

from ui.panels.workflow_panel_qt  import WorkflowPanel
from ui.panels.variable_panel_qt  import VariablePanel
from ui.panels.template_panel_qt  import TemplatePanel
from ui.widgets.collapsible_panel import CollapsiblePanel


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase I Test — Mittlere Panels")
        self.resize(900, 600)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Linke Spalte: Workflow Panel ──────────────────────────────────────
        links = QWidget()
        links.setFixedWidth(260)
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)

        wf_panel_wrap = CollapsiblePanel("WORKFLOWS", expanded=True, stretch=True)
        self.wf_panel = WorkflowPanel()
        self.wf_panel.aktualisieren(
            master_workflows={
                "Haupt-Loop": {"nodes": [1, 2, 3], "connections": [1, 2]},
                "Backup-Flow": {"nodes": [1], "connections": []},
            },
            aktiver_master="Haupt-Loop",
            workflows={
                "Angriff":  {"nodes": [1, 2, 3, 4], "connections": [1, 2, 3]},
                "Heilung":  {"nodes": [1, 2], "connections": [1]},
                "Navigation": {"nodes": [1, 2, 3], "connections": [2]},
            }
        )
        wf_panel_wrap.content_layout.addWidget(self.wf_panel)
        ll.addWidget(wf_panel_wrap)
        splitter.addWidget(links)

        # ── Mitte: Variable Panel ─────────────────────────────────────────────
        mitte = QWidget()
        mitte.setFixedWidth(280)
        ml = QVBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)

        var_wrap = CollapsiblePanel("OCR VARIABLEN", expanded=True, stretch=True)
        self.var_panel = VariablePanel()
        self.var_panel.aktualisieren(
            regionen={
                "health_bar": {"modus": "Zahl"},
                "timer_feld":  {"modus": "Timer"},
            },
            ocr_konfig={
                "Gegner_hp":   {"template": "Gegner", "modus": "Zahl"},
                "Gegner_name": {"template": "Gegner", "modus": "Text"},
                "Item_count":  {"template": "Item",   "modus": "Zahl"},
            },
            template_farbe_func=lambda n: "#42a5f5"
        )
        var_wrap.content_layout.addWidget(self.var_panel)
        ml.addWidget(var_wrap)
        splitter.addWidget(mitte)

        # ── Rechts: CollapsiblePanel Demo ────────────────────────────────────
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)

        p1 = CollapsiblePanel("AUFGEKLAPPT", expanded=True)
        p1.content_layout.addWidget(QLabel("Inhalt sichtbar"))
        p1.content_layout.addWidget(QLabel("Zeile 2"))
        rl.addWidget(p1)

        p2 = CollapsiblePanel("ZUGEKLAPPT", expanded=False)
        p2.content_layout.addWidget(QLabel("Dieser Inhalt ist versteckt"))
        rl.addWidget(p2)

        p3 = CollapsiblePanel("MIT EXTRA-WIDGET", expanded=True)
        from PyQt6.QtWidgets import QPushButton
        extra_btn = QPushButton("Nur Aktive")
        extra_btn.setCheckable(True)
        p3.set_header_extra(extra_btn)
        p3.content_layout.addWidget(QLabel("Header hat extra Button rechts"))
        rl.addWidget(p3)

        rl.addStretch()
        splitter.addWidget(rechts)

        root.addWidget(splitter)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
