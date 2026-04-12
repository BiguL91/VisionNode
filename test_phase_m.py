"""
Phase M Test — Workflow-Editor (Qt)
Launcher zum manuellen Testen von WorkflowEditorDialogQt.
Verwendet einen Minimal-Mock des Bots — keine GPU, kein ADB nötig.
"""
import sys
import uuid
from unittest.mock import MagicMock

import style
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt

from ui.dialogs.workflow_editor_qt import WorkflowEditorDialogQt


# ── Mock-Objekte ──────────────────────────────────────────────────────────────

def _make_mock_bot():
    bot = MagicMock()

    # Template-Engine — gibt Gruppen und Templates zurück
    bot.template_engine.templates = {
        "Hauptmenü":    {"gruppe": "Menu",   "kategorie": "workflow"},
        "Gegner":       {"gruppe": "Kampf",  "kategorie": "workflow"},
        "Item":         {"gruppe": "Kampf",  "kategorie": "workflow"},
        "Ladescreen":   {"gruppe": "System", "kategorie": "workflow"},
    }
    bot.template_engine.settings = {
        "Hauptmenü":  {"gruppe": "Menu",   "kategorie": "workflow"},
        "Gegner":     {"gruppe": "Kampf",  "kategorie": "workflow"},
        "Item":       {"gruppe": "Kampf",  "kategorie": "workflow"},
        "Ladescreen": {"gruppe": "System", "kategorie": "workflow"},
    }

    # Workflow-Engine — gibt Workflow-Namen zurück
    bot.workflow_engine.workflows = {
        "main":    {"nodes": [], "connections": []},
        "kampf":   {"nodes": [], "connections": []},
        "farming": {"nodes": [], "connections": []},
    }

    # Action-Engine — Klickzonen-Lookup
    bot.action_engine.klickzonen_laden.return_value = {
        "start_btn": {"klick_rel_x": 0.5, "klick_rel_y": 0.9},
    }

    # State / OCR-Variablen
    bot.app.state.game_states = {
        "is_kampf": False,
        "is_menu":  True,
        "is_ladescreen": False,
    }
    bot.app.state.ocr_vars = {
        "global":   {"health": "", "mana": ""},
        "template": {"Item_count": ""},
    }
    bot.app.state.db_listen = []

    # Log
    bot._log.side_effect = lambda msg: print(f"[BOT] {msg}")

    return bot


# ── Beispiel-Graphen ──────────────────────────────────────────────────────────

def _leerer_graph():
    """Graph ohne Nodes — Editor erstellt automatisch einen Start-Node."""
    return {"nodes": [], "connections": []}


def _einfacher_graph():
    """Start → Suche → Klick."""
    return {
        "nodes": [
            {"id": "a1", "typ": "start",  "x": 60,  "y": 220},
            {"id": "a2", "typ": "suche",  "x": 280, "y": 160,
             "template": "Hauptmenü", "schwellwert": 0.85, "scan_regions": []},
            {"id": "a3", "typ": "klick",  "x": 500, "y": 160,
             "template": "Hauptmenü", "schwellwert": 0.85, "scan_regions": []},
        ],
        "connections": [
            {"von": "a1", "port_von": "out",     "zu": "a2", "port_zu": "in"},
            {"von": "a2", "port_von": "success",  "zu": "a3", "port_zu": "in"},
        ],
    }


def _komplexer_graph():
    """Start → Bedingung → call_workflow / warten — testet viele Node-Typen."""
    return {
        "nodes": [
            {"id": "b1", "typ": "start",        "x": 60,  "y": 280},
            {"id": "b2", "typ": "bedingung",     "x": 260, "y": 200,
             "condition": {"nodes": [], "connections": []}},
            {"id": "b3", "typ": "call_workflow", "x": 480, "y": 120,
             "workflow": "kampf"},
            {"id": "b4", "typ": "warten",        "x": 480, "y": 340,
             "sekunden": 2.0},
            {"id": "b5", "typ": "priority_selector", "x": 700, "y": 200,
             "ausgaenge": [
                 {"port": "menu",  "template": "Hauptmenü", "schwellwert": 0.85},
                 {"port": "fight", "template": "Gegner",    "schwellwert": 0.80},
             ]},
        ],
        "connections": [
            {"von": "b1", "port_von": "out",     "zu": "b2", "port_zu": "in"},
            {"von": "b2", "port_von": "true",    "zu": "b3", "port_zu": "in"},
            {"von": "b2", "port_von": "false",   "zu": "b4", "port_zu": "in"},
            {"von": "b3", "port_von": "done",    "zu": "b5", "port_zu": "in"},
        ],
    }


# ── Test-Fenster ──────────────────────────────────────────────────────────────

class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase M Test — Workflow-Editor (Qt)")
        self.resize(420, 340)
        self._bot = _make_mock_bot()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        lbl = QLabel("Phase M — Workflow-Editor Launcher")
        lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        root.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3a3a3a;")
        root.addWidget(sep)

        self._status = QLabel("— Ergebnis erscheint hier —")
        self._status.setStyleSheet("color: #666666; font-size: 10px;")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        def btn(label, fn):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            root.addWidget(b)

        btn("1 · Leerer Workflow (nur Start-Node)",   self._test_leer)
        btn("2 · Einfacher Graph (Start→Suche→Klick)", self._test_einfach)
        btn("3 · Komplexer Graph (alle Node-Typen)",  self._test_komplex)

        root.addStretch()

    def _show(self, text: str):
        self._status.setText(str(text))
        print(f"[STATUS] {text}")

    def _oeffne(self, name: str, graph: dict):
        dlg = WorkflowEditorDialogQt(
            parent=self,
            bot=self._bot,
            name=name,
            graph=graph,
        )
        dlg.gespeichert.connect(
            lambda n, g: self._show(
                f"Gespeichert: \"{n}\" — {len(g['nodes'])} Nodes, "
                f"{len(g['connections'])} Verbindungen"
            )
        )
        dlg.abgebrochen.connect(lambda: self._show("Abgebrochen."))
        dlg.show()

    def _test_leer(self):
        self._oeffne("neuer_workflow", _leerer_graph())
        self._show("Leerer Workflow geöffnet — Editor erstellt Start-Node automatisch.")

    def _test_einfach(self):
        self._oeffne("einfach", _einfacher_graph())
        self._show("Einfacher Graph geöffnet (Start → Suche → Klick).")

    def _test_komplex(self):
        self._oeffne("komplex", _komplexer_graph())
        self._show("Komplexer Graph geöffnet (Bedingung, call_workflow, priority_selector).")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
