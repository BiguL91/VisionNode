import tkinter as tk

class WorkflowPanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.workflow_engine = bot.workflow_engine
        
        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        # ── Workflow-Liste ────────────────────────────────────────────────────
        tk.Label(self.parent, text="Workflows", bg="#2d2d2d", fg="#666666",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=2)

        wf_frame = tk.Frame(self.parent, bg="#2d2d2d")
        wf_frame.pack(fill=tk.X)

        wf_scroll = tk.Scrollbar(wf_frame, orient=tk.VERTICAL, bg="#3a3a3a",
                                  troughcolor="#1a1a1a", width=8)
        wf_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.workflow_liste = tk.Listbox(wf_frame, bg="#1a1a1a", fg="#cccccc",
                                          selectbackground="#0d47a1", font=("Segoe UI", 9),
                                          relief=tk.FLAT, bd=0, height=4,
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
                  cursor="hand2", command=self._workflow_loeschen).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(wf_btns, text="→ zu Scheduler", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._schedule_hinzufuegen).pack(side=tk.LEFT)

        # ── Schedule-Queue ────────────────────────────────────────────────────
        tk.Frame(self.parent, bg="#3a3a3a", height=1).pack(fill=tk.X, pady=(2, 6))
        tk.Label(self.parent, text="Schedule (Loop)", bg="#2d2d2d", fg="#666666",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=2)

        sc_frame = tk.Frame(self.parent, bg="#2d2d2d")
        sc_frame.pack(fill=tk.X)

        sc_scroll = tk.Scrollbar(sc_frame, orient=tk.VERTICAL, bg="#3a3a3a",
                                  troughcolor="#1a1a1a", width=8)
        sc_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.schedule_liste = tk.Listbox(sc_frame, bg="#1a1a1a", fg="#cccccc",
                                          selectbackground="#0d47a1", font=("Segoe UI", 9),
                                          relief=tk.FLAT, bd=0, height=4,
                                          yscrollcommand=sc_scroll.set)
        self.schedule_liste.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sc_scroll.config(command=self.schedule_liste.yview)

        sc_btns = tk.Frame(self.parent, bg="#2d2d2d")
        sc_btns.pack(anchor="w", pady=(2, 0))

        tk.Button(sc_btns, text="↑", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=lambda: self._schedule_verschieben(-1)).pack(side=tk.LEFT, padx=(0, 2))
        tk.Button(sc_btns, text="↓", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=lambda: self._schedule_verschieben(1)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(sc_btns, text="✕", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._schedule_entfernen).pack(side=tk.LEFT)

    def aktualisieren(self):
        self._workflows_liste_aktualisieren()
        self._schedule_liste_aktualisieren()

    def _workflows_liste_aktualisieren(self):
        self.workflow_liste.delete(0, tk.END)
        if self.workflow_engine.workflows:
            for name in sorted(self.workflow_engine.workflows.keys()):
                anzahl = len(self.workflow_engine.workflows[name])
                self.workflow_liste.insert(tk.END, f"  {name}  ({anzahl} Schritte)")
        else:
            self.workflow_liste.insert(tk.END, "  (Keine Workflows)")

    def _schedule_liste_aktualisieren(self):
        self.schedule_liste.delete(0, tk.END)
        if self.workflow_engine.schedule:
            for i, name in enumerate(self.workflow_engine.schedule):
                self.schedule_liste.insert(tk.END, f"  {i + 1}. {name}")
        else:
            self.schedule_liste.insert(tk.END, "  (Leer)")

    def _get_auswahl_name(self):
        auswahl = self.workflow_liste.curselection()
        if not auswahl:
            return None
        eintrag = self.workflow_liste.get(auswahl[0]).strip()
        if eintrag.startswith("("):
            return None
        return eintrag.split("  (")[0].strip()

    def _workflow_neu(self):
        res = self.bot._workflow_editor_dialog(None, [])
        if res is None: return
        name, schritte = res
        if name:
            self.workflow_engine.workflow_speichern(name, schritte)
            self._workflows_liste_aktualisieren()
            self.bot._log(f"Workflow erstellt: {name} ({len(schritte)} Schritte)")

    def _workflow_bearbeiten(self):
        name = self._get_auswahl_name()
        if not name: return
        schritte = list(self.workflow_engine.workflows.get(name, []))
        ergebnis = self.bot._workflow_editor_dialog(name, schritte)
        if ergebnis is None: return
        neuer_name, neue_schritte = ergebnis
        if neuer_name != name:
            self.workflow_engine.workflow_umbenennen(name, neuer_name)
        self.workflow_engine.workflow_speichern(neuer_name, neue_schritte)
        self._workflows_liste_aktualisieren()
        self._schedule_liste_aktualisieren()
        self.bot._log(f"Workflow gespeichert: {neuer_name} ({len(neue_schritte)} Schritte)")

    def _workflow_loeschen(self):
        name = self._get_auswahl_name()
        if not name: return
        self.workflow_engine.workflow_loeschen(name)
        self._workflows_liste_aktualisieren()
        self._schedule_liste_aktualisieren()
        self.bot._log(f"Workflow gelöscht: {name}")

    def _schedule_hinzufuegen(self):
        name = self._get_auswahl_name()
        if not name: return
        self.workflow_engine.schedule_hinzufuegen(name)
        self._schedule_liste_aktualisieren()

    def _schedule_verschieben(self, richtung):
        auswahl = self.schedule_liste.curselection()
        if not auswahl: return
        index = auswahl[0]
        self.workflow_engine.schedule_verschieben(index, richtung)
        self._schedule_liste_aktualisieren()
        neue_pos = max(0, min(index + richtung, len(self.workflow_engine.schedule) - 1))
        self.schedule_liste.selection_set(neue_pos)

    def _schedule_entfernen(self):
        auswahl = self.schedule_liste.curselection()
        if not auswahl: return
        self.workflow_engine.schedule_entfernen(auswahl[0])
        self._schedule_liste_aktualisieren()
