from lang import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont
from core.event_bus import bus

# ── Masterflow Panel ──────────────────────────────────────────────────────────

class MasterflowPanel(QWidget):
    neu_requested        = pyqtSignal()
    bearbeiten_requested = pyqtSignal(str)
    loeschen_requested   = pyqtSignal(str)
    aktiv_requested      = pyqtSignal(str)

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._setup_ui()
        
        bus.subscribe("workflow.config.changed", self._on_changed)
        bus.subscribe("workflow.active.changed", self._on_changed)

    def _on_changed(self, event):
        if self.engine:
            QTimer.singleShot(0, lambda: self.aktualisieren(self.engine.master_workflows, self.engine.aktiver_master))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        lbl = QLabel("MASTER-FLOWS (Schrittketten)")
        lbl.setProperty("class", "lbl_header_gold")
        layout.addWidget(lbl)

        self.liste = QListWidget()
        self.liste.setObjectName("master_liste")
        self.liste.itemDoubleClicked.connect(self._bearbeiten)
        layout.addWidget(self.liste)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        
        self.btn_neu = QPushButton("+ Neu")
        self.btn_neu.setObjectName("btn_new_sm")
        self.btn_neu.clicked.connect(self.neu_requested)
        
        self.btn_bearbeiten = QPushButton("✎ Bearbeiten")
        self.btn_bearbeiten.setObjectName("btn_sm")
        self.btn_bearbeiten.clicked.connect(self._bearbeiten)
        
        self.btn_aktiv = QPushButton("★ Aktiv")
        self.btn_aktiv.setObjectName("btn_master_aktiv")
        self.btn_aktiv.clicked.connect(self._aktiv)
        
        self.btn_loeschen = QPushButton("✕")
        self.btn_loeschen.setObjectName("btn_del_sm")
        self.btn_loeschen.clicked.connect(self._loeschen)

        for btn in [self.btn_neu, self.btn_bearbeiten, self.btn_aktiv, self.btn_loeschen]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btns.addWidget(btn)
        layout.addLayout(btns)

    def aktualisieren(self, master_workflows: dict, aktiver_master: str):
        self.liste.clear()
        if not master_workflows:
            item = QListWidgetItem("  (Keine Master-Flows)")
            item.setForeground(QColor("#555555"))
            self.liste.addItem(item)
            return
        for name in sorted(master_workflows.keys()):
            ist_aktiv = (name == aktiver_master)
            prefix = " ★ " if ist_aktiv else "   "
            item = QListWidgetItem(f"{prefix}{name}")
            if ist_aktiv:
                item.setForeground(QColor("#ffca28"))
            self.liste.addItem(item)

    def _get_name(self) -> str | None:
        item = self.liste.currentItem()
        if not item: return None
        text = item.text().strip()
        if text.startswith("("): return None
        for icon in ["★", " "]:
            text = text.replace(icon, "")
        return text.strip()

    def _bearbeiten(self):
        name = self._get_name()
        if name: self.bearbeiten_requested.emit(name)

    def _aktiv(self):
        name = self._get_name()
        if name: self.aktiv_requested.emit(name)

    def _loeschen(self):
        name = self._get_name()
        if name: self.loeschen_requested.emit(name)


# ── Sub-Workflow Panel ────────────────────────────────────────────────────────

class SubWorkflowPanel(QWidget):
    neu_requested        = pyqtSignal()
    bearbeiten_requested = pyqtSignal(str)
    kopieren_requested   = pyqtSignal(str)
    loeschen_requested   = pyqtSignal(str)

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._setup_ui()
        bus.subscribe("workflow.config.changed", self._on_changed)

    def _on_changed(self, event):
        if self.engine:
            QTimer.singleShot(0, lambda: self.aktualisieren(self.engine.workflows))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        lbl = QLabel("SUB-WORKFLOWS (Bausteine)")
        lbl.setProperty("class", "lbl_header_dim")
        layout.addWidget(lbl)

        self.liste = QListWidget()
        self.liste.setObjectName("workflow_liste")
        self.liste.itemDoubleClicked.connect(self._bearbeiten)
        layout.addWidget(self.liste)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        
        self.btn_neu = QPushButton("+ Neu")
        self.btn_neu.setObjectName("btn_new_sm")
        self.btn_neu.clicked.connect(self.neu_requested)
        
        self.btn_bearbeiten = QPushButton("✎ Bearbeiten")
        self.btn_bearbeiten.setObjectName("btn_sm")
        self.btn_bearbeiten.clicked.connect(self._bearbeiten)
        
        self.btn_kopieren = QPushButton("❐ Kopieren")
        self.btn_kopieren.setObjectName("btn_copy_sm")
        self.btn_kopieren.clicked.connect(self._kopieren)
        
        self.btn_loeschen = QPushButton("✕")
        self.btn_loeschen.setObjectName("btn_del_sm")
        self.btn_loeschen.clicked.connect(self._loeschen)

        for btn in [self.btn_neu, self.btn_bearbeiten, self.btn_kopieren, self.btn_loeschen]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btns.addWidget(btn)
        layout.addLayout(btns)

    def aktualisieren(self, workflows: dict):
        self.liste.clear()
        if not workflows:
            item = QListWidgetItem("  (Keine Workflows)")
            item.setForeground(QColor("#555555"))
            self.liste.addItem(item)
            return
        for name in sorted(workflows.keys()):
            graph = workflows[name]
            n_nodes = len(graph.get("nodes", []))
            n_conn  = len(graph.get("connections", []))
            self.liste.addItem(f"  {name}  ({n_nodes} Nodes, {n_conn} Links)")

    def _get_name(self) -> str | None:
        item = self.liste.currentItem()
        if not item: return None
        text = item.text().strip()
        if text.startswith("("): return None
        if "  (" in text: return text.split("  (")[0].strip()
        if " (" in text: return text.split(" (")[0].strip()
        return text

    def _bearbeiten(self):
        name = self._get_name()
        if name: self.bearbeiten_requested.emit(name)

    def _kopieren(self):
        name = self._get_name()
        if name: self.kopieren_requested.emit(name)

    def _loeschen(self):
        name = self._get_name()
        if name: self.loeschen_requested.emit(name)


