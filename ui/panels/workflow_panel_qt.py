import lang
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


class WorkflowPanel(QWidget):
    # Signals → Bot-Controller
    master_neu_requested      = pyqtSignal()
    master_bearbeiten_requested = pyqtSignal(str)   # name
    master_loeschen_requested = pyqtSignal(str)     # name
    master_aktiv_requested    = pyqtSignal(str)     # name
    workflow_neu_requested    = pyqtSignal()
    workflow_bearbeiten_requested = pyqtSignal(str) # name
    workflow_loeschen_requested   = pyqtSignal(str) # name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Master-Flows ───────────────────────────────────────────────────────
        lbl_master = QLabel("MASTER-FLOWS (Schrittketten)")
        lbl_master.setStyleSheet("color: #c8a800; font-size: 10px; font-weight: bold;")
        layout.addWidget(lbl_master)

        self.master_liste = QListWidget()
        self.master_liste.setFixedHeight(120)
        self.master_liste.setStyleSheet(
            "QListWidget { font-weight: bold; }"
            "QListWidget::item:selected { background: #1565c0; }"
        )
        layout.addWidget(self.master_liste)

        m_btns = QHBoxLayout()
        m_btns.setSpacing(4)
        self.btn_master_neu      = QPushButton("+ Neu")
        self.btn_master_neu.setStyleSheet("color: #55ff88; background: #1a3a1a; border-color: #1a3a1a;")
        self.btn_master_bearbeiten = QPushButton("✎")
        self.btn_master_aktiv    = QPushButton("★ Aktiv")
        self.btn_master_aktiv.setStyleSheet("color: #ffca28;")
        self.btn_master_loeschen = QPushButton("✕")
        self.btn_master_loeschen.setObjectName("btn_danger")
        for btn in [self.btn_master_neu, self.btn_master_bearbeiten,
                    self.btn_master_aktiv, self.btn_master_loeschen]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            m_btns.addWidget(btn)
        m_btns.addStretch()
        layout.addLayout(m_btns)

        self.btn_master_neu.clicked.connect(self.master_neu_requested)
        self.btn_master_bearbeiten.clicked.connect(self._master_bearbeiten)
        self.btn_master_aktiv.clicked.connect(self._master_aktiv)
        self.btn_master_loeschen.clicked.connect(self._master_loeschen)

        # Trenner
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2a2a2a;")
        layout.addWidget(line)

        # ── Sub-Workflows ──────────────────────────────────────────────────────
        lbl_sub = QLabel("SUB-WORKFLOWS (Funktionsbausteine)")
        lbl_sub.setStyleSheet("color: #666666; font-size: 10px; font-weight: bold;")
        layout.addWidget(lbl_sub)

        self.workflow_liste = QListWidget()
        layout.addWidget(self.workflow_liste)

        wf_btns = QHBoxLayout()
        wf_btns.setSpacing(4)
        self.btn_wf_neu       = QPushButton("+ Neu")
        self.btn_wf_bearbeiten = QPushButton("✎ Bearbeiten")
        self.btn_wf_loeschen  = QPushButton("✕")
        self.btn_wf_loeschen.setObjectName("btn_danger")
        for btn in [self.btn_wf_neu, self.btn_wf_bearbeiten, self.btn_wf_loeschen]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            wf_btns.addWidget(btn)
        wf_btns.addStretch()
        layout.addLayout(wf_btns)

        self.btn_wf_neu.clicked.connect(self.workflow_neu_requested)
        self.btn_wf_bearbeiten.clicked.connect(self._wf_bearbeiten)
        self.btn_wf_loeschen.clicked.connect(self._wf_loeschen)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def aktualisieren(self, master_workflows: dict, aktiver_master: str, workflows: dict):
        self._master_aktualisieren(master_workflows, aktiver_master)
        self._workflows_aktualisieren(workflows)

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

    # ── Hilfsmethoden ──────────────────────────────────────────────────────────

    def _get_master_name(self) -> str | None:
        item = self.master_liste.currentItem()
        if not item:
            return None
        text = item.text().strip()
        if text.startswith("("):
            return None
        return text[3:].strip()  # Präfix "   " oder " ★ " entfernen

    def _get_workflow_name(self) -> str | None:
        item = self.workflow_liste.currentItem()
        if not item:
            return None
        text = item.text().strip()
        if text.startswith("("):
            return None
        return text.split("  (")[0].strip()

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

    def _wf_loeschen(self):
        name = self._get_workflow_name()
        if name:
            self.workflow_loeschen_requested.emit(name)
