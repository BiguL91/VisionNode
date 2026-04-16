"""
FUP Logik-Netzwerk Editor (Qt).

Verwendung:
    dlg = LogicEditorDialogQt(name, graph, game_states, templates, ocr_vars, parent)
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
    def __init__(self, node: NodeItem, game_states: dict, templates: list, ocr_vars: dict, parent=None, bot=None):
        super().__init__(parent)
        self.setWindowTitle(f"Konfiguration: {node.data['typ'].upper()}")
        self.setObjectName("logic_param_dialog")
        self.setModal(True)
        self.setFixedSize(420, 260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._node = node
        self._game_states = game_states
        self._templates = templates
        self._ocr_vars = ocr_vars
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

            self._var_btn = QPushButton(self._node.data.get("variable", "Bitte wählen..."))
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
            combo.addItems(["=", "!=", ">", "<", ">=", "<="])
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

            t_var = self._node.data.get("variable", "")
            self._timer_btn = QPushButton(t_var or "Timer wählen...")
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
        menu = QMenu(self)

        # 1. Game States (Sortiert)
        s_menu = menu.addMenu("🚩 Game States")
        for s in sorted(self._game_states.keys()):
            act = QAction(s, self)
            act.triggered.connect(lambda _, x=s: self._var_btn.setText(f"state::{x}"))
            s_menu.addAction(act)

        # 2. OCR Werte (Strukturiert und Sortiert)
        o_menu = menu.addMenu("🔤 OCR Werte")

        # a) Global (Feste Regionen)
        glob_vars = sorted(self._ocr_vars.get("global", {}).keys())
        if glob_vars:
            g_sub = o_menu.addMenu("🌐 Global")
            for o in glob_vars:
                act = QAction(o, self)
                act.triggered.connect(lambda _, x=o: self._var_btn.setText(f"ocr::{x}"))
                g_sub.addAction(act)

        # b) Template OCR (Gruppiert nach Kategorie -> Template)
        t_vars = self._ocr_vars.get("template", {})
        if t_vars:
            # Struktur aufbauen: { Kategorie: { TemplateName: [Variablen] } }
            struk = {}
            for en, cfg in t_vars.items():
                tn = cfg.get("template", "Unbekannt")
                # Kategorie aus Bot-Settings holen (falls verfügbar)
                kat = "Workflow"
                if self._bot:
                    kat = self._bot.template_engine.settings.get(tn, {}).get("kategorie", "Workflow").capitalize()

                if kat not in struk: struk[kat] = {}
                if tn not in struk[kat]: struk[kat][tn] = []
                struk[kat][tn].append(en)

            # Menü nach Kategorien aufbauen
            for kat in sorted(struk.keys()):
                k_menu = o_menu.addMenu(f"📁 {kat}")
                for tn in sorted(struk[kat].keys()):
                    t_menu = k_menu.addMenu(f"🖼 {tn}")
                    for en in sorted(struk[kat][tn]):
                        # Anzeige-Name säubern (Präfix entfernen)
                        v_anzeige = en[len(tn)+1:] if en.startswith(f"{tn}_") else en
                        act = QAction(v_anzeige, self)
                        act.triggered.connect(lambda _, x=en: self._var_btn.setText(f"ocr::{x}"))
                        t_menu.addAction(act)

        # 3. Datenbank (Daten-Listen)
        try:
            from core import daten_manager as dm
            listen = dm.alle_listen()
            if listen:
                d_menu = menu.addMenu("📋 Datenbank")
                for l in listen:
                    l_sub = d_menu.addMenu(f"📋 {l['name']}")
                    spalten = dm.spalten_der_liste(l["id"])
                    trans = dm.transformationen_der_liste(l["id"])
                    vars = sorted(list(set([s["name"] for s in spalten] + [t["name"] for t in trans])))
                    for v in vars:
                        act = QAction(v, self)
                        act.triggered.connect(lambda _, ln=l["name"], vn=v: self._var_btn.setText(f"db::{ln}::{vn}"))
                        l_sub.addAction(act)
        except Exception:
            pass

        if menu.isEmpty():
            menu.addAction("(Keine Variablen verfügbar)").setEnabled(False)

        menu.exec(self._var_btn.mapToGlobal(self._var_btn.rect().bottomLeft()))

    def _timer_menu_zeigen(self):
        """Spezialisierter Picker für Timer-Variablen – zwei Kategorien."""
        from core import daten_manager as dm
        menu = QMenu(self)
        try:
            listen = sorted(dm.alle_listen(), key=lambda x: x["name"].lower())
            found = False

            # ── Kategorie 1: Globale Timer-Listen (typ == "timer") ────────────
            kat_global = menu.addMenu("⏳ Globale Timer Liste")
            for l in listen:
                if l.get("typ") != "timer":
                    continue
                zeilen = sorted(dm.zeilen_der_liste(l["id"]), key=lambda x: x["name"].lower())
                if zeilen:
                    sub = kat_global.addMenu(l["name"])
                    for z in zeilen:
                        found = True
                        var_path = f"db::{l['name']}::{z['name']}"
                        sub.addAction(z["name"], lambda _, x=var_path: self._timer_btn.setText(x))
            if kat_global.isEmpty():
                kat_global.addAction("(keine)").setEnabled(False)

            # ── Kategorie 2: Standard Daten-Listen mit Timer-Spalten/Transforms ─
            kat_daten = menu.addMenu("📊 Standard Daten-Liste")
            for l in listen:
                timer_vars = []
                spalten = dm.spalten_der_liste(l["id"])
                for s in spalten:
                    if s.get("typ") == "timer": timer_vars.append(s["name"])
                trans = dm.transformationen_der_liste(l["id"])
                for t in trans:
                    if t.get("typ") == "timer": timer_vars.append(t["name"])
                timer_vars = sorted(list(set(timer_vars)), key=lambda x: x.lower())
                if timer_vars:
                    sub = kat_daten.addMenu(l["name"])
                    for v in timer_vars:
                        found = True
                        var_path = f"db::{l['name']}::{v}"
                        sub.addAction(v, lambda _, x=var_path: self._timer_btn.setText(x))
            if kat_daten.isEmpty():
                kat_daten.addAction("(keine)").setEnabled(False)

            if not found:
                menu.addAction("(Keine Timer gefunden)").setEnabled(False)
        except Exception as e:
            menu.addAction(f"Fehler: {e}").setEnabled(False)

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
                val = widget.text()
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
                 game_states: dict | None = None,
                 templates: list | None = None,
                 ocr_vars: dict | None = None,
                 parent=None,
                 bot=None):
        super().__init__(parent)
        self.setWindowTitle(f"Logik-Netzwerk: {name}")
        self.setModal(False)
        self.resize(1100, 700)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._game_states = game_states or {}
        self._templates = templates or []
        self._ocr_vars = ocr_vars or {}
        
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
        dlg = NodeParamDialog(node, self._game_states, self._templates, self._ocr_vars, self, bot=self._bot)
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
                   game_states: dict | None = None,
                   templates: list | None = None,
                   ocr_vars: dict | None = None,
                   parent=None,
                   bot=None) -> dict | None:
        result = {}
        dlg = LogicEditorDialogQt(name, graph, game_states, templates, ocr_vars, parent, bot=bot)
        dlg.gespeichert.connect(lambda g: result.update(g))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result
        return None