# ── Logic Network Panel ───────────────────────────────────────────────────────

class LogicNetworkPanel(QWidget):
    edit_requested = pyqtSignal(str, str, str, str, dict) # wf_type, wf_name, node_id, port_name, graph
    copy_requested = pyqtSignal(str, str, str, str, dict)

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._logic_data = []
        self._setup_ui()
        bus.subscribe("workflow.config.changed", self._on_changed)

    def _on_changed(self, event):
        if self.engine:
            QTimer.singleShot(0, lambda: self.aktualisieren(self.engine.master_workflows, self.engine.workflows))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        lbl = QLabel("LOGIK-NETZWERKE (FUP)")
        lbl.setProperty("class", "lbl_header_dim")
        layout.addWidget(lbl)

        self.liste = QListWidget()
        self.liste.setObjectName("logic_liste")
        self.liste.itemDoubleClicked.connect(self._bearbeiten)
        layout.addWidget(self.liste)

        btns = QHBoxLayout()
        btns.setSpacing(4)

        self.btn_bearbeiten = QPushButton("✎ Bearbeiten")
        self.btn_bearbeiten.setObjectName("btn_sm")
        self.btn_bearbeiten.clicked.connect(self._bearbeiten)
        
        self.btn_kopieren = QPushButton("❐ Kopieren")
        self.btn_kopieren.setObjectName("btn_copy_sm")
        self.btn_kopieren.clicked.connect(self._kopieren)

        for btn in [self.btn_bearbeiten, self.btn_kopieren]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btns.addWidget(btn)
        layout.addLayout(btns)

    def aktualisieren(self, master_workflows: dict, workflows: dict):
        self.liste.clear()
        self._logic_data.clear()

        def scan_wf(wf_dict, wf_type):
            for wf_name, graph in wf_dict.items():
                for node in graph.get("nodes", []):
                    if node.get("typ") == "priority_selector":
                        for aus in node.get("ausgaenge", []):
                            net = aus.get("logic_graph")
                            if net and net.get("nodes"):
                                port = aus.get("port", "Port")
                                self._logic_data.append((wf_type, wf_name, node["id"], port, net))
                                self.liste.addItem(f"  {wf_name} → {port}")

        scan_wf(master_workflows, "master")
        scan_wf(workflows, "sub")

        if not self._logic_data:
            item = QListWidgetItem("  (Keine Netzwerke)")
            item.setForeground(QColor("#555555"))
            self.liste.addItem(item)

    def _bearbeiten(self):
        idx = self.liste.currentRow()
        if 0 <= idx < len(self._logic_data):
            self.edit_requested.emit(*self._logic_data[idx])

    def _kopieren(self):
        idx = self.liste.currentRow()
        if 0 <= idx < len(self._logic_data):
            self.copy_requested.emit(*self._logic_data[idx])


# ── Legacy WorkflowPanel (Abwärtskompatibilität, falls nötig) ──────────────────

class WorkflowPanel(QWidget):
    """Kombiniert die drei neuen Panels in einem Widget (für altes Layout)."""
    master_neu_requested      = pyqtSignal()
    master_bearbeiten_requested = pyqtSignal(str)
    master_loeschen_requested = pyqtSignal(str)
    master_aktiv_requested    = pyqtSignal(str)
    workflow_neu_requested    = pyqtSignal()
    workflow_bearbeiten_requested = pyqtSignal(str)
    workflow_kopieren_requested   = pyqtSignal(str)
    workflow_loeschen_requested   = pyqtSignal(str)
    logic_network_edit_requested  = pyqtSignal(str, str, str, str, dict)
    logic_network_copy_requested  = pyqtSignal(str, str, str, str, dict)

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        self.master_panel = MasterflowPanel(engine=self.engine)
        self.sub_panel = SubWorkflowPanel(engine=self.engine)
        self.logic_panel = LogicNetworkPanel(engine=self.engine)

        l.addWidget(self.master_panel)
        
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setProperty("class", "separator")
        l.addWidget(line)
        
        l.addWidget(self.sub_panel)
        
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine); line2.setProperty("class", "separator")
        l.addWidget(line2)
        
        l.addWidget(self.logic_panel)

        # Signale weiterleiten
        self.master_panel.neu_requested.connect(self.master_neu_requested)
        self.master_panel.bearbeiten_requested.connect(self.master_bearbeiten_requested)
        self.master_panel.loeschen_requested.connect(self.master_loeschen_requested)
        self.master_panel.aktiv_requested.connect(self.master_aktiv_requested)

        self.sub_panel.neu_requested.connect(self.workflow_neu_requested)
        self.sub_panel.bearbeiten_requested.connect(self.workflow_bearbeiten_requested)
        self.sub_panel.kopieren_requested.connect(self.workflow_kopieren_requested)
        self.sub_panel.loeschen_requested.connect(self.workflow_loeschen_requested)

        self.logic_panel.edit_requested.connect(self.logic_network_edit_requested)
        self.logic_panel.copy_requested.connect(self.logic_network_copy_requested)

    def aktualisieren(self, master_workflows, aktiver_master, workflows):
        self.master_panel.aktualisieren(master_workflows, aktiver_master)
        self.sub_panel.aktualisieren(workflows)
        self.logic_panel.aktualisieren(master_workflows, workflows)
