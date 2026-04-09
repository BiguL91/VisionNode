import tkinter as tk
import time
from core.daten_manager import (
    datenbank_initialisieren, alle_listen, spalten_der_liste,
    liste_lesen, berechneten_wert_ermitteln
)


class DatenPanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self._update_job = None
        self._listen_cache = []      # Liste aller Listen-Dicts
        self._ausgeklappt = {}       # listen_id → bool (ob aufgeklappt)

        datenbank_initialisieren()
        self._setup_ui()
        self._alles_aufbauen()

    def _setup_ui(self):
        # Kopfleiste: Dropdown (für Edit-Auswahl) + Buttons
        kopf = tk.Frame(self.parent, bg="#2d2d2d")
        kopf.pack(fill=tk.X, pady=(0, 4))

        tk.Button(kopf, text="+ Neu", bg="#1a3a1a", fg="#2ea043",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._neue_liste).pack(side=tk.LEFT, padx=(0, 4))

        self._listen_var = tk.StringVar()
        self._listen_dropdown = tk.OptionMenu(kopf, self._listen_var, "")
        self._listen_dropdown.config(bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 8),
                                     relief=tk.FLAT, bd=0, activebackground="#4a4a4a",
                                     highlightthickness=0, cursor="hand2")
        self._listen_dropdown["menu"].config(bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 8))
        self._listen_dropdown.pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(kopf, text="✎ Edit", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._liste_bearbeiten).pack(side=tk.LEFT)

        # Scrollbarer Bereich für alle Listen
        scroll_container = tk.Frame(self.parent, bg="#2d2d2d")
        scroll_container.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(scroll_container, bg="#2d2d2d", highlightthickness=0)
        scroll_y = tk.Scrollbar(scroll_container, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg="#2d2d2d")
        self._canvas_fenster = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(
            self._canvas_fenster, width=e.width))
        self._inner.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))

    # ── Aufbau aller Listen ──────────────────────────────────────────────────

    def _alles_aufbauen(self):
        """Baut alle Listen-Blöcke untereinander neu auf."""
        for w in self._inner.winfo_children():
            w.destroy()

        self._listen_cache = alle_listen()
        self._dropdown_aktualisieren()

        if not self._listen_cache:
            tk.Label(self._inner, text="Keine Listen vorhanden.",
                     bg="#2d2d2d", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=8)
            return

        for l in self._listen_cache:
            # Standard: aufgeklappt
            if l["id"] not in self._ausgeklappt:
                self._ausgeklappt[l["id"]] = True
            self._listen_block_erstellen(self._inner, l)

        self._update_starten()

    def _listen_block_erstellen(self, parent, l):
        """Erstellt einen einzelnen Listen-Block mit Header + Tabelle."""
        block = tk.Frame(parent, bg="#1e1e1e", relief=tk.FLAT, bd=1)
        block.pack(fill=tk.X, pady=(0, 4))

        # Header
        header = tk.Frame(block, bg="#252525")
        header.pack(fill=tk.X)

        aufgeklappt = self._ausgeklappt.get(l["id"], True)
        pfeil_lbl = tk.Label(header, text="▼" if aufgeklappt else "▶",
                             bg="#252525", fg="#555555", font=("Segoe UI", 8),
                             cursor="hand2", padx=4)
        pfeil_lbl.pack(side=tk.LEFT, pady=3)

        tk.Label(header, text=l["name"], bg="#252525", fg="#aaaaaa",
                 font=("Segoe UI", 8, "bold"), anchor="w", padx=2, pady=3).pack(side=tk.LEFT)

        # Tabellen-Inhalt
        inhalt = tk.Frame(block, bg="#2d2d2d")
        if aufgeklappt:
            inhalt.pack(fill=tk.X, padx=4, pady=(2, 4))
        self._tabelle_zeichnen(inhalt, l)

        # Letzter-Scan Label
        scan_lbl = tk.Label(block, text="", bg="#1e1e1e", fg="#444444", font=("Segoe UI", 7))
        scan_lbl.pack(anchor="w", padx=6, pady=(0, 2))
        self._scan_label_aktualisieren(scan_lbl, l["id"])

        # Collapse-Toggle
        def _toggle(event=None, lid=l["id"], inh=inhalt, pf=pfeil_lbl, sl=scan_lbl):
            self._ausgeklappt[lid] = not self._ausgeklappt.get(lid, True)
            if self._ausgeklappt[lid]:
                inh.pack(fill=tk.X, padx=4, pady=(2, 4))
                pf.config(text="▼")
            else:
                inh.pack_forget()
                pf.config(text="▶")

        pfeil_lbl.bind("<Button-1>", _toggle)
        header.bind("<Button-1>", _toggle)

    def _tabelle_zeichnen(self, parent, l):
        """Zeichnet die Tabelle einer Liste in den gegebenen Frame."""
        for w in parent.winfo_children():
            w.destroy()

        spalten = spalten_der_liste(l["id"])
        zeilen = liste_lesen(l["id"])

        if not spalten:
            tk.Label(parent, text="Keine Spalten — Edit zum Konfigurieren.",
                     bg="#2d2d2d", fg="#555555", font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=4)
            return

        # Header-Zeile
        header_row = tk.Frame(parent, bg="#1a1a1a")
        header_row.pack(fill=tk.X, pady=(0, 1))
        tk.Label(header_row, text="Zeile", bg="#1a1a1a", fg="#666666",
                 font=("Segoe UI", 7, "bold"), padx=6, pady=2, anchor="w",
                 width=10).pack(side=tk.LEFT)
        for sp in spalten:
            tk.Label(header_row, text=sp["name"], bg="#1a1a1a", fg="#666666",
                     font=("Segoe UI", 7, "bold"), padx=6, pady=2, anchor="e",
                     width=8).pack(side=tk.LEFT)

        # Datenzeilen
        if not zeilen:
            tk.Label(parent, text="(Keine Daten)", bg="#2d2d2d", fg="#444444",
                     font=("Segoe UI", 8), padx=6, pady=3).pack(anchor="w")
            return

        for r, zeile in enumerate(zeilen):
            hg = "#1a1a1a" if r % 2 == 0 else "#212121"
            zeile_row = tk.Frame(parent, bg=hg)
            zeile_row.pack(fill=tk.X, pady=1)

            tk.Label(zeile_row, text=zeile["zeile_name"], bg=hg, fg="#cccccc",
                     font=("Segoe UI", 8), padx=6, pady=2, anchor="w",
                     width=10).pack(side=tk.LEFT)

            for sp in spalten:
                if sp["typ"] == "berechnet":
                    wert = berechneten_wert_ermitteln(zeile, sp, zeile)
                    farbe = "#4fc3f7"
                else:
                    wert = zeile.get(sp["name"], "—")
                    farbe = "#cccccc"

                tk.Label(zeile_row, text=wert, bg=hg, fg=farbe,
                         font=("Consolas", 8), padx=6, pady=2, anchor="e",
                         width=8).pack(side=tk.LEFT)

    def _scan_label_aktualisieren(self, lbl, listen_id):
        """Setzt den 'Letzter Scan' Text."""
        zeilen = liste_lesen(listen_id)
        if zeilen:
            neuester = max(z.get("gescant_am") or 0 for z in zeilen)
            if neuester:
                ts = time.strftime("%H:%M:%S", time.localtime(neuester))
                lbl.config(text=f"  Scan: {ts}")

    # ── Dropdown ────────────────────────────────────────────────────────────

    def _dropdown_aktualisieren(self):
        menu = self._listen_dropdown["menu"]
        menu.delete(0, tk.END)
        if not self._listen_cache:
            self._listen_var.set("")
            return
        for l in self._listen_cache:
            menu.add_command(label=l["name"],
                             command=lambda n=l["name"]: self._listen_var.set(n))
        if not self._listen_var.get():
            self._listen_var.set(self._listen_cache[0]["name"])

    # ── Neue Liste / Edit ────────────────────────────────────────────────────

    def _neue_liste(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("Neue Liste", "Name der Liste:", parent=self.parent)
        if not name or not name.strip():
            return
        from core.daten_manager import liste_erstellen
        liste_erstellen(name.strip())
        self._alles_aufbauen()
        self._listen_var.set(name.strip())

    def _liste_bearbeiten(self):
        """Öffnet den Edit-Dialog für die im Dropdown gewählte Liste."""
        name = self._listen_var.get()
        if not name:
            return
        l = next((x for x in self._listen_cache if x["name"] == name), None)
        if not l:
            return
        from ui.dialogs.daten_editor import DatenListeEditor
        DatenListeEditor(
            self.bot.root, self.bot, l,
            on_gespeichert=self._alles_aufbauen
        )

    # ── Auto-Update ──────────────────────────────────────────────────────────

    def _update_starten(self):
        if self._update_job:
            self.bot.root.after_cancel(self._update_job)
        self._update_job = self.bot.root.after(1000, self._auto_update)

    def _auto_update(self):
        """Aktualisiert alle sichtbaren Tabellen periodisch."""
        if not self._listen_cache:
            self._update_job = self.bot.root.after(5000, self._auto_update)
            return

        # Kürzestes Intervall aller Listen bestimmen
        min_intervall = min(l["update_intervall"] for l in self._listen_cache)

        # Tabellen der aufgeklappten Listen neu zeichnen
        for block, l in zip(self._inner.winfo_children(), self._listen_cache):
            if not self._ausgeklappt.get(l["id"], True):
                continue
            # Inhalt-Frame ist zweites Kind des Blocks (nach Header)
            kinder = block.winfo_children()
            if len(kinder) >= 2:
                self._tabelle_zeichnen(kinder[1], l)
                if len(kinder) >= 3:
                    self._scan_label_aktualisieren(kinder[2], l["id"])

        self._update_job = self.bot.root.after(min_intervall * 1000, self._auto_update)

    def listen_neu_laden(self):
        """Öffentliche Methode — nach externen Änderungen aufrufen."""
        self._alles_aufbauen()
