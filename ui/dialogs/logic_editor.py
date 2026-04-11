import tkinter as tk
import uuid
import copy

# Konfiguration für Logik-Editor
L_NODE_BREITE = 165
L_NODE_HOEHE  = 85
L_TITEL_HOEHE = 26
L_PORT_RADIUS = 10

L_FARBEN = {
    "l_var":    "#1e88e5", # Blau: Input
    "l_match":  "#00acc1", # Cyan: Template gefunden?
    "l_const":  "#546e7a", # Grau: Konstante
    "l_and":    "#2ea043", # Grün: Gatter
    "l_or":     "#2ea043",
    "l_not":    "#b71c1c", # Rot: NOT
    "l_cmp":    "#f9a825", # Gelb: Vergleich
    "l_result": "#673ab7", # Lila: Ausgang
}

# (Eingänge, Ausgänge)
L_PORTS = {
    "l_var":    ([], ["out"]),
    "l_match":  ([], ["out"]),
    "l_const":  ([], ["out"]),
    "l_and":    (["in1", "in2"], ["out"]),
    "l_or":     (["in1", "in2"], ["out"]),
    "l_not":    (["in"], ["out"]),
    "l_cmp":    (["in1", "in2"], ["out"]),
    "l_result": (["in"], []),
}

class LogicEditorDialog:
    def __init__(self, parent, bot, name, graph, callback):
        self.parent = parent
        self.bot = bot
        self.callback = callback
        self.nodes = [dict(n) for n in graph.get("nodes", [])]
        self.connections = [dict(c) for c in graph.get("connections", [])]
        
        if not self.nodes:
            self.nodes = [{"id": str(uuid.uuid4()), "typ": "l_result", "x": 600, "y": 200}]

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Logik-Netzwerk: {name}")
        self.dialog.geometry("1100x750")
        self.dialog.configure(bg="#1e1e1e")
        self.dialog.grab_set()

        self._setup_ui()
        self._gitter_zeichnen()
        self._alles_neu_zeichnen()

    def _setup_ui(self):
        bar = tk.Frame(self.dialog, bg="#2d2d2d", pady=5)
        bar.pack(fill=tk.X)
        
        typen = [("Variable", "l_var"), ("Gefunden?", "l_match"), ("Konstante", "l_const"), 
                 ("AND", "l_and"), ("OR", "l_or"), ("NOT", "l_not"), ("Vergleich", "l_cmp")]
        for label, typ in typen:
            tk.Button(bar, text=label, bg=L_FARBEN[typ], fg="white", font=("Segoe UI", 8, "bold"),
                      relief=tk.FLAT, padx=10, command=lambda t=typ: self._node_hinzufuegen(t)).pack(side=tk.LEFT, padx=5)

        tk.Button(bar, text="💾 Speichern", bg="#2ea043", fg="white", font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=15, command=self._speichern).pack(side=tk.RIGHT, padx=10)

        self.canvas = tk.Canvas(self.dialog, bg="#121212", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self._drag_data = {"node": None, "port": None}

    def _gitter_zeichnen(self):
        for i in range(0, 3000, 100):
            self.canvas.create_line(i, 0, i, 3000, fill="#1a1a1a", tags="bg")
            self.canvas.create_line(0, i, 3000, i, fill="#1a1a1a", tags="bg")

    def _node_hinzufuegen(self, typ):
        nid = str(uuid.uuid4())
        node = {"id": nid, "typ": typ, "x": 150, "y": 150}
        if typ == "l_cmp": node["operator"] = "="
        self.nodes.append(node)
        self._alles_neu_zeichnen()

    def _alles_neu_zeichnen(self):
        self.canvas.delete("node", "conn", "port")
        for conn in self.connections:
            self._verbindung_zeichnen(conn)
        for node in self.nodes:
            self._node_zeichnen(node)

    def _node_zeichnen(self, node):
        x, y, nid, typ = node["x"], node["y"], node["id"], node["typ"]
        farbe = L_FARBEN.get(typ, "#555")
        node_tag = f"node_{nid}"
        tags_main = ("node", node_tag)
        
        self.canvas.create_rectangle(x, y, x+L_NODE_BREITE, y+L_NODE_HOEHE, fill="#252525", outline=farbe, width=2, tags=tags_main)
        self.canvas.create_rectangle(x, y, x+L_NODE_BREITE, y+L_TITEL_HOEHE, fill=farbe, outline=farbe, tags=tags_main)
        
        titel = typ.replace("l_", "").upper()
        self.canvas.create_text(x+8, y+13, text=titel, fill="white", anchor="w", font=("Segoe UI", 9, "bold"), tags=tags_main)
        
        detail = self._get_node_detail(node)
        self.canvas.create_text(x+8, y+L_TITEL_HOEHE+20, text=detail, fill="#aaa", anchor="nw", font=("Segoe UI", 8), tags=tags_main, width=L_NODE_BREITE-16)

        ins, outs = L_PORTS.get(typ, ([], []))
        for i, p in enumerate(ins):
            py = y + L_TITEL_HOEHE + 24 + (i * 24)
            self._port_zeichnen(x, py, p, "in", nid)
            self.canvas.create_text(x+15, py, text=p, fill="#666", anchor="w", font=("Segoe UI", 7), tags=("node", node_tag, "port_label"))
            
        for i, p in enumerate(outs):
            py = y + L_NODE_HOEHE/2 + 12
            self._port_zeichnen(x+L_NODE_BREITE, py, p, "out", nid)

    def _port_zeichnen(self, x, y, name, art, nid):
        p_tag = f"port_{nid}_{name}"
        node_tag = f"node_{nid}"
        self.canvas.create_oval(x-15, y-15, x+15, y+15, fill="", outline="", tags=("port", p_tag, "node", node_tag))
        self.canvas.create_oval(x-L_PORT_RADIUS, y-L_PORT_RADIUS, x+L_PORT_RADIUS, y+L_PORT_RADIUS, 
                                fill="#1a1a1a", outline="#888", width=2, tags=("port", p_tag, "node", node_tag))

    def _get_node_detail(self, node):
        typ = node["typ"]
        if typ == "l_var": return node.get("variable", "Bitte wählen...")
        if typ == "l_match": return f"Bild: {node.get('template', '–')}"
        if typ == "l_const": return f"Wert: {node.get('wert', '0')}"
        if typ == "l_cmp": return f"{node.get('operator','=')} {node.get('wert','')}"
        return ""

    def _on_click(self, event):
        items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
        for item in items:
            tags = self.canvas.gettags(item)
            if "port" in tags:
                for t in tags:
                    if t.startswith("port_"):
                        parts = t.split("_")
                        self._drag_data["port"] = {"node_id": parts[1], "name": parts[2], "x": event.x, "y": event.y}
                        return
        for item in items:
            tags = self.canvas.gettags(item)
            if "node" in tags:
                for t in tags:
                    if t.startswith("node_"):
                        nid = t[5:]
                        node = next(n for n in self.nodes if n["id"] == nid)
                        self._drag_data["node"] = node
                        self._drag_data["offset_x"] = event.x - node["x"]
                        self._drag_data["offset_y"] = event.y - node["y"]
                        return

    def _on_drag(self, event):
        if self._drag_data["node"]:
            n = self._drag_data["node"]
            n["x"], n["y"] = event.x - self._drag_data["offset_x"], event.y - self._drag_data["offset_y"]
            self._alles_neu_zeichnen()
        elif self._drag_data["port"]:
            p = self._drag_data["port"]
            self.canvas.delete("temp_line")
            self.canvas.create_line(p["x"], p["y"], event.x, event.y, fill="white", width=2, dash=(4,4), tags="temp_line")

    def _on_release(self, event):
        if self._drag_data["port"]:
            items = self.canvas.find_overlapping(event.x-10, event.y-10, event.x+10, event.y+10)
            for item in items:
                tags = self.canvas.gettags(item)
                if "port" in tags:
                    for t in tags:
                        if t.startswith("port_"):
                            parts = t.split("_")
                            von_nid, von_port = self._drag_data["port"]["node_id"], self._drag_data["port"]["name"]
                            zu_nid, zu_port = parts[1], parts[2]
                            if von_nid != zu_nid and von_port == "out" and zu_port.startswith("in"):
                                self.connections = [c for c in self.connections if not (c["zu"] == zu_nid and c["port_zu"] == zu_port)]
                                self.connections.append({"von": von_nid, "port_von": von_port, "zu": zu_nid, "port_zu": zu_port})
            self.canvas.delete("temp_line")
            self._alles_neu_zeichnen()
        self._drag_data = {"node": None, "port": None}

    def _on_double_click(self, event):
        items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
        for item in items:
            tags = self.canvas.gettags(item)
            for t in tags:
                if t.startswith("node_"):
                    nid = t[5:]
                    node = next(n for n in self.nodes if n["id"] == nid)
                    self._node_parameter_editieren(node)
                    return

    def _on_right_click(self, event):
        items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
        for item in items:
            tags = self.canvas.gettags(item)
            for t in tags:
                if t.startswith("node_"):
                    nid = t[5:]
                    if not any(n["id"] == nid and n["typ"] == "l_result" for n in self.nodes):
                        self.nodes = [n for n in self.nodes if n["id"] != nid]
                        self.connections = [c for c in self.connections if c["von"] != nid and c["zu"] != nid]
                        self._alles_neu_zeichnen()
                    return

    def _node_parameter_editieren(self, node):
        typ = node["typ"]
        if typ in ("l_and", "l_or", "l_not", "l_result"): return
        popup = tk.Toplevel(self.dialog)
        popup.title(f"Konfiguration: {typ.upper()}")
        popup.geometry("450x350")
        popup.configure(bg="#2d2d2d")
        popup.grab_set()
        inhalt = tk.Frame(popup, bg="#2d2d2d", padx=25, pady=25)
        inhalt.pack(fill=tk.BOTH, expand=True)
        felder = {}
        
        if typ == "l_var":
            tk.Label(inhalt, text="Variable auswählen:", bg="#2d2d2d", fg="#aaa", font=("Segoe UI", 10)).pack(anchor="w")
            var_var = tk.StringVar(value=node.get("variable", ""))
            def _set_var(v): var_var.set(v)
            btn = tk.Button(inhalt, textvariable=var_var, bg="#1a1a1a", fg="#55ff88", relief=tk.FLAT, pady=10, font=("Segoe UI", 10, "bold"))
            btn.pack(fill=tk.X, pady=10)
            
            menu = tk.Menu(btn, tearoff=0, bg="#1a1a1a", fg="white")
            # 🔵 Game States
            s_menu = tk.Menu(menu, tearoff=0, bg="#1a1a1a", fg="white")
            for s in sorted(self.bot.app.state.game_states.keys()): s_menu.add_command(label=s, command=lambda x=s: _set_var(f"state::{x}"))
            menu.add_cascade(label="🔵 Game States", menu=s_menu)
            # 🔤 OCR Werte
            o_menu = tk.Menu(menu, tearoff=0, bg="#1a1a1a", fg="white")
            # Globale OCR Regionen
            for o in sorted(self.bot.ocr_engine.regionen.keys()): o_menu.add_command(label=f"🌐 {o}", command=lambda x=o: _set_var(f"ocr::{x}"))
            # Template OCR
            t_ocr = self.bot.ocr_engine.template_ocr_konfigurationen()
            if t_ocr:
                o_menu.add_separator()
                for t_name in sorted(t_ocr.keys()): o_menu.add_command(label=f"🖼 {t_name}", command=lambda x=t_name: _set_var(f"ocr::{x}"))
            menu.add_cascade(label="🔤 OCR Werte", menu=o_menu)
            # 📊 Datenbank-Listen
            try:
                from core import daten_manager as dm
                d_menu = tk.Menu(menu, tearoff=0, bg="#1a1a1a", fg="white")
                for l in dm.alle_listen():
                    l_menu = tk.Menu(d_menu, tearoff=0, bg="#1a1a1a", fg="white")
                    cache = dm.cache_lesen(l["id"])
                    for var in sorted(cache.keys()): l_menu.add_command(label=var, command=lambda ln=l["name"], vn=var: _set_var(f"db::{ln}::{vn}"))
                    d_menu.add_cascade(label=f"📊 {l['name']}", menu=l_menu)
                menu.add_cascade(label="📊 Datenbank", menu=d_menu)
            except: pass
            btn.config(command=lambda: menu.post(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height()))
            felder["variable"] = var_var

        elif typ == "l_match":
            tk.Label(inhalt, text="Template wählen (Gefunden = True):", bg="#2d2d2d", fg="#aaa").pack(anchor="w")
            tpl_var = tk.StringVar(value=node.get("template", ""))
            def _set_tpl(t): tpl_var.set(t)
            btn = tk.Button(inhalt, textvariable=tpl_var, bg="#1a1a1a", fg="#55ff88", relief=tk.FLAT, pady=10, font=("Segoe UI", 10, "bold"))
            btn.pack(fill=tk.X, pady=10)
            menu = tk.Menu(btn, tearoff=0, bg="#1a1a1a", fg="white")
            for t in sorted(self.bot.template_engine.settings.keys()): menu.add_command(label=t, command=lambda x=t: _set_tpl(x))
            btn.config(command=lambda: menu.post(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height()))
            felder["template"] = tpl_var

        elif typ == "l_const":
            tk.Label(inhalt, text="Konstanter Wert:", bg="#2d2d2d", fg="#aaa").pack(anchor="w")
            val_var = tk.StringVar(value=node.get("wert", "0"))
            tk.Entry(inhalt, textvariable=val_var, bg="#1a1a1a", fg="white", relief=tk.FLAT, font=("Segoe UI", 11), insertbackground="white").pack(fill=tk.X, pady=10)
            felder["wert"] = val_var

        elif typ == "l_cmp":
            tk.Label(inhalt, text="Vergleich (Input 1 gegen ...):", bg="#2d2d2d", fg="#aaa").pack(anchor="w")
            f = tk.Frame(inhalt, bg="#2d2d2d")
            f.pack(fill=tk.X, pady=10)
            op_var = tk.StringVar(value=node.get("operator", "="))
            tk.OptionMenu(f, op_var, "=", "!=", ">", "<", ">=", "<=").pack(side=tk.LEFT)
            val_var = tk.StringVar(value=node.get("wert", ""))
            tk.Entry(f, textvariable=val_var, bg="#1a1a1a", fg="white", relief=tk.FLAT, width=15, font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=10)
            tk.Label(inhalt, text="Tipp: Feld leer lassen, um Input 2 zu verwenden.", bg="#2d2d2d", fg="#666", font=("Segoe UI", 8)).pack(anchor="w", pady=5)
            felder["operator"] = op_var
            felder["wert"] = val_var

        def speichern():
            for k, v in felder.items(): node[k] = v.get()
            popup.destroy(); self._alles_neu_zeichnen()
        tk.Button(inhalt, text="Übernehmen", bg="#2ea043", fg="white", font=("Segoe UI", 10, "bold"), command=speichern, pady=8).pack(side=tk.BOTTOM, fill=tk.X)

    def _verbindung_zeichnen(self, c):
        n1 = next((n for n in self.nodes if n["id"] == c["von"]), None)
        n2 = next((n for n in self.nodes if n["id"] == c["zu"]), None)
        if not n1 or not n2: return
        x1, y1 = n1["x"] + L_NODE_BREITE, n1["y"] + L_NODE_HOEHE/2 + 12
        ins = L_PORTS[n2["typ"]][0]
        idx = ins.index(c["port_zu"])
        x2, y2 = n2["x"], n2["y"] + L_TITEL_HOEHE + 24 + (idx * 24)
        dx = abs(x2 - x1); offset = min(dx * 0.5, 100)
        self.canvas.create_line(x1, y1, x1+offset, y1, x2-offset, y2, x2, y2, fill="#4caf50", width=2, smooth=True, tags="conn")

    def _speichern(self):
        self.callback({"nodes": self.nodes, "connections": self.connections})
        self.dialog.destroy()
