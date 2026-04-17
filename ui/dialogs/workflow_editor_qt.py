"""
Workflow-Editor (Qt) — Migriert von workflow_editor.py (tkinter).
Kernlogik (workflow_engine, bot) bleibt vollständig unangetastet.
"""
from __future__ import annotations
import uuid
import threading
import time
from collections import defaultdict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QWidget, QFrame, QMenu, QPlainTextEdit, QScrollArea, QSizePolicy,
    QMessageBox, QRadioButton, QButtonGroup, QFormLayout, QDoubleSpinBox,
    QSpinBox, QComboBox, QApplication, QAbstractSpinBox,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPoint,
    QMetaObject, Q_ARG, pyqtSlot,
)
from PyQt6.QtGui import (
    QAction, QCursor,
)
from ui.widgets.node_canvas import NodeCanvas, NODE_BREITE, NODE_HOEHE


def _neue_id():
    return uuid.uuid4().hex[:8]


# ── Haupt-Dialog ───────────────────────────────────────────────────────────────

class WorkflowEditorDialogQt(QDialog):
    gespeichert = pyqtSignal(str, dict)
    abgebrochen = pyqtSignal()
    _sim_fragen_signal = pyqtSignal(str, str)

    def __init__(self, parent, bot, name: str, graph: dict, callback=None, is_master=False):
        super().__init__(parent)
        self.bot = bot
        self._callback = callback
        self.is_master = is_master
        self.nodes = [dict(n) for n in graph.get("nodes", [])]
        self.connections = [dict(c) for c in graph.get("connections", [])]
        
        if self.is_master:
            # Sicherstellen, dass ein Selector da ist
            selector = next((n for n in self.nodes if n["typ"] == "priority_selector"), None)
            if not selector:
                sel_id = _neue_id()
                selector = {
                    "id": sel_id, 
                    "typ": "priority_selector", 
                    "x": 300, "y": 240,
                    "ausgaenge": [{"port": "Prio 1", "variable": "", "operator": "=", "wert": "true", "cooldown": 0, "max_runs": 0}]
                }
                self.nodes.append(selector)
            
            # Sicherstellen, dass ein Start da ist
            start_node = next((n for n in self.nodes if n["typ"] == "start"), None)
            if not start_node:
                start_id = _neue_id()
                start_node = {"id": start_id, "typ": "start", "x": 50, "y": 240}
                self.nodes.append(start_node)
                # Automatisch verbinden
                self.connections.append({"von": start_id, "port_aus": "out", "zu": selector["id"], "port_ein": "in"})
        else:
            if not self.nodes:
                self.nodes.append({"id": _neue_id(), "typ": "start", "x": 80, "y": 240})
        self._sim_aktiv = False
        self._sim_zustand = {}
        self._sim_progress = {}
        self._sim_fragen_event = None
        self._sim_fragen_result = None
        self._sim_fragen_signal.connect(self._sim_fragen_slot)
        self.setWindowTitle(f"{'Master' if is_master else 'Workflow'} Editor")
        self.resize(960, 640)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._setup_ui(name)
        self._sync_canvas()

    def _setup_ui(self, name: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)
        tb = QFrame()
        tb.setObjectName("workflow_editor_toolbar")
        tb_lay = QHBoxLayout(tb)
        tb_lay.setContentsMargins(4, 4, 4, 4)
        tb_lay.setSpacing(6)
        tb_lay.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(name)
        self._name_edit.setFixedWidth(160)
        self._name_edit.textChanged.connect(self._on_name_changed)
        tb_lay.addWidget(self._name_edit)
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setProperty("class", "separator")
        tb_lay.addWidget(sep1)
        lbl = QLabel("+ Node:")
        lbl.setProperty("class", "lbl_dim")
        tb_lay.addWidget(lbl)

        # Filter nodes based on is_master
        if self.is_master:
            typen = [
                ("Workflow","call_workflow"),
                ("Bedingung","bedingung"),
                ("Set Timer", "set_timer"),
                ("Warten","warten")
            ]
        else:
            typen = [
                ("Suche","suche"),
                ("Optional","suche_optional"),
                ("Klick","klick"),
                ("Set Timer", "set_timer"),
                ("Warten","warten"),
                ("Zurück","zurueck"),
                ("Home","home"),
                ("Bedingung","bedingung"),
                ("Selector","priority_selector")
            ]

        for label, typ in typen:
            btn = QPushButton(label)
            btn.setObjectName("btn_add_node")
            btn.setProperty("node_typ", typ)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=typ: self._node_hinzufuegen(t))
            tb_lay.addWidget(btn)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setProperty("class", "separator")
        tb_lay.addWidget(sep2)
        self._sim_btn = QPushButton("▶ Simulieren")
        self._sim_btn.setObjectName("btn_simulate")
        self._sim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sim_btn.clicked.connect(self._simulation_toggle)
        tb_lay.addWidget(self._sim_btn)
        tb_lay.addStretch()
        root.addWidget(tb)
        self._canvas = NodeCanvas()
        self._canvas.node_double_clicked.connect(self._node_parameter_editieren)
        self._canvas.node_right_clicked.connect(self._node_kontext_menu)
        self._canvas.conn_right_clicked.connect(self._verbindung_kontext_menu)
        self._canvas.connection_added.connect(self._sync_canvas)
        root.addWidget(self._canvas, stretch=1)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(90)
        self._log.setObjectName("workflow_editor_log")
        root.addWidget(self._log)
        bar = QFrame()
        bar.setObjectName("workflow_editor_statusbar")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(4, 4, 4, 4)
        self._status_lbl = QLabel("")
        self._status_lbl.setProperty("class", "lbl_info")
        bar_lay.addWidget(self._status_lbl)
        bar_lay.addStretch()
        btn_ab = QPushButton("Abbrechen")
        btn_ab.setObjectName("btn_sm")
        btn_ab.clicked.connect(self._abbrechen)
        bar_lay.addWidget(btn_ab)
        btn_sp = QPushButton("Speichern")
        btn_sp.setObjectName("btn_new")
        btn_sp.clicked.connect(self._speichern)
        bar_lay.addWidget(btn_sp)
        root.addWidget(bar)
        self._status_aktualisieren()

    @pyqtSlot()
    def _sync_canvas(self):
        self._canvas.nodes = self.nodes
        self._canvas.connections = self.connections
        self._canvas._workflow_name = self._name_edit.text()
        self._canvas._sim_zustand = self._sim_zustand
        self._canvas._sim_progress = self._sim_progress
        self._canvas.update()
        self._status_aktualisieren()

    def _on_name_changed(self, text):
        self._canvas._workflow_name = text
        self._canvas.update()

    def _node_hinzufuegen(self, typ: str):
        off = (len(self.nodes) % 8) * 22
        wx = self._canvas._wx(max(self._canvas.width(),300)/2) - NODE_BREITE/2 + off
        wy = self._canvas._wy(max(self._canvas.height(),200)/2) - NODE_HOEHE/2 + off
        node = {"id": _neue_id(), "typ": typ, "x": wx, "y": wy}
        if typ in ("suche", "suche_optional"):
            node["template"] = ""
            node["timeout"] = 10
        elif typ == "klick":
            node["template"] = ""
            node["index"] = "1"
        elif typ == "warten":
            node["sekunden"] = 1.0
        elif typ == "set_timer":
            node["timer_var"] = ""
            node["dauer"] = 60.0
        elif typ == "bedingung":

            node["variable"] = ""
            node["operator"] = ">"
            node["wert"] = "0"
        elif typ == "priority_selector":
            node["ausgaenge"] = [{"port": "Prio 1", "variable": "", "operator": "=", "wert": "true", "cooldown": 0, "max_runs": 0}]
        self.nodes.append(node)
        self._sync_canvas()

    def _node_loeschen(self, node: dict):
        # Start-Node darf nie gelöscht werden
        if node["typ"] == "start":
            return
        # In Master-Workflows darf der Selector nie gelöscht werden
        if self.is_master and node["typ"] == "priority_selector":
            return
            
        nid = node["id"]
        self.nodes = [n for n in self.nodes if n["id"] != nid]
        self.connections = [c for c in self.connections if c["von"] != nid and c["zu"] != nid]
        self._sync_canvas()

    def _verbindung_loeschen(self, conn: dict):
        if conn in self.connections:
            self.connections.remove(conn)
            self._sync_canvas()

    def _node_kontext_menu(self, node: dict, global_pos: QPoint):
        menu = QMenu(self)
        typ = node.get("typ")

        # Editieren
        if typ not in ("start", "zurueck", "home"):
            act_edit = menu.addAction("⚙ Parameter bearbeiten")
            act_edit.triggered.connect(lambda: self._node_parameter_editieren(node))
            menu.addSeparator()

        # Löschen
        can_delete = True
        if typ == "start": can_delete = False
        if self.is_master and typ == "priority_selector": can_delete = False

        if can_delete:
            act_del = menu.addAction("🗑 Node löschen")
            act_del.triggered.connect(lambda: self._node_loeschen(node))
        else:
            msg = "Start-Node" if typ == "start" else "Haupt-Selector"
            menu.addAction(f"({msg} kann nicht gelöscht werden)").setEnabled(False)

        menu.exec(global_pos)

    def _verbindung_kontext_menu(self, conn: dict, global_pos: QPoint):
        menu = QMenu(self)
        act_del = menu.addAction("🗑 Verbindung löschen")
        act_del.triggered.connect(lambda: self._verbindung_loeschen(conn))
        menu.exec(global_pos)

    def _node_parameter_editieren(self, node: dict):
        typ = node.get("typ")
        if typ in ("start", "zurueck", "home"):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{typ.upper()} – Parameter")
        dlg.setObjectName("workflow_param_dialog")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(6)
        felder = {}
        def add_row(label, key, widget):
            form.addRow(QLabel(label), widget)
            felder[key] = widget
        if typ in ("suche", "suche_optional", "klick"):
            tpl_btn = self._template_picker_btn(node.get("template", ""), dlg)
            add_row("Template:", "template", tpl_btn)
            if typ in ("suche", "suche_optional"):
                sp = QSpinBox()
                sp.setRange(1, 300)
                sp.setValue(int(node.get("timeout", 10)))
                sp.setProperty("class", "input_dark")
                add_row("Timeout (s):", "timeout", sp)
            elif typ == "klick":
                idx_btn = self._variablen_picker_btn(str(node.get("index", "1")), dlg)
                add_row("Match-Index:", "index", idx_btn)
        elif typ == "warten":
            sp = QDoubleSpinBox()
            sp.setRange(0.1, 300.0)
            sp.setSingleStep(0.5)
            sp.setValue(float(node.get("sekunden", 1.0)))
            sp.setProperty("class", "input_dark")
            add_row("Dauer (s):", "sekunden", sp)
        elif typ == "set_timer":
            t_var = node.get("timer_var", "")
            timer_btn = self._db_timer_picker_btn(t_var, dlg)
            add_row("Timer:", "timer_var", timer_btn)

            sp = QDoubleSpinBox()
            sp.setRange(0.1, 3600.0)
            sp.setSingleStep(1.0)
            sp.setValue(float(node.get("dauer", 10)))
            sp.setProperty("class", "input_dark")
            add_row("Dauer (s):", "dauer", sp)
        elif typ == "bedingung":

            var_btn = self._variablen_picker_btn(node.get("variable", ""), dlg)
            add_row("Variable:", "variable", var_btn)
            op_widget = QWidget()
            op_lay = QHBoxLayout(op_widget)
            op_lay.setContentsMargins(0,0,0,0)
            op_group = QButtonGroup(op_widget)
            op_selected = [node.get("operator", ">")]
            for op in [">", "<", ">=", "<=", "=", "!="]:
                rb = QRadioButton(op)
                rb.setChecked(op == op_selected[0])
                rb.setProperty("class", "lbl_dim")
                rb.toggled.connect(lambda chk, o=op: op_selected.__setitem__(0, o) if chk else None)
                op_group.addButton(rb)
                op_lay.addWidget(rb)
            felder["operator"] = op_selected
            add_row("Operator:", "operator_widget", op_widget)
            wert_edit = QLineEdit(str(node.get("wert", "0")))
            wert_edit.setProperty("class", "input_dark")
            add_row("Wert:", "wert", wert_edit)
        elif typ == "call_workflow":
            wf_btn = self._workflow_picker_btn(node.get("workflow", ""), dlg)
            add_row("Workflow:", "workflow", wf_btn)
        elif typ == "priority_selector":
            self._selector_editor(dlg, lay, node)
            return
        lay.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        def anwenden():
            for key, w in felder.items():
                if key == "operator":
                    node["operator"] = w[0]
                elif key in ("template", "variable", "workflow", "index"):
                    val = w.text()
                    if key == "template":
                        node[key] = "" if val == "Bitte wählen..." else val
                    elif key == "index":
                        # Standardwert "1" falls nichts gewählt
                        node[key] = "1" if val in ("Bitte wählen...", "") else val
                    else:
                        node[key] = "" if val == "Bitte wählen..." else val
                elif key == "timer_var":
                    val = w.text()
                    node["timer_var"] = "" if val == "Timer wählen..." else val
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    node[key] = w.value()
                elif isinstance(w, QLineEdit):
                    node[key] = w.text().strip()
            dlg.accept()
            self._sync_canvas()
        btn_ab = QPushButton("Abbrechen")
        btn_ab.setObjectName("btn_sm")
        btn_ok = QPushButton("Anwenden")
        btn_ok.setObjectName("btn_new")
        btn_ab.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(anwenden)
        btn_row.addWidget(btn_ab)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        # Um GC zu verhindern, hängen wir den Dialog an self
        if not hasattr(self, "_active_dialogs"):
            self._active_dialogs = []
        self._active_dialogs.append(dlg)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.destroyed.connect(lambda: self._active_dialogs.remove(dlg) if dlg in self._active_dialogs else None)
        dlg.show()

    def _selector_editor(self, parent_dlg: QDialog, lay: QVBoxLayout, node: dict):
        ausgaenge_liste = [dict(a) for a in node.get("ausgaenge", [])]
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        container = QWidget()
        c_lay = QVBoxLayout(container)
        scroll.setWidget(container)
        lay.addWidget(scroll)
        rows_widgets = []
        def rebuild():
            for w in container.findChildren(QWidget):
                w.deleteLater()
            while c_lay.count():
                c_lay.takeAt(0)
            rows_widgets.clear()
            for i, aus in enumerate(ausgaenge_liste):
                row = QFrame()
                row.setObjectName("selector_row")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(4, 2, 4, 2)
                p_edit = QLineEdit(aus.get("port", f"Prio {i+1}"))
                p_edit.setFixedWidth(100)
                p_edit.setProperty("class", "input_dark")
                has_logic = aus.get("logic_graph")
                btn_logic = QPushButton("★ Netzwerk" if has_logic else "🛠 Netzwerk")
                btn_logic.setObjectName("btn_logic_net")
                def _edit_logic(_, a_obj=aus, b=btn_logic):
                    from ui.dialogs.logic_editor_qt import LogicEditorDialogQt
                    g = a_obj.get("logic_graph") or {"nodes": [], "connections": []}
                    dlg2 = LogicEditorDialogQt(
                        name=a_obj.get("port", "Port"), graph=g,
                        game_states=self.bot.app.state.game_states,
                        templates=list(self.bot.template_engine.templates.keys()),
                        ocr_vars={
                            "global": self.bot.ocr_engine.regionen, 
                            "template": self.bot.ocr_engine.template_ocr_konfigurationen()
                        },
                        parent=parent_dlg, bot=self.bot)
                    dlg2.gespeichert.connect(lambda ng: (a_obj.__setitem__("logic_graph", ng), b.setText("★ Netzwerk")))
                    
                    # GC verhindern
                    if not hasattr(parent_dlg, "_sub_dialogs"):
                        parent_dlg._sub_dialogs = []
                    parent_dlg._sub_dialogs.append(dlg2)
                    dlg2.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                    dlg2.destroyed.connect(lambda: parent_dlg._sub_dialogs.remove(dlg2) if dlg2 in parent_dlg._sub_dialogs else None)
                    dlg2.show()
                btn_logic.clicked.connect(_edit_logic)
                c_sp = QDoubleSpinBox()
                c_sp.setRange(0, 3600)
                c_sp.setValue(float(aus.get("cooldown", 0)))
                c_sp.setFixedWidth(55)
                c_sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                c_sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
                c_sp.setProperty("class", "input_dark")
                
                m_sp = QSpinBox()
                m_sp.setRange(0, 9999)
                m_sp.setValue(int(aus.get("max_runs", 0)))
                m_sp.setFixedWidth(55)
                m_sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                m_sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
                m_sp.setProperty("class", "input_dark")
                btn_up = QPushButton("↑")
                btn_dn = QPushButton("↓")
                btn_dl = QPushButton("✕")
                btn_dl.setObjectName("btn_del_sm")
                
                # Verwende capture-local variables in lambdas
                btn_up.clicked.connect(lambda _, x=i: (ausgaenge_liste.insert(x-1, ausgaenge_liste.pop(x)), rebuild()) if x>0 else None)
                btn_dn.clicked.connect(lambda _, x=i: (ausgaenge_liste.insert(x+1, ausgaenge_liste.pop(x)), rebuild()) if x<len(ausgaenge_liste)-1 else None)
                btn_dl.clicked.connect(lambda _, x=i: (ausgaenge_liste.pop(x), rebuild()) if len(ausgaenge_liste)>1 else None)
                
                rl.addWidget(p_edit)
                rl.addWidget(btn_logic)
                rl.addWidget(QLabel("Wait:"))
                rl.addWidget(c_sp)
                rl.addWidget(QLabel("Limit:"))
                rl.addWidget(m_sp)
                rl.addWidget(btn_up)
                rl.addWidget(btn_dn)
                rl.addWidget(btn_dl)
                c_lay.addWidget(row)
                rows_widgets.append((p_edit, c_sp, m_sp, aus))
        
        rebuild()
        btn_add = QPushButton("+ Ausgang hinzufügen")
        btn_add.setObjectName("btn_new_sm")
        btn_add.clicked.connect(lambda: (ausgaenge_liste.append({"port": f"Prio {len(ausgaenge_liste)+1}", "cooldown": 0, "max_runs": 0, "logic_graph": None}), rebuild()))
        lay.addWidget(btn_add)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        def anwenden():
            # Wichtig: Vorhandene Daten (variable, operator, wert) behalten, wenn sie existieren
            node["ausgaenge"] = []
            for (p, c, m, a) in rows_widgets:
                aus_data = {
                    "port": p.text(),
                    "cooldown": c.value(),
                    "max_runs": m.value(),
                    "logic_graph": a.get("logic_graph")
                }
                # Fallback-Felder von 'a' (Original-Objekt) übernehmen
                if "variable" in a: aus_data["variable"] = a["variable"]
                if "operator" in a: aus_data["operator"] = a["operator"]
                if "wert" in a: aus_data["wert"] = a["wert"]
                
                node["ausgaenge"].append(aus_data)

            gültige = [a["port"] for a in node["ausgaenge"]] + ["else"]
            self.connections = [c for c in self.connections if not (c["von"] == node["id"] and c["port_aus"] not in gültige)]
            parent_dlg.accept()
            self._sync_canvas()

        btn_ab = QPushButton("Abbrechen")
        btn_ok = QPushButton("Anwenden")
        btn_ok.setObjectName("btn_new")
        btn_ab.clicked.connect(parent_dlg.reject)
        btn_ok.clicked.connect(anwenden)
        btn_row.addWidget(btn_ab)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)
        parent_dlg.exec()

    def _template_picker_btn(self, current: str, parent) -> QPushButton:
        btn = QPushButton(current or "Bitte wählen...")
        btn.setObjectName("btn_logic_net")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.build_template_menu(self.bot, parent, lambda n: btn.setText(n)).exec(QCursor.pos()))
        return btn

    @staticmethod
    def build_template_menu(bot, parent, on_selected_callback) -> QMenu:
        menu = QMenu(parent)
        engine = bot.template_engine
        settings = engine.settings
        def _p_key(p, name):
            """Baum-Schlüssel: immer Kurzname (letztes Segment), nie Vollpfad."""
            if not p or p == name:
                return ""
            return p.split("/")[-1]

        def _fill_kat(submenu: QMenu, kat: str):
            baum = defaultdict(list)
            alle_keys = set()
            for name, t in engine.templates.items():
                if name.startswith("_") or "__" in name:
                    continue
                s = settings.get(name, {})
                if s.get("kategorie", "workflow") != kat:
                    continue
                alle_keys.add(name)
                p = s.get("gruppe", "")
                baum[_p_key(p, name)].append(name)
            for s_name, s in settings.items():
                if s.get("typ") not in ("aktiv_gruppe", "passiv_gruppe") or s.get("kategorie", "workflow") != kat:
                    continue
                alle_keys.add(s_name)
                p = s.get("gruppe", "")
                key = _p_key(p, s_name)
                if s_name not in baum[key]:
                    baum[key].append(s_name)
            if not alle_keys:
                submenu.addAction("(keine Einträge)").setEnabled(False)
                return
            ex_gr = {k for k in alle_keys if settings.get(k, {}).get("typ") in ("aktiv_gruppe", "passiv_gruppe")}
            for p in list(baum.keys()):
                if p != "" and p not in ex_gr:
                    baum[""].extend(baum.pop(p))
            def render(pfad, m: QMenu, tiefe=0):
                # Sortierung wie im TemplatePanel:
                # Root (tiefe 0): Gruppen zuerst (False/0), dann Templates (True/1)
                # Submenus: Templates zuerst (False/0), dann Gruppen (True/1)
                if tiefe == 0:
                    items = sorted(baum.get(pfad, []), key=lambda x: (
                        settings.get(x, {}).get("typ") not in ("aktiv_gruppe", "passiv_gruppe"), 
                        x.lower()
                    ))
                else:
                    items = sorted(baum.get(pfad, []), key=lambda x: (
                        settings.get(x, {}).get("typ") in ("aktiv_gruppe", "passiv_gruppe"), 
                        x.lower()
                    ))

                for name in items:
                    s = settings.get(name, {})
                    typ = s.get("typ", "template")
                    if typ == "aktiv_gruppe":
                        sub = m.addMenu(f"★ {name}")
                        sub.addAction(f"Auswählen: {name}", lambda n=name: on_selected_callback(n))
                        sub.addSeparator()
                        render(name, sub, tiefe + 1)
                    elif typ == "passiv_gruppe":
                        sub = m.addMenu(f"📦 {name}")
                        render(name, sub, tiefe + 1)
                        if sub.isEmpty():
                            sub.addAction("(leer)").setEnabled(False)
                    else:
                        m.addAction(name, lambda n=name: on_selected_callback(n))
            render("", submenu)
        # Kategorien alphabetisch sortieren: State (🚩) vor Workflow (🔄)
        st = menu.addMenu("🚩 State")
        _fill_kat(st, "state")
        wf = menu.addMenu("🔄 Workflow")
        _fill_kat(wf, "workflow")
        return menu

    def _variablen_picker_btn(self, current: str, parent) -> QPushButton:
        btn = QPushButton(current or "Bitte wählen...")
        btn.setObjectName("btn_logic_net")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        def show():
            menu = QMenu(parent)
            st_sub = menu.addMenu("🚩 State")
            try:
                for n in sorted(self.bot.app.state.game_states.keys()):
                    st_sub.addAction(n, lambda x=n: btn.setText(f"state::{x}"))
            except:
                st_sub.addAction("(keine)").setEnabled(False)
            
            ocr_sub = menu.addMenu("🔤 OCR")
            if hasattr(self.bot.app.state, "get_all_ocr"):
                ocr_vars = self.bot.app.state.get_all_ocr()
            else:
                ocr_vars = {**self.bot.app.state.ocr_values, **self.bot.app.state.template_ocr_values}
            try:
                for n in sorted(ocr_vars.keys()):
                    ocr_sub.addAction(n, lambda x=n: btn.setText(f"ocr::{x}"))
            except:
                ocr_sub.addAction("(keine)").setEnabled(False)
            
            db_sub = menu.addMenu("📊 Daten")
            try:
                from core import daten_manager as dm
                for l in dm.alle_listen():
                    ls = db_sub.addMenu(l["name"])
                    for t in dm.transformationen_der_liste(l["id"]):
                        ls.addAction(t["name"], lambda ln=l["name"], tn=t["name"]: btn.setText(f"db::{ln}::{tn}"))
                    for b in dm.berechnungen_der_liste(l["id"]):
                        ls.addAction(b["name"], lambda ln=l["name"], bn=b["name"]: btn.setText(f"db::{ln}::{bn}"))
            except:
                db_sub.addAction("(DB Fehler)").setEnabled(False)
            menu.exec(QCursor.pos())
        btn.clicked.connect(show)
        return btn

    def _db_timer_picker_btn(self, current: str, parent) -> QPushButton:
        btn = QPushButton(current or "Timer wählen...")
        btn.setObjectName("btn_logic_net")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        def show():
            from core import daten_manager as dm
            menu = QMenu(parent)
            listen = sorted(dm.alle_listen(), key=lambda x: x["name"].lower())
            found = False
            for l in listen:
                if l.get("typ") == "timer":
                    zeilen = sorted(dm.zeilen_der_liste(l["id"]), key=lambda x: x["name"].lower())
                    if zeilen:
                        sub = menu.addMenu(f"⏳ {l['name']}")
                        for z in zeilen:
                            found = True
                            var_path = f"db::{l['name']}::{z['name']}"
                            sub.addAction(z["name"], lambda _, x=var_path: btn.setText(x))
            if not found:
                menu.addAction("(Keine Timer-Listen gefunden)").setEnabled(False)
            menu.exec(QCursor.pos())
        btn.clicked.connect(show)
        return btn

    def _workflow_picker_btn(self, current: str, parent) -> QPushButton:
        btn = QPushButton(current or "Bitte wählen...")
        btn.setObjectName("btn_logic_net")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        def show():
            menu = QMenu(parent)
            try:
                wfs = sorted(self.bot.workflow_engine.workflows.keys())
                eig = self._name_edit.text().strip()
                wfs = [w for w in wfs if w != eig]
                if not wfs:
                    menu.addAction("(keine anderen)").setEnabled(False)
                for w in wfs:
                    menu.addAction(f"🔄 {w}", lambda x=w: btn.setText(x))
            except:
                menu.addAction("(Fehler)").setEnabled(False)
            menu.exec(QCursor.pos())
        btn.clicked.connect(show)
        return btn

    # ── Simulation ─────────────────────────────────────────────────────────────

    def _simulation_toggle(self):
        if self._sim_aktiv:
            self._simulation_stoppen()
        else:
            self._simulation_starten()

    def _simulation_starten(self):
        start = next((n for n in self.nodes if n.get("typ") == "start"), None)
        if not start:
            self._sim_log("Kein Start-Node!", "failure")
            return
        self._sim_aktiv = True
        self._sim_zustand = {}
        self._sim_progress = {}
        self._sim_btn.setText("⏹ Stopp")
        self._sim_btn.setProperty("state", "active")
        self._sim_btn.style().unpolish(self._sim_btn)
        self._sim_btn.style().polish(self._sim_btn)
        self._log.clear()
        self._sim_log("▶ Simulation gestartet", "info")
        self._sim_engine = self.SimulatedActionEngine(self, self.bot.action_engine, self._sim_log)
        self._sim_nodes_index = {n["id"]: n for n in self.nodes}
        self._sim_aktueller_schritt = 0
        self._simulation_schritt_gui(start)

    def _simulation_stoppen(self):
        self._sim_aktiv = False
        self._sim_zustand = {}
        self._sim_progress = {}
        self._sim_btn.setText("▶ Simulieren")
        self._sim_btn.setProperty("state", "stopped")
        self._sim_btn.style().unpolish(self._sim_btn)
        self._sim_btn.style().polish(self._sim_btn)
        self._sync_canvas()

    @pyqtSlot(dict)
    def _simulation_schritt_gui(self, node):
        if not self._sim_aktiv or node is None or self._sim_aktueller_schritt > 200:
            QMetaObject.invokeMethod(self, "_simulation_fertig", Qt.ConnectionType.QueuedConnection)
            return
        self._sim_aktueller_schritt += 1
        nid = node["id"]
        typ = node.get("typ", "?")
        self._sim_zustand[nid] = "aktiv"
        if nid in self._sim_progress:
            self._sim_progress.pop(nid)
        self._sync_canvas()
        self._sim_log(f"► {typ.upper()}: {self._canvas._node_detail(node)}", "aktiv")
        
        def run():
            if not self._sim_aktiv:
                return
            def m_func():
                return self.bot.app.state.active_matches
            def o_func():
                data = dict(self.bot.app.state.ocr_values)
                for sn, sv in self.bot.app.state.game_states.items():
                    data[f"__state__{sn}"] = "true" if sv else "false"
                data.update(self.bot.app.state.template_ocr_values)
                return data
            def sim_state_func(cmd, val):
                if not (self.bot and hasattr(self.bot.app.state, "force_include")):
                    return
                fi = self.bot.app.state.force_include
                if cmd == "add_force_include":
                    if val and val not in fi:
                        fi.append(val)
                elif cmd == "remove_force_include":
                    if val in fi:
                        fi.remove(val)

            # force_include für search_only Templates setzen (wie in workflow_ausfuehren)
            sim_t_name = node.get("template") if typ in ("suche", "suche_optional", "klick") else None
            if sim_t_name:
                sim_state_func("add_force_include", sim_t_name)

            port = self.bot.workflow_engine._node_ausfuehren(
                node, self._sim_engine, m_func, ocr_func=o_func,
                log_func=self._sim_log, laeuft_func=lambda: self._sim_aktiv,
                state_func=sim_state_func)

            if sim_t_name:
                sim_state_func("remove_force_include", sim_t_name)
            
            if port is None:
                self._sim_log(f"!! Unbekannter Typ: {typ}", "failure")
                self._sim_zustand[nid] = "failure"
                QMetaObject.invokeMethod(self, "_simulation_fertig", Qt.ConnectionType.QueuedConnection)
                return
            
            self._sim_zustand[nid] = "success" if port in ("success", "true", "out") else "failure"
            if nid in self._sim_progress:
                self._sim_progress.pop(nid)
            QMetaObject.invokeMethod(self, "_sync_canvas", Qt.ConnectionType.QueuedConnection)
            self._sim_log(f"→ Port: {port}", "success" if self._sim_zustand[nid] == "success" else "failure")
            
            next_n = None
            for c in self.connections:
                if c["von"] == nid and c["port_aus"] == port:
                    next_n = self._sim_nodes_index.get(c["zu"])
                    break
            
            if next_n is None:
                self._sim_log("(Ende)", "done")
                QMetaObject.invokeMethod(self, "_sim_fertig_verzoegert", Qt.ConnectionType.QueuedConnection)
            else:
                QMetaObject.invokeMethod(self, "_sim_naechster_schritt", Qt.ConnectionType.QueuedConnection, Q_ARG(dict, next_n))
        
        threading.Thread(target=run, daemon=True).start()

    @pyqtSlot(str, str)
    def _sim_fragen_slot(self, titel, msg):
        dlg = QMessageBox(self)
        dlg.setWindowTitle(titel)
        dlg.setText(msg)
        b_sim = dlg.addButton("Simulieren", QMessageBox.ButtonRole.NoRole)
        b_adb = dlg.addButton("ADB", QMessageBox.ButtonRole.YesRole)
        b_ab  = dlg.addButton("Stop", QMessageBox.ButtonRole.RejectRole)
        dlg.exec()
        c = dlg.clickedButton()
        if c == b_adb:
            self._sim_fragen_result = "adb"
        elif c == b_ab:
            self._sim_fragen_result = "stop"
        else:
            self._sim_fragen_result = "sim"
        if self._sim_fragen_event:
            self._sim_fragen_event.set()

    @pyqtSlot()
    def _sim_fertig_verzoegert(self):
        QTimer.singleShot(400, self._simulation_fertig)

    @pyqtSlot(dict)
    def _sim_naechster_schritt(self, next_n):
        QTimer.singleShot(300, lambda: self._simulation_schritt_gui(next_n))

    @pyqtSlot()
    def _simulation_fertig(self):
        if not self._sim_aktiv:
            return
        self._sim_log("✓ Simulation beendet", "done")
        self._sim_aktiv = False
        self._sim_btn.setText("▶ Simulieren")
        self._sim_btn.setProperty("state", "stopped")
        self._sim_btn.style().unpolish(self._sim_btn)
        self._sim_btn.style().polish(self._sim_btn)
        self._status_aktualisieren()
        self._sync_canvas()

    def _sim_log(self, text: str, tag: str = "done"):
        if text.startswith("__timer__"):
            val = text[9:]
            for nid, status in self._sim_zustand.items():
                if status == "aktiv":
                    node = next((n for n in self.nodes if n["id"] == nid), None)
                    if node and node.get("typ") in ("suche", "suche_optional", "warten"):
                        self._sim_progress[nid] = f"⏳ {val}s"
                        QMetaObject.invokeMethod(self, "_sync_canvas", Qt.ConnectionType.QueuedConnection)
                    break
            return
        farbe = {"aktiv":"#f9a825","success":"#4caf50","failure":"#ef5350","info":"#90caf9","done":"#aaaaaa"}.get(tag, "#cccccc")
        QMetaObject.invokeMethod(self, "_append_to_log", Qt.ConnectionType.QueuedConnection, Q_ARG(str, text), Q_ARG(str, farbe))

    @pyqtSlot(str, str)
    def _append_to_log(self, text, farbe):
        cursor = self._log.textCursor()
        from PyQt6.QtGui import QTextCharFormat, QColor as _C
        fmt = QTextCharFormat()
        fmt.setForeground(_C(farbe))
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def _status_aktualisieren(self):
        z = int(self._canvas._scale * 100)
        if self._sim_aktiv:
            self._status_lbl.setText(f"▶ Simulation läuft …  ·  Zoom {z}%")
            self._status_lbl.setProperty("class", "lbl_warning")
        else:
            self._status_lbl.setText(f"{len(self.nodes)} Nodes  ·  {len(self.connections)} Verbindungen  ·  Zoom {z}%")
            self._status_lbl.setProperty("class", "lbl_dim")
        self._status_lbl.style().unpolish(self._status_lbl)
        self._status_lbl.style().polish(self._status_lbl)

    def _speichern(self):
        name = self._name_edit.text().strip()
        if not name:
            return
        self.gespeichert.emit(name, {"nodes": self.nodes, "connections": self.connections})
        if self._callback:
            self._callback(name, {"nodes": self.nodes, "connections": self.connections})
        self.accept()

    def _abbrechen(self):
        self.abgebrochen.emit()
        if self._callback:
            self._callback(None, None)
        self.reject()

    def closeEvent(self, event):
        self._abbrechen()
        super().closeEvent(event)

    class SimulatedActionEngine:
        def __init__(self, parent, real, log):
            self.parent = parent
            self.real = real
            self.log = log
        
        def _fragen(self, titel, msg):
            import threading as _threading
            event = _threading.Event()
            self.parent._sim_fragen_event = event
            self.parent._sim_fragen_result = None
            self.parent._sim_fragen_signal.emit(titel, msg)
            event.wait()
            return self.parent._sim_fragen_result
        
        def auf_template_warten(self, t, mf, timeout=10, intervall=0.3, log_func=None, laeuft_func=None):
            return self.real.auf_template_warten(t, mf, timeout, intervall, log_func=log_func, laeuft_func=laeuft_func)
        
        def template_tippen(self, t, m, log_func=None):
            for i in m:
                if i[0] == t:
                    _, mx, my, mw, mh = i[:5]
                    kx, ky = self.real.klickpunkt_berechnen(t, mx, my, mw, mh)
                    w = self._fragen("KLICK", f"Auf '{t}' ({kx}, {ky}) klicken?")
                    if w == "stop":
                        self.parent._simulation_stoppen()
                        return False
                    if w == "adb":
                        self.log(f"[ADB] {t}", "success")
                        return self.real.template_tippen(t, m, log_func=None)
                    self.log(f"[SIM] {t}", "info")
                    return True
            return False
        
        def warten(self, s):
            time.sleep(min(s, 2.0))
        
        def zurueck(self):
            w = self._fragen("ZURÜCK", "Zurück?")
            if w == "adb":
                self.log("[ADB] Back", "success")
                self.real.zurueck()
            elif w == "stop":
                self.parent._simulation_stoppen()
            else:
                self.log("[SIM] Back", "info")
        
        def home(self):
            w = self._fragen("HOME", "Home?")
            if w == "adb":
                self.log("[ADB] Home", "success")
                self.real.home()
            elif w == "stop":
                self.parent._simulation_stoppen()
            else:
                self.log("[SIM] Home", "info")
