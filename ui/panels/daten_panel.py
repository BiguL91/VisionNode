import tkinter as tk
import time
from core.daten_manager import (
    datenbank_initialisieren, alle_listen, spalten_der_liste,
    zeilen_der_liste, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen,
    zuordnungen_der_liste, sekunden_formatieren
)


class DatenPanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self._update_job = None
        self._transform_job = None
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
                  cursor="hand2", command=self._liste_bearbeiten).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(kopf, text="⚖️ Einheiten", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=lambda: self.bot._einheiten_dialog()).pack(side=tk.LEFT)

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
        self._transform_loop_starten()

        # Spaltenbreite nach Rebuild anpassen (after(0) damit daten_panel bereits zugewiesen ist)
        if hasattr(self.bot, "_daten_spalte_breite_anpassen"):
            self.bot.root.after(0, self.bot._daten_spalte_breite_anpassen)

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
        db_cache = cache_lesen(l["id"]) # var_name -> (wert, zeit)
        ocr_werte = {k: v for k, v in db_cache.items()}

        # 2. Aktuelle OCR-Rohwerte (Live)
        ocr_roh_live = {}
        if hasattr(self.bot, "app"):
            ocr_roh_live.update(self.bot.app.state.ocr_values)
            ocr_roh_live.update(self.bot.app.state.template_ocr_values)

        # 3. Live-OCR erzwingen (Reset auf '—' bei Wegfall)
        ausgabe_namen = {t["name"] for t in transformationen}
        ausgabe_namen.update({b["name"] for b in berechnungen})
        alle_ocr_namen = set(self.bot.ocr_engine.regionen.keys())
        alle_ocr_namen.update(self.bot.ocr_engine.template_ocr_konfigurationen().keys())

        jetzt = time.time()
        neue_cache_werte = {}

        # Alle aktuellen Live-Werte durchgehen und in ocr_werte / Cache übertragen
        for name, val in ocr_roh_live.items():
            if name in ausgabe_namen: continue
            if val not in (None, "", "—"):
                ocr_werte[name] = (val, jetzt)
                neue_cache_werte[name] = val

        # Sicherstellen, dass auch konfigurierte aber gerade nicht sichtbare OCRs
        # zumindest mit "—" initialisiert werden, falls sie noch nie im Cache waren.
        for name in alle_ocr_namen:
            if name not in ocr_werte and name not in ausgabe_namen:
                ocr_werte[name] = ("—", jetzt)

        # Debug-Log Setting
        log_debug = self.bot.app.settings.get("log_daten_berechnungen", False)

        # 4. Transformer anwenden
        for t in transformationen:
            rohwert = ocr_roh_live.get(t["ocr_var"])
            if rohwert not in (None, "", "—"):
                wert = transformation_anwenden(rohwert, t["typ"])
                if wert not in ("", "—", "?"):
                    # Logging bei Änderung
                    alt_wert = db_cache.get(t["name"], ("—", 0))[0]
                    if log_debug and str(wert) != str(alt_wert):
                        self.bot.app._log(f"[Transform] {t['name']}: {rohwert} -> {wert}")
                    ocr_werte[t["name"]] = (wert, jetzt)
                    neue_cache_werte[t["name"]] = wert
                    if t["typ"] == "timer":
                        # Deadline einmalig setzen wenn OCR frischen Wert liefert
                        try:
                            deadline = jetzt + float(wert)
                            neue_cache_werte[f"Timer.{t['name']}._deadline"] = str(deadline)
                        except (ValueError, TypeError):
                            pass
            elif t["typ"] == "timer":
                # OCR nicht sichtbar → aus Deadline weiterzählen
                deadline_eintrag = db_cache.get(f"Timer.{t['name']}._deadline")
                if deadline_eintrag and deadline_eintrag[0] not in (None, "", "—", "?"):
                    try:
                        rest = max(0, int(float(deadline_eintrag[0]) - jetzt))
                        ocr_werte[t["name"]] = (str(rest), jetzt)
                        neue_cache_werte[t["name"]] = str(rest)
                        if rest == 0:
                            flag_name = f"Timer.{t['name']}"
                            neue_cache_werte[flag_name] = "false"
                            if log_debug:
                                self.bot.app._log(f"[Timer] {t['name']} abgelaufen → {flag_name}=false")
                    except (ValueError, TypeError):
                        pass

        # 5. Berechnungen anwenden (Zwischenberechnungen zuerst)
        berech_sortiert = (
            [b for b in berechnungen if b.get("typ") == "zwischen"] +
            [b for b in berechnungen if b.get("typ") != "zwischen"]
        )
        for b in berech_sortiert:
            ergebnis = berechnung_auswerten(b["formel_json"], ocr_werte, l["update_intervall"])
            if ergebnis in ("?", "—") or not b["formel_json"]:
                pass
            else:
                alt_wert = db_cache.get(b["name"], ("—", 0))[0]
                if log_debug and str(ergebnis) != str(alt_wert):
                    self.bot.app._log(f"[Berechnung] {b['name']}: {ergebnis}")
                
                ocr_werte[b["name"]] = (ergebnis, jetzt)
                neue_cache_werte[b["name"]] = ergebnis

        # Neue Werte in Cache schreiben
        for var_name, wert in neue_cache_werte.items():
            cache_schreiben(l["id"], var_name, wert)

        if not spalten:
            tk.Label(parent, text="Keine Spalten — Edit zum Konfigurieren.",
                     bg="#2d2d2d", fg="#555555", font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=4)
            return

        # Datenzeilen (aus konfigurierten Zeilen-Namen)
        if not zeilen_namen:
            tk.Label(parent, text="(Keine Zeilen — Edit zum Konfigurieren)", bg="#2d2d2d",
                     fg="#444444", font=("Segoe UI", 8), padx=6, pady=3).pack(anchor="w")
            return

        # Berechnungs-Namen für farbliche Markierung sammeln
        berech_namen = {b["name"] for b in berechnungen}

        # Spezifische Zell-Zuordnungen laden
        zuordnungen = zuordnungen_der_liste(l["id"])

        # Grid-Tabelle: Header + Daten in einem Frame → pixelgenaue Spaltenausrichtung
        tabel = tk.Frame(parent, bg="#1a1a1a")
        tabel.pack(fill=tk.X, pady=(0, 2))

        # Spaltenbreiten festlegen
        tabel.grid_columnconfigure(0, minsize=95)
        for i in range(len(spalten)):
            tabel.grid_columnconfigure(i + 1, minsize=72)

        # Header-Zeile (Zeile 0)
        tk.Label(tabel, text="Zeile", bg="#1a1a1a", fg="#555555",
                 font=("Segoe UI", 8, "bold"), padx=6, pady=2, anchor="w"
                 ).grid(row=0, column=0, sticky="ew")
        for i, sp in enumerate(spalten):
            tk.Label(tabel, text=sp["name"], bg="#1a1a1a", fg="#555555",
                     font=("Consolas", 8, "bold"), padx=6, pady=2, anchor="e"
                     ).grid(row=0, column=i + 1, sticky="ew")

        # Trennlinie
        tk.Frame(tabel, bg="#333333", height=1).grid(
            row=1, column=0, columnspan=len(spalten) + 1, sticky="ew")

        # Datenzeilen (ab Zeile 2)
        for r, z in enumerate(zeilen_namen):
            hg = "#1a1a1a" if r % 2 == 0 else "#212121"
            row_idx = r + 2

            tk.Label(tabel, text=z["name"], bg=hg, fg="#cccccc",
                     font=("Segoe UI", 8), padx=6, pady=2, anchor="w"
                     ).grid(row=row_idx, column=0, sticky="ew")

            for ci, sp in enumerate(spalten):
                # 1. Spezifische Zuordnung (Zelle) prüfen
                ocr_var = zuordnungen.get((z["name"], sp["id"]))

                # 2. Falls keine Zelle: Globalen Spalten-Wert prüfen (inkl. Placeholder)
                if not ocr_var:
                    ocr_var = sp.get("ocr_var")
                    if ocr_var and "{row}" in ocr_var:
                        ocr_var = ocr_var.replace("{row}", z["name"])

                entry = ocr_werte.get(ocr_var, ("—", 0)) if ocr_var else ("—", 0)
                wert = entry[0]

                format_typ = sp.get("format", "standard")
                anzeige_wert = self._format_wert(wert, format_typ)

                farbe = "#4fc3f7" if ocr_var in berech_namen else "#cccccc"

                tk.Label(tabel, text=anzeige_wert, bg=hg, fg=farbe,
                         font=("Consolas", 8), padx=6, pady=2, anchor="e"
                         ).grid(row=row_idx, column=ci + 1, sticky="ew")

    def _format_wert(self, wert, format_typ):
        """Formatiert einen Wert für die UI-Anzeige."""
        if wert in (None, "", "—", "?"):
            return str(wert)
        
        try:
            num = float(str(wert).replace(",", "."))
        except (ValueError, TypeError):
            return str(wert)

        if format_typ == "K/M/B":
            if abs(num) >= 10**9:
                return f"{num / 10**9:.1f}B"
            if abs(num) >= 10**6:
                return f"{num / 10**6:.1f}M"
            if abs(num) >= 10**3:
                return f"{num / 10**3:.1f}K"
            return str(round(num, 1))
        
        if format_typ == "0 (Ganzzahl)":
            return str(int(round(num)))
        
        if format_typ == ".2 (2 Nachkomma)":
            return f"{num:.2f}"

        if format_typ == "timer":
            return sekunden_formatieren(num)

        # Standard: Wenn Ganzzahl dann ohne .0, sonst 1 Nachkommastelle
        if num == int(num):
            return str(int(num))
        return str(round(num, 1))

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

    # ── Echtzeit-Transform-Loop ──────────────────────────────────────────────

    def _transform_loop_starten(self):
        """Startet den schnellen Transform-Loop (unabhängig vom Anzeige-Timer)."""
        if self._transform_job:
            self.bot.root.after_cancel(self._transform_job)
        self._transform_job = self.bot.root.after(800, self._transform_tick)

    def _transform_tick(self):
        """OCR-Werte → Transformer → Cache für alle Listen (Echtzeit)."""
        for l in self._listen_cache:
            self._transforms_cachen(l)
        self._transform_job = self.bot.root.after(800, self._transform_tick)

    def _transforms_cachen(self, l):
        """Liest Live-OCR, führt Transformer aus und schreibt Ergebnis sofort in Cache."""
        transformationen = transformationen_der_liste(l["id"])
        if not transformationen:
            return

        ocr_roh_live = {}
        if hasattr(self.bot, "app"):
            ocr_roh_live.update(self.bot.app.state.ocr_values)
            ocr_roh_live.update(self.bot.app.state.template_ocr_values)

        if not ocr_roh_live:
            return

        db_cache = cache_lesen(l["id"])
        log_debug = hasattr(self.bot, "app") and self.bot.app.settings.get("log_daten_berechnungen", False)
        jetzt = time.time()

        for t in transformationen:
            rohwert = ocr_roh_live.get(t["ocr_var"])
            if rohwert not in (None, "", "—"):
                wert = transformation_anwenden(rohwert, t["typ"])
                if wert not in ("", "—", "?"):
                    alt_wert = db_cache.get(t["name"], ("—", 0))[0]
                    if log_debug and str(wert) != str(alt_wert):
                        self.bot.app._log(f"[Transform] {t['name']}: {rohwert} → {wert}")
                    cache_schreiben(l["id"], t["name"], wert)
                    if t["typ"] == "timer":
                        # Deadline einmalig setzen wenn OCR frischen Wert liefert
                        try:
                            deadline = jetzt + float(wert)
                            cache_schreiben(l["id"], f"Timer.{t['name']}._deadline", str(deadline))
                        except (ValueError, TypeError):
                            pass
            elif t["typ"] == "timer":
                # OCR nicht sichtbar → aus Deadline weiterzählen
                deadline_eintrag = db_cache.get(f"Timer.{t['name']}._deadline")
                if deadline_eintrag and deadline_eintrag[0] not in (None, "", "—", "?"):
                    try:
                        rest = max(0, int(float(deadline_eintrag[0]) - jetzt))
                        cache_schreiben(l["id"], t["name"], str(rest))
                        if rest == 0:
                            flag_name = f"Timer.{t['name']}"
                            cache_schreiben(l["id"], flag_name, "false")
                            if log_debug:
                                self.bot.app._log(f"[Timer] {t['name']} abgelaufen → {flag_name}=false")
                    except (ValueError, TypeError):
                        pass

    def listen_neu_laden(self):
        """Öffentliche Methode — nach externen Änderungen aufrufen."""
        self._alles_aufbauen()
