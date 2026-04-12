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
    QMetaObject, Q_ARG,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath,
    QPainterPathStroker, QAction, QCursor, QFontMetrics,
)


# ── Visuelle Konstanten (Welt-Koordinaten) ─────────────────────────────────────

NODE_BREITE  = 170
NODE_HOEHE   = 64
TITEL_HOEHE  = 22
PORT_RADIUS  = 7
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
    """Custom-Paint-Widget für den Workflow-Graphen.
    Signals: node_double_clicked, node_right_clicked, conn_right_clicked,
             connection_added
    """
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
        self.setStyleSheet(f"background: {CANVAS_BG};")

        self.nodes:       list[dict] = []
        self.connections: list[dict] = []
        self._scale  = 1.0
        self._tx     = 0.0
        self._ty     = 0.0
        self._sim_zustand:  dict = {}
        self._sim_progress: dict = {}

        # Hit-Test-Cache (aktualisiert in paintEvent)
        self._port_rects: dict[tuple, QRectF] = {}   # (nid, port) → QRectF
        self._node_rects: dict[str, QRectF]   = {}   # nid → QRectF
        self._conn_paths: dict[str, tuple]    = {}   # conn_key → (QPainterPath, conn)

        # Drag-Zustand
        self._drag_node   = None
        self._drag_start  = QPointF()
        self._drag_origin = (0.0, 0.0)
        self._pan_aktiv   = False
        self._pan_last    = QPoint()
        self._conn_drag_aktiv = False
        self._conn_drag_von   = None   # {"node": …, "port": …}
        self._conn_drag_pos   = None   # QPointF

    # ── Transform ──────────────────────────────────────────────────────────────

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

    # ── Paint ──────────────────────────────────────────────────────────────────

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

            pen = QPen(farbe, max(1, 2 * self._scale))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

            # Endpunkt-Kreis
            r = 4
            p.setBrush(QBrush(farbe))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(p2.x(), p2.y()), r, r)

            key = f"{conn['von']}_{conn['port_aus']}_{conn['zu']}"
            self._conn_paths[key] = (path, conn)

    def _zeichne_temp_conn(self, p: QPainter):
        if not (self._conn_drag_aktiv and self._conn_drag_von and self._conn_drag_pos):
            return
        von_node = self._conn_drag_von["node"]
        von_port = self._conn_drag_von["port"]
        p1 = self._port_pos(von_node, von_port)
        p2 = self._conn_drag_pos
        farbe = QColor(PORT_FARBEN.get(von_port, "#aaaaaa"))
        pen = QPen(farbe, 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(p1, p2)

    def _zeichne_nodes(self, p: QPainter):
        for node in self.nodes:
            self._zeichne_node(p, node)

    def _zeichne_node(self, p: QPainter, node: dict):
        s   = self._scale
        x   = self._cx(node["x"])
        y   = self._cy(node["y"])
        w   = NODE_BREITE * s
        h   = NODE_HOEHE  * s
        th  = TITEL_HOEHE * s
        r   = max(3.0, PORT_RADIUS * s)
        typ  = node["typ"]
        nid  = node["id"]
        farbe = QColor(NODE_FARBEN.get(typ, "#555555"))

        if typ == "priority_selector":
            aus_ports = [a.get("port") for a in node.get("ausgaenge", [])] + ["else"]
            hat_ein   = True
        else:
            hat_ein, aus_ports = NODE_PORTS.get(typ, (True, ["out"]))

        sim = self._sim_zustand.get(nid)
        if sim == "aktiv":
            rahmen = QColor("#f9a825"); rw = max(3, 3*s); koerper = QColor("#2e2a1a")
        elif sim == "success":
            rahmen = QColor("#4caf50"); rw = max(2, 2*s); koerper = QColor("#1a2e1a")
        elif sim == "failure":
            rahmen = QColor("#ef5350"); rw = max(2, 2*s); koerper = QColor("#2e1a1a")
        else:
            rahmen = farbe; rw = max(1, 2*s); koerper = QColor(NODE_BG)

        rect = QRectF(x, y, w, h)
        self._node_rects[nid] = rect

        # Schatten
        p.setBrush(QBrush(QColor("#111111")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x+3, y+3, w, h), 3, 3)

        # Körper
        p.setBrush(QBrush(koerper))
        p.setPen(QPen(rahmen, rw))
        p.drawRoundedRect(rect, 3, 3)

        # Titelstreifen
        p.setBrush(QBrush(farbe))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x+2, y+2, w-4, th), 2, 2)

        # Titel-Text
        fs = max(6, int(8 * s))
        p.setPen(QPen(QColor("white")))
        p.setFont(QFont("Segoe UI", fs, QFont.Weight.Bold))
        p.drawText(QRectF(x, y, w, th), Qt.AlignmentFlag.AlignCenter, typ.upper())

        # Parameter-Text
        if s > 0.4:
            detail = self._node_detail(node)
            if detail:
                p.setPen(QPen(QColor("#cccccc")))
                p.setFont(QFont("Segoe UI", max(5, int(8*s))))
                p.drawText(QRectF(x+4, y+th, w-8, h-th),
                           Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, detail)

        # Eingangs-Port links
        if hat_ein:
            pp = self._port_pos(node, "in")
            rect_p = QRectF(pp.x()-r, pp.y()-r, 2*r, 2*r)
            p.setBrush(QBrush(QColor("#333333")))
            p.setPen(QPen(QColor("#888888"), max(1, 2*s)))
            p.drawEllipse(rect_p)
            self._port_rects[(nid, "in")] = rect_p

        # Ausgangs-Ports rechts
        for port in aus_ports:
            pp    = self._port_pos(node, port)
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
            to  = node.get("timeout")
            return tpl + (f"  [{to}s]" if to else "")
        elif typ == "warten":
            return f"{node.get('sekunden', 1.0)} s"
        elif typ == "bedingung":
            return f"{node.get('variable','?')} {node.get('operator','=')} {node.get('wert','0')}"
        elif typ == "call_workflow":
            return f"➔ {node.get('workflow', '–')}"
        return ""

    # ── Mouse Events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.position()

        if event.button() == Qt.MouseButton.RightButton:
            self._rechtsklick(pos.toPoint(), event.globalPosition().toPoint())
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # Ausgangs-Port → Verbindung starten
            r = max(PORT_RADIUS, PORT_RADIUS * self._scale) + 4
            hit_rect = QRectF(pos.x()-r, pos.y()-r, 2*r, 2*r)
            for (nid, port), prect in self._port_rects.items():
                if port != "in" and prect.intersects(hit_rect):
                    node = next((n for n in self.nodes if n["id"] == nid), None)
                    if node:
                        self._conn_drag_aktiv = True
                        self._conn_drag_von   = {"node": node, "port": port}
                        self._conn_drag_pos   = pos
                        self.setCursor(Qt.CursorShape.CrossCursor)
                        return

            # Node → Drag starten
            for nid, nrect in self._node_rects.items():
                if nrect.contains(pos):
                    node = next((n for n in self.nodes if n["id"] == nid), None)
                    if node:
                        self._drag_node   = node
                        self._drag_start  = QPointF(self._wx(pos.x()), self._wy(pos.y()))
                        self._drag_origin = (node["x"], node["y"])
                        self.setCursor(Qt.CursorShape.ClosedHandCursor)
                        return

            # Fläche → Pan
            self._pan_aktiv = True
            self._pan_last  = event.position().toPoint()
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
            dx = cur.x() - self._pan_last.x()
            dy = cur.y() - self._pan_last.y()
            self._pan_last = cur
            self._tx += dx
            self._ty += dy
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._conn_drag_aktiv:
                self._conn_drag_abschliessen(event.position())
            self._drag_node   = None
            self._conn_drag_aktiv = False
            self._conn_drag_von   = None
            self._conn_drag_pos   = None
            self._pan_aktiv       = False
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
        delta  = event.angleDelta().y()
        faktor = 1.12 if delta > 0 else (1 / 1.12)
        neuer  = max(SCALE_MIN, min(SCALE_MAX, self._scale * faktor))
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
        # Verbindung treffen (Toleranz 8px)
        hit_rect = QRectF(pf.x()-5, pf.y()-5, 10, 10)
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        for key, (path, conn) in self._conn_paths.items():
            if stroker.createStroke(path).intersects(hit_rect):
                self.conn_right_clicked.emit(conn, global_pos)
                return

    def _conn_drag_abschliessen(self, pos: QPointF):
        von = self._conn_drag_von
        if von is None:
            return
        r = max(PORT_RADIUS, PORT_RADIUS * self._scale) + 5
        hit_rect = QRectF(pos.x()-r, pos.y()-r, 2*r, 2*r)
        for (nid, port), prect in self._port_rects.items():
            if port == "in" and prect.intersects(hit_rect):
                ziel = next((n for n in self.nodes if n["id"] == nid), None)
                if ziel and ziel["id"] != von["node"]["id"]:
                    # Bestehende Verbindung von selben Port entfernen
                    self.connections = [
                        c for c in self.connections
                        if not (c["von"] == von["node"]["id"] and c["port_aus"] == von["port"])
                    ]
                    self.connections.append({
                        "von":      von["node"]["id"],
                        "port_aus": von["port"],
                        "zu":       nid,
                        "port_ein": "in",
                    })
                    self._template_vererben(von["node"], ziel)
                    self.connection_added.emit()
                return

    def _template_vererben(self, von_node, zu_node):
        if von_node.get("typ") not in ("suche", "suche_optional"):
            return
        if zu_node.get("typ") != "klick":
            return
        if zu_node.get("template"):
            return
        tpl = von_node.get("template", "")
        if tpl:
            zu_node["template"] = tpl


