"""
FUP Logik-Netzwerk Editor (Qt).

Verwendung:
    dlg = LogicEditorDialogQt(name, graph, templates, parent, bot)
    dlg.gespeichert.connect(lambda g: ...)  # g = {"nodes": [...], "connections": [...]}
    dlg.exec()
"""
from __future__ import annotations
import uuid

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QFrame, QMenu, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction

from ui.widgets.logic_graph import LogicView, NodeItem, LogicScene, TYPEN_LABEL


# ── Parameter-Dialog ──────────────────────────────────────────────────────────
class NodeParamDialog(QDialog):
    def __init__(self, node: NodeItem, templates: list, parent=None, bot=None):
        super().__init__(parent)
        self.setWindowTitle(f"Konfiguration: {node.data['typ'].upper()}")
        self.setObjectName("logic_param_dialog")
        self.setModal(True)
        self.setFixedSize(420, 260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._node = node
        self._templates = templates
        self._bot = bot
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        typ = self._node.data["typ"]
        self._felder: dict[str, QWidget] = {}

        if typ == "l_var":
            lbl = QLabel("Variable auswählen:")
            lbl.setProperty("class", "lbl_dim")
            layout.addWidget(lbl)

            from ui.variable_source import display_name as _dn
            cur_var = self._node.data.get("variable", "")
            self._var_btn = QPushButton(_dn(cur_var) if cur_var else "Bitte wählen...")
            self._var_btn.setProperty("_val", cur_var)
            self._var_btn.setObjectName("btn_logic_net")
            self._var_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._var_btn.clicked.connect(self._var_menu_zeigen)
            layout.addWidget(self._var_btn)
            self._felder["variable"] = self._var_btn

        elif typ == "l_match":
            lbl = QLabel("Template wählen (Gefunden = True):")
            lbl.setProperty("class", "lbl_dim")
            layout.addWidget(lbl)

            self._tpl_btn = QPushButton(self._node.data.get("template", "Bitte wählen..."))
            self._tpl_btn.setObjectName("btn_logic_net")
            self._tpl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._tpl_btn.clicked.connect(self._tpl_menu_zeigen)
            layout.addWidget(self._tpl_btn)
            self._felder["template"] = self._tpl_btn

        elif typ == "l_const":
            lbl = QLabel("Konstanter Wert:")
            lbl.setProperty("class", "lbl_dim")
            layout.addWidget(lbl)

            entry = QLineEdit(self._node.data.get("wert", "0"))
            entry.setProperty("class", "input_dark")
            layout.addWidget(entry)
            self._felder["wert"] = entry

        elif typ == "l_cmp":
            lbl = QLabel("Vergleich (Input 1 gegen ...):")
            lbl.setProperty("class", "lbl_dim")
            layout.addWidget(lbl)

            row = QHBoxLayout()
            combo = QComboBox()
            combo.addItems(["=", "!=", ">", "<", ">=", "<=", "~", "!~"])
            combo.setCurrentText(self._node.data.get("operator", "="))
            combo.setFixedWidth(70)
            combo.setProperty("class", "input_dark")
            row.addWidget(combo)

            entry = QLineEdit(self._node.data.get("wert", ""))
            entry.setPlaceholderText("Leer = Input 2 verwenden")
            entry.setProperty("class", "input_dark")
            row.addWidget(entry)
            layout.addLayout(row)
            self._felder["operator"] = combo
            self._felder["wert"] = entry

            info = QLabel("Tipp: Feld leer lassen, um Input 2 zu verwenden.")
            info.setProperty("class", "lbl_info")
            layout.addWidget(info)

        elif typ == "l_timer":
            lbl = QLabel("Timer auswählen:")
            lbl.setProperty("class", "lbl_dim")
            layout.addWidget(lbl)

            from ui.variable_source import display_name as _dn
            cur_var = self._node.data.get("variable", "")
            self._timer_btn = QPushButton(_dn(cur_var) if cur_var else "Timer wählen...")
            self._timer_btn.setProperty("_val", cur_var)
            self._timer_btn.setObjectName("btn_logic_net")
            self._timer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._timer_btn.clicked.connect(self._timer_menu_zeigen)
            layout.addWidget(self._timer_btn)
            self._felder["variable"] = self._timer_btn

            info = QLabel("Gibt die restlichen Sekunden bis zum Ablauf aus.")
            info.setProperty("class", "lbl_info")
            layout.addWidget(info)

        layout.addStretch()

        btn_apply = QPushButton("Übernehmen")
        btn_apply.setObjectName("btn_new")
        btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_apply.clicked.connect(self._speichern)
        layout.addWidget(btn_apply)

    def _var_menu_zeigen(self):
        from ui.variable_source import get_picker_data, build_var_menu

        def on_select(full_val, disp):
            self._var_btn.setProperty("_val", full_val)
            self._var_btn.setText(disp or full_val)

        data = get_picker_data(self._bot) if self._bot else {}
        menu = QMenu(self)
        build_var_menu(menu, data, on_select)
        if menu.isEmpty():
            menu.addAction("(Keine Variablen verfügbar)").setEnabled(False)
        menu.exec(self._var_btn.mapToGlobal(self._var_btn.rect().bottomLeft()))

    def _timer_menu_zeigen(self):
        """Strukturierter Picker für Timer-Variablen."""
        from core import daten_manager as dm
        from ui.variable_source import get_picker_data, _get_or_create_sub_menu
        
        menu = QMenu(self)
        data = get_picker_data(self._bot) if self._bot else {}

        def on_select(full_val, disp):
            self._timer_btn.setProperty("_val", full_val)
            self._timer_btn.setText(disp)
        
        # ── 1. OCR-basierte Timer (aus Templates) ───────────────────────────
        ocr_timers = data.get("ocr_template", {})
        if ocr_timers:
            ocr_sub = menu.addMenu("🔤 OCR Timer")
            for kat, grp_dict in ocr_timers.items():
                k_sub = ocr_sub.addMenu(f"📁 {kat}")
                for grp, tmpl_dict in grp_dict.items():
                    # Untergruppen auflösen
                    if grp != "Keine Gruppe":
                        parts = grp.replace("\\", "/").split("/")
                        g_sub = _get_or_create_sub_menu(k_sub, parts)
                    else:
                        g_sub = k_sub.addMenu("📦 (ohne Gruppe)") if len(grp_dict) > 1 else k_sub
                    
                    for tmpl, entries in tmpl_dict.items():
                        t_sub = g_sub.addMenu(f"🖼 {tmpl}")
                        for disp, entry_key in entries:
                            t_sub.addAction(disp, lambda *args, x=f"ocr::{entry_key}", d=disp: on_select(x, d))

        # ── 2. Datenbank-Timer (Global & Standard) ─────────────────────────
        db_menu = menu.addMenu("📊 Datenbank Timer")
        
        # Globale Timer-Listen
        db_global = data.get("db_global", {})
        if db_global:
            g_sub = db_menu.addMenu("🌐 Global")
            for liste, entries in db_global.items():
                l_sub = g_sub.addMenu(f"⏳ {liste}")
                for disp, stored in entries:
                    var_path = f"db::{liste}::{stored}"
                    l_sub.addAction(disp, lambda *args, x=var_path, d=disp: on_select(x, d))
        
        # Standard Daten-Listen (gefiltert nach Timer-Spalten)
        db_std = data.get("db_standard", {})
        if db_std:
            s_sub = db_menu.addMenu("📋 Listen-Spalten")
            for liste, vars_ in db_std.items():
                l_id = next((l["id"] for l in dm.alle_listen() if l["name"] == liste), None)
                if l_id:
                    timer_vars = []
                    spalten = dm.spalten_der_liste(l_id)
                    for s in spalten:
                        if s.get("typ") == "timer": timer_vars.append(s["name"])
                    trans = dm.transformationen_der_liste(l_id)
                    for t in trans:
                        if t.get("typ") == "timer": timer_vars.append(t["name"])
                    
                    if timer_vars:
                        l_sub = s_sub.addMenu(liste)
                        for v in sorted(list(set(timer_vars)), key=str.casefold):
                            var_path = f"db::{liste}::{v}"
                            l_sub.addAction(v, lambda *args, x=var_path, d=v: on_select(x, d))

        if menu.isEmpty():
            menu.addAction("(Keine Timer verfügbar)").setEnabled(False)

        menu.exec(self._timer_btn.mapToGlobal(self._timer_btn.rect().bottomLeft()))


    def _tpl_menu_zeigen(self):
        if self._bot:
            from ui.dialogs.workflow_editor_qt import WorkflowEditorDialogQt
            menu = WorkflowEditorDialogQt.build_template_menu(
                self._bot, self, lambda n: self._tpl_btn.setText(n)
            )
        else:
            menu = QMenu(self)
            for t in sorted(self._templates):
                act = QAction(t, self)
                act.triggered.connect(lambda _, x=t: self._tpl_btn.setText(x))
                menu.addAction(act)
            if not self._templates:
                menu.addAction("(keine Templates)").setEnabled(False)

        menu.exec(self._tpl_btn.mapToGlobal(self._tpl_btn.rect().bottomLeft()))

    def _speichern(self):
        for key, widget in self._felder.items():
            if isinstance(widget, QPushButton):
                actual = widget.property("_val")
                val = actual if actual is not None else widget.text()
                self._node.data[key] = "" if val in ("Bitte wählen...", "Timer wählen...") else val
            elif isinstance(widget, QLineEdit):
                self._node.data[key] = widget.text()
            elif isinstance(widget, QComboBox):
                self._node.data[key] = widget.currentText()
        self._node.update()
        self.accept()


# ── Haupt-Dialog ──────────────────────────────────────────────────────────────
class LogicEditorDialogQt(QDialog):
    """
    FUP Logik-Editor (Qt). Ersetzt LogicEditorDialog (tkinter).

    Signals:
        gespeichert(graph: dict)  — {"nodes": [...], "connections": [...]}
    """
    gespeichert = pyqtSignal(dict)

    def __init__(self, name: str, graph: dict,
                 templates: list | None = None,
                 parent=None,
                 bot=None,
                 # Legacy-Parameter – werden ignoriert, bleiben für Rückwärtskompatibilität
                 game_states=None, ocr_vars=None):
        super().__init__(parent)
        self.setWindowTitle(f"Logik-Netzwerk: {name}")
        self.setModal(False)
        self.resize(1100, 700)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._templates = templates or []

        # Falls bot ein Fenster ist, nimm die app-Instanz
        self._bot = bot
        if hasattr(bot, "app"):
            self._bot = bot.app

        nodes = [dict(n) for n in graph.get("nodes", [])]
        connections = [dict(c) for c in graph.get("connections", [])]
        if not nodes:
            nodes = [{"id": str(uuid.uuid4()), "typ": "l_result", "x": 600, "y": 200}]

        self._setup_ui()

        self._scene.load_graph(nodes, connections)

        # Trackt, welche Templates DIESER Editor dem Bot aufgezwungen hat
        self._added_force_includes = set()

        # Live-Vorschau Timer
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self._update_live_preview)
        if self._bot:
            self._preview_timer.start()

    def closeEvent(self, event):
        """Beim Schließen alle erzwungenen Scans wieder freigeben."""
        if hasattr(self, "_bot") and self._bot and hasattr(self._bot.state, "force_include"):
            for t in list(self._added_force_includes):
                if t in self._bot.state.force_include:
                    self._bot.state.force_include.remove(t)
        self._added_force_includes.clear()
        super().closeEvent(event)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setProperty("class", "bg_dialog_mid")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 6, 8, 6)
        bar_layout.setSpacing(6)

        for label, typ in TYPEN_LABEL:
            btn = QPushButton(label)
            btn.setProperty("class", "btn_node_type")
            btn.setProperty("type", typ)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=typ: self._node_hinzufuegen(t))
            bar_layout.addWidget(btn)

        bar_layout.addStretch()

        btn_save = QPushButton("💾 Speichern")
        btn_save.setObjectName("btn_new")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._speichern)
        bar_layout.addWidget(btn_save)

        root.addWidget(bar)

        # ── Canvas ────────────────────────────────────────────────────────────
        self._scene = LogicScene()
        self._scene.node_edit_requested.connect(self._edit_node)

        self._view = LogicView(self._scene)
        self._view.setSceneRect(0, 0, 3000, 2000)
        root.addWidget(self._view)

    def _node_hinzufuegen(self, typ: str):
        data = {"id": str(uuid.uuid4()), "typ": typ, "x": 150, "y": 150}
        if typ == "l_cmp":
            data["operator"] = "="
        self._scene.add_node_item(data)

    def _edit_node(self, node: NodeItem):
        if node.data["typ"] in ("l_and", "l_or", "l_not", "l_result"):
            return
        dlg = NodeParamDialog(node, self._templates, self, bot=self._bot)
        dlg.exec()

    def _update_live_preview(self):
        if not self._bot: return
        graph = self._scene.collect_graph()
        
        # 1. Aktuell im Graph benötigte Templates sammeln (l_match Nodes)
        current_needed = set()
        for node in graph.get("nodes", []):
            if node.get("typ") == "l_match":
                t = node.get("template")
                if t: current_needed.add(t)
        
        # 2. Synchronisierung mit dem Bot-State
        # a) Nicht mehr benötigte entfernen
        for t in list(self._added_force_includes):
            if t not in current_needed:
                if t in self._bot.state.force_include:
                    self._bot.state.force_include.remove(t)
                self._added_force_includes.remove(t)
        
        # b) Neue hinzufügen
        for t in current_needed:
            if t not in self._added_force_includes:
                if t not in self._bot.state.force_include:
                    self._bot.state.force_include.append(t)
                self._added_force_includes.add(t)

        # Hilfsfunktionen für Bot-Daten
        def ocr_f():
            # Die WorkflowEngine erwartet ein Dictionary aller Werte
            all_vals = self._bot.state.get_all_ocr()
            # Game-States injizieren
            for k, v in self._bot.state.game_states.items():
                all_vals[f"__state__{k}"] = "true" if v else "false"
            return all_vals
        
        def mat_f(): return self._bot.state.active_matches
        
        # Logik auswerten mit memo-Return
        _, memo = self._bot.workflow_engine._logik_auswerten(
            graph, ocr_f, mat_f, return_memo=True
        )
        self._scene.update_live_data(memo)

    def _speichern(self):
        graph = self._scene.collect_graph()
        self.gespeichert.emit(graph)
        self.accept()

    @staticmethod
    def ausfuehren(name: str, graph: dict,
                   templates: list | None = None,
                   parent=None,
                   bot=None,
                   game_states=None, ocr_vars=None) -> dict | None:
        result = {}
        dlg = LogicEditorDialogQt(name, graph, templates=templates, parent=parent, bot=bot)
        dlg.gespeichert.connect(lambda g: result.update(g))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result
        return None
