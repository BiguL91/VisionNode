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
    QSpinBox, QComboBox, QApplication,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPointF, QRectF, QPoint, QSizeF,
    QMetaObject, Q_ARG, pyqtSlot,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath,
    QPainterPathStroker, QAction, QCursor, QFontMetrics,
)


# ── Visuelle Konstanten (Welt-Koordinaten) ─────────────────────────────────────

NODE_BREITE  = 170
NODE_HOEHE   = 64
TITEL_HOEHE  = 22
PORT_RADIUS  = 8
CANVAS_BG    = "#1a1a1a"
NODE_BG      = "#2a2a2a"

NODE_FARBEN = {
    "start":             "#2ea043",
    "suche":             "#1e88e5",
    "suche_optional":    "#00897b",
    "klick":             "#fb8c00",
    "warten":            "#546e7a",
    "zurueck":           "#8e24aa",
    "home":              "#8e24aa",
    "bedingung":         "#f9a825",
    "call_workflow":     "#673ab7",
    "priority_selector": "#fbc02d",
}

NODE_PORTS = {
    "start":             (False, ["out"]),
    "suche":             (True,  ["success", "failure"]),
    "suche_optional":    (True,  ["out"]),
    "klick":             (True,  ["out", "failure"]),
    "warten":            (True,  ["out"]),
    "zurueck":           (True,  ["out"]),
    "home":              (True,  ["out"]),
    "bedingung":         (True,  ["true", "false"]),
    "call_workflow":     (True,  ["done", "failure"]),
    "priority_selector": (True,  []),
}

PORT_FARBEN = {
    "out":     "#aaaaaa",
    "success": "#4caf50",
    "failure": "#ef5350",
    "true":    "#4caf50",
    "false":   "#ef5350",
    "done":    "#9c27b0",
    "else":    "#ff5722",
    "in":      "#777777",
}

SCALE_MIN = 0.25
SCALE_MAX = 4.0


def _neue_id():
    return uuid.uuid4().hex[:8]


# ── Node-Canvas ────────────────────────────────────────────────────────────────

