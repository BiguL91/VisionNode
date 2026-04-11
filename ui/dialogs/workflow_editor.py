import tkinter as tk
import uuid
import threading
import time
from collections import defaultdict


# ── Visuelle Konstanten (in Welt-Koordinaten) ────────────────────────────────

NODE_BREITE  = 170
NODE_HOEHE   = 64
TITEL_HOEHE  = 22
PORT_RADIUS  = 7
CANVAS_BG    = "#1a1a1a"
NODE_BG      = "#2a2a2a"

NODE_FARBEN = {
    "start":          "#2ea043",
    "suche":          "#1e88e5",
    "suche_optional": "#00897b",
    "klick":          "#fb8c00",
    "warten":         "#546e7a",
    "zurueck":        "#8e24aa",
    "home":           "#8e24aa",
    "bedingung":      "#f9a825",
}

# (hat_eingang, [ausgangs_ports])
NODE_PORTS = {
    "start":          (False, ["out"]),
    "suche":          (True,  ["success", "failure"]),
    "suche_optional": (True,  ["out"]),
    "klick":          (True,  ["out", "failure"]),
    "warten":         (True,  ["out"]),
    "zurueck":        (True,  ["out"]),
    "home":           (True,  ["out"]),
    "bedingung":      (True,  ["true", "false"]),
}

PORT_FARBEN = {
    "out":     "#aaaaaa",
    "success": "#4caf50",
    "failure": "#ef5350",
    "true":    "#4caf50",
    "false":   "#ef5350",
    "in":      "#777777",
}

SCALE_MIN = 0.25
SCALE_MAX = 4.0


def _neue_id():
    return uuid.uuid4().hex[:8]


# ── Haupt-Dialog ─────────────────────────────────────────────────────────────

