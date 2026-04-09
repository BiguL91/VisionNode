import tkinter as tk
from core.daten_manager import (
    datenbank_initialisieren, alle_listen, spalten_der_liste,
    zeilen_der_liste, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen
)


class DatenPanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self._update_job = None
        self._listen_cache = []      # Liste aller Listen-Dicts
        self._ausgeklappt = {}       # listen_id → bool (ob aufgeklappt)
        self._tabellen_frames = {}   # listen_id → Inhalt-Frame

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
        self._tabellen_frames = {}
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
        self._tabellen_frames[l["id"]] = inhalt
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
        zeilen_namen = zeilen_der_liste(l["id"])
        transformationen = transformationen_der_liste(l["id"])
        berechnungen = berechnungen_der_liste(l["id"])

        # 1. Gedächtnis laden: Alles aus Cache als Basis
        db_cache = cache_lesen(l["id"])
        ocr_werte = {k: v for k, v in db_cache.items()}

        # 2. Aktuelle OCR-Rohwerte (Live)
        ocr_roh_live = {}
        if hasattr(self.bot, "app"):
            ocr_roh_live.update(self.bot.app.state.ocr_values)
            ocr_roh_live.update(self.bot.app.state.template_ocr_values)

        # 3. Live-OCR erzwingen (Reset auf '—' bei Wegfall)
        # Wir sammeln Namen, die von Transformern/Berechnungen erzeugt werden
        ausgabe_namen = {t["name"] for t in transformationen}
        ausgabe_namen.update({b["name"] for b in berechnungen})

        # Wir sammeln alle Namen von möglichen OCR-Quellen
        alle_ocr_namen = set(self.bot.ocr_engine.regionen.keys())
        alle_ocr_namen.update(self.bot.ocr_engine.template_ocr_konfigurationen().keys())

        # Nur für diese REINEN OCR-Variablen erzwingen wir den Live-Status
        # Aber nur, wenn sie NICHT auch als Transformer-Ausgabe dienen
        for name in alle_ocr_namen:
            if name in ausgabe_namen:
                continue
            val = ocr_roh_live.get(name)
            ocr_werte[name] = val if val not in (None, "") else "—"

        # Debug-Log Setting
        log_debug = self.bot.app.settings.get("log_daten_berechnungen", False)

        # 4. Transformer anwenden
        neue_cache_werte = {}
        for t in transformationen:
            rohwert = ocr_roh_live.get(t["ocr_var"])
            if rohwert not in (None, "", "—"):
                wert = transformation_anwenden(rohwert, t["typ"])
                if wert not in ("", "—", "?"):
                    # Logging bei Änderung
                    if log_debug and str(wert) != str(db_cache.get(t["name"])):
                        self.bot.app._log(f"[Transform] {t['name']}: {rohwert} -> {wert}")
                    
                    ocr_werte[t["name"]] = wert
                    neue_cache_werte[t["name"]] = wert
            else:
                # Transformer MERKT sich den letzten Stand aus dem Cache
                # (Wert ist durch Schritt 1 bereits in ocr_werte drin)
                pass

        # 5. Berechnungen anwenden (Zwischenberechnungen zuerst)
        berech_sortiert = (
            [b for b in berechnungen if b.get("typ") == "zwischen"] +
            [b for b in berechnungen if b.get("typ") != "zwischen"]
        )
        for b in berech_sortiert:
            ergebnis = berechnung_auswerten(b["formel_json"], ocr_werte, l["update_intervall"])
            if ergebnis in ("?", "—") or not b["formel_json"]:
                # Fallback auf Cache (schon in ocr_werte drin)
                pass
            else:
                # Logging bei Änderung
                if log_debug and str(ergebnis) != str(db_cache.get(b["name"])):
                    self.bot.app._log(f"[Berechnung] {b['name']}: {ergebnis}")
                
                ocr_werte[b["name"]] = ergebnis
                neue_cache_werte[b["name"]] = ergebnis

        # Neue Werte in Cache schreiben
        for var_name, wert in neue_cache_werte.items():
            cache_schreiben(l["id"], var_name, wert)

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

        # Datenzeilen (aus konfigurierten Zeilen-Namen)
        if not zeilen_namen:
            tk.Label(parent, text="(Keine Zeilen — Edit zum Konfigurieren)", bg="#2d2d2d",
                     fg="#444444", font=("Segoe UI", 8), padx=6, pady=3).pack(anchor="w")
            return

        # Berechnungs-Namen für farbliche Markierung sammeln
        berech_namen = {b["name"] for b in berechnungen}

        for r, z in enumerate(zeilen_namen):
            hg = "#1a1a1a" if r % 2 == 0 else "#212121"
            zeile_row = tk.Frame(parent, bg=hg)
            zeile_row.pack(fill=tk.X, pady=1)

            tk.Label(zeile_row, text=z["name"], bg=hg, fg="#cccccc",
                     font=("Segoe UI", 8), padx=6, pady=2, anchor="w",
                     width=10).pack(side=tk.LEFT)

            for sp in spalten:
                ocr_var = sp.get("ocr_var")
                wert = ocr_werte.get(ocr_var, "—") if ocr_var else "—"
                
                # Farbe: Berechnungen in Blau, Transformationen/OCR in Grau
                farbe = "#4fc3f7" if ocr_var in berech_namen else "#cccccc"

                tk.Label(zeile_row, text=wert, bg=hg, fg=farbe,
                         font=("Consolas", 8), padx=6, pady=2, anchor="e",
                         width=8).pack(side=tk.LEFT)

    def _scan_label_aktualisieren(self, lbl, listen_id):
        pass  # Scan-Timestamp entfällt — Werte kommen direkt aus OCR-State

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

        min_intervall = min(l["update_intervall"] for l in self._listen_cache)

        for l in self._listen_cache:
            if not self._ausgeklappt.get(l["id"], True):
                continue
            frame = self._tabellen_frames.get(l["id"])
            if frame and frame.winfo_exists():
                self._tabelle_zeichnen(frame, l)

        self._update_job = self.bot.root.after(min_intervall * 1000, self._auto_update)

    def listen_neu_laden(self):
        """Öffentliche Methode — nach externen Änderungen aufrufen."""
        self._alles_aufbauen()