class NodeCanvas(QWidget):
    """Custom-Paint-Widget für den Workflow-Graphen."""
    node_double_clicked  = pyqtSignal(dict)
    node_right_clicked   = pyqtSignal(dict, QPoint)
    conn_right_clicked   = pyqtSignal(dict, QPoint)
    connection_added     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setObjectName("node_canvas")

        self.nodes:       list[dict] = []
        self.connections: list[dict] = []
        self._scale  = 1.0
        self._tx     = 0.0
        self._ty     = 0.0
        self._sim_zustand:  dict = {}
        self._sim_progress: dict = {}

        self._port_rects: dict[tuple, QRectF] = {}
        self._node_rects: dict[str, QRectF]   = {}
        self._conn_paths: dict[str, tuple]    = {}

        self._drag_node   = None
        self._drag_start  = QPointF()
        self._drag_origin = (0.0, 0.0)
        self._pan_aktiv   = False
        self._pan_last    = QPoint()
        self._conn_drag_aktiv = False
        self._conn_drag_von   = None
        self._conn_drag_pos   = None

    def _cx(self, wx): return wx * self._scale + self._tx
    def _cy(self, wy): return wy * self._scale + self._ty
    def _wx(self, cx): return (cx - self._tx) / self._scale
    def _wy(self, cy): return (cy - self._ty) / self._scale

    def _port_pos(self, node, port_name):
        x  = self._cx(node["x"])
        y  = self._cy(node["y"])
        w  = NODE_BREITE * self._scale
        h  = NODE_HOEHE  * self._scale
        typ = node["typ"]
        if typ == "priority_selector":
            aus_ports = [a.get("port") for a in node.get("ausgaenge", [])] + ["else"]
        else:
            _, aus_ports = NODE_PORTS.get(typ, (True, ["out"]))
        if port_name == "in":
            return QPointF(x, y + h / 2)
        if port_name in aus_ports:
            n    = len(aus_ports)
            i    = aus_ports.index(port_name)
            frac = (i + 1) / (n + 1)
            return QPointF(x + w, y + h * frac)
        return QPointF(x + w / 2, y + h / 2)

    def _bezier_path(self, x1, y1, x2, y2) -> QPainterPath:
        offset = max(40 * self._scale, abs(x2 - x1) * 0.45)
        path = QPainterPath()
        path.moveTo(x1, y1)
        path.cubicTo(x1 + offset, y1, x2 - offset, y2, x2, y2)
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(CANVAS_BG))

        self._port_rects.clear()
        self._node_rects.clear()
        self._conn_paths.clear()

        self._zeichne_gitter(painter)
        self._zeichne_verbindungen(painter)
        self._zeichne_temp_conn(painter)
        self._zeichne_nodes(painter)
        painter.end()

    def _zeichne_gitter(self, p: QPainter):
        w, h    = self.width(), self.height()
        abstand = max(15.0, 30.0 * self._scale)
        off_x   = self._tx % abstand
        off_y   = self._ty % abstand
        pen = QPen(QColor("#1f1f1f"), 1)
        p.setPen(pen)
        x = off_x
        while x < w:
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            x += abstand
        y = off_y
        while y < h:
            p.drawLine(QPointF(0, y), QPointF(w, y))
            y += abstand

    def _zeichne_verbindungen(self, p: QPainter):
        for conn in self.connections:
            nv = next((n for n in self.nodes if n["id"] == conn["von"]), None)
            nz = next((n for n in self.nodes if n["id"] == conn["zu"]),  None)
            if not nv or not nz:
                continue
            p1 = self._port_pos(nv, conn["port_aus"])
            p2 = self._port_pos(nz, conn["port_ein"])
            farbe = QColor(PORT_FARBEN.get(conn["port_aus"], "#aaaaaa"))
            path  = self._bezier_path(p1.x(), p1.y(), p2.x(), p2.y())
            p.setPen(QPen(farbe, max(1, 2 * self._scale)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            # Endpunkt-Kreis
            p.setBrush(QBrush(farbe))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(p2.x(), p2.y()), 4, 4)
            key = f"{conn['von']}_{conn['port_aus']}_{conn['zu']}"
            self._conn_paths[key] = (path, conn)

    def _zeichne_temp_conn(self, p: QPainter):
        if not (self._conn_drag_aktiv and self._conn_drag_von and self._conn_drag_pos):
            return
        p1 = self._port_pos(self._conn_drag_von["node"], self._conn_drag_von["port"])
        farbe = QColor(PORT_FARBEN.get(self._conn_drag_von["port"], "#aaaaaa"))
        p.setPen(QPen(farbe, 2, Qt.PenStyle.DashLine))
        p.drawLine(p1, self._conn_drag_pos)

    def _zeichne_nodes(self, p: QPainter):
        for node in self.nodes:
            self._zeichne_node(p, node)

    def _zeichne_node(self, p: QPainter, node: dict):
        s = self._scale
        x = self._cx(node["x"])
        y = self._cy(node["y"])
        w = NODE_BREITE * s
        h = NODE_HOEHE * s
        th = TITEL_HOEHE * s
        r = max(3.0, PORT_RADIUS * s)
        typ = node["typ"]
        nid = node["id"]
        farbe = QColor(NODE_FARBEN.get(typ, "#555555"))
        if typ == "priority_selector":
            aus_ports = [a.get("port") for a in node.get("ausgaenge", [])] + ["else"]
            hat_ein = True
        else:
            hat_ein, aus_ports = NODE_PORTS.get(typ, (True, ["out"]))
        
        sim = self._sim_zustand.get(nid)
        if sim == "aktiv":
            rahmen = QColor("#f9a825")
            rw = max(3, 3*s)
            koerper = QColor("#2e2a1a")
        elif sim == "success":
            rahmen = QColor("#4caf50")
            rw = max(2, 2*s)
            koerper = QColor("#1a2e1a")
        elif sim == "failure":
            rahmen = QColor("#ef5350")
            rw = max(2, 2*s)
            koerper = QColor("#2e1a1a")
        else:
            rahmen = farbe
            rw = max(1, 2*s)
            koerper = QColor(NODE_BG)

        rect = QRectF(x, y, w, h)
        self._node_rects[nid] = rect
        p.setBrush(QBrush(QColor("#111111")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x+3, y+3, w, h), 3, 3)
        p.setBrush(QBrush(koerper))
        p.setPen(QPen(rahmen, rw))
        p.drawRoundedRect(rect, 3, 3)
        p.setBrush(QBrush(farbe))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x+2, y+2, w-4, th), 2, 2)
        p.setPen(QPen(QColor("white")))
        p.setFont(QFont("Segoe UI", max(6, int(8*s)), QFont.Weight.Bold))
        p.drawText(QRectF(x, y, w, th), Qt.AlignmentFlag.AlignCenter, typ.upper())

        if s > 0.4:
            detail = self._node_detail(node)
            if detail:
                p.setPen(QPen(QColor("#cccccc")))
                p.setFont(QFont("Segoe UI", max(5, int(8*s))))
                p.drawText(QRectF(x+4, y+th, w-8, h-th), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, detail)

        if hat_ein:
            pp = self._port_pos(node, "in")
            rect_p = QRectF(pp.x()-r, pp.y()-r, 2*r, 2*r)
            p.setBrush(QBrush(QColor("#333333")))
            p.setPen(QPen(QColor("#888888"), max(1, 2*s)))
            p.drawEllipse(rect_p)
            self._port_rects[(nid, "in")] = rect_p

        for port in aus_ports:
            pp = self._port_pos(node, port)
            pfarbe = QColor(PORT_FARBEN.get(port, "#aaaaaa"))
            rect_p = QRectF(pp.x()-r, pp.y()-r, 2*r, 2*r)
            p.setBrush(QBrush(pfarbe))
            p.setPen(QPen(QColor("white"), max(1, s)))
            p.drawEllipse(rect_p)
            self._port_rects[(nid, port)] = rect_p
            if len(aus_ports) > 1 and s > 0.5:
                p.setPen(QPen(pfarbe))
                p.setFont(QFont("Segoe UI", max(5, int(7*s))))
                p.drawText(QPointF(pp.x() + r + 2, pp.y() + 4), port)

    def _node_detail(self, node: dict) -> str:
        typ = node.get("typ")
        nid = node.get("id")
        if self._sim_progress.get(nid):
            return self._sim_progress[nid]
        if typ in ("suche", "suche_optional", "klick"):
            tpl = node.get("template", "–")
            to = node.get("timeout")
            return tpl + (f" [{to}s]" if to else "")
        elif typ == "warten":
            return f"{node.get('sekunden', 1.0)} s"
        elif typ == "bedingung":
            return f"{node.get('variable','?')} {node.get('operator','=')} {node.get('wert','0')}"
        elif typ == "call_workflow":
            return f"➔ {node.get('workflow', '–')}"
        return ""

    def _get_port_at(self, pos: QPointF) -> tuple[dict, str, bool] | tuple[None, None, None]:
        fang_radius_sq = 25 * 25
        for node in reversed(self.nodes):
            typ = node["typ"]
            if typ == "priority_selector":
                aus_ports = [a.get("port") for a in node.get("ausgaenge", [])] + ["else"]
            else:
                _, aus_ports = NODE_PORTS.get(typ, (True, ["out"]))
            for p_name in aus_ports:
                pp = self._port_pos(node, p_name)
                dx = pos.x()-pp.x()
                dy = pos.y()-pp.y()
                if (dx*dx + dy*dy) <= fang_radius_sq:
                    return node, p_name, False
            if typ != "start":
                pp = self._port_pos(node, "in")
                dx = pos.x()-pp.x()
                dy = pos.y()-pp.y()
                if (dx*dx + dy*dy) <= fang_radius_sq:
                    return node, "in", True
        return None, None, None

    def mousePressEvent(self, event):
        pos_global = event.globalPosition().toPoint()
        pos_local = self.mapFromGlobal(pos_global)
        pos_f = QPointF(pos_local)
        if event.button() == Qt.MouseButton.RightButton:
            self._rechtsklick(pos_local, pos_global)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            node, p_name, ist_in = self._get_port_at(pos_f)
            if node and not ist_in:
                self._conn_drag_aktiv = True
                self._conn_drag_von = {"node": node, "port": p_name}
                self._conn_drag_pos = pos_f
                self.setCursor(Qt.CursorShape.CrossCursor)
                self.update()
                return
            for node in reversed(self.nodes):
                nx = self._cx(node["x"])
                ny = self._cy(node["y"])
                nw = NODE_BREITE * self._scale
                nh = NODE_HOEHE * self._scale
                if QRectF(nx, ny, nw, nh).contains(pos_f):
                    self._drag_node = node
                    self._drag_start = QPointF(self._wx(pos_f.x()), self._wy(pos_f.y()))
                    self._drag_origin = (node["x"], node["y"])
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.nodes.remove(node)
                    self.nodes.append(node)
                    self.update()
                    return
            self._pan_aktiv = True
            self._pan_last = pos_local
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._conn_drag_aktiv:
            self._conn_drag_pos = pos
            self.update()
            return
        if self._drag_node is not None:
            wx = self._wx(pos.x())
            wy = self._wy(pos.y())
            self._drag_node["x"] = self._drag_origin[0] + (wx - self._drag_start.x())
            self._drag_node["y"] = self._drag_origin[1] + (wy - self._drag_start.y())
            self.update()
            return
        if self._pan_aktiv:
            cur = event.position().toPoint()
            self._tx += cur.x() - self._pan_last.x()
            self._ty += cur.y() - self._pan_last.y()
            self._pan_last = cur
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._conn_drag_aktiv:
                self._conn_drag_abschliessen(QPointF(self.mapFromGlobal(event.globalPosition().toPoint())))
            self._drag_node = None
            self._conn_drag_aktiv = False
            self._conn_drag_von = None
            self._conn_drag_pos = None
            self._pan_aktiv = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseDoubleClickEvent(self, event):
        pos = event.position()
        for nid, nrect in self._node_rects.items():
            if nrect.contains(pos):
                node = next((n for n in self.nodes if n["id"] == nid), None)
                if node:
                    self.node_double_clicked.emit(node)
                    return

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        faktor = 1.12 if delta > 0 else (1 / 1.12)
        neuer = max(SCALE_MIN, min(SCALE_MAX, self._scale * faktor))
        if neuer == self._scale:
            return
        cx, cy = event.position().x(), event.position().y()
        self._tx = cx + (self._tx - cx) * (neuer / self._scale)
        self._ty = cy + (self._ty - cy) * (neuer / self._scale)
        self._scale = neuer
        self.update()

    def _rechtsklick(self, pos: QPoint, global_pos: QPoint):
        pf = QPointF(pos)
        for nid, nrect in self._node_rects.items():
            if nrect.contains(pf):
                node = next((n for n in self.nodes if n["id"] == nid), None)
                if node:
                    self.node_right_clicked.emit(node, global_pos)
                    return
        hit_rect = QRectF(pf.x()-5, pf.y()-5, 10, 10)
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        for key, (path, conn) in self._conn_paths.items():
            if stroker.createStroke(path).intersects(hit_rect):
                self.conn_right_clicked.emit(conn, global_pos)
                return

    def _conn_drag_abschliessen(self, pos: QPointF):
        if self._conn_drag_von is None:
            return
        node, p_name, ist_in = self._get_port_at(pos)
        if node and ist_in and node["id"] != self._conn_drag_von["node"]["id"]:
            self.connections[:] = [c for c in self.connections if not (c["von"] == self._conn_drag_von["node"]["id"] and c["port_aus"] == self._conn_drag_von["port"])]
            self.connections.append({"von": self._conn_drag_von["node"]["id"], "port_aus": self._conn_drag_von["port"], "zu": node["id"], "port_ein": "in"})
            self._template_vererben(self._conn_drag_von["node"], node)
            self.connection_added.emit()

    def _template_vererben(self, von_node, zu_node):
        if von_node.get("typ") in ("suche", "suche_optional") and zu_node.get("typ") == "klick" and not zu_node.get("template"):
            tpl = von_node.get("template", "")
            if tpl:
                zu_node["template"] = tpl