# ── Haupt-Dialog ───────────────────────────────────────────────────────────────

class WorkflowEditorDialogQt(QDialog):
    """Visueller Workflow-Editor (Qt). Ersetzt WorkflowEditorDialog (tkinter).

    Signals:
        gespeichert(str, dict)  — name, graph
        abgebrochen()
    """
    gespeichert = pyqtSignal(str, dict)
    abgebrochen = pyqtSignal()

    def __init__(self, parent, bot, name: str, graph: dict, callback=None):
        super().__init__(parent)
        self.bot      = bot
        self._callback = callback  # Legacy: callback(name, graph) | callback(None, None)

        self.nodes       = [dict(n) for n in graph.get("nodes", [])]
        self.connections = [dict(c) for c in graph.get("connections", [])]
        if not self.nodes:
            self.nodes.append({"id": _neue_id(), "typ": "start", "x": 80, "y": 240})

        self._sim_aktiv    = False
        self._sim_zustand  = {}
        self._sim_progress = {}

        self.setWindowTitle("Workflow Editor")
        self.resize(960, 640)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._setup_ui(name)
        self._sync_canvas()

    # ── UI Aufbau ──────────────────────────────────────────────────────────────

    def _setup_ui(self, name: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # ── Toolbar ────────────────────────────────────────────────────────────
        tb = QFrame()
        tb.setStyleSheet("background: #2d2d2d;")
        tb_lay = QHBoxLayout(tb)
        tb_lay.setContentsMargins(4, 4, 4, 4)
        tb_lay.setSpacing(6)

        tb_lay.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(name)
        self._name_edit.setFixedWidth(160)
        tb_lay.addWidget(self._name_edit)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #444444;")
        tb_lay.addWidget(sep1)

        lbl = QLabel("+ Node:")
        lbl.setStyleSheet("color: #666666; font-size: 8pt;")
        tb_lay.addWidget(lbl)

        typen = [
            ("Start",    "start"),
            ("Suche",    "suche"),
            ("Optional", "suche_optional"),
            ("Klick",    "klick"),
            ("Warten",   "warten"),
            ("Zurück",   "zurueck"),
            ("Home",     "home"),
            ("Bedingung","bedingung"),
            ("Workflow", "call_workflow"),
            ("Selector", "priority_selector"),
        ]
        for label, typ in typen:
            farbe = NODE_FARBEN.get(typ, "#555555")
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"background: {farbe}; color: white; font-size: 8pt; padding: 2px 7px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=typ: self._node_hinzufuegen(t))
            tb_lay.addWidget(btn)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #444444;")
        tb_lay.addWidget(sep2)

        self._sim_btn = QPushButton("▶ Simulieren")
        self._sim_btn.setStyleSheet(
            "background: #1565c0; color: white; font-weight: bold; font-size: 8pt; padding: 2px 10px;")
        self._sim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sim_btn.clicked.connect(self._simulation_toggle)
        tb_lay.addWidget(self._sim_btn)

        tb_lay.addStretch()
        root.addWidget(tb)

        # ── Canvas ─────────────────────────────────────────────────────────────
        self._canvas = NodeCanvas()
        self._canvas.node_double_clicked.connect(self._node_parameter_editieren)
        self._canvas.node_right_clicked.connect(self._node_kontext_menu)
        self._canvas.conn_right_clicked.connect(self._verbindung_kontext_menu)
        self._canvas.connection_added.connect(self._sync_canvas)
        root.addWidget(self._canvas, stretch=1)

        # ── Log-Panel ──────────────────────────────────────────────────────────
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(90)
        self._log.setStyleSheet(
            "background: #111111; color: #cccccc; font-family: Consolas; font-size: 8pt; border: none;")
        root.addWidget(self._log)

        # ── Status + Buttons ───────────────────────────────────────────────────
        bar = QFrame()
        bar.setStyleSheet("background: #2d2d2d;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(4, 4, 4, 4)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #666666; font-size: 8pt;")
        bar_lay.addWidget(self._status_lbl)
        bar_lay.addStretch()

        btn_ab = QPushButton("Abbrechen")
        btn_ab.setObjectName("btn_icon")
        btn_ab.clicked.connect(self._abbrechen)
        bar_lay.addWidget(btn_ab)

        btn_sp = QPushButton("Speichern")
        btn_sp.setObjectName("btn_success")
        btn_sp.clicked.connect(self._speichern)
        bar_lay.addWidget(btn_sp)

        root.addWidget(bar)
        self._status_aktualisieren()

    # ── Sync ───────────────────────────────────────────────────────────────────

    def _sync_canvas(self):
        self._canvas.nodes       = self.nodes
        self._canvas.connections = self.connections
        self._canvas._sim_zustand  = self._sim_zustand
        self._canvas._sim_progress = self._sim_progress
        self._canvas.update()
        self._status_aktualisieren()

    # ── Node-Verwaltung ────────────────────────────────────────────────────────

    def _node_hinzufuegen(self, typ: str):
        w  = max(self._canvas.width(), 300)
        h  = max(self._canvas.height(), 200)
        off = (len(self.nodes) % 8) * 22
        wx = self._canvas._wx(w / 2) - NODE_BREITE / 2 + off
        wy = self._canvas._wy(h / 2) - NODE_HOEHE  / 2 + off
        node = {"id": _neue_id(), "typ": typ, "x": wx, "y": wy}
        if typ in ("suche", "suche_optional"):
            node["template"] = ""; node["timeout"] = 10
        elif typ == "klick":
            node["template"] = ""
        elif typ == "warten":
            node["sekunden"] = 2.0
        elif typ == "bedingung":
            node["variable"] = ""; node["operator"] = ">"; node["wert"] = "0"
        elif typ == "priority_selector":
            node["ausgaenge"] = [
                {"port": "Prio 1", "variable": "", "operator": "=",
                 "wert": "true", "cooldown": 0, "max_runs": 0}
            ]
        self.nodes.append(node)
        self._sync_canvas()

    def _node_loeschen(self, node: dict):
        nid = node["id"]
        self.nodes       = [n for n in self.nodes if n["id"] != nid]
        self.connections = [c for c in self.connections
                            if c["von"] != nid and c["zu"] != nid]
        self._sync_canvas()

    def _verbindung_loeschen(self, conn: dict):
        if conn in self.connections:
            self.connections.remove(conn)
        self._sync_canvas()

    def _node_kontext_menu(self, node: dict, global_pos: QPoint):
        menu = QMenu(self)
        menu.addAction(
            f"Node löschen ({node['typ']})",
            lambda: self._node_loeschen(node))
        menu.addSeparator()
        menu.addAction(
            "Parameter bearbeiten",
            lambda: self._node_parameter_editieren(node))
        menu.exec(global_pos)

    def _verbindung_kontext_menu(self, conn: dict, global_pos: QPoint):
        menu = QMenu(self)
        menu.addAction("Verbindung löschen", lambda: self._verbindung_loeschen(conn))
        menu.exec(global_pos)

    # ── Parameter-Editor ───────────────────────────────────────────────────────

    def _node_parameter_editieren(self, node: dict):
        typ = node.get("typ")
        if typ in ("start", "zurueck", "home"):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{typ.upper()} – Parameter")
        dlg.setStyleSheet("background: #2d2d2d;")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dlg.setMinimumWidth(420)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(6)
        felder: dict = {}

        def add_row(label, key, widget):
            form.addRow(QLabel(label), widget)
            felder[key] = widget

        if typ in ("suche", "suche_optional", "klick"):
            tpl_btn = self._template_picker_btn(node.get("template", ""), dlg)
            add_row("Template:", "template", tpl_btn)
            if typ in ("suche", "suche_optional"):
                sp = QSpinBox()
                sp.setRange(1, 300); sp.setValue(int(node.get("timeout", 10)))
                sp.setStyleSheet("background: #1a1a1a; color: white;")
                add_row("Timeout (s):", "timeout", sp)

        elif typ == "warten":
            sp = QDoubleSpinBox()
            sp.setRange(0.1, 300.0); sp.setSingleStep(0.5)
            sp.setValue(float(node.get("sekunden", 2.0)))
            sp.setStyleSheet("background: #1a1a1a; color: white;")
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
                rb.setStyleSheet("color: #cccccc;")
                rb.toggled.connect(lambda chk, o=op: op_selected.__setitem__(0, o) if chk else None)
                op_group.addButton(rb)
                op_lay.addWidget(rb)
            felder["operator"] = op_selected
            add_row("Operator:", "operator_widget", op_widget)

            wert_edit = QLineEdit(str(node.get("wert", "0")))
            wert_edit.setStyleSheet("background: #1a1a1a; color: white;")
            add_row("Wert:", "wert", wert_edit)

        elif typ == "call_workflow":
            wf_btn = self._workflow_picker_btn(node.get("workflow", ""), dlg)
            add_row("Workflow:", "workflow", wf_btn)

        elif typ == "priority_selector":
            self._selector_editor(dlg, lay, node)
            return  # Eigene Button-Leiste

        lay.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def anwenden():
            for key, w in felder.items():
                if key == "operator":
                    node["operator"] = w[0]
                elif key == "template":
                    node["template"] = w.text()
                elif key == "variable":
                    node["variable"] = w.text()
                elif key == "workflow":
                    node["workflow"] = w.text()
                elif isinstance(w, QSpinBox):
                    node[key] = w.value()
                elif isinstance(w, QDoubleSpinBox):
                    node[key] = w.value()
                elif isinstance(w, QLineEdit):
                    node[key] = w.text().strip()
            dlg.accept()
            self._sync_canvas()

        btn_ab = QPushButton("Abbrechen"); btn_ab.setObjectName("btn_icon")
        btn_ok = QPushButton("Anwenden");  btn_ok.setObjectName("btn_success")
        btn_ab.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(anwenden)
        btn_row.addWidget(btn_ab); btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)
        dlg.exec()

    def _selector_editor(self, parent_dlg: QDialog, lay: QVBoxLayout, node: dict):
        """Spezieller Editor für priority_selector."""
        ausgaenge_liste = [dict(a) for a in node.get("ausgaenge", [])]

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: #1a1a1a; border: none;")
        scroll.setMinimumHeight(200)
        container = QWidget()
        container.setStyleSheet("background: #1a1a1a;")
        c_lay = QVBoxLayout(container)
        scroll.setWidget(container)
        lay.addWidget(scroll)

        rows_widgets = []

        def rebuild():
            for w in container.findChildren(QWidget):
                w.deleteLater()
            # Need fresh layout items
            while c_lay.count():
                c_lay.takeAt(0)
            rows_widgets.clear()
            for i, aus in enumerate(ausgaenge_liste):
                row = QWidget()
                row.setStyleSheet("background: #2d2d2d;")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(4, 2, 4, 2)

                p_edit = QLineEdit(aus.get("port", f"Prio {i+1}"))
                p_edit.setFixedWidth(100)
                p_edit.setStyleSheet("background: #1a1a1a; color: white; font-weight: bold;")

                has_logic = aus.get("logic_graph")
                btn_logic = QPushButton("★ Netzwerk" if has_logic else "🛠 Netzwerk")
                btn_logic.setStyleSheet("color: #55ff88; background: #444; font-size: 8pt;")
                def _edit_logic(a_obj=aus, b=btn_logic):
                    from ui.dialogs.logic_editor_qt import LogicEditorDialogQt
                    g = a_obj.get("logic_graph") or {"nodes": [], "connections": []}
                    def on_save(new_g):
                        a_obj["logic_graph"] = new_g
                        b.setText("★ Netzwerk")
                    dlg2 = LogicEditorDialogQt(
                        name=a_obj.get("port", "Port"), graph=g,
                        game_states={}, templates=[], ocr_vars={}, parent=parent_dlg)
                    dlg2.gespeichert.connect(on_save)
                    dlg2.exec()
                btn_logic.clicked.connect(_edit_logic)

                c_sp = QDoubleSpinBox()
                c_sp.setRange(0, 3600); c_sp.setValue(float(aus.get("cooldown", 0)))
                c_sp.setFixedWidth(70); c_sp.setStyleSheet("background: #1a1a1a; color: #fbc02d;")

                m_sp = QSpinBox()
                m_sp.setRange(0, 9999); m_sp.setValue(int(aus.get("max_runs", 0)))
                m_sp.setFixedWidth(70); m_sp.setStyleSheet("background: #1a1a1a; color: #ff7043;")

                btn_up = QPushButton("↑"); btn_up.setFixedWidth(28)
                btn_dn = QPushButton("↓"); btn_dn.setFixedWidth(28)
                btn_dl = QPushButton("✕"); btn_dl.setFixedWidth(28)
                btn_dl.setStyleSheet("background: #b71c1c; color: white;")

                def _up(idx=i):
                    if idx > 0:
                        ausgaenge_liste[idx], ausgaenge_liste[idx-1] = ausgaenge_liste[idx-1], ausgaenge_liste[idx]
                        rebuild()
                def _dn(idx=i):
                    if idx < len(ausgaenge_liste)-1:
                        ausgaenge_liste[idx], ausgaenge_liste[idx+1] = ausgaenge_liste[idx+1], ausgaenge_liste[idx]
                        rebuild()
                def _dl(idx=i):
                    if len(ausgaenge_liste) > 1:
                        ausgaenge_liste.pop(idx); rebuild()

                btn_up.clicked.connect(_up); btn_dn.clicked.connect(_dn); btn_dl.clicked.connect(_dl)

                rl.addWidget(p_edit); rl.addWidget(btn_logic)
                rl.addWidget(QLabel("Wait:")); rl.addWidget(c_sp)
                rl.addWidget(QLabel("Limit:")); rl.addWidget(m_sp)
                rl.addWidget(btn_up); rl.addWidget(btn_dn); rl.addWidget(btn_dl)
                c_lay.addWidget(row)
                rows_widgets.append((p_edit, c_sp, m_sp, aus))

        rebuild()

        btn_add = QPushButton("+ Ausgang hinzufügen")
        btn_add.setStyleSheet("background: #1a3a1a; color: #55ff88; padding: 5px;")
        def _add():
            ausgaenge_liste.append({"port": f"Prio {len(ausgaenge_liste)+1}",
                                    "cooldown": 0, "max_runs": 0, "logic_graph": None})
            rebuild()
        btn_add.clicked.connect(_add)
        lay.addWidget(btn_add)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def anwenden():
            neue_aus = []
            for (p_edit, c_sp, m_sp, a_obj) in rows_widgets:
                neue_aus.append({
                    "port":       p_edit.text(),
                    "cooldown":   c_sp.value(),
                    "max_runs":   m_sp.value(),
                    "logic_graph": a_obj.get("logic_graph"),
                })
            node["ausgaenge"] = neue_aus
            gültige = [a["port"] for a in neue_aus] + ["else"]
            self.connections = [
                c for c in self.connections
                if not (c["von"] == node["id"] and c["port_aus"] not in gültige)
            ]
            parent_dlg.accept()
            self._sync_canvas()

        btn_ab = QPushButton("Abbrechen"); btn_ab.setObjectName("btn_icon")
        btn_ok = QPushButton("Anwenden");  btn_ok.setObjectName("btn_success")
        btn_ab.clicked.connect(parent_dlg.reject)
        btn_ok.clicked.connect(anwenden)
        btn_row.addWidget(btn_ab); btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

    # ── Picker-Buttons ─────────────────────────────────────────────────────────

    def _template_picker_btn(self, current: str, parent) -> QLineEdit:
        """Gibt ein QLineEdit+Button-Composite zurück (einfachste sichere Lösung)."""
        # In Qt: QPushButton mit QMenu als Dropdown
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        edit = QLineEdit(current)
        edit.setStyleSheet("background: #1a1a1a; color: white;")
        lay.addWidget(edit)

        btn = QPushButton("▾")
        btn.setFixedWidth(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = self._build_template_menu(edit, parent)
        btn.setMenu(menu)
        lay.addWidget(btn)

        # Trick: return the QLineEdit but embed it in a container via a proxy
        # Simpler: just return the edit directly (user can also type manually)
        edit._container = container  # keep ref
        return edit

    def _build_template_menu(self, edit: QLineEdit, parent) -> QMenu:
        menu = QMenu(parent)
        if not self.bot:
            menu.addAction("(kein Bot)").setEnabled(False)
            return menu
        engine   = self.bot.template_engine
        settings = engine.settings

        def _fill_kat(submenu: QMenu, kat: str):
            nach_gruppen: dict = defaultdict(list)
            for name, t in engine.templates.items():
                if name.startswith("_") or "__" in name:
                    continue
                if settings.get(name, {}).get("kategorie", "workflow") != kat:
                    continue
                g = (t["gruppe"] or "").strip().replace("\\", "/")
                nach_gruppen[g].append(name)
            if not nach_gruppen:
                submenu.addAction("(keine Templates)").setEnabled(False)
                return
            for name in sorted(nach_gruppen.get("", [])):
                submenu.addAction(name, lambda n=name: edit.setText(n))
            for gruppe in sorted(set(nach_gruppen.keys()) - {""}, key=str.lower):
                sub = submenu.addMenu(f"📁 {gruppe.split('/')[-1]}")
                for name in sorted(nach_gruppen[gruppe]):
                    sub.addAction(name, lambda n=name: edit.setText(n))

        wf_menu = menu.addMenu("🔄 Workflow")
        _fill_kat(wf_menu, "workflow")
        st_menu = menu.addMenu("🚩 State")
        _fill_kat(st_menu, "state")
        return menu

    def _variablen_picker_btn(self, current: str, parent) -> QLineEdit:
        edit = QLineEdit(current)
        edit.setStyleSheet("background: #1a1a1a; color: white;")
        btn = QPushButton("▾")
        btn.setFixedWidth(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0,0,0,0); lay.setSpacing(2)
        lay.addWidget(edit); lay.addWidget(btn)
        edit._container = container

        menu = QMenu(parent)
        st_sub = menu.addMenu("🔵 State")
        try:
            for name in sorted(self.bot.app.state.game_states.keys()):
                st_sub.addAction(name, lambda n=name: edit.setText(f"state::{n}"))
        except Exception:
            st_sub.addAction("(keine)").setEnabled(False)

        ocr_sub = menu.addMenu("🔤 OCR")
        try:
            for name in sorted(self.bot.app.state.get_all_ocr().keys()):
                ocr_sub.addAction(name, lambda n=name: edit.setText(f"ocr::{n}"))
        except Exception:
            ocr_sub.addAction("(keine)").setEnabled(False)

        db_sub = menu.addMenu("📊 Daten-Listen")
        try:
            from core import daten_manager as dm
            for liste in dm.alle_listen():
                lsub = db_sub.addMenu(liste["name"])
                for t in dm.transformationen_der_liste(liste["id"]):
                    lsub.addAction(t["name"],
                        lambda ln=liste["name"], tn=t["name"]: edit.setText(f"db::{ln}::{tn}"))
                for b in dm.berechnungen_der_liste(liste["id"]):
                    lsub.addAction(b["name"],
                        lambda ln=liste["name"], bn=b["name"]: edit.setText(f"db::{ln}::{bn}"))
        except Exception:
            db_sub.addAction("(DB nicht verfügbar)").setEnabled(False)

        btn.setMenu(menu)
        return edit

    def _workflow_picker_btn(self, current: str, parent) -> QLineEdit:
        edit = QLineEdit(current)
        edit.setStyleSheet("background: #1a1a1a; color: white;")
        btn = QPushButton("▾")
        btn.setFixedWidth(28)
        menu = QMenu(parent)
        try:
            workflows = sorted(self.bot.workflow_engine.workflows.keys())
            eigener = self._name_edit.text().strip()
            workflows = [w for w in workflows if w != eigener]
            for w in workflows:
                menu.addAction(f"🔄 {w}", lambda n=w: edit.setText(n))
            if not workflows:
                menu.addAction("(keine anderen Workflows)").setEnabled(False)
        except Exception:
            menu.addAction("(nicht verfügbar)").setEnabled(False)
        btn.setMenu(menu)

        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0,0,0,0); lay.setSpacing(2)
        lay.addWidget(edit); lay.addWidget(btn)
        edit._container = container
        return edit

    # ── Simulation ─────────────────────────────────────────────────────────────

    def _simulation_toggle(self):
        if self._sim_aktiv:
            self._simulation_stoppen()
        else:
            self._simulation_starten()

    def _simulation_starten(self):
        start = next((n for n in self.nodes if n.get("typ") == "start"), None)
        if not start:
            self._sim_log("Kein Start-Node vorhanden.", "failure")
            return
        self._sim_aktiv    = True
        self._sim_zustand  = {}
        self._sim_progress = {}
        self._sim_btn.setText("⏹ Stopp")
        self._sim_btn.setStyleSheet(
            "background: #b71c1c; color: white; font-weight: bold; font-size: 8pt; padding: 2px 10px;")
        self._log.clear()
        self._sim_log("▶ Live-Simulation gestartet", "info")

        self._sim_engine = self.SimulatedActionEngine(self, self.bot.action_engine, self._sim_log)
        nodes_index = {n["id"]: n for n in self.nodes}
        self._simulation_schritt(start, nodes_index, 0)

    def _simulation_stoppen(self):
        self._sim_aktiv    = False
        self._sim_zustand  = {}
        self._sim_progress = {}
        self._sim_btn.setText("▶ Simulieren")
        self._sim_btn.setStyleSheet(
            "background: #1565c0; color: white; font-weight: bold; font-size: 8pt; padding: 2px 10px;")
        self._sync_canvas()

    def _simulation_schritt(self, node, nodes_index, schritt):
        if not self._sim_aktiv or node is None or schritt > 200:
            self._simulation_fertig(); return
        nid = node["id"]
        typ = node.get("typ", "?")
        self._sim_zustand[nid] = "aktiv"
        self._sim_progress.pop(nid, None)
        self._sync_canvas()

        detail = self._canvas._node_detail(node)
        self._sim_log(f"► {typ.upper()}" + (f":  {detail}" if detail else ""), "aktiv")

        def _ausfuehren():
            if not self._sim_aktiv: return
            def m_func(): return self.bot.app.state.active_matches
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
                self._sim_log(f"  !! Unbekannter Node-Typ: {typ}", "failure")
                self._sim_zustand[nid] = "failure"
                QTimer.singleShot(0, self._simulation_fertig); return

            self._sim_zustand[nid] = "success" if port in ("success", "true", "out") else "failure"
            self._sim_progress.pop(nid, None)
            QMetaObject.invokeMethod(self, "_sync_canvas", Qt.ConnectionType.QueuedConnection)

            self._sim_log(
                f"  → Port: {port}",
                "success" if self._sim_zustand[nid] == "success" else "failure")

            naechster = None
            for conn in self.connections:
                if conn["von"] == nid and conn["port_aus"] == port:
                    naechster = nodes_index.get(conn["zu"]); break

            if naechster is None:
                self._sim_log("  (kein Folge-Node → Ende)", "done")
                QTimer.singleShot(400, self._simulation_fertig)
            else:
                QTimer.singleShot(
                    300, lambda: self._simulation_schritt(naechster, nodes_index, schritt + 1))

        threading.Thread(target=_ausfuehren, daemon=True).start()

    def _simulation_fertig(self):
        if not self._sim_aktiv: return
        self._sim_log("✓ Simulation abgeschlossen", "done")
        self._sim_aktiv = False
        self._sim_btn.setText("▶ Simulieren")
        self._sim_btn.setStyleSheet(
            "background: #1565c0; color: white; font-weight: bold; font-size: 8pt; padding: 2px 10px;")
        self._status_aktualisieren()

    def _sim_log(self, text: str, tag: str = "done"):
        if text.startswith("__timer__"):
            val = text[9:]
            for nid, status in self._sim_zustand.items():
                if status == "aktiv":
                    node = next((n for n in self.nodes if n["id"] == nid), None)
                    if node and node.get("typ") in ("suche", "suche_optional", "warten"):
                        self._sim_progress[nid] = f"⏳ {val}s"
                        QMetaObject.invokeMethod(
                            self, "_sync_canvas", Qt.ConnectionType.QueuedConnection)
                    break
            return

        FARBEN = {
            "aktiv":   "#f9a825", "success": "#4caf50",
            "failure": "#ef5350", "info":    "#90caf9", "done": "#aaaaaa",
        }
        farbe = FARBEN.get(tag, "#cccccc")

        def _append():
            cursor = self._log.textCursor()
            from PyQt6.QtGui import QTextCharFormat, QColor as _C
            fmt = QTextCharFormat()
            fmt.setForeground(_C(farbe))
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText(text + "\n", fmt)
            self._log.setTextCursor(cursor)
            self._log.ensureCursorVisible()

        QTimer.singleShot(0, _append)

    # ── Status / Speichern ─────────────────────────────────────────────────────

    def _status_aktualisieren(self):
        z = int(self._canvas._scale * 100)
        if self._sim_aktiv:
            self._status_lbl.setText(
                f"▶ Simulation läuft …  ·  {len(self.nodes)} Nodes  ·  Zoom {z}%")
            self._status_lbl.setStyleSheet("color: #f9a825; font-size: 8pt;")
        else:
            self._status_lbl.setText(
                f"{len(self.nodes)} Nodes  ·  {len(self.connections)} Verbindungen"
                f"  ·  Zoom {z}%  ·  Port ziehen = Verbindung  ·  Scrollen = Zoom")
            self._status_lbl.setStyleSheet("color: #666666; font-size: 8pt;")

    def _speichern(self):
        name = self._name_edit.text().strip()
        if not name: return
        graph = {"nodes": self.nodes, "connections": self.connections}
        self.gespeichert.emit(name, graph)
        if self._callback:
            self._callback(name, graph)
        self.accept()

    def _abbrechen(self):
        self.abgebrochen.emit()
        if self._callback:
            self._callback(None, None)
        self.reject()

    def closeEvent(self, event):
        self._abbrechen()
        super().closeEvent(event)

    # ── SimulatedActionEngine ──────────────────────────────────────────────────

    class SimulatedActionEngine:
        def __init__(self, parent_dialog, real_engine, log_func):
            self.parent = parent_dialog
            self.real   = real_engine
            self.log    = log_func

        def _fragen(self, titel: str, msg: str) -> str:
            result = {"wahl": "sim"}
            dlg = QMessageBox(self.parent)
            dlg.setWindowTitle(titel)
            dlg.setText(msg)
            dlg.setStyleSheet("background: #2d2d2d; color: white;")
            btn_sim = dlg.addButton("Simulieren",     QMessageBox.ButtonRole.NoRole)
            btn_adb = dlg.addButton("ADB Ausführen",  QMessageBox.ButtonRole.YesRole)
            btn_ab  = dlg.addButton("Abbrechen",      QMessageBox.ButtonRole.RejectRole)
            dlg.exec()
            clicked = dlg.clickedButton()
            if clicked == btn_adb: return "adb"
            if clicked == btn_ab:  return "stop"
            return "sim"

        def auf_template_warten(self, template, matches_func, timeout=10,
                                intervall=0.3, log_func=None, laeuft_func=None):
            return self.real.auf_template_warten(
                template, matches_func, timeout, intervall,
                log_func=log_func, laeuft_func=laeuft_func)

        def template_tippen(self, template, matches, log_func=None):
            for m in matches:
                if m[0] == template:
                    _, mx, my, mw, mh = m[:5]
                    kx, ky = self.real.klickpunkt_berechnen(template, mx, my, mw, mh)
                    wahl = self._fragen("KLICK-AKTION",
                        f"Soll auf '{template}' an ({kx}, {ky}) geklickt werden?")
                    if wahl == "stop":
                        self.parent._simulation_stoppen(); return False
                    if wahl == "adb":
                        self.log(f"[ADB] Klick auf {template} ({kx}, {ky})", "success")
                        return self.real.template_tippen(template, matches, log_func=None)
                    self.log(f"[SIM] Klick auf {template} ({kx}, {ky}) (simuliert)", "info")
                    return True
            return False

        def warten(self, sekunden):
            time.sleep(min(sekunden, 2.0))

        def zurueck(self):
            wahl = self._fragen("ZURÜCK", "Soll der Zurück-Button gedrückt werden?")
            if wahl == "adb":
                self.log("[ADB] Zurück-Button", "success"); self.real.zurueck()
            elif wahl == "stop":
                self.parent._simulation_stoppen()
            else:
                self.log("[SIM] Zurück-Button (simuliert)", "info")

        def home(self):
            wahl = self._fragen("HOME", "Soll der Home-Button gedrückt werden?")
            if wahl == "adb":
                self.log("[ADB] Home-Button", "success"); self.real.home()
            elif wahl == "stop":
                self.parent._simulation_stoppen()
            else:
                self.log("[SIM] Home-Button (simuliert)", "info")
