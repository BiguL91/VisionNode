from lang import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont


class WorkflowPanel(QWidget):
    # Signals → Bot-Controller
    master_neu_requested      = pyqtSignal()
    master_bearbeiten_requested = pyqtSignal(str)   # name
    master_loeschen_requested = pyqtSignal(str)     # name
    master_aktiv_requested    = pyqtSignal(str)     # name
    workflow_neu_requested    = pyqtSignal()
    workflow_bearbeiten_requested = pyqtSignal(str) # name
    workflow_kopieren_requested   = pyqtSignal(str) # name
    workflow_loeschen_requested   = pyqtSignal(str) # name
    logic_network_edit_requested  = pyqtSignal(str, str, str, str, dict) # wf_type, wf_name, node_id, port_name, graph
    logic_network_copy_requested  = pyqtSignal(dict) # graph
    logic_network_paste_requested = pyqtSignal(str, str, str, str) # wf_type, wf_name, node_id, port_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logic_data = [] # Liste von (wf_type, wf_name, node_id, port_name, graph)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Master-Flows ───────────────────────────────────────────────────────
        lbl_master = QLabel("MASTER-FLOWS (Schrittketten)")
        lbl_master.setProperty("class", "lbl_header_gold")
        layout.addWidget(lbl_master)

        self.master_liste = QListWidget()
        self.master_liste.setFixedHeight(120)
        self.master_liste.setObjectName("master_liste")
        layout.addWidget(self.master_liste)

        m_btns = QHBoxLayout()
        m_btns.setSpacing(4)
        self.btn_master_neu      = QPushButton("+ Neu")
        self.btn_master_neu.setObjectName("btn_new_sm")
        self.btn_master_bearbeiten = QPushButton("✎ Bearbeiten")
        self.btn_master_bearbeiten.setObjectName("btn_sm")
        self.btn_master_aktiv    = QPushButton("★ Aktiv")
        self.btn_master_aktiv.setObjectName("btn_master_aktiv")
        self.btn_master_loeschen = QPushButton("✕")
        self.btn_master_loeschen.setObjectName("btn_del_sm")
        for btn in [self.btn_master_neu, self.btn_master_bearbeiten,
                    self.btn_master_aktiv, self.btn_master_loeschen]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            m_btns.addWidget(btn)
        layout.addLayout(m_btns)

        self.btn_master_neu.clicked.connect(self.master_neu_requested)
        self.btn_master_bearbeiten.clicked.connect(self._master_bearbeiten)
        self.btn_master_aktiv.clicked.connect(self._master_aktiv)
        self.btn_master_loeschen.clicked.connect(self._master_loeschen)
        self.master_liste.itemDoubleClicked.connect(self._master_bearbeiten)

        # Trenner
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setProperty("class", "separator")
        layout.addWidget(line)

        # ── Sub-Workflows ──────────────────────────────────────────────────────
        lbl_sub = QLabel("SUB-WORKFLOWS (Funktionsbausteine)")
        lbl_sub.setProperty("class", "lbl_header_dim")
        layout.addWidget(lbl_sub)

        self.workflow_liste = QListWidget()
        self.workflow_liste.setObjectName("workflow_liste")
        layout.addWidget(self.workflow_liste)

        wf_btns = QHBoxLayout()
        wf_btns.setSpacing(4)
        self.btn_wf_neu       = QPushButton("+ Neu")
        self.btn_wf_neu.setObjectName("btn_new_sm")
        self.btn_wf_bearbeiten = QPushButton("✎ Bearbeiten")
        self.btn_wf_bearbeiten.setObjectName("btn_sm")
        self.btn_wf_kopieren   = QPushButton("❐ Kopieren")
        self.btn_wf_kopieren.setObjectName("btn_copy_sm")
        self.btn_wf_loeschen  = QPushButton("✕")
        self.btn_wf_loeschen.setObjectName("btn_del_sm")
        for btn in [self.btn_wf_neu, self.btn_wf_bearbeiten, self.btn_wf_kopieren, self.btn_wf_loeschen]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            wf_btns.addWidget(btn)
        layout.addLayout(wf_btns)

        self.btn_wf_neu.clicked.connect(self.workflow_neu_requested)
        self.btn_wf_bearbeiten.clicked.connect(self._wf_bearbeiten)
        self.btn_wf_kopieren.clicked.connect(self._wf_kopieren)
        self.btn_wf_loeschen.clicked.connect(self._wf_loeschen)
        self.workflow_liste.itemDoubleClicked.connect(self._wf_bearbeiten)

        # Trenner 2
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setProperty("class", "separator")
        layout.addWidget(line2)

        # ── Logik-Netzwerke ───────────────────────────────────────────────────
        lbl_logic = QLabel("LOGIK-NETZWERKE (FUP)")
        lbl_logic.setProperty("class", "lbl_header_dim")
        layout.addWidget(lbl_logic)

        self.logic_liste = QListWidget()
        self.logic_liste.setObjectName("logic_liste")
        self.logic_liste.setFixedHeight(150)
        self.logic_liste.itemDoubleClicked.connect(self._logic_bearbeiten)
        layout.addWidget(self.logic_liste)

        l_btns = QHBoxLayout()
        self.btn_logic_bearbeiten = QPushButton("✎ Netzwerk bearbeiten")
        self.btn_logic_bearbeiten.setObjectName("btn_sm")
        self.btn_logic_bearbeiten.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logic_bearbeiten.clicked.connect(self._logic_bearbeiten)
        l_btns.addWidget(self.btn_logic_bearbeiten)

        self.btn_logic_kopieren = QPushButton("❐ Kopieren")
        self.btn_logic_kopieren.setObjectName("btn_copy_sm")
        self.btn_logic_kopieren.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logic_kopieren.clicked.connect(self._logic_kopieren)
        l_btns.addWidget(self.btn_logic_kopieren)

        self.btn_logic_einfuegen = QPushButton("📋 Einfügen")
        self.btn_logic_einfuegen.setObjectName("btn_paste_sm")
        self.btn_logic_einfuegen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logic_einfuegen.clicked.connect(self._logic_einfuegen)
        l_btns.addWidget(self.btn_logic_einfuegen)

        layout.addLayout(l_btns)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def aktualisieren(self, master_workflows: dict, aktiver_master: str, workflows: dict):
        self._master_aktualisieren(master_workflows, aktiver_master)
        self._workflows_aktualisieren(workflows)
        self._logic_aktualisieren(master_workflows, workflows)

    def _master_aktualisieren(self, master_workflows: dict, aktiver_master: str):
        self.master_liste.clear()
        if not master_workflows:
            item = QListWidgetItem("  (Keine Master-Flows)")
            item.setForeground(QColor("#555555"))
            self.master_liste.addItem(item)
            return
        for name in sorted(master_workflows.keys()):
            ist_aktiv = (name == aktiver_master)
            prefix = " ★ " if ist_aktiv else "   "
            item = QListWidgetItem(f"{prefix}{name}")
            if ist_aktiv:
                item.setForeground(QColor("#ffca28"))
            self.master_liste.addItem(item)

    def _workflows_aktualisieren(self, workflows: dict):
        self.workflow_liste.clear()
        if not workflows:
            item = QListWidgetItem("  (Keine Workflows)")
            item.setForeground(QColor("#555555"))
            self.workflow_liste.addItem(item)
            return
        for name in sorted(workflows.keys()):
            graph = workflows[name]
            n_nodes = len(graph.get("nodes", []))
            n_conn  = len(graph.get("connections", []))
            self.workflow_liste.addItem(f"  {name}  ({n_nodes} Nodes, {n_conn} Links)")

    def _logic_aktualisieren(self, master_workflows: dict, workflows: dict):
        self.logic_liste.clear()
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
                                self.logic_liste.addItem(f"  {wf_name} → {port}")

        scan_wf(master_workflows, "master")
        scan_wf(workflows, "sub")

        if not self._logic_data:
            item = QListWidgetItem("  (Keine Netzwerke gefunden)")
            item.setForeground(QColor("#555555"))
            self.logic_liste.addItem(item)

    # ── Hilfsmethoden ──────────────────────────────────────────────────────────

    def _get_master_name(self) -> str | None:
        item = self.master_liste.currentItem()
        if not item:
            return None
        text = item.text().strip()
        if text.startswith("("):
            return None
        # Icons und Leerzeichen am Anfang entfernen
        for icon in ["★", " "]:
            text = text.replace(icon, "")
        return text.strip()

    def _get_workflow_name(self) -> str | None:
        item = self.workflow_liste.currentItem()
        if not item:
            return None
        text = item.text().strip()
        if text.startswith("("):
            return None
        # Name ist alles vor dem doppelten Leerzeichen oder der Klammer
        if "  (" in text:
            return text.split("  (")[0].strip()
        if " (" in text:
            return text.split(" (")[0].strip()
        return text

    def _master_bearbeiten(self):
        name = self._get_master_name()
        if name:
            self.master_bearbeiten_requested.emit(name)

    def _master_aktiv(self):
        name = self._get_master_name()
        if name:
            self.master_aktiv_requested.emit(name)

    def _master_loeschen(self):
        name = self._get_master_name()
        if name:
            self.master_loeschen_requested.emit(name)

    def _wf_bearbeiten(self):
        name = self._get_workflow_name()
        if name:
            self.workflow_bearbeiten_requested.emit(name)

    def _wf_kopieren(self):
        name = self._get_workflow_name()
        if name:
            self.workflow_kopieren_requested.emit(name)

    def _wf_loeschen(self):
        name = self._get_workflow_name()
        if name:
            self.workflow_loeschen_requested.emit(name)

    def _logic_bearbeiten(self):
        idx = self.logic_liste.currentRow()
        if 0 <= idx < len(self._logic_data):
            self.logic_network_edit_requested.emit(*self._logic_data[idx])

    def _logic_kopieren(self):
        idx = self.logic_liste.currentRow()
        if 0 <= idx < len(self._logic_data):
            # Der 5. Parameter in _logic_data ist der Graph (dict)
            self.logic_network_copy_requested.emit(self._logic_data[idx][4])

    def _logic_einfuegen(self):
        idx = self.logic_liste.currentRow()
        if 0 <= idx < len(self._logic_data):
            # wf_type, wf_name, node_id, port_name
            d = self._logic_data[idx]
            self.logic_network_paste_requested.emit(d[0], d[1], d[2], d[3])