class WorkflowEditorDialog:
    """Visueller Workflow-Editor im Blueprint-Stil (Canvas-basiert).

    Bedienung:
        - Node-Typ-Button   → Node hinzufügen
        - Linksklick+Drag auf Node  → Node verschieben
        - Linksklick+Drag auf Port  → Verbindung ziehen
        - Linksklick+Drag auf Fläche → Canvas verschieben (Pan)
        - Scrollrad         → Zoom um Cursor-Position
        - Doppelklick Node  → Parameter bearbeiten
        - Rechtsklick Node/Verbindung → Löschen
    """

    def __init__(self, parent, bot, name, graph, callback):
        self.bot      = bot
        self.callback = callback

        # Arbeitskopien
        self.nodes       = [dict(n) for n in graph.get("nodes", [])]
        self.connections = [dict(c) for c in graph.get("connections", [])]

        # Neuer Workflow: Start-Node automatisch einfügen
        if not self.nodes:
            self.nodes.append({"id": _neue_id(), "typ": "start", "x": 80, "y": 240})

        # ── View-Transform ────────────────────────────────────────────────────
        self._scale = 1.0   # Zoom-Faktor
        self._tx    = 0.0   # Pan-Offset X (Canvas-Pixel)
        self._ty    = 0.0   # Pan-Offset Y (Canvas-Pixel)

        # ── Drag-Zustand ──────────────────────────────────────────────────────
        self._drag_node   = None
        self._drag_start  = (0.0, 0.0)   # Welt-Koordinaten beim Press
        self._drag_origin = (0.0, 0.0)   # Node-Position beim Press

        # ── Pan-Zustand ───────────────────────────────────────────────────────
        self._pan_aktiv = False
        self._pan_last  = (0, 0)         # Canvas-Pixel

        # ── Verbindungs-Drag-Zustand ──────────────────────────────────────────
        self._conn_drag_aktiv = False
        self._conn_drag_von   = None     # {"node": ..., "port": ...}

        # ── Simulations-Zustand ───────────────────────────────────────────────
        self._sim_aktiv   = False
        self._sim_zustand = {}           # node_id → "aktiv" | "success" | "failure"

        self._dialog_aufbauen(parent, name or "Neuer Workflow")

    # ── Transform-Hilfsfunktionen ─────────────────────────────────────────────

    def _cx(self, wx):
        """Welt-X → Canvas-X."""
        return wx * self._scale + self._tx

    def _cy(self, wy):
        """Welt-Y → Canvas-Y."""
        return wy * self._scale + self._ty

    def _wx(self, cx):
        """Canvas-X → Welt-X."""
        return (cx - self._tx) / self._scale

    def _wy(self, cy):
        """Canvas-Y → Welt-Y."""
        return (cy - self._ty) / self._scale

    # ── Dialog aufbauen ──────────────────────────────────────────────────────

    def _dialog_aufbauen(self, parent, name):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Workflow Editor 2.0")
        self.dialog.configure(bg="#2d2d2d")
        self.dialog.geometry("960x620")
        self.dialog.resizable(True, True)
        self.dialog.grab_set()
        self.dialog.protocol("WM_DELETE_WINDOW",
                             lambda: (self.callback(None, None), self.dialog.destroy()))

        self._toolbar_aufbauen(name)
        self._canvas_aufbauen()
        self._log_panel_aufbauen()
        self._statusbar_aufbauen()
        self.dialog.after(50, self._vollstaendige_neu_zeichnen)

    def _toolbar_aufbauen(self, name):
        bar = tk.Frame(self.dialog, bg="#2d2d2d", pady=5)
        bar.pack(fill=tk.X, padx=8)

        tk.Label(bar, text="Name:", bg="#2d2d2d", fg="#aaaaaa",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.name_var = tk.StringVar(value=name)
        tk.Entry(bar, textvariable=self.name_var, bg="#1a1a1a", fg="#ffffff",
                 relief=tk.FLAT, bd=4, font=("Segoe UI", 9),
                 width=20).pack(side=tk.LEFT, padx=(0, 12))

        tk.Frame(bar, bg="#444444", width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2, padx=(0, 8))
        tk.Label(bar, text="+ Node:", bg="#2d2d2d", fg="#666666",
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))

        typen = [
            ("Start",     "start"),
            ("Suche",     "suche"),
            ("Optional",  "suche_optional"),
            ("Klick",     "klick"),
            ("Warten",    "warten"),
            ("Zurueck",   "zurueck"),
            ("Home",      "home"),
            ("Bedingung", "bedingung"),
        ]
        for label, typ in typen:
            farbe = NODE_FARBEN.get(typ, "#555555")
            tk.Button(bar, text=label, bg=farbe, fg="white",
                      font=("Segoe UI", 8), relief=tk.FLAT, padx=7, pady=2,
                      cursor="hand2",
                      command=lambda t=typ: self._node_hinzufuegen(t)
                      ).pack(side=tk.LEFT, padx=2)

        tk.Frame(bar, bg="#444444", width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2, padx=(8, 8))
        self._sim_btn = tk.Button(
            bar, text="▶ Simulieren", bg="#1565c0", fg="white",
            font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=10, pady=2,
            cursor="hand2", command=self._simulation_toggle,
        )
        self._sim_btn.pack(side=tk.LEFT, padx=2)

    def _log_panel_aufbauen(self):
        """Scrollbares Log-Panel unterhalb des Canvas."""
        frame = tk.Frame(self.dialog, bg="#111111", height=90)
        frame.pack(fill=tk.X, padx=8, pady=(0, 2))
        frame.pack_propagate(False)

        self.log_text = tk.Text(
            frame, bg="#111111", fg="#cccccc",
            font=("Consolas", 8), relief=tk.FLAT,
            state=tk.DISABLED, wrap=tk.WORD,
            bd=0, highlightthickness=0,
        )
        sb = tk.Scrollbar(frame, command=self.log_text.yview,
                          bg="#222222", troughcolor="#111111", width=8)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        # Farb-Tags für das Log
        self.log_text.tag_config("aktiv",   foreground="#f9a825")
        self.log_text.tag_config("success", foreground="#4caf50")
        self.log_text.tag_config("failure", foreground="#ef5350")
        self.log_text.tag_config("info",    foreground="#90caf9")
        self.log_text.tag_config("done",    foreground="#aaaaaa")

    def _canvas_aufbauen(self):
        frame = tk.Frame(self.dialog, bg="#1a1a1a", bd=1, relief=tk.SOLID)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        self.canvas = tk.Canvas(frame, bg=CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Resize → alles neu zeichnen inkl. Hintergrund
        self.canvas.bind("<Configure>",      lambda e: self._vollstaendige_neu_zeichnen())

        # Alle Interaktionen auf Canvas-Widget-Ebene (zuverlässiger auf Windows)
        self.canvas.bind("<ButtonPress-1>",   self._canvas_press)
        self.canvas.bind("<B1-Motion>",       self._canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_release)
        self.canvas.bind("<Button-3>",        self._canvas_rechtsklick)

        # Zoom per Scrollrad (Windows: MouseWheel)
        self.canvas.bind("<MouseWheel>", self._zoomen)

    def _statusbar_aufbauen(self):
        bar = tk.Frame(self.dialog, bg="#2d2d2d")
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.status_label = tk.Label(bar, text="", bg="#2d2d2d", fg="#666666",
                                     font=("Segoe UI", 8))
        self.status_label.pack(side=tk.LEFT)

        tk.Button(bar, text="Abbrechen", bg="#444444", fg="white",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=12, pady=4,
                  cursor="hand2",
                  command=lambda: (self.callback(None, None), self.dialog.destroy())
                  ).pack(side=tk.RIGHT, padx=(4, 0))

        tk.Button(bar, text="Speichern", bg="#2ea043", fg="white",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=4,
                  cursor="hand2", command=self._speichern
                  ).pack(side=tk.RIGHT)

    # ── Zeichnen ─────────────────────────────────────────────────────────────

    def _vollstaendige_neu_zeichnen(self):
        """Alles inkl. Hintergrundgitter neu zeichnen (bei Resize/Zoom/Init)."""
        self.canvas.delete("all")
        self._hintergrund_zeichnen()
        for conn in self.connections:
            self._verbindung_zeichnen(conn)
        for node in self.nodes:
            self._node_zeichnen(node)
        self._status_aktualisieren()

    def _alles_neu_zeichnen(self):
        """Nur Nodes und Verbindungen neu zeichnen – Hintergrund bleibt."""
        self.canvas.delete("node")
        self.canvas.delete("connection")
        self.canvas.delete("temp_conn")
        for conn in self.connections:
            self._verbindung_zeichnen(conn)
        for node in self.nodes:
            self._node_zeichnen(node)
        self._status_aktualisieren()

    def _hintergrund_zeichnen(self):
        """Skaliertes Liniengitter als Hintergrund (einmalig bei Resize/Zoom)."""
        w       = self.canvas.winfo_width()
        h       = self.canvas.winfo_height()
        abstand = max(15, 30 * self._scale)

        # Gitter-Offset aus Pan berechnen
        off_x = self._tx % abstand
        off_y = self._ty % abstand

        x = off_x
        while x < w:
            self.canvas.create_line(x, 0, x, h, fill="#1f1f1f", tags="hintergrund")
            x += abstand
        y = off_y
        while y < h:
            self.canvas.create_line(0, y, w, y, fill="#1f1f1f", tags="hintergrund")
            y += abstand

    def _port_pos(self, node, port_name):
        """Canvas-Koordinaten eines Ports (berücksichtigt Zoom + Pan)."""
        x = self._cx(node["x"])
        y = self._cy(node["y"])
        w = NODE_BREITE * self._scale
        h = NODE_HOEHE  * self._scale
        hat_ein, aus_ports = NODE_PORTS.get(node["typ"], (True, ["out"]))

        if port_name == "in":
            return (x, y + h / 2)

        if port_name in aus_ports:
            n    = len(aus_ports)
            i    = aus_ports.index(port_name)
            frac = (i + 1) / (n + 1)
            return (x + w, y + h * frac)

        return (x + w / 2, y + h / 2)

    def _bezier_punkte(self, x1, y1, x2, y2):
        """Punkte einer kubischen Bézier-Kurve (Canvas-Koordinaten)."""
        offset = max(40 * self._scale, abs(x2 - x1) * 0.45)
        cx1, cy1 = x1 + offset, y1
        cx2, cy2 = x2 - offset, y2
        punkte = []
        for i in range(21):
            t  = i / 20
            mt = 1 - t
            bx = mt**3*x1 + 3*mt**2*t*cx1 + 3*mt*t**2*cx2 + t**3*x2
            by = mt**3*y1 + 3*mt**2*t*cy1 + 3*mt*t**2*cy2 + t**3*y2
            punkte.extend([bx, by])
        return punkte

    def _verbindung_zeichnen(self, conn):
        """Zeichnet eine Bézier-Verbindungslinie."""
        node_von = next((n for n in self.nodes if n["id"] == conn["von"]), None)
        node_zu  = next((n for n in self.nodes if n["id"] == conn["zu"]),  None)
        if not node_von or not node_zu:
            return

        x1, y1 = self._port_pos(node_von, conn["port_aus"])
        x2, y2 = self._port_pos(node_zu,  conn["port_ein"])
        farbe   = PORT_FARBEN.get(conn["port_aus"], "#aaaaaa")
        tag     = f"conn_{conn['von']}_{conn['port_aus']}"

        self.canvas.create_line(*self._bezier_punkte(x1, y1, x2, y2),
                                fill=farbe, width=max(1, 2 * self._scale),
                                tags=("connection", tag))
        self.canvas.create_oval(x2 - 4, y2 - 4, x2 + 4, y2 + 4,
                                fill=farbe, outline="",
                                tags=("connection", tag))
        self.canvas.tag_bind(tag, "<Button-3>",
                             lambda e, c=conn: self._verbindung_loeschen(c))

    def _node_zeichnen(self, node):
        """Zeichnet einen Node skaliert auf den Canvas."""
        s  = self._scale
        x  = self._cx(node["x"])
        y  = self._cy(node["y"])
        w  = NODE_BREITE * s
        h  = NODE_HOEHE  * s
        th = TITEL_HOEHE * s
        r  = max(3, PORT_RADIUS * s)

        typ   = node["typ"]
        nid   = node["id"]
        farbe = NODE_FARBEN.get(typ, "#555555")
        tag   = f"node_{nid}"
        hat_ein, aus_ports = NODE_PORTS.get(typ, (True, ["out"]))

        fs      = max(6,  int(8 * s))   # Schriftgröße Titel
        fs_par  = max(5,  int(8 * s))   # Schriftgröße Parameter
        fs_port = max(5,  int(7 * s))   # Schriftgröße Port-Label

        # Simulations-Highlight
        sim_status = self._sim_zustand.get(nid)
        if sim_status == "aktiv":
            rahmen_farbe = "#f9a825"
            rahmen_breite = max(3, 3 * s)
            koerper_bg    = "#2e2a1a"
        elif sim_status == "success":
            rahmen_farbe = "#4caf50"
            rahmen_breite = max(2, 2 * s)
            koerper_bg    = "#1a2e1a"
        elif sim_status == "failure":
            rahmen_farbe = "#ef5350"
            rahmen_breite = max(2, 2 * s)
            koerper_bg    = "#2e1a1a"
        else:
            rahmen_farbe  = farbe
            rahmen_breite = max(1, 2 * s)
            koerper_bg    = NODE_BG

        # Schatten (bei aktiv etwas größer für Glow-Effekt)
        if sim_status == "aktiv":
            for off in (5, 3):
                self.canvas.create_rectangle(x+off, y+off, x+w+off, y+h+off,
                                             fill="#3a2e00", outline="",
                                             tags=(tag, "node"))
        else:
            self.canvas.create_rectangle(x+3, y+3, x+w+3, y+h+3,
                                         fill="#111111", outline="",
                                         tags=(tag, "node"))
        # Körper
        self.canvas.create_rectangle(x, y, x+w, y+h,
                                     fill=koerper_bg, outline=rahmen_farbe,
                                     width=rahmen_breite,
                                     tags=(tag, "node"))
        # Titel-Streifen
        self.canvas.create_rectangle(x+2, y+2, x+w-2, y+th,
                                     fill=farbe, outline="",
                                     tags=(tag, "node"))
        self.canvas.create_text(x + w/2, y + th/2 + 1,
                                text=typ.upper(), fill="white",
                                font=("Segoe UI", fs, "bold"),
                                tags=(tag, "node"))

        # Parameter-Text
        detail = self._node_detail(node)
        if detail and s > 0.4:
            self.canvas.create_text(x + w/2, y + th + (h - th)/2,
                                    text=detail, fill="#cccccc",
                                    font=("Segoe UI", fs_par),
                                    width=w - 14,
                                    tags=(tag, "node"))

        # Eingangs-Port (links)
        if hat_ein:
            px, py   = self._port_pos(node, "in")
            port_tag = f"port_{nid}_in"
            self.canvas.create_oval(px-r, py-r, px+r, py+r,
                                    fill="#333333", outline="#888888",
                                    width=max(1, 2*s),
                                    tags=(tag, "node", port_tag, "port"))

        # Ausgangs-Ports (rechts)
        for port in aus_ports:
            px, py   = self._port_pos(node, port)
            pfarbe   = PORT_FARBEN.get(port, "#aaaaaa")
            port_tag = f"port_{nid}_{port}"
            self.canvas.create_oval(px-r, py-r, px+r, py+r,
                                    fill=pfarbe, outline="white",
                                    width=max(1, s),
                                    tags=(tag, "node", port_tag, "port"))
            if len(aus_ports) > 1 and s > 0.5:
                self.canvas.create_text(px + r + 2, py,
                                        text=port, fill=pfarbe,
                                        font=("Segoe UI", fs_port),
                                        anchor="w",
                                        tags=(tag, "node"))

        # Node-Events (Drag + Doppelklick)
        self.canvas.tag_bind(tag, "<ButtonPress-1>",
                             lambda e, n=node: self._node_drag_start(e, n))
        self.canvas.tag_bind(tag, "<B1-Motion>",
                             lambda e, n=node: self._node_drag_bewegen(e, n))
        self.canvas.tag_bind(tag, "<ButtonRelease-1>",
                             lambda e: self._node_drag_ende())
        self.canvas.tag_bind(tag, "<Button-3>",
                             lambda e, n=node: self._node_kontext_menu(e, n))
        self.canvas.tag_bind(tag, "<Double-Button-1>",
                             lambda e, n=node: self._node_parameter_editieren(e, n))

    def _node_detail(self, node):
        """Kurztext der Node-Parameter."""
        typ = node.get("typ")
        nid = node.get("id")

        # Live-Countdown während der Simulation zeigen
        if self._sim_aktiv and self._sim_zustand.get(nid) == "aktiv":
            prog = self._sim_progress.get(nid)
            if prog: return prog

        if typ in ("suche", "suche_optional", "klick"):
            tpl = node.get("template", "–")
            to  = node.get("timeout")
            return tpl + (f"  [{to}s]" if to else "")
        elif typ == "warten":
            return f"{node.get('sekunden', 1.0)} s"
        elif typ == "bedingung":
            return (f"{node.get('variable','?')} "
                    f"{node.get('operator','=')} "
                    f"{node.get('wert','0')}")
        return ""

    # ── Template-Picker (gruppiert) ───────────────────────────────────────────

    def _template_picker_bauen(self, eltern_frame, tpl_var):
        """Erstellt einen gruppierten Template-Picker als Menubutton.
        Struktur: Kategorie (Workflow / State) → Gruppe → Templates
        """
        engine   = self.bot.template_engine
        settings = engine.settings

        def _waehlen(name):
            tpl_var.set(name)

        # Passive Gruppen aus Settings
        passive_gruppen = {
            engine._gruppe_vollpfad(k)
            for k, v in settings.items()
            if isinstance(v, dict) and v.get("typ") == "passiv_gruppe"
        }

        def _gruppen_menu_fuellen(ziel_menu, kat_filter):
            """Füllt ein Menu mit Gruppen+Templates der angegebenen Kategorie."""
            nach_gruppen = defaultdict(list)
            for name, t in engine.templates.items():
                if name.startswith("_") or "__" in name:
                    continue
                kat = settings.get(name, {}).get("kategorie", "workflow")
                if kat != kat_filter:
                    continue
                g = (t["gruppe"] or "").strip().replace("\\", "/")
                nach_gruppen[g].append(name)

            # Globale Templates (ohne Gruppe) zuerst
            if nach_gruppen.get(""):
                for name in sorted(nach_gruppen[""]):
                    ziel_menu.add_command(
                        label=f"  {name}", command=lambda n=name: _waehlen(n))
                if len(nach_gruppen) > 1:
                    ziel_menu.add_separator()

            # Passive Gruppen dieser Kategorie
            kat_passive = {
                engine._gruppe_vollpfad(k)
                for k, v in settings.items()
                if isinstance(v, dict)
                and v.get("typ") == "passiv_gruppe"
                and v.get("kategorie", "workflow") == kat_filter
            }

            alle_gruppen = sorted(
                (set(nach_gruppen.keys()) - {""}) | kat_passive,
                key=lambda x: x.lower()
            )

            for gruppe in alle_gruppen:
                kurzname   = gruppe.split("/")[-1]
                ist_passiv = gruppe in passive_gruppen
                hat_master = kurzname in engine.templates and (
                    engine.templates[kurzname].get("gruppe", "").replace("\\", "/")
                    == "/".join(gruppe.split("/")[:-1])
                    or kurzname == gruppe
                )

                if hat_master:
                    prefix = "★ "
                elif ist_passiv:
                    prefix = "📦 "
                else:
                    prefix = "📁 "

                kinder = sorted(n for n in nach_gruppen.get(gruppe, []) if n != kurzname)

                if not kinder and not hat_master:
                    ziel_menu.add_command(
                        label=f"{prefix}{kurzname}  (leer)",
                        foreground="#555555",
                        state="disabled",
                    )
                    continue

                sub = tk.Menu(ziel_menu, tearoff=0, bg="#1a1a1a", fg="#ffffff",
                              activebackground="#333333", activeforeground="#ffffff",
                              font=("Segoe UI", 9))
                ziel_menu.add_cascade(label=f"{prefix}{kurzname}", menu=sub)

                if hat_master:
                    sub.add_command(
                        label=f"★ {kurzname}  (Master)",
                        foreground="#ffca28",
                        command=lambda n=kurzname: _waehlen(n),
                    )
                    if kinder:
                        sub.add_separator()

                for name in kinder:
                    sub.add_command(label=f"  {name}", command=lambda n=name: _waehlen(n))

            if not nach_gruppen and not kat_passive:
                ziel_menu.add_command(label="  (keine Templates)", state="disabled")

        # ── Menubutton ────────────────────────────────────────────────────────
        btn = tk.Menubutton(
            eltern_frame,
            textvariable=tpl_var,
            bg="#1a1a1a", fg="#ffffff",
            relief=tk.FLAT, bd=2,
            font=("Segoe UI", 9),
            width=22,
            anchor="w",
            cursor="hand2",
        )
        btn.pack(side=tk.LEFT)

        haupt_menu = tk.Menu(btn, tearoff=0, bg="#1a1a1a", fg="#ffffff",
                             activebackground="#333333", activeforeground="#ffffff",
                             font=("Segoe UI", 9))
        btn["menu"] = haupt_menu

        # Kategorie-Ebene: Workflow + State als Kaskaden
        wf_menu = tk.Menu(haupt_menu, tearoff=0, bg="#1a1a1a", fg="#ffffff",
                          activebackground="#333333", activeforeground="#ffffff",
                          font=("Segoe UI", 9))
        haupt_menu.add_cascade(label="🔄 Workflow", menu=wf_menu)
        _gruppen_menu_fuellen(wf_menu, "workflow")

        st_menu = tk.Menu(haupt_menu, tearoff=0, bg="#1a1a1a", fg="#ffffff",
                          activebackground="#333333", activeforeground="#ffffff",
                          font=("Segoe UI", 9))
        haupt_menu.add_cascade(label="🚩 State", menu=st_menu)
        _gruppen_menu_fuellen(st_menu, "state")

        return btn

    def _variablen_picker_bauen(self, eltern_frame, var_var):
        """Grupierter Variablen-Picker: State / OCR / Daten-Listen."""

        def _waehlen(name):
            var_var.set(name)

        def _sub(parent):
            return tk.Menu(parent, tearoff=0, bg="#1a1a1a", fg="#ffffff",
                           activebackground="#333333", activeforeground="#ffffff",
                           font=("Segoe UI", 9))

        btn = tk.Menubutton(
            eltern_frame,
            textvariable=var_var,
            bg="#1a1a1a", fg="#ffffff",
            relief=tk.FLAT, bd=2,
            font=("Segoe UI", 9),
            width=22, anchor="w",
            cursor="hand2",
        )
        btn.pack(side=tk.LEFT)

        haupt = _sub(btn)
        btn["menu"] = haupt

        # ── 🔵 State (True / False) ───────────────────────────────────────
        st_menu = _sub(haupt)
        haupt.add_cascade(label="🔵 State  (True / False)", menu=st_menu)
        try:
            states = sorted(self.bot.app.state.game_states.keys())
        except Exception:
            states = []
        if states:
            for name in states:
                st_menu.add_command(
                    label=f"  {name}",
                    command=lambda n=name: _waehlen(f"state::{n}"),
                )
        else:
            st_menu.add_command(label="  (keine States)", state="disabled")

        # ── 🔤 OCR (Zahl / Timer) ─────────────────────────────────────────
        ocr_menu = _sub(haupt)
        haupt.add_cascade(label="🔤 OCR  (Zahl / Timer)", menu=ocr_menu)
        try:
            ocr_vars = sorted(self.bot.app.state.get_all_ocr().keys())
        except Exception:
            ocr_vars = []
        if ocr_vars:
            for name in ocr_vars:
                ocr_menu.add_command(
                    label=f"  {name}",
                    command=lambda n=name: _waehlen(f"ocr::{n}"),
                )
        else:
            ocr_menu.add_command(label="  (keine OCR-Variablen)", state="disabled")

        # ── 📊 Daten-Listen (Transform / Berechnung) ──────────────────────
        db_menu = _sub(haupt)
        haupt.add_cascade(label="📊 Daten-Listen", menu=db_menu)
        try:
            from core import daten_manager as dm
            listen = dm.alle_listen()
            if listen:
                for liste in listen:
                    lsub = _sub(db_menu)
                    db_menu.add_cascade(label=f"  {liste['name']}", menu=lsub)

                    trans  = dm.transformationen_der_liste(liste["id"])
                    berech = dm.berechnungen_der_liste(liste["id"])

                    if trans:
                        lsub.add_command(label="— Transformationen —",
                                         state="disabled", foreground="#666666")
                        for t in trans:
                            lsub.add_command(
                                label=f"  {t['name']}",
                                command=lambda ln=liste["name"], tn=t["name"]:
                                    _waehlen(f"db::{ln}::{tn}"),
                            )
                    if berech:
                        if trans:
                            lsub.add_separator()
                        lsub.add_command(label="— Berechnungen —",
                                         state="disabled", foreground="#666666")
                        for b in berech:
                            lsub.add_command(
                                label=f"  {b['name']}",
                                command=lambda ln=liste["name"], bn=b["name"]:
                                    _waehlen(f"db::{ln}::{bn}"),
                            )
                    if not trans and not berech:
                        lsub.add_command(label="  (keine Ausgaben)", state="disabled")
            else:
                db_menu.add_command(label="  (keine Listen)", state="disabled")
        except Exception:
            db_menu.add_command(label="  (DB nicht verfügbar)", state="disabled")

        return btn

    # ── Zoom & Pan ───────────────────────────────────────────────────────────

    def _zoomen(self, event):
        """Scrollrad → Zoom um Cursor-Position."""
        faktor = 1.12 if event.delta > 0 else (1 / 1.12)
        neuer_scale = max(SCALE_MIN, min(SCALE_MAX, self._scale * faktor))
        if neuer_scale == self._scale:
            return

        # Cursor-Position soll Welt-Position behalten
        cx, cy = event.x, event.y
        self._tx = cx + (self._tx - cx) * (neuer_scale / self._scale)
        self._ty = cy + (self._ty - cy) * (neuer_scale / self._scale)
        self._scale = neuer_scale

        self._vollstaendige_neu_zeichnen()

    # ── Einheitlicher Canvas-Event-Handler ───────────────────────────────────

    def _canvas_press(self, event):
        """Erkennt: Ausgangs-Port-Klick → Verbindung; sonst → Pan."""
        r       = max(PORT_RADIUS, PORT_RADIUS * self._scale) + 4
        treffer = self.canvas.find_overlapping(
            event.x - r, event.y - r, event.x + r, event.y + r)

        for item in reversed(treffer):
            for tag in self.canvas.gettags(item):
                if tag.startswith("port_") and "_" in tag[5:] and not tag.endswith("_in"):
                    teile = tag.split("_", 2)
                    if len(teile) == 3:
                        nid, port_name = teile[1], teile[2]
                        von_node = next((n for n in self.nodes if n["id"] == nid), None)
                        if von_node:
                            self._conn_drag_aktiv = True
                            self._conn_drag_von   = {"node": von_node, "port": port_name}
                            self._drag_node       = None
                            return

        # Kein Port getroffen → Pan starten (falls auch kein Node)
        naechstes = self.canvas.find_closest(event.x, event.y)
        auf_node  = naechstes and "node" in self.canvas.gettags(naechstes[0])
        if not auf_node:
            self._pan_aktiv = True
            self._pan_last  = (event.x, event.y)

    def _canvas_drag(self, event):
        """Verteilt B1-Motion an: Verbindungs-Vorschau oder Pan."""
        if self._conn_drag_aktiv and self._conn_drag_von:
            # Gestrichelte Vorschau-Linie aktualisieren
            von_node = self._conn_drag_von["node"]
            von_port = self._conn_drag_von["port"]
            px, py   = self._port_pos(von_node, von_port)
            farbe    = PORT_FARBEN.get(von_port, "#aaaaaa")
            self.canvas.delete("temp_conn")
            self.canvas.create_line(px, py, event.x, event.y,
                                    fill=farbe, width=2, dash=(6, 4),
                                    tags="temp_conn")
        elif self._pan_aktiv:
            dx = event.x - self._pan_last[0]
            dy = event.y - self._pan_last[1]
            self._pan_last = (event.x, event.y)
            self._tx += dx
            self._ty += dy
            # Gitter mitverschieben (günstiger als alles neu zeichnen)
            self.canvas.move("hintergrund", dx, dy)
            self.canvas.move("node",        dx, dy)
            self.canvas.move("connection",  dx, dy)
            # Node-Weltkoordinaten bleiben unverändert – nur _tx/_ty ist verschoben

    def _canvas_release(self, event):
        """B1-Release: Verbindung abschließen oder Pan beenden."""
        if self._conn_drag_aktiv:
            self._conn_drag_ende(event)
        self._pan_aktiv = False

    # ── Node-Drag ────────────────────────────────────────────────────────────

    def _node_drag_start(self, event, node):
        if self._conn_drag_aktiv or self._pan_aktiv:
            return
        self._drag_node   = node
        self._drag_start  = (self._wx(event.x), self._wy(event.y))
        self._drag_origin = (node["x"], node["y"])

    def _node_drag_bewegen(self, event, node):
        if self._drag_node is None or self._conn_drag_aktiv or self._pan_aktiv:
            return
        wx = self._wx(event.x)
        wy = self._wy(event.y)
        neues_x = self._drag_origin[0] + (wx - self._drag_start[0])
        neues_y = self._drag_origin[1] + (wy - self._drag_start[1])

        # Canvas-Delta in Pixel berechnen (Skala berücksichtigen)
        move_dx = (neues_x - node["x"]) * self._scale
        move_dy = (neues_y - node["y"]) * self._scale

        node["x"] = neues_x
        node["y"] = neues_y

        self.canvas.move(f"node_{node['id']}", move_dx, move_dy)

        # Nur betroffene Verbindungen neu zeichnen
        nid = node["id"]
        for conn in self.connections:
            if conn["von"] == nid or conn["zu"] == nid:
                conn_tag = f"conn_{conn['von']}_{conn['port_aus']}"
                self.canvas.delete(conn_tag)
                self._verbindung_zeichnen(conn)

    def _node_drag_ende(self):
        self._drag_node = None

    # ── Verbindungs-Drag Abschluss ────────────────────────────────────────────

    def _conn_drag_ende(self, event):
        """Erstellt Verbindung wenn Eingangs-Port getroffen wurde."""
        self._conn_drag_aktiv = False
        self.canvas.delete("temp_conn")

        von = self._conn_drag_von
        self._conn_drag_von = None
        if von is None:
            return

        # Eingangs-Port unter Cursor suchen
        r       = max(PORT_RADIUS, PORT_RADIUS * self._scale) + 5
        treffer = self.canvas.find_overlapping(
            event.x - r, event.y - r, event.x + r, event.y + r)
        ziel_node = None
        for item in reversed(treffer):
            for tag in self.canvas.gettags(item):
                if tag.startswith("port_") and tag.endswith("_in"):
                    nid       = tag[5:-3]
                    ziel_node = next((n for n in self.nodes if n["id"] == nid), None)
                    break
            if ziel_node:
                break

        if not ziel_node or ziel_node["id"] == von["node"]["id"]:
            return

        # Bestehende Verbindung vom selben Port ersetzen
        self.connections = [c for c in self.connections
                            if not (c["von"] == von["node"]["id"]
                                    and c["port_aus"] == von["port"])]
        self.connections.append({
            "von":      von["node"]["id"],
            "port_aus": von["port"],
            "zu":       ziel_node["id"],
            "port_ein": "in",
        })

        # Auto-Vererbung: suche → klick übernimmt Template automatisch
        self._template_vererben(von["node"], ziel_node)

        self._alles_neu_zeichnen()

    def _template_vererben(self, von_node, zu_node):
        """Überträgt das Template von einem Suche-Node auf einen Klick-Node,
        wenn der Klick-Node noch kein Template hat."""
        if von_node.get("typ") not in ("suche", "suche_optional"):
            return
        if zu_node.get("typ") != "klick":
            return
        if zu_node.get("template"):
            return  # Klick-Node hat bereits ein Template → nicht überschreiben
        tpl = von_node.get("template", "")
        if tpl:
            zu_node["template"] = tpl

    # ── Node-Verwaltung ──────────────────────────────────────────────────────

    def _node_hinzufuegen(self, typ):
        """Neuen Node in der Mitte des sichtbaren Bereichs platzieren."""
        w      = max(self.canvas.winfo_width(),  300)
        h      = max(self.canvas.winfo_height(), 200)
        offset = (len(self.nodes) % 8) * 22
        # Canvas-Mitte → Welt-Koordinaten
        wx = self._wx(w / 2) - NODE_BREITE / 2 + offset
        wy = self._wy(h / 2) - NODE_HOEHE  / 2 + offset

        node = {"id": _neue_id(), "typ": typ, "x": wx, "y": wy}

        if typ in ("suche", "suche_optional"):
            node["template"] = ""
            node["timeout"]  = 10
        elif typ == "klick":
            node["template"] = ""
        elif typ == "warten":
            node["sekunden"] = 2.0
        elif typ == "bedingung":
            node["variable"] = ""
            node["operator"] = ">"
            node["wert"]     = "0"

        self.nodes.append(node)
        self._alles_neu_zeichnen()

    def _node_kontext_menu(self, event, node):
        menu = tk.Menu(self.canvas, tearoff=0, bg="#2d2d2d", fg="#cccccc",
                       activebackground="#444444", activeforeground="#ffffff",
                       font=("Segoe UI", 9))
        menu.add_command(label=f"Node loeschen ({node['typ']})",
                         command=lambda: self._node_loeschen(node))
        menu.add_separator()
        menu.add_command(label="Parameter bearbeiten",
                         command=lambda: self._node_parameter_editieren(None, node))
        menu.tk_popup(event.x_root, event.y_root)

    def _node_loeschen(self, node):
        nid = node["id"]
        self.nodes       = [n for n in self.nodes if n["id"] != nid]
        self.connections = [c for c in self.connections
                            if c["von"] != nid and c["zu"] != nid]
        self._alles_neu_zeichnen()

    def _canvas_rechtsklick(self, event):
        pass  # Node-eigenes Menü übernimmt

    def _verbindung_loeschen(self, conn):
        if conn in self.connections:
            self.connections.remove(conn)
            self._alles_neu_zeichnen()

    # ── Parameter-Editor ─────────────────────────────────────────────────────

    def _node_parameter_editieren(self, event, node):
        typ = node.get("typ")
        if typ in ("start", "zurueck", "home"):
            return

        popup = tk.Toplevel(self.dialog)
        popup.title(f"{typ.upper()} – Parameter")
        popup.configure(bg="#2d2d2d")
        popup.grab_set()
        popup.resizable(False, False)

        inhalt = tk.Frame(popup, bg="#2d2d2d")
        inhalt.pack(padx=16, pady=12, fill=tk.BOTH)

        felder = {}

        def zeile(label, key, breite=22):
            f = tk.Frame(inhalt, bg="#2d2d2d")
            f.pack(fill=tk.X, pady=3)
            tk.Label(f, text=label, bg="#2d2d2d", fg="#aaaaaa",
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(node.get(key, "")))
            tk.Entry(f, textvariable=var, bg="#1a1a1a", fg="#ffffff",
                     relief=tk.FLAT, bd=4, font=("Segoe UI", 9),
                     width=breite).pack(side=tk.LEFT)
            felder[key] = var

        if typ in ("suche", "suche_optional", "klick"):
            f = tk.Frame(inhalt, bg="#2d2d2d")
            f.pack(fill=tk.X, pady=3)
            tk.Label(f, text="Template:", bg="#2d2d2d", fg="#aaaaaa",
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side=tk.LEFT)
            tpl_var = tk.StringVar(value=node.get("template", ""))
            if self.bot:
                self._template_picker_bauen(f, tpl_var)
            else:
                tk.Entry(f, textvariable=tpl_var, bg="#1a1a1a", fg="#ffffff",
                         relief=tk.FLAT, bd=4, font=("Segoe UI", 9),
                         width=22).pack(side=tk.LEFT)
            felder["template"] = tpl_var
            if typ in ("suche", "suche_optional"):
                zeile("Timeout (s):", "timeout", 8)

        elif typ == "warten":
            zeile("Sekunden:", "sekunden", 8)

        elif typ == "bedingung":
            f = tk.Frame(inhalt, bg="#2d2d2d")
            f.pack(fill=tk.X, pady=3)
            tk.Label(f, text="Variable:", bg="#2d2d2d", fg="#aaaaaa",
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side=tk.LEFT)
            var_var = tk.StringVar(value=node.get("variable", ""))
            if self.bot:
                self._variablen_picker_bauen(f, var_var)
            else:
                tk.Entry(f, textvariable=var_var, bg="#1a1a1a", fg="#ffffff",
                         relief=tk.FLAT, bd=4, font=("Segoe UI", 9),
                         width=20).pack(side=tk.LEFT)
            felder["variable"] = var_var

            f2 = tk.Frame(inhalt, bg="#2d2d2d")
            f2.pack(fill=tk.X, pady=3)
            tk.Label(f2, text="Operator:", bg="#2d2d2d", fg="#aaaaaa",
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side=tk.LEFT)
            op_var = tk.StringVar(value=node.get("operator", ">"))
            for op in [">", "<", ">=", "<=", "=", "!="]:
                tk.Radiobutton(f2, text=op, variable=op_var, value=op,
                               bg="#2d2d2d", fg="#cccccc", selectcolor="#444",
                               activebackground="#2d2d2d",
                               font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=3)
            felder["operator"] = op_var
            zeile("Wert:", "wert", 12)

        def anwenden():
            for key, var in felder.items():
                wert = var.get().strip()
                if key == "timeout":
                    try:    node[key] = int(wert)
                    except: node[key] = 10
                elif key == "sekunden":
                    try:    node[key] = float(wert)
                    except: node[key] = 1.0
                else:
                    node[key] = wert
            popup.destroy()
            self._alles_neu_zeichnen()

        btn_f = tk.Frame(inhalt, bg="#2d2d2d")
        btn_f.pack(fill=tk.X, pady=(10, 0))
        tk.Button(btn_f, text="Abbrechen", bg="#444", fg="white",
                  relief=tk.FLAT, padx=10, pady=4,
                  command=popup.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_f, text="Anwenden", bg="#2ea043", fg="white",
                  relief=tk.FLAT, padx=10, pady=4,
                  command=anwenden).pack(side=tk.RIGHT)

    # ── Hilfs-Funktionen ─────────────────────────────────────────────────────

    # ── Simulation ───────────────────────────────────────────────────────────

    class SimulatedActionEngine:
        """Imitiert die ActionEngine für die Simulation.
        Fragt bei jeder Aktion nach: Simulieren oder Ausführen?
        """
        def __init__(self, parent_dialog, real_engine, log_func):
            self.parent = parent_dialog
            self.real   = real_engine
            self.log    = log_func

        def _entscheidung_einholen(self, titel, msg):
            """Fragt den Nutzer via UI nach der gewünschten Aktion."""
            # Da wir in einem Thread sind, nutzen wir eine Thread-sichere Abfrage
            ergebnis = {"wahl": "sim"} # Default: nur loggen
            event = threading.Event()

            def _ui_abfrage():
                popup = tk.Toplevel(self.parent.dialog)
                popup.title("Aktion Bestätigen")
                popup.configure(bg="#2d2d2d")
                popup.geometry("350x180")
                popup.resizable(False, False)
                popup.grab_set()
                
                # Zentrieren
                px = self.parent.dialog.winfo_x() + (self.parent.dialog.winfo_width() // 2) - 175
                py = self.parent.dialog.winfo_y() + (self.parent.dialog.winfo_height() // 2) - 90
                popup.geometry(f"+{px}+{py}")

                tk.Label(popup, text=titel, bg="#2d2d2d", fg="#ffffff",
                         font=("Segoe UI", 10, "bold")).pack(pady=(15, 5))
                tk.Label(popup, text=msg, bg="#2d2d2d", fg="#aaaaaa",
                         font=("Segoe UI", 9), wraplength=300).pack(pady=(0, 20))

                btn_f = tk.Frame(popup, bg="#2d2d2d")
                btn_f.pack(fill=tk.X, padx=20)

                def _wahl(w):
                    ergebnis["wahl"] = w
                    popup.destroy()
                    event.set()

                tk.Button(btn_f, text="Simulieren", bg="#444444", fg="white",
                          relief=tk.FLAT, padx=10, pady=5, width=10,
                          command=lambda: _wahl("sim")).pack(side=tk.LEFT, padx=2)
                
                tk.Button(btn_f, text="ADB Ausführen", bg="#2ea043", fg="white",
                          relief=tk.FLAT, padx=10, pady=5, width=12,
                          command=lambda: _wahl("adb")).pack(side=tk.LEFT, padx=2)
                
                tk.Button(btn_f, text="Abbrechen", bg="#da3633", fg="white",
                          relief=tk.FLAT, padx=10, pady=5, width=10,
                          command=lambda: _wahl("stop")).pack(side=tk.LEFT, padx=2)

                popup.protocol("WM_DELETE_WINDOW", lambda: _wahl("stop"))

            self.parent.dialog.after(0, _ui_abfrage)
            event.wait() # Warten bis Nutzer geklickt hat
            return ergebnis["wahl"]

        def auf_template_warten(self, template, matches_func, timeout=10, intervall=0.3, log_func=None, laeuft_func=None):
            # Nutzt die echte Logik der ActionEngine und gibt log_func/laeuft_func weiter
            return self.real.auf_template_warten(template, matches_func, timeout, intervall, log_func=log_func, laeuft_func=laeuft_func)

        def template_tippen(self, template, matches, log_func=None):
            for m in matches:
                if m[0] == template:
                    _, mx, my, mw, mh = m[:5]
                    kx, ky = self.real.klickpunkt_berechnen(template, mx, my, mw, mh)
                    
                    wahl = self._entscheidung_einholen("KLICK-AKTION", f"Soll auf '{template}' an ({kx}, {ky}) geklickt werden?")
                    
                    if wahl == "stop":
                        self.parent._simulation_stoppen()
                        return False
                    
                    if wahl == "adb":
                        self.log(f"[ADB] Klick auf {template} ({kx}, {ky})", "success")
                        return self.real.template_tippen(template, matches, log_func=None)
                    else:
                        self.log(f"[SIM] Klick auf {template} ({kx}, {ky}) (nur simuliert)", "info")
                        return True
            return False

        def warten(self, sekunden):
            time.sleep(min(sekunden, 2.0))

        def zurueck(self):
            wahl = self._entscheidung_einholen("ZURÜCK", "Soll der Zurück-Button gedrückt werden?")
            if wahl == "adb":
                self.log("[ADB] Zurück-Button", "success")
                self.real.zurueck()
            elif wahl == "stop":
                self.parent._simulation_stoppen()
            else:
                self.log("[SIM] Zurück-Button (nur simuliert)", "info")

        def home(self):
            wahl = self._entscheidung_einholen("HOME", "Soll der Home-Button gedrückt werden?")
            if wahl == "adb":
                self.log("[ADB] Home-Button", "success")
                self.real.home()
            elif wahl == "stop":
                self.parent._simulation_stoppen()
            else:
                self.log("[SIM] Home-Button (nur simuliert)", "info")

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

        self._sim_aktiv   = True
        self._sim_zustand = {}
        self._sim_progress = {}
        self._sim_btn.config(text="⏹ Stopp", bg="#b71c1c")

        # Log leeren
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

        self._sim_log("▶ Live-Simulation gestartet", "info")
        
        # Hilfs-Engines für die Simulation vorbereiten
        self._sim_engine = self.SimulatedActionEngine(self, self.bot.action_engine, self._sim_log)
        
        nodes_index = {n["id"]: n for n in self.nodes}
        self._simulation_schritt(start, nodes_index, 0)

    def _simulation_stoppen(self):
        self._sim_aktiv = False
        self._sim_btn.config(text="▶ Simulieren", bg="#1565c0")
        self._sim_zustand = {}
        self._sim_progress = {}
        self._alles_neu_zeichnen()
        self._status_aktualisieren()

    def _simulation_schritt(self, node, nodes_index, schritt):
        """Führt einen Node mit echten Daten aus und traversiert zum nächsten."""
        if not self._sim_aktiv or node is None or schritt > 200:
            self._simulation_fertig()
            return

        nid = node["id"]
        typ = node.get("typ", "?")

        # Node als aktiv markieren
        self._sim_zustand[nid] = "aktiv"
        self._sim_progress.pop(nid, None)
        self._alles_neu_zeichnen()

        detail = self._node_detail(node)
        self._sim_log(f"► {typ.upper()}" + (f":  {detail}" if detail else ""), "aktiv")

        def _ausfuehren():
            if not self._sim_aktiv: return

            # Live-Daten Funktionen vorbereiten
            def m_func(): return self.bot.app.state.active_matches
            def o_func():
                # Kombiniert OCR-Werte und Game-States für die Engine
                data = dict(self.bot.app.state.ocr_values)
                for s_name, s_val in self.bot.app.state.game_states.items():
                    data[f"__state__{s_name}"] = "true" if s_val else "false"
                # Auch Template-OCR hinzufügen
                data.update(self.bot.app.state.template_ocr_values)
                return data

            # Echte Logik der WorkflowEngine nutzen
            port = self.bot.workflow_engine._node_ausfuehren(
                node, self._sim_engine, m_func, ocr_func=o_func, 
                log_func=self._sim_log, laeuft_func=lambda: self._sim_aktiv
            )

            if port is None:
                self._sim_log(f"  !! Unbekannter Node-Typ: {typ}", "failure")
                self._sim_zustand[nid] = "failure"
                self._simulation_fertig()
                return

            # Status des Nodes setzen (visuell)
            self._sim_zustand[nid] = "success" if port in ("success", "true", "out") else "failure"
            self._sim_progress.pop(nid, None) # Timer nach Abschluss löschen
            self._alles_neu_zeichnen()
            
            self._sim_log(f"  → Port: {port}", "success" if self._sim_zustand[nid] == "success" else "failure")

            # Nächsten Node über Verbindungen suchen
            naechster = None
            for conn in self.connections:
                if conn["von"] == nid and conn["port_aus"] == port:
                    naechster = nodes_index.get(conn["zu"])
                    break

            if naechster is None:
                self._sim_log("  (kein Folge-Node → Ende)", "done")
                self.dialog.after(400, self._simulation_fertig)
            else:
                self.dialog.after(300, lambda: self._simulation_schritt(naechster, nodes_index, schritt + 1))

        # Threading nutzen, da _node_ausfuehren (z.B. bei 'suche') blockieren kann
        import threading
        threading.Thread(target=_ausfuehren, daemon=True).start()

    def _simulation_fertig(self):
        if not self._sim_aktiv:
            return
        self._sim_log("✓ Simulation abgeschlossen", "done")
        self._sim_aktiv = False
        self._sim_btn.config(text="▶ Simulieren", bg="#1565c0")
        self._status_aktualisieren()


    def _sim_log(self, text, tag="done"):
        """Schreibt eine Zeile ins Log-Panel oder aktualisiert Timer."""
        if text.startswith("__timer__"):
            try:
                val = text[9:]
                # Aktiven Node finden
                fuer_nid = None
                for nid, status in self._sim_zustand.items():
                    if status == "aktiv":
                        # Nur Nodes mit Timer-Logik sollen Fortschritt anzeigen
                        node = next((n for n in self.nodes if n["id"] == nid), None)
                        if node and node.get("typ") in ("suche", "suche_optional", "warten"):
                            self._sim_progress[nid] = f"⏳ {val}s"
                            fuer_nid = nid
                        break
                
                if fuer_nid:
                    # Gezieltes Redraw NUR für diesen Node
                    tag = f"node_{fuer_nid}"
                    self.canvas.delete(tag)
                    node = next((n for n in self.nodes if n["id"] == fuer_nid), None)
                    if node: self._node_zeichnen(node)
            except: pass
            return

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _status_aktualisieren(self):
        zoom_pct = int(self._scale * 100)
        if self._sim_aktiv:
            self.status_label.config(
                text=f"▶ Simulation läuft …  ·  {len(self.nodes)} Nodes  ·  Zoom {zoom_pct}%",
                fg="#f9a825",
            )
        else:
            self.status_label.config(
                text=f"{len(self.nodes)} Nodes  ·  {len(self.connections)} Verbindungen"
                     f"  ·  Zoom {zoom_pct}%"
                     f"  ·  Port ziehen = Verbindung  ·  Scrollen = Zoom  ·  Fläche ziehen = Pan",
                fg="#666666",
            )

    def _speichern(self):
        name = self.name_var.get().strip()
        if not name:
            return
        self.callback(name, {"nodes": self.nodes, "connections": self.connections})
        self.dialog.destroy()
