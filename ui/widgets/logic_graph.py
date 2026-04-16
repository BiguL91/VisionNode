"""
FUP Logik-Graph Widgets — extrahiert aus logic_editor_qt.py.
Enthält alle Qt-Scene/Item-Klassen sowie die Farb- und Port-Konstanten.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsLineItem, QMenu,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QLineF, QPoint
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QFont,
    QPainterPathStroker,
)

# ── Konstanten ────────────────────────────────────────────────────────────────
NW, NH, TH = 165, 85, 26
PR = 8   # Port-Radius

FARBEN = {
    "l_var":    "#1e88e5",
    "l_match":  "#00acc1",
    "l_const":  "#546e7a",
    "l_and":    "#2ea043",
    "l_or":     "#2ea043",
    "l_not":    "#b71c1c",
    "l_cmp":    "#f9a825",
    "l_timer":  "#e91e63",
    "l_result": "#673ab7",
}

PORTS = {
    "l_var":    ([], ["out"]),
    "l_match":  ([], ["out"]),
    "l_const":  ([], ["out"]),
    "l_and":    (["in1", "in2"], ["out"]),
    "l_or":     (["in1", "in2"], ["out"]),
    "l_not":    (["in"], ["out"]),
    "l_cmp":    (["in1", "in2"], ["out"]),
    "l_timer":  ([], ["out"]),
    "l_result": (["in"], []),
}

TYPEN_LABEL = [
    ("Variable",  "l_var"),
    ("Gefunden?", "l_match"),
    ("Konstante", "l_const"),
    ("AND",       "l_and"),
    ("OR",        "l_or"),
    ("NOT",       "l_not"),
    ("Vergleich", "l_cmp"),
    ("Timer",     "l_timer"),
]


# ── LogicView ─────────────────────────────────────────────────────────────────
class LogicView(QGraphicsView):
    """
    Spezialisierte View für den Logik-Editor.
    Übernimmt das Navigationsverhalten vom Workflow-Editor (Pan & Zoom).
    """
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(True)
        self.setObjectName("logic_view")
        self._pan_start = QPoint()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item is None:
                self._pan_start = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._pan_start.isNull():
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pan_start = QPoint()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)


# ── Port-Item ─────────────────────────────────────────────────────────────────
class PortItem(QGraphicsEllipseItem):
    def __init__(self, node: "NodeItem", port_name: str, port_type: str, x: float, y: float):
        r = PR
        super().__init__(-r, -r, 2 * r, 2 * r, node)
        self.node = node
        self.port_name = port_name
        self.port_type = port_type   # "in" | "out"
        self.setPos(x, y)
        self.setPen(QPen(QColor("#888888"), 2))
        self.setBrush(QBrush(QColor("#1a1a1a")))
        self.setZValue(2)
        self.setAcceptHoverEvents(True)

    def scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def hoverEnterEvent(self, e):
        self.setBrush(QBrush(QColor("#444444")))
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setBrush(QBrush(QColor("#1a1a1a")))
        super().hoverLeaveEvent(e)


# ── Node-Item ─────────────────────────────────────────────────────────────────
class NodeItem(QGraphicsItem):
    def __init__(self, node_data: dict):
        super().__init__()
        self.data = node_data
        self._status_val = None  # True | False | None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(node_data.get("x", 100), node_data.get("y", 100))
        self.setZValue(1)
        self._ports: dict[str, PortItem] = {}
        self._build_ports()

    def set_status(self, val):
        b_val = bool(val) if val is not None else None
        if self._status_val != b_val:
            self._status_val = b_val
            self.update()

    def _build_ports(self):
        typ = self.data["typ"]
        ins, outs = PORTS.get(typ, ([], []))
        for i, name in enumerate(ins):
            py = TH + 24 + i * 24
            self._ports[name] = PortItem(self, name, "in", 0, py)
        for name in outs:
            py = NH / 2 + 12
            self._ports[name] = PortItem(self, name, "out", NW, py)

    def get_port(self, name: str) -> PortItem | None:
        return self._ports.get(name)

    def node_id(self) -> str:
        return self.data["id"]

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, NW + 4, NH + 4)

    def paint(self, painter: QPainter, option, widget=None):
        typ = self.data["typ"]
        farbe = QColor(FARBEN.get(typ, "#555555"))
        selected = self.isSelected()

        border_color = farbe if not selected else QColor("#ffffff")
        border_width = 2
        if self._status_val is True:
            border_color = QColor("#00ff00")
            border_width = 3
        elif self._status_val is False:
            border_color = QColor("#ff4444")
            border_width = 2

        painter.setBrush(QBrush(QColor("#111111")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(3, 3, NW, NH), 5, 5)

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(QColor("#252525")))
        painter.drawRoundedRect(0, 0, NW, NH, 5, 5)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(farbe))
        painter.drawRoundedRect(QRectF(2, 2, NW - 4, TH), 3, 3)

        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(8, 0, NW - 16, TH, Qt.AlignmentFlag.AlignVCenter, typ.replace("l_", "").upper())

        painter.setPen(QColor("#aaaaaa"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(8, TH + 4, NW - 16, NH - TH - 4,
                         Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self._detail())

        ins, _ = PORTS.get(typ, ([], []))
        painter.setFont(QFont("Segoe UI", 7))
        painter.setPen(QColor("#666666"))
        for i, name in enumerate(ins):
            py = TH + 24 + i * 24
            painter.drawText(15, py - 8, 60, 16, Qt.AlignmentFlag.AlignVCenter, name)

    def _detail(self) -> str:
        typ = self.data["typ"]
        if typ == "l_var":    return self.data.get("variable", "Bitte wählen...")
        if typ == "l_match":  return f"Bild: {self.data.get('template', '–')}"
        if typ == "l_const":  return f"Wert: {self.data.get('wert', '0')}"
        if typ == "l_cmp":    return f"{self.data.get('operator','=')} {self.data.get('wert','')}"
        if typ == "l_timer":
            t_var = self.data.get("variable", "–")
            if t_var.startswith("db::"):
                parts = t_var.split("::")
                if len(parts) >= 3:
                    t_var = f"{parts[1]} -> {parts[2]}"
            return f"Timer: {t_var}"
        return ""

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data["x"] = int(self.x())
            self.data["y"] = int(self.y())
            if self.scene():
                self.scene().update_connections_for(self)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if self.scene():
            self.scene().node_double_clicked(self)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self.scene():
            self.scene().node_right_clicked(self, event.screenPos())


# ── Connection-Item ───────────────────────────────────────────────────────────
class ConnectionItem(QGraphicsPathItem):
    def __init__(self, src_port: PortItem, dst_port: PortItem, conn_data: dict):
        super().__init__()
        self.src_port = src_port
        self.dst_port = dst_port
        self.conn_data = conn_data
        self._status_val = None
        self.setPen(QPen(QColor("#444444"), 2))
        self.setZValue(0)
        self.setAcceptHoverEvents(True)
        self.update_path()

    def set_status(self, val):
        b_val = bool(val) if val is not None else None
        if self._status_val != b_val:
            self._status_val = b_val
            if b_val is True:
                self.setPen(QPen(QColor("#00ff00"), 3))
            elif b_val is False:
                self.setPen(QPen(QColor("#884444"), 2))
            else:
                self.setPen(QPen(QColor("#444444"), 2))
            self.update()

    def update_path(self):
        p1 = self.src_port.scene_pos()
        p2 = self.dst_port.scene_pos()
        path = QPainterPath(p1)
        dx = max(abs(p2.x() - p1.x()) * 0.5, 60)
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        self.setPath(path)

    def shape(self) -> QPainterPath:
        ps = QPainterPathStroker()
        ps.setWidth(10)
        return ps.createStroke(super().shape())

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("#ffffff"), 3))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.set_status(self._status_val)
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        if self.scene():
            self.scene().connection_right_clicked(self, event.screenPos())


# ── Scene ─────────────────────────────────────────────────────────────────────
class LogicScene(QGraphicsScene):
    node_edit_requested = pyqtSignal(object)   # NodeItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connections: list[ConnectionItem] = []
        self._nodes: dict[str, NodeItem] = {}
        self._drag_port: PortItem | None = None
        self._temp_line: QGraphicsLineItem | None = None
        self.setBackgroundBrush(QBrush(QColor("#121212")))

    # ── Öffentliche API ───────────────────────────────────────────────────────

    def load_graph(self, nodes: list, connections: list):
        self.clear()
        self._connections.clear()
        self._nodes.clear()
        for nd in nodes:
            self.add_node_item(nd)
        for cd in connections:
            self._add_connection_from_data(cd)

    def add_node_item(self, node_data: dict) -> NodeItem:
        item = NodeItem(node_data)
        self.addItem(item)
        self._nodes[node_data["id"]] = item
        return item

    def _add_connection_from_data(self, cd: dict):
        src_node = self._nodes.get(cd["von"])
        dst_node = self._nodes.get(cd["zu"])
        if not src_node or not dst_node:
            return
        src_port = src_node.get_port(cd["port_von"])
        dst_port = dst_node.get_port(cd["port_zu"])
        if not src_port or not dst_port:
            return
        conn = ConnectionItem(src_port, dst_port, cd)
        self.addItem(conn)
        self._connections.append(conn)

    def update_connections_for(self, node: NodeItem):
        for conn in self._connections:
            if conn.src_port.node is node or conn.dst_port.node is node:
                conn.update_path()

    def update_live_data(self, results: dict):
        for nid, node in self._nodes.items():
            node.set_status(results.get(nid))
        for conn in self._connections:
            conn.set_status(results.get(conn.src_port.node.node_id()))

    def collect_graph(self) -> dict:
        nodes = [dict(item.data) for item in self._nodes.values()]
        connections = [dict(c.conn_data) for c in self._connections]
        return {"nodes": nodes, "connections": connections}

    # ── Mouse Events für Port-Verbindungen ───────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            port = self._port_at(event.scenePos())
            if port:
                self._drag_port = port
                self._temp_line = QGraphicsLineItem()
                self._temp_line.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine))
                self.addItem(self._temp_line)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_port and self._temp_line:
            self._temp_line.setLine(QLineF(self._drag_port.scene_pos(), event.scenePos()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_port:
            self.removeItem(self._temp_line)
            self._temp_line = None
            dst_port = self._port_at(event.scenePos())
            if dst_port and dst_port is not self._drag_port:
                self._try_connect(self._drag_port, dst_port)
            self._drag_port = None
            return
        super().mouseReleaseEvent(event)

    def _port_at(self, scene_pos: QPointF) -> PortItem | None:
        for item in self.items(scene_pos):
            if isinstance(item, PortItem):
                return item
        return None

    def _try_connect(self, a: PortItem, b: PortItem):
        if a.port_type == "out" and b.port_type == "in":
            src, dst = a, b
        elif a.port_type == "in" and b.port_type == "out":
            src, dst = b, a
        else:
            return
        if src.node is dst.node:
            return
        self._connections = [c for c in self._connections if not (c.dst_port is dst)]
        self._redraw_connections()
        cd = {
            "von": src.node.node_id(), "port_von": src.port_name,
            "zu":  dst.node.node_id(), "port_zu":  dst.port_name,
        }
        conn = ConnectionItem(src, dst, cd)
        self.addItem(conn)
        self._connections.append(conn)

    def _redraw_connections(self):
        for item in list(self.items()):
            if isinstance(item, ConnectionItem):
                self.removeItem(item)
        for conn in self._connections:
            self.addItem(conn)
            conn.update_path()

    # ── Node Events ──────────────────────────────────────────────────────────

    def node_double_clicked(self, node: NodeItem):
        self.node_edit_requested.emit(node)

    def node_right_clicked(self, node: NodeItem, pos):
        menu = QMenu()
        if node.data["typ"] in ("l_var", "l_match", "l_const", "l_cmp", "l_timer"):
            act_edit = menu.addAction("⚙ Parameter bearbeiten")
            act_edit.triggered.connect(lambda: self.node_edit_requested.emit(node))
            menu.addSeparator()
        if node.data["typ"] != "l_result":
            act_del = menu.addAction("🗑 Node löschen")
            def _loeschen():
                nid = node.node_id()
                self._connections = [
                    c for c in self._connections
                    if c.src_port.node.node_id() != nid and c.dst_port.node.node_id() != nid
                ]
                self._redraw_connections()
                self._nodes.pop(nid, None)
                self.removeItem(node)
            act_del.triggered.connect(_loeschen)
        else:
            menu.addAction("(Resultat kann nicht gelöscht werden)").setEnabled(False)
        menu.exec(pos)

    def connection_right_clicked(self, conn: ConnectionItem, pos):
        menu = QMenu()
        act_del = menu.addAction("🗑 Verbindung löschen")
        def _loeschen():
            if conn in self._connections:
                self._connections.remove(conn)
            self.removeItem(conn)
        act_del.triggered.connect(_loeschen)
        menu.exec(pos)
