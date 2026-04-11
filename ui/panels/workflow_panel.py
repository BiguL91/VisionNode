import tkinter as tk

class WorkflowPanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.workflow_engine = bot.workflow_engine
        
        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        # ── Sektion 1: Master-Flows (Schrittketten) ───────────────────────────
        tk.Label(self.parent, text="MASTER-FLOWS (Schrittketten)", bg="#2d2d2d", fg="#ffca28",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=2)

        m_frame = tk.Frame(self.parent, bg="#2d2d2d")
        m_frame.pack(fill=tk.X)

        m_scroll = tk.Scrollbar(m_frame, orient=tk.VERTICAL, bg="#3a3a3a",
                                 troughcolor="#1a1a1a", width=8)
        m_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.master_liste = tk.Listbox(m_frame, bg="#1a1a1a", fg="#ffffff",
                                         selectbackground="#1565c0", font=("Segoe UI", 9, "bold"),
                                         relief=tk.FLAT, bd=0, height=5,
                                         yscrollcommand=m_scroll.set)
        self.master_liste.pack(side=tk.LEFT, fill=tk.X, expand=True)
        m_scroll.config(command=self.master_liste.yview)

        m_btns = tk.Frame(self.parent, bg="#2d2d2d")
        m_btns.pack(anchor="w", pady=(2, 8))

        tk.Button(m_btns, text="+ Neu", bg="#1a3a1a", fg="#55ff88",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._master_neu).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(m_btns, text="✎", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._master_bearbeiten).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(m_btns, text="★ Aktiv", bg="#3a3a3a", fg="#ffca28",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._master_aktiv_setzen).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(m_btns, text="✕", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._master_loeschen).pack(side=tk.LEFT)

        # ── Trenner ───────────────────────────────────────────────────────────
        tk.Frame(self.parent, bg="#3a3a3a", height=1).pack(fill=tk.X, pady=(2, 8))

        # ── Sektion 2: Sub-Workflows (Funktionsbausteine) ────────────────────
        tk.Label(self.parent, text="SUB-WORKFLOWS (Funktionsbausteine)", bg="#2d2d2d", fg="#666666",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=2)

        wf_frame = tk.Frame(self.parent, bg="#2d2d2d")
        wf_frame.pack(fill=tk.X)

        wf_scroll = tk.Scrollbar(wf_frame, orient=tk.VERTICAL, bg="#3a3a3a",
                                  troughcolor="#1a1a1a", width=8)
        wf_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.workflow_liste = tk.Listbox(wf_frame, bg="#1a1a1a", fg="#cccccc",
                                          selectbackground="#0d47a1", font=("Segoe UI", 9),
                                          relief=tk.FLAT, bd=0, height=8,
                                          yscrollcommand=wf_scroll.set)
        self.workflow_liste.pack(side=tk.LEFT, fill=tk.X, expand=True)
        wf_scroll.config(command=self.workflow_liste.yview)

        wf_btns = tk.Frame(self.parent, bg="#2d2d2d")
        wf_btns.pack(anchor="w", pady=(2, 6))

        tk.Button(wf_btns, text="+ Neu", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._workflow_neu).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(wf_btns, text="✎ Bearbeiten", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._workflow_bearbeiten).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(wf_btns, text="✕", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._workflow_loeschen).pack(side=tk.LEFT)

    def aktualisieren(self):
        self._master_liste_aktualisieren()
        self._workflows_liste_aktualisieren()

    def _master_liste_aktualisieren(self):
        self.master_liste.delete(0, tk.END)
        active = self.workflow_engine.aktiver_master
        if self.workflow_engine.master_workflows:
            for name in sorted(self.workflow_engine.master_workflows.keys()):
                prefix = " ★ " if name == active else "   "
                self.master_liste.insert(tk.END, f"{prefix}{name}")
                if name == active:
                    self.master_liste.itemconfig(tk.END, fg="#ffca28")
        else:
            self.master_liste.insert(tk.END, "  (Keine Master-Flows)")

    def _workflows_liste_aktualisieren(self):
        self.workflow_liste.delete(0, tk.END)
        if self.workflow_engine.workflows:
            for name in sorted(self.workflow_engine.workflows.keys()):
                graph  = self.workflow_engine.workflows[name]
                n_nodes = len(graph.get("nodes", []))
                n_conn  = len(graph.get("connections", []))
                self.workflow_liste.insert(tk.END, f"  {name}  ({n_nodes} Nodes, {n_conn} Links)")
        else:
            self.workflow_liste.insert(tk.END, "  (Keine Workflows)")

    def _get_master_auswahl(self):
        auswahl = self.master_liste.curselection()
        if not auswahl: return None
        eintrag = self.master_liste.get(auswahl[0])
        return eintrag[3:].strip() # Präfix entfernen

    def _get_auswahl_name(self):
        auswahl = self.workflow_liste.curselection()
        if not auswahl: return None
        eintrag = self.workflow_liste.get(auswahl[0]).strip()
        if eintrag.startswith("("): return None
        return eintrag.split("  (")[0].strip()

    # ── Master-Methoden ──────────────────────────────────────────────────────

    def _master_neu(self):
        res = self.bot._workflow_editor_dialog(None, {})
        if res is None: return
        name, graph = res
        if name:
            self.workflow_engine.master_speichern(name, graph)
            self._master_liste_aktualisieren()
            self.bot._log(f"Master-Flow erstellt: {name}")

    def _master_bearbeiten(self):
        name = self._get_master_auswahl()
        if not name: return
        graph = dict(self.workflow_engine.master_workflows.get(name, {}))
        res = self.bot._workflow_editor_dialog(name, graph)
        if res is None: return
        neuer_name, neuer_graph = res
        if neuer_name != name:
            self.workflow_engine.master_umbenennen(name, neuer_name)
        self.workflow_engine.master_speichern(neuer_name, neuer_graph)
        self._master_liste_aktualisieren()
        self.bot._log(f"Master-Flow gespeichert: {neuer_name}")

    def _master_loeschen(self):
        name = self._get_master_auswahl()
        if not name: return
        self.workflow_engine.master_loeschen(name)
        self._master_liste_aktualisieren()
        self.bot._log(f"Master-Flow gelöscht: {name}")

    def _master_aktiv_setzen(self):
        name = self._get_master_auswahl()
        if not name: return
        self.workflow_engine.master_aktiv_setzen(name)
        self._master_liste_aktualisieren()
        self.bot._log(f"Master-Flow aktiv gesetzt: {name}")

    def _workflow_neu(self):
        res = self.bot._workflow_editor_dialog(None, {})
        if res is None: return
        name, graph = res
        if name:
            self.workflow_engine.workflow_speichern(name, graph)
            self._workflows_liste_aktualisieren()
            n = len(graph.get("nodes", []))
            self.bot._log(f"Workflow erstellt: {name} ({n} Nodes)")

    def _workflow_bearbeiten(self):
        name = self._get_auswahl_name()
        if not name: return
        graph    = dict(self.workflow_engine.workflows.get(name, {}))
        ergebnis = self.bot._workflow_editor_dialog(name, graph)
        if ergebnis is None: return
        neuer_name, neuer_graph = ergebnis
        if neuer_name != name:
            self.workflow_engine.workflow_umbenennen(name, neuer_name)
        self.workflow_engine.workflow_speichern(neuer_name, neuer_graph)
        self._workflows_liste_aktualisieren()
        n = len(neuer_graph.get("nodes", []))
        self.bot._log(f"Workflow gespeichert: {neuer_name} ({n} Nodes)")

    def _workflow_loeschen(self):
        name = self._get_auswahl_name()
        if not name: return
        self.workflow_engine.workflow_loeschen(name)
        self._workflows_liste_aktualisieren()
        self.bot._log(f"Workflow gelöscht: {name}")
