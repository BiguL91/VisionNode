"""
FUP Logik-Netzwerk Editor (Qt).
Ersetzt LogicEditorDialog (tkinter Canvas).

Verwendung:
    dlg = LogicEditorDialogQt(name, graph, game_states, templates, ocr_vars, parent)
    dlg.gespeichert.connect(lambda g: ...)  # g = {"nodes": [...], "connections": [...]}
    dlg.exec()
"""
import uuid
import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsLineItem, QLabel, QLineEdit, QComboBox, QFrame, QMenu,
    QFormLayout, QWidget
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QLineF, QMetaObject, Q_ARG, QTimer, QPoint
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QFont, QAction,
    QPainterPathStroker
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
        self.setDragMode(QGraphicsView.DragMode.NoDrag) # RubberBand deaktiviert
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(True)
        self.setObjectName("logic_view")
        
        self._pan_start = QPoint()

    def wheelEvent(self, event):
        # Zoom ohne Modifikatoren (wie im Workflow)
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            # Wenn kein Item (Node/Port) getroffen wurde -> Panning starten
            if item is None:
                self._pan_start = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._pan_start.isNull():
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            
            # Verschiebt den Bildschirmausschnitt
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
        self._status_val = None  # True | False | None (unbekannt)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(node_data.get("x", 100), node_data.get("y", 100))
        self.setZValue(1)
        self._ports: dict[str, PortItem] = {}
        self._build_ports()

    def set_status(self, val):
        # Konvertiere in bool für die Visualisierung (grüner/roter Rahmen)
        b_val = bool(val) if val is not None else None
        if self._status_val != b_val:
            self._status_val = b_val
            self.update()

    def _build_ports(self):
        typ = self.data["typ"]
        ins, outs = PORTS.get(typ, ([], []))
        for i, name in enumerate(ins):
            py = TH + 24 + i * 24
            p = PortItem(self, name, "in", 0, py)
            self._ports[name] = p
        for name in outs:
            py = NH / 2 + 12
            p = PortItem(self, name, "out", NW, py)
            self._ports[name] = p

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

        # Rahmenfarbe basierend auf Status
        border_color = farbe if not selected else QColor("#ffffff")
        border_width = 2
        if self._status_val is True:
            border_color = QColor("#00ff00")
            border_width = 3
        elif self._status_val is False:
            border_color = QColor("#ff4444")
            border_width = 2

        # Schatten (wie im Workflow)
        painter.setBrush(QBrush(QColor("#111111")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(3, 3, NW, NH), 5, 5)

        # Haupt-Body (abgerundet wie im Workflow)
        body_pen = QPen(border_color, border_width)
        painter.setPen(body_pen)
        painter.setBrush(QBrush(QColor("#252525")))
        painter.drawRoundedRect(0, 0, NW, NH, 5, 5)

        # Titel-Balken (abgerundet)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(farbe))
        painter.drawRoundedRect(QRectF(2, 2, NW - 4, TH), 3, 3)

        # Titel-Text
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(8, 0, NW - 16, TH, Qt.AlignmentFlag.AlignVCenter, typ.replace("l_", "").upper())

        # Detail-Text
        painter.setPen(QColor("#aaaaaa"))
        painter.setFont(QFont("Segoe UI", 8))
        detail = self._detail()
        painter.drawText(8, TH + 4, NW - 16, NH - TH - 4,
                         Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, detail)

        # Port-Labels (Eingänge)
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
        if typ == "l_timer":  return f"Timer: {self.data.get('variable', '–')}"
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
        dx = abs(p2.x() - p1.x()) * 0.5
        dx = max(dx, 60)
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        self.setPath(path)

    def shape(self) -> QPainterPath:
        # Breiterer Shape für einfacheres Klicken
        s = super().shape()
        ps = QPainterPathStroker()
        ps.setWidth(10)
        return ps.createStroke(s)

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
        self._nodes: dict[str, NodeItem] = {}   # id → NodeItem
        self._drag_port: PortItem | None = None
        self._temp_line: QGraphicsLineItem | None = None

        # Gitter-Hintergrund via Brush
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
        # results: { node_id: value }
        for nid, node in self._nodes.items():
            val = results.get(nid)
            node.set_status(val)
        
        for conn in self._connections:
            # Verbindung ist aktiv, wenn der Quell-Port-Wert True liefert
            src_val = results.get(conn.src_port.node.node_id())
            conn.set_status(src_val)

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
            p1 = self._drag_port.scene_pos()
            p2 = event.scenePos()
            self._temp_line.setLine(QLineF(p1, p2))
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
        # Reihenfolge: out → in
        if a.port_type == "out" and b.port_type == "in":
            src, dst = a, b
        elif a.port_type == "in" and b.port_type == "out":
            src, dst = b, a
        else:
            return
        if src.node is dst.node:
            return
        # Bestehende Verbindung zu diesem Eingang entfernen
        self._connections = [
            c for c in self._connections
            if not (c.dst_port is dst)
        ]
        self._redraw_connections()

        cd = {
            "von": src.node.node_id(), "port_von": src.port_name,
            "zu":  dst.node.node_id(), "port_zu":  dst.port_name,
        }
        conn = ConnectionItem(src, dst, cd)
        self.addItem(conn)
        self._connections.append(conn)

    def _redraw_connections(self):
        # Entfernt alle veralteten ConnectionItems aus der Scene
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
        
        # Nur editierbare Nodes (nicht AND, OR, etc. -> wobei Timer, Var, Match, Const, Cmp editierbar sind)
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
            lbl = QLabel("Timer aus Datenliste wählen:")
            lbl.setProperty("class", "lbl_dim")
            layout.addWidget(lbl)

            self._var_btn = QPushButton(self._node.data.get("variable", "Bitte wählen..."))
            self._var_btn.setObjectName("btn_logic_net")
            self._var_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._var_btn.clicked.connect(self._timer_menu_zeigen)
            layout.addWidget(self._var_btn)
            self._felder["variable"] = self._var_btn

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
        """Spezialisierter Picker für Timer-Variablen."""
        from core import daten_manager as dm
        menu = QMenu(self)
        try:
            listen = dm.alle_listen()
            for l in listen:
                l_menu = QMenu(f"📋 {l['name']}", self)
                timer_vars = []
                
                # Nur Spalten/Transformationen vom Typ 'timer'
                spalten = dm.spalten_der_liste(l["id"])
                for s in spalten:
                    if s.get("typ") == "timer": timer_vars.append(s["name"])
                
                trans = dm.transformationen_der_liste(l["id"])
                for t in trans:
                    if t.get("typ") == "timer": timer_vars.append(t["name"])
                
                timer_vars = sorted(list(set(timer_vars)))
                for v in timer_vars:
                    act = QAction(v, self)
                    act.triggered.connect(lambda _, ln=l["name"], vn=v: self._var_btn.setText(f"db::{ln}::{vn}"))
                    l_menu.addAction(act)
                
                if timer_vars:
                    menu.addMenu(l_menu)
                    
            if not listen:
                menu.addAction("(Keine Listen vorhanden)").setEnabled(False)
            elif menu.isEmpty():
                 menu.addAction("(Keine Timer-Spalten gefunden)").setEnabled(False)
        except Exception as e:
            menu.addAction(f"Fehler: {e}").setEnabled(False)
             
        menu.exec(self._var_btn.mapToGlobal(self._var_btn.rect().bottomLeft()))


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
                self._node.data[key] = widget.text()
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
