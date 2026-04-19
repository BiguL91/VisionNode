"""
NodeCanvas — Custom-Paint-Widget für den Workflow-Graphen.
Extrahiert aus workflow_editor_qt.py.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QPoint
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath,
    QPainterPathStroker,
)
from style.colors import CANVAS_BG, NODE_FARBEN, PORT_FARBEN, NODE_BG

# ── Layout-Konstanten (Welt-Koordinaten) ──────────────────────────────────────
NODE_BREITE  = 170
NODE_HOEHE   = 80
TITEL_HOEHE  = 22
PORT_RADIUS  = 8
SCALE_MIN    = 0.25
SCALE_MAX    = 4.0

# ── Port-Definitionen ─────────────────────────────────────────────────────────
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
    "set_timer":         (True,  ["out"]),
    "set_value":         (True,  ["out"]),
    "loop":              (True,  ["body", "done"]),
    "suche_klick":       (True,  ["success", "failure"]),
}


class NodeCanvas(QWidget):
    """Custom-Paint-Widget für den Workflow-Graphen."""
    node_double_clicked = pyqtSignal(dict)
    node_right_clicked  = pyqtSignal(dict, QPoint)
    conn_right_clicked  = pyqtSignal(dict, QPoint)
    connection_added    = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setObjectName("node_canvas")

        self.nodes:       list[dict] = []
        self.connections: list[dict] = []
        self._workflow_name = ""
        self._scale  = 1.0
        self._tx     = 0.0
        self._ty     = 0.0
        self._sim_zustand:  dict = {}
        self._sim_progress: dict = {}

        self._port_rects: dict[tuple, QRectF] = {}
        self._node_rects: dict[str, QRectF]   = {}
        self._conn_paths: dict[str, tuple]    = {}
        self._hover_conn: str | None          = None

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

    def _node_h(self, node: dict) -> float:
        typ = node["typ"]
        if typ == "priority_selector":
            aus_ports = [a.get("port") for a in node.get("ausgaenge", [])] + ["else"]
        else:
            _, aus_ports = NODE_PORTS.get(typ, (True, ["out"]))
        return max(NODE_HOEHE, (len(aus_ports) + 1) * 28)

    def _port_pos(self, node, port_name):
        x   = self._cx(node["x"])
        y   = self._cy(node["y"])
        w   = NODE_BREITE * self._scale
        h   = self._node_h(node) * self._scale
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
        p.setPen(QPen(QColor("#1f1f1f"), 1))
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
            key = f"{conn['von']}_{conn['port_aus']}_{conn['zu']}"
            is_hover = (self._hover_conn == key)
            farbe = QColor(PORT_FARBEN.get(conn["port_aus"], "#aaaaaa"))
            if is_hover:
                farbe = QColor("#ffffff")
            path = self._bezier_path(p1.x(), p1.y(), p2.x(), p2.y())
            p.setPen(QPen(farbe, max(1, (3 if is_hover else 2) * self._scale)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setBrush(QBrush(farbe))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(p2.x(), p2.y()), 4, 4)
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
        h = self._node_h(node) * s
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
            rahmen, rw, koerper = QColor("#f9a825"), max(3, 3*s), QColor("#2e2a1a")
        elif sim == "success":
            rahmen, rw, koerper = QColor("#4caf50"), max(2, 2*s), QColor("#1a2e1a")
        elif sim == "failure":
            rahmen, rw, koerper = QColor("#ef5350"), max(2, 2*s), QColor("#2e1a1a")
        else:
            rahmen, rw, koerper = farbe, max(1, 2*s), QColor(NODE_BG)

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
        titel = typ.upper()
        if typ == "priority_selector" and self._workflow_name:
            titel = self._workflow_name.upper()
        p.drawText(QRectF(x, y, w, th), Qt.AlignmentFlag.AlignCenter, titel)

        if s > 0.4:
            detail = self._node_detail(node)
            if detail:
                p.setPen(QPen(QColor("#cccccc")))
                p.setFont(QFont("Segoe UI", max(5, int(8*s))))
                p.drawText(QRectF(x+4, y+th, w-8, h-th),
                           Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, detail)

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
            
        if typ in ("suche", "suche_optional", "klick", "suche_klick"):
            tpl = node.get("template", "–")
            suffix = []
            
            # Timeout anzeigen bei Suche
            if typ in ("suche", "suche_optional", "suche_klick"):
                to = node.get("timeout")
                if to: suffix.append(f"{to}s")
                
            # Index anzeigen bei Klick
            if typ in ("klick", "suche_klick"):
                idx = str(node.get("index", "1"))
                if idx != "1": suffix.append(f"#{idx}")
                
            if suffix:
                tpl += f" [{', '.join(suffix)}]"
            return tpl
            
        elif typ == "warten":
            return f"{node.get('sekunden', 1.0)} s"
        elif typ == "bedingung":
            return f"{node.get('variable','?')} {node.get('operator','=')} {node.get('wert','0')}"
        elif typ == "call_workflow":
            return f"➔ {node.get('workflow', '–')}"
        elif typ == "set_timer":
            t_var = node.get("timer_var", "–")
            return f"{t_var} [{node.get('dauer', 60)}s]"
        elif typ == "set_value":
            return f"{node.get('variable','?')} = {node.get('wert','0')}"
        elif typ == "loop":
            return f"n = {node.get('count', 5)}"
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
                dx, dy = pos.x()-pp.x(), pos.y()-pp.y()
                if (dx*dx + dy*dy) <= fang_radius_sq:
                    return node, p_name, False
            if typ != "start":
                pp = self._port_pos(node, "in")
                dx, dy = pos.x()-pp.x(), pos.y()-pp.y()
                if (dx*dx + dy*dy) <= fang_radius_sq:
                    return node, "in", True
        return None, None, None

    def mousePressEvent(self, event):
        pos_global = event.globalPosition().toPoint()
        pos_local  = self.mapFromGlobal(pos_global)
        pos_f      = QPointF(pos_local)
        if event.button() == Qt.MouseButton.RightButton:
            self._rechtsklick(pos_local, pos_global)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            node, p_name, ist_in = self._get_port_at(pos_f)
            if node and not ist_in:
                self._conn_drag_aktiv = True
                self._conn_drag_von   = {"node": node, "port": p_name}
                self._conn_drag_pos   = pos_f
                self.setCursor(Qt.CursorShape.CrossCursor)
                self.update()
                return
            for node in reversed(self.nodes):
                nx = self._cx(node["x"])
                ny = self._cy(node["y"])
                nw = NODE_BREITE * self._scale
                nh = NODE_HOEHE  * self._scale
                if QRectF(nx, ny, nw, nh).contains(pos_f):
                    self._drag_node   = node
                    self._drag_start  = QPointF(self._wx(pos_f.x()), self._wy(pos_f.y()))
                    self._drag_origin = (node["x"], node["y"])
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.nodes.remove(node)
                    self.nodes.append(node)
                    self.update()
                    return
            self._pan_aktiv = True
            self._pan_last  = pos_local
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
            return

        old_hover = self._hover_conn
        self._hover_conn = None
        pf       = event.position()
        hit_rect = QRectF(pf.x()-5, pf.y()-5, 10, 10)
        stroker  = QPainterPathStroker()
        stroker.setWidth(10)
        for key, (path, _) in self._conn_paths.items():
            if stroker.createStroke(path).intersects(hit_rect):
                self._hover_conn = key
                break
        if self._hover_conn != old_hover:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._conn_drag_aktiv:
                self._conn_drag_abschliessen(
                    QPointF(self.mapFromGlobal(event.globalPosition().toPoint()))
                )
            self._drag_node       = None
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
        cx, cy   = event.position().x(), event.position().y()
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
        stroker  = QPainterPathStroker()
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
            self.connections[:] = [
                c for c in self.connections
                if not (c["von"] == self._conn_drag_von["node"]["id"]
                        and c["port_aus"] == self._conn_drag_von["port"])
            ]
            self.connections.append({
                "von":      self._conn_drag_von["node"]["id"],
                "port_aus": self._conn_drag_von["port"],
                "zu":       node["id"],
                "port_ein": "in",
            })
            self._template_vererben(self._conn_drag_von["node"], node)
            self.connection_added.emit()

    def _template_vererben(self, von_node, zu_node):
        if (von_node.get("typ") in ("suche", "suche_optional")
                and zu_node.get("typ") == "klick"
                and not zu_node.get("template")):
            tpl = von_node.get("template", "")
            if tpl:
                zu_node["template"] = tpl