# ── Haupt-Dialog ───────────────────────────────────────────────────────────────

class WorkflowEditorDialogQt(QDialog):
    gespeichert = pyqtSignal(str, dict)
    abgebrochen = pyqtSignal()

    def __init__(self, parent, bot, name: str, graph: dict, callback=None):
        super().__init__(parent)
        self.bot = bot
        self._callback = callback
        self.nodes = [dict(n) for n in graph.get("nodes", [])]
        self.connections = [dict(c) for c in graph.get("connections", [])]
        if not self.nodes:
            self.nodes.append({"id": _neue_id(), "typ": "start", "x": 80, "y": 240})
        self._sim_aktiv = False
        self._sim_zustand = {}
        self._sim_progress = {}
        self.setWindowTitle("Workflow Editor")
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
        tb_lay.addWidget(self._name_edit)
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setProperty("class", "separator")
        tb_lay.addWidget(sep1)
        lbl = QLabel("+ Node:")
        lbl.setProperty("class", "lbl_dim")
        tb_lay.addWidget(lbl)
        typen = [("Start","start"),("Suche","suche"),("Optional","suche_optional"),("Klick","klick"),("Warten","warten"),("Zurück","zurueck"),("Home","home"),("Bedingung","bedingung"),("Workflow","call_workflow"),("Selector","priority_selector")]
        for label, typ in typen:
            btn = QPushButton(label)
            btn.setObjectName("btn_add_node")
            btn.setStyleSheet(f"background-color: {NODE_FARBEN.get(typ, '#555555')};")
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
        self._canvas._sim_zustand = self._sim_zustand
        self._canvas._sim_progress = self._sim_progress
        self._canvas.update()
        self._status_aktualisieren()

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
        elif typ == "warten":
            node["sekunden"] = 2.0
        elif typ == "bedingung":
            node["variable"] = ""
            node["operator"] = ">"
            node["wert"] = "0"
        elif typ == "priority_selector":
            node["ausgaenge"] = [{"port": "Prio 1", "variable": "", "operator": "=", "wert": "true", "cooldown": 0, "max_runs": 0}]
        self.nodes.append(node)
        self._sync_canvas()

    def _node_loeschen(self, node: dict):
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
        menu.addAction(f"Node löschen ({node['typ']})", lambda: self._node_loeschen(node))
        menu.addSeparator()
        menu.addAction("Parameter bearbeiten", lambda: self._node_parameter_editieren(node))
        menu.exec(global_pos)

    def _verbindung_kontext_menu(self, conn: dict, global_pos: QPoint):
        menu = QMenu(self)
        menu.addAction("Verbindung löschen", lambda: self._verbindung_loeschen(conn))
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
        elif typ == "warten":
            sp = QDoubleSpinBox()
            sp.setRange(0.1, 300.0)
            sp.setSingleStep(0.5)
            sp.setValue(float(node.get("sekunden", 2.0)))
            sp.setProperty("class", "input_dark")
            add_row("Sekunden:", "sekunden", sp)
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
                elif key in ("template", "variable", "workflow"):
                    val = w.text()
                    node[key] = "" if val == "Bitte wählen..." else val
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
        dlg.exec()

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
                def _edit_logic(a_obj=aus, b=btn_logic):
                    from ui.dialogs.logic_editor_qt import LogicEditorDialogQt
                    g = a_obj.get("logic_graph") or {"nodes": [], "connections": []}
                    dlg2 = LogicEditorDialogQt(
                        name=a_obj.get("port", "Port"), graph=g,
                        game_states=self.bot.app.state.game_states,
                        templates=list(self.bot.template_engine.templates.keys()),
                        ocr_vars={"global": self.bot.app.state.ocr_values, "template": self.bot.app.state.template_ocr_values},
                        parent=parent_dlg, bot=self.bot)
                    dlg2.gespeichert.connect(lambda ng: (a_obj.__setitem__("logic_graph", ng), b.setText("★ Netzwerk")))
                    dlg2.exec()
                btn_logic.clicked.connect(_edit_logic)
                c_sp = QDoubleSpinBox()
                c_sp.setRange(0, 3600)
                c_sp.setValue(float(aus.get("cooldown", 0)))
                c_sp.setFixedWidth(70)
                c_sp.setProperty("class", "input_dark")
                m_sp = QSpinBox()
                m_sp.setRange(0, 9999)
                m_sp.setValue(int(aus.get("max_runs", 0)))
                m_sp.setFixedWidth(70)
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
            node["ausgaenge"] = [{"port": p.text(), "cooldown": c.value(), "max_runs": m.value(), "logic_graph": a.get("logic_graph")} for (p,c,m,a) in rows_widgets]
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
                baum["" if p == name else p].append(name)
            for s_name, s in settings.items():
                if s.get("typ") not in ("aktiv_gruppe", "passiv_gruppe") or s.get("kategorie", "workflow") != kat:
                    continue
                alle_keys.add(s_name)
                p = s.get("gruppe", "")
                if s_name not in baum["" if p == s_name else p]:
                    baum["" if p == s_name else p].append(s_name)
            if not alle_keys:
                submenu.addAction("(keine Einträge)").setEnabled(False)
                return
            ex_gr = {k for k in alle_keys if settings.get(k, {}).get("typ") in ("aktiv_gruppe", "passiv_gruppe")}
            for p in list(baum.keys()):
                if p != "" and p not in ex_gr:
                    baum[""].extend(baum.pop(p))
            def render(pfad, m: QMenu):
                items = sorted(baum.get(pfad, []), key=lambda x: (settings.get(x, {}).get("typ") not in ("aktiv_gruppe", "passiv_gruppe"), x.lower()))
                for name in items:
                    s = settings.get(name, {})
                    typ = s.get("typ", "template")
                    if typ == "aktiv_gruppe":
                        sub = m.addMenu(f"★ {name}")
                        sub.addAction(f"Auswählen: {name}", lambda n=name: on_selected_callback(n))
                        sub.addSeparator()
                        render(name, sub)
                    elif typ == "passiv_gruppe":
                        sub = m.addMenu(f"📦 {name}")
                        render(name, sub)
                        if sub.isEmpty():
                            sub.addAction("(leer)").setEnabled(False)
                    else:
                        m.addAction(name, lambda n=name: on_selected_callback(n))
            render("", submenu)
        wf = menu.addMenu("🔄 Workflow")
        _fill_kat(wf, "workflow")
        st = menu.addMenu("🚩 State")
        _fill_kat(st, "state")
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
            
            port = self.bot.workflow_engine._node_ausfuehren(
                node, self._sim_engine, m_func, ocr_func=o_func,
                log_func=self._sim_log, laeuft_func=lambda: self._sim_aktiv)
            
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
                QTimer.singleShot(400, lambda: QMetaObject.invokeMethod(self, "_simulation_fertig", Qt.ConnectionType.QueuedConnection))
            else:
                QTimer.singleShot(300, lambda: QMetaObject.invokeMethod(self, "_simulation_schritt_gui", Qt.ConnectionType.QueuedConnection, Q_ARG(dict, next_n)))
        
        threading.Thread(target=run, daemon=True).start()

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
            dlg = QMessageBox(self.parent)
            dlg.setWindowTitle(titel)
            dlg.setText(msg)
            b_sim = dlg.addButton("Simulieren", QMessageBox.ButtonRole.NoRole)
            b_adb = dlg.addButton("ADB", QMessageBox.ButtonRole.YesRole)
            b_ab = dlg.addButton("Stop", QMessageBox.ButtonRole.RejectRole)
            dlg.exec()
            c = dlg.clickedButton()
            if c == b_adb:
                return "adb"
            elif c == b_ab:
                return "stop"
            return "sim"
        
        def auf_template_warten(self, t, mf, to=10, iv=0.3, lf=None, laf=None):
            return self.real.auf_template_warten(t, mf, to, iv, log_func=lf, laeuft_func=laf)
        
        def template_tippen(self, t, m, lf=None):
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
