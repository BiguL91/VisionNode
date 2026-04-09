import tkinter as tk
import time
from core.daten_manager import (
    spalten_der_liste, spalte_hinzufuegen, spalte_aktualisieren, spalte_loeschen,
    zeilen_der_liste, zeile_hinzufuegen, zeile_umbenennen, zeile_loeschen,
    liste_umbenennen, liste_intervall_setzen, liste_loeschen,
    transformationen_der_liste, transformation_hinzufuegen,
    transformation_aktualisieren, transformation_loeschen, transformation_anwenden,
    berechnungen_der_liste, berechnung_hinzufuegen, berechnung_aktualisieren,
    berechnung_loeschen, berechnung_auswerten, cache_lesen
)


class DatenListeEditor:
    def __init__(self, parent, bot, liste, on_gespeichert=None):
        self.parent = parent
        self.bot = bot
        self.liste = liste
        self.on_gespeichert = on_gespeichert

        self._spalten = spalten_der_liste(liste["id"])
        self._zeilen = zeilen_der_liste(liste["id"])
        self._transformationen = transformationen_der_liste(liste["id"])
        self._berechnungen = berechnungen_der_liste(liste["id"])
        self._ocr_vars = self._ocr_vars_laden()
        
        # Cache für Previews
        self._db_cache = cache_lesen(liste["id"])

        # Original-Namen merken für Umbenennung-Erkennung beim Speichern
        self._orig_transform_namen = {t["id"]: t["name"] for t in self._transformationen}
        self._orig_berech_namen    = {b["id"]: b["name"] for b in self._berechnungen}

        self._setup_fenster()

    def _ocr_vars_laden(self):
        """Globale OCR-Regionen + Template-OCR-Variablen sammeln."""
        namen = set()

        # Globale OCR-Regionen
        namen.update(getattr(self.bot.ocr_engine, "regionen", {}).keys())

        # Template-OCR-Variablen (aus ocr_engine Konfigurationen)
        if hasattr(self.bot.ocr_engine, "template_ocr_konfigurationen"):
            for key in self.bot.ocr_engine.template_ocr_konfigurationen().keys():
                namen.add(key)

        # Aktuell bekannte OCR-Werte aus State (runtime)
        if hasattr(self.bot, "app"):
            namen.update(self.bot.app.state.ocr_values.keys())
            namen.update(self.bot.app.state.template_ocr_values.keys())

        return sorted(namen)

    def _setup_fenster(self):
        self.fenster = tk.Toplevel(self.parent)
        self.fenster.title(f"Liste bearbeiten: {self.liste['name']}")
        self.fenster.configure(bg="#2d2d2d")
        self.fenster.resizable(True, True)
        self.fenster.transient(self.parent)
        self.fenster.grab_set()

        self.fenster.geometry("620x560")
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 620) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 560) // 2
        self.fenster.geometry(f"+{max(0,x)}+{max(0,y)}")

        self._kopf_aufbauen()
        self._tabs_aufbauen()
        self._buttons_aufbauen()

    # ── Kopfbereich ──────────────────────────────────────────────────────────

    def _kopf_aufbauen(self):
        kopf = tk.Frame(self.fenster, bg="#252525")
        kopf.pack(fill=tk.X, padx=12, pady=(12, 8))

        tk.Label(kopf, text="Name:", bg="#252525", fg="#888888",
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._name_var = tk.StringVar(value=self.liste["name"])
        tk.Entry(kopf, textvariable=self._name_var, bg="#1a1a1a", fg="#ffffff",
                 insertbackground="white", font=("Segoe UI", 9), relief=tk.FLAT,
                 bd=4, width=22).grid(row=0, column=1, sticky="ew", padx=(0, 16))

        tk.Label(kopf, text="Update alle:", bg="#252525", fg="#888888",
                 font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self._intervall_var = tk.StringVar(value=str(self.liste["update_intervall"]))
        tk.Entry(kopf, textvariable=self._intervall_var, bg="#1a1a1a", fg="#ffffff",
                 insertbackground="white", font=("Segoe UI", 9), relief=tk.FLAT,
                 bd=4, width=5).grid(row=0, column=3)
        tk.Label(kopf, text="s", bg="#252525", fg="#888888",
                 font=("Segoe UI", 9)).grid(row=0, column=4, sticky="w", padx=(2, 0))

        kopf.columnconfigure(1, weight=1)
        tk.Frame(self.fenster, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=12, pady=(0, 6))

    # ── Tabs: Zeilen | Spalten ───────────────────────────────────────────────

    def _tabs_aufbauen(self):
        tab_leiste = tk.Frame(self.fenster, bg="#2d2d2d")
        tab_leiste.pack(fill=tk.X, padx=12)

        self._tab_inhalt = tk.Frame(self.fenster, bg="#2d2d2d")
        self._tab_inhalt.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        self._aktiver_tab = tk.StringVar(value="zeilen")
        self._tab_btns = {}

        for key, label in [("transform", "OCR Transform"), ("berechnung", "Berechnung"),
                           ("zeilen", "Zeilen"), ("spalten", "Spalten")]:
            btn = tk.Button(tab_leiste, text=label, font=("Segoe UI", 9),
                            relief=tk.FLAT, padx=14, pady=4, cursor="hand2",
                            command=lambda k=key: self._tab_wechseln(k))
            btn.pack(side=tk.LEFT, padx=(0, 2))
            self._tab_btns[key] = btn

        self._tab_wechseln("transform")

    def _tab_wechseln(self, key):
        self._aktiver_tab.set(key)
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.config(bg="#3a3a3a", fg="#ffffff")
            else:
                btn.config(bg="#252525", fg="#666666")

        for w in self._tab_inhalt.winfo_children():
            w.destroy()

        if key == "transform":
            self._transform_tab_aufbauen(self._tab_inhalt)
        elif key == "berechnung":
            # Transformationen neu laden damit neue Einträge im Dropdown erscheinen
            self._transformationen = transformationen_der_liste(self.liste["id"])
            self._orig_transform_namen = {t["id"]: t["name"] for t in self._transformationen}
            self._berechnung_tab_aufbauen(self._tab_inhalt)
        elif key == "zeilen":
            self._zeilen_tab_aufbauen(self._tab_inhalt)
        else:
            # Transformationen + Berechnungen neu laden für aktuelles Dropdown
            self._transformationen = transformationen_der_liste(self.liste["id"])
            self._berechnungen = berechnungen_der_liste(self.liste["id"])
            self._spalten_tab_aufbauen(self._tab_inhalt)

    # ── Tab: Berechnung ──────────────────────────────────────────────────────

    def _berechnung_vars(self, nur_zwischen=False):
        """
        Verfügbare Variablen für Berechnungen.
        nur_zwischen=True: nur Transformationen + Zwischenberechnungen (für Ausgabe-Formeln)
        """
        namen = [t["name"] for t in self._transformationen if t.get("name")]
        # Zwischenberechnungen immer verfügbar
        namen += [b["name"] for b in self._berechnungen if b.get("name") and b.get("typ") == "zwischen"]
        if not nur_zwischen:
            # Ausgabe-Berechnungen auch (für Verkettung)
            namen += [b["name"] for b in self._berechnungen if b.get("name") and b.get("typ") == "ausgabe"]
        return namen + ["update_intervall"]

    def _berechnung_tab_aufbauen(self, parent):
        canvas = tk.Canvas(parent, bg="#2d2d2d", highlightthickness=0)
        scroll = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._berech_container = tk.Frame(canvas, bg="#2d2d2d")
        cw = canvas.create_window((0, 0), window=self._berech_container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._berech_container.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._berech_zeilen_aufbauen()

    def _berech_zeilen_aufbauen(self):
        for w in self._berech_container.winfo_children():
            w.destroy()

        zwischen = [b for b in self._berechnungen if b.get("typ") == "zwischen"]
        ausgabe  = [b for b in self._berechnungen if b.get("typ") != "zwischen"]

        # Sektion: Zwischenberechnungen
        self._berech_sektion_erstellen(self._berech_container, "ZWISCHENBERECHNUNG",
                                        "#1a2a1a", "#4caf50", zwischen, "zwischen")
        # Sektion: Ausgabe
        self._berech_sektion_erstellen(self._berech_container, "AUSGABE",
                                        "#1a1a2a", "#4fc3f7", ausgabe, "ausgabe")

    def _berech_sektion_erstellen(self, parent, titel, hg_farbe, titel_farbe, berechnungen, typ):
        rahmen = tk.Frame(parent, bg="#2d2d2d")
        rahmen.pack(fill=tk.X, pady=(4, 0))

        kopf = tk.Frame(rahmen, bg=hg_farbe)
        kopf.pack(fill=tk.X)
        tk.Label(kopf, text=titel, bg=hg_farbe, fg=titel_farbe,
                 font=("Segoe UI", 8, "bold"), padx=8, pady=3).pack(side=tk.LEFT)
        tk.Button(kopf, text="+ Hinzufügen", bg=hg_farbe, fg=titel_farbe,
                  font=("Segoe UI", 7), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2",
                  command=lambda t=typ: self._berechnung_hinzufuegen(t)).pack(side=tk.RIGHT, padx=4)

        for b in berechnungen:
            self._berech_block_erstellen(rahmen, b)

    def _berech_block_erstellen(self, parent, b):
        block = tk.Frame(parent, bg="#1a1a1a", relief=tk.FLAT, bd=1)
        block.pack(fill=tk.X, pady=2, padx=2)

        # Kopfzeile: Name + Löschen
        kopf = tk.Frame(block, bg="#1a1a1a")
        kopf.pack(fill=tk.X, padx=6, pady=(6, 4))

        tk.Label(kopf, text="Name:", bg="#1a1a1a", fg="#888888",
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        name_var = tk.StringVar(value=b["name"])
        tk.Entry(kopf, textvariable=name_var, bg="#252525", fg="#cccccc",
                 insertbackground="white", font=("Segoe UI", 8), relief=tk.FLAT,
                 bd=3, width=20).pack(side=tk.LEFT, padx=(0, 8))

        ergebnis_lbl = tk.Label(kopf, text="= —", bg="#1a1a1a", fg="#4fc3f7",
                                font=("Consolas", 8))
        ergebnis_lbl.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(kopf, text="✕", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=4, cursor="hand2",
                  command=lambda bid=b["id"]: self._berechnung_loeschen(bid)).pack(side=tk.RIGHT)

        # Formel-Builder Bereich
        formel_frame = tk.Frame(block, bg="#1a1a1a")
        formel_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

        # Formel als lokale Liste (Referenz auf b["formel_json"])
        formel = b["formel_json"] if b["formel_json"] else [{"var": ""}]
        b_typ = b.get("typ", "ausgabe")

        def _formel_neu_zeichnen(ff=formel_frame, fl=formel, el=ergebnis_lbl, nv=name_var, bid=b["id"], bt=b_typ):
            for w in ff.winfo_children():
                w.destroy()
            self._formel_builder_zeichnen(ff, fl, _formel_neu_zeichnen, el, bt)
            self._berech_ergebnis_aktualisieren(fl, el)
            for bb in self._berechnungen:
                if bb["id"] == bid:
                    cur_name = nv.get()
                    bb["name"] = cur_name
                    bb["formel_json"] = fl
                    berechnung_aktualisieren(bid, name=cur_name, formel_json=fl)
                    break

        def _name_geaendert(*_, bid=b["id"], nv=name_var):
            neuer_name = nv.get().strip()
            for bb in self._berechnungen:
                if bb["id"] == bid:
                    bb["name"] = neuer_name
                    berechnung_aktualisieren(bid, name=neuer_name)
                    self._orig_berech_namen[bid] = neuer_name
                    break

        name_var.trace_add("write", _name_geaendert)
        _formel_neu_zeichnen()

    def _formel_builder_zeichnen(self, parent, formel, neu_zeichnen_cb, ergebnis_lbl, b_typ="ausgabe"):
        """Zeichnet den Formel-Builder für eine Berechnung."""
        # Zwischenberechnungen sehen nur Transformationen + andere Zwischen
        # Ausgabe sieht alles
        vars_verfuegbar = self._berechnung_vars(nur_zwischen=(b_typ == "zwischen"))
        optionen = vars_verfuegbar if vars_verfuegbar else ["(keine Vars)"]

        zeile = tk.Frame(parent, bg="#1a1a1a")
        zeile.pack(anchor="w")

        i = 0
        while i < len(formel):
            teil = formel[i]
            if "op" in teil:
                # Operator-Dropdown + ✕ zum Löschen des Operator+Variable Paars
                op_var = tk.StringVar(value=teil["op"])
                op_menu = tk.OptionMenu(zeile, op_var, "+", "-", "*", "/")
                op_menu.config(bg="#252525", fg="#ffca28", font=("Segoe UI", 9, "bold"),
                               relief=tk.FLAT, bd=0, width=2, highlightthickness=0,
                               activebackground="#3a3a3a", cursor="hand2")
                op_menu["menu"].config(bg="#252525", fg="#ffca28", font=("Segoe UI", 9))
                op_menu.pack(side=tk.LEFT, padx=2)

                def _op_change(*_, idx=i, ov=op_var):
                    formel[idx]["op"] = ov.get()
                    neu_zeichnen_cb()
                op_var.trace_add("write", _op_change)

                # Nächstes Element: Var oder feste Zahl
                if i + 1 < len(formel):
                    naechstes = formel[i + 1]

                    if "var" in naechstes:
                        self._var_slot_zeichnen(zeile, naechstes, i + 1, formel, optionen, neu_zeichnen_cb)
                    elif "zahl" in naechstes:
                        self._zahl_slot_zeichnen(zeile, naechstes, i + 1, formel, neu_zeichnen_cb)

                    # Löschen-Button für Operator + Wert
                    tk.Button(zeile, text="–", bg="#3a1a1a", fg="#da3633",
                              font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=5,
                              cursor="hand2",
                              command=lambda idx=i: self._operand_loeschen(formel, idx, neu_zeichnen_cb)
                              ).pack(side=tk.LEFT, padx=(0, 4))
                    i += 2
                    continue

            elif i == 0:
                # Erster Wert — Var oder feste Zahl, kein Löschen
                if "var" in teil:
                    self._var_slot_zeichnen(zeile, teil, 0, formel, optionen, neu_zeichnen_cb)
                elif "zahl" in teil:
                    self._zahl_slot_zeichnen(zeile, teil, 0, formel, neu_zeichnen_cb)

            i += 1

        # + Var und + Zahl Buttons
        tk.Button(zeile, text="+ Var", bg="#1a3a1a", fg="#2ea043",
                  font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=6,
                  cursor="hand2",
                  command=lambda: self._operand_hinzufuegen(formel, neu_zeichnen_cb, "var")).pack(side=tk.LEFT, padx=(4, 2))
        tk.Button(zeile, text="+ Zahl", bg="#1a2a3a", fg="#4fc3f7",
                  font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=6,
                  cursor="hand2",
                  command=lambda: self._operand_hinzufuegen(formel, neu_zeichnen_cb, "zahl")).pack(side=tk.LEFT, padx=2)

    def _var_slot_zeichnen(self, parent, teil, idx, formel, optionen, neu_zeichnen_cb):
        """Zeichnet ein Variablen-Dropdown."""
        v_var = tk.StringVar(value=teil.get("var", ""))
        v_menu = tk.OptionMenu(parent, v_var, *optionen)
        v_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                      relief=tk.FLAT, bd=0, width=16, highlightthickness=0,
                      activebackground="#3a3a3a", cursor="hand2")
        v_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        v_menu.pack(side=tk.LEFT, padx=2)

        def _var_change(*_, i=idx, vv=v_var):
            formel[i]["var"] = vv.get()
            neu_zeichnen_cb()
        v_var.trace_add("write", _var_change)

    def _zahl_slot_zeichnen(self, parent, teil, idx, formel, neu_zeichnen_cb):
        """Zeichnet ein Eingabefeld für feste Zahlen."""
        z_var = tk.StringVar(value=str(teil.get("zahl", "")))
        entry = tk.Entry(parent, textvariable=z_var, bg="#1a2a3a", fg="#4fc3f7",
                         insertbackground="white", font=("Consolas", 8), relief=tk.FLAT,
                         bd=3, width=8)
        entry.pack(side=tk.LEFT, padx=2)

        # Nur Wert merken, KEIN neu_zeichnen_cb — sonst verliert Entry den Fokus
        def _zahl_change(*_, i=idx, zv=z_var):
            formel[i]["zahl"] = zv.get()
        z_var.trace_add("write", _zahl_change)

    def _operand_hinzufuegen(self, formel, neu_zeichnen_cb, slot_typ="var"):
        """Fügt Operator + neuen Slot an die Formel an."""
        formel.append({"op": "+"})
        if slot_typ == "zahl":
            formel.append({"zahl": ""})
        else:
            formel.append({"var": ""})
        neu_zeichnen_cb()

    def _operand_loeschen(self, formel, idx, neu_zeichnen_cb):
        """Löscht Operator + Variable an Position idx und idx+1."""
        if idx >= 0 and idx + 1 < len(formel):
            del formel[idx:idx + 2]
        neu_zeichnen_cb()

    def _berech_ergebnis_aktualisieren(self, formel, ergebnis_lbl):
        """Zeigt das Live-Ergebnis der Berechnung an (inkl. Zwischenberechnungen)."""
        # Aktuelle transformierte Werte sammeln
        ocr_roh = {}
        if hasattr(self.bot, "app"):
            ocr_roh.update(self.bot.app.state.ocr_values)
            ocr_roh.update(self.bot.app.state.template_ocr_values)

        # 1. Alles aus Cache laden als Basis
        self._db_cache = cache_lesen(self.liste["id"])
        werte = {k: v for k, v in self._db_cache.items()}
        jetzt = time.time()

        # 2. Transformationen ausführen (überschreibt Cache bei Live-Daten)
        for t in self._transformationen:
            rohwert = ocr_roh.get(t["ocr_var"])
            if rohwert not in (None, "", "—"):
                ausgabe = transformation_anwenden(rohwert, t["typ"])
                if ausgabe not in (None, "", "—", "?"):
                    werte[t["name"]] = (ausgabe, jetzt)

        # 3. Berechnungen ausführen (Zwischen zuerst, dann Rest)
        berech_sortiert = (
            [b for b in self._berechnungen if b.get("typ") == "zwischen"] +
            [b for b in self._berechnungen if b.get("typ") != "zwischen"]
        )
        for b in berech_sortiert:
            ergebnis = berechnung_auswerten(b["formel_json"], werte, self.liste.get("update_intervall", 30))
            if ergebnis not in ("?", "—") and b["formel_json"]:
                werte[b["name"]] = (ergebnis, jetzt)

        # 4. Das eigentliche Ergebnis für DIESE Formel anzeigen
        ergebnis = berechnung_auswerten(formel, werte, self.liste.get("update_intervall", 30))
        ergebnis_lbl.config(text=f"= {ergebnis}")

    def _berechnung_hinzufuegen(self, typ="ausgabe"):
        name = "neue_zwischen" if typ == "zwischen" else "neue_ausgabe"
        berechnung_hinzufuegen(self.liste["id"], name, typ=typ)
        self._berechnungen = berechnungen_der_liste(self.liste["id"])
        self._berech_zeilen_aufbauen()

    def _berechnung_loeschen(self, berech_id):
        berechnung_loeschen(berech_id)
        self._berechnungen = [b for b in self._berechnungen if b["id"] != berech_id]
        self._berech_zeilen_aufbauen()

    # ── Tab: Zeilen ──────────────────────────────────────────────────────────

    def _zeilen_tab_aufbauen(self, parent):
        tk.Button(parent, text="+ Zeile hinzufügen", bg="#1a3a1a", fg="#2ea043",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._zeile_hinzufuegen).pack(anchor="w", pady=(4, 6))

        # Scrollbarer Bereich
        canvas = tk.Canvas(parent, bg="#2d2d2d", highlightthickness=0)
        scroll = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._zeilen_container = tk.Frame(canvas, bg="#2d2d2d")
        cw = canvas.create_window((0, 0), window=self._zeilen_container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._zeilen_container.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._zeilen_zeilen_aufbauen()

    def _zeilen_zeilen_aufbauen(self):
        for w in self._zeilen_container.winfo_children():
            w.destroy()

        if not self._zeilen:
            tk.Label(self._zeilen_container, text="Keine Zeilen — füge eine hinzu.",
                     bg="#2d2d2d", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=8)
            return

        for z in self._zeilen:
            zeile = tk.Frame(self._zeilen_container, bg="#1a1a1a")
            zeile.pack(fill=tk.X, pady=1)

            name_var = tk.StringVar(value=z["name"])
            tk.Entry(zeile, textvariable=name_var, bg="#252525", fg="#cccccc",
                     insertbackground="white", font=("Segoe UI", 9), relief=tk.FLAT,
                     bd=3, width=30).pack(side=tk.LEFT, padx=(6, 4), pady=4)

            def _on_name_change(*_, zid=z["id"], nv=name_var):
                for zz in self._zeilen:
                    if zz["id"] == zid:
                        neuer_name = nv.get()
                        zz["name"] = neuer_name
                        zeile_umbenennen(zid, neuer_name)
                        break

            name_var.trace_add("write", _on_name_change)

            tk.Button(zeile, text="✕", bg="#1a1a1a", fg="#555555",
                      font=("Segoe UI", 8), relief=tk.FLAT, padx=6,
                      cursor="hand2",
                      command=lambda zid=z["id"]: self._zeile_loeschen(zid)).pack(side=tk.LEFT, padx=4)

    def _zeile_hinzufuegen(self):
        neue_id = zeile_hinzufuegen(self.liste["id"], "Neu")
        self._zeilen = zeilen_der_liste(self.liste["id"])
        self._zeilen_zeilen_aufbauen()

    def _zeile_loeschen(self, zeile_id):
        zeile_loeschen(zeile_id)
        self._zeilen = [z for z in self._zeilen if z["id"] != zeile_id]
        self._zeilen_zeilen_aufbauen()

    # ── Tab: Spalten ─────────────────────────────────────────────────────────

    def _spalten_tab_aufbauen(self, parent):
        # Header
        header = tk.Frame(parent, bg="#1e1e1e")
        header.pack(fill=tk.X, pady=(4, 2))
        for text, breite in [("Name", 13), ("Typ", 8), ("OCR-Variable", 18), ("Format", 10), ("", 3)]:
            tk.Label(header, text=text, bg="#1e1e1e", fg="#666666",
                     font=("Segoe UI", 8, "bold"), width=breite, anchor="w",
                     padx=4, pady=3).pack(side=tk.LEFT)

        tk.Button(parent, text="+ Spalte hinzufügen", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._spalte_hinzufuegen).pack(anchor="w", pady=(0, 4))

        canvas = tk.Canvas(parent, bg="#2d2d2d", highlightthickness=0)
        scroll = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._spalten_container = tk.Frame(canvas, bg="#2d2d2d")
        cw = canvas.create_window((0, 0), window=self._spalten_container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._spalten_container.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._spalten_zeilen_aufbauen()

    def _spalten_zeilen_aufbauen(self):
        for w in self._spalten_container.winfo_children():
            w.destroy()
        for sp in self._spalten:
            self._spalten_zeile_erstellen(sp)

    def _spalten_zeile_erstellen(self, sp):
        zeile = tk.Frame(self._spalten_container, bg="#1a1a1a")
        zeile.pack(fill=tk.X, pady=1)

        name_var = tk.StringVar(value=sp["name"])
        tk.Entry(zeile, textvariable=name_var, bg="#252525", fg="#cccccc",
                 insertbackground="white", font=("Segoe UI", 8), relief=tk.FLAT,
                 bd=3, width=13).pack(side=tk.LEFT, padx=(4, 2), pady=3)

        typ_var = tk.StringVar(value=sp["typ"])
        typ_menu = tk.OptionMenu(zeile, typ_var, "zahl", "text")
        typ_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                        relief=tk.FLAT, bd=0, width=8, highlightthickness=0,
                        activebackground="#3a3a3a", cursor="hand2")
        typ_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        typ_menu.pack(side=tk.LEFT, padx=2)

        # Nur Transformationen + Ausgabe-Berechnungen im Spalten-Tab
        verarbeitete_vars = (
            [t["name"] for t in self._transformationen if t.get("name")] +
            [b["name"] for b in self._berechnungen if b.get("name") and b.get("typ") != "zwischen"]
        )
        ocr_var = tk.StringVar(value=sp.get("ocr_var") or "")
        ocr_optionen = [""] + verarbeitete_vars
        ocr_menu = tk.OptionMenu(zeile, ocr_var, *ocr_optionen if ocr_optionen else [""])
        ocr_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                        relief=tk.FLAT, bd=0, width=18, highlightthickness=0,
                        activebackground="#3a3a3a", cursor="hand2")
        ocr_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        ocr_menu.pack(side=tk.LEFT, padx=2)

        format_var = tk.StringVar(value=sp.get("format") or "standard")
        format_options = ["standard", "K/M/B", "0 (Ganzzahl)", ".2 (2 Nachkomma)"]
        format_menu = tk.OptionMenu(zeile, format_var, *format_options)
        format_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                           relief=tk.FLAT, bd=0, width=10, highlightthickness=0,
                           activebackground="#3a3a3a", cursor="hand2")
        format_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        format_menu.pack(side=tk.LEFT, padx=2)

        tk.Button(zeile, text="✕", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=4, cursor="hand2",
                  command=lambda sid=sp["id"]: self._spalte_loeschen(sid)).pack(side=tk.LEFT, padx=(4, 2))

        def _on_aenderung(*_, sid=sp["id"], nv=name_var, tv=typ_var, ov=ocr_var, fv=format_var):
            neuer_name = nv.get().strip()
            neuer_typ = tv.get()
            neue_ocr = ov.get() or None
            neues_format = fv.get()
            for s in self._spalten:
                if s["id"] == sid:
                    s["name"] = neuer_name
                    s["typ"] = neuer_typ
                    s["ocr_var"] = neue_ocr
                    s["format"] = neues_format
                    # Sofort in DB schreiben
                    spalte_aktualisieren(sid, name=neuer_name, typ=neuer_typ, ocr_var=neue_ocr, format=neues_format)
                    break

        for var in (name_var, typ_var, ocr_var, format_var):
            var.trace_add("write", _on_aenderung)

    def _spalte_hinzufuegen(self):
        spalte_hinzufuegen(self.liste["id"], "Neu", typ="zahl")
        self._spalten = spalten_der_liste(self.liste["id"])
        self._spalten_zeilen_aufbauen()

    def _spalte_loeschen(self, spalte_id):
        spalte_loeschen(spalte_id)
        self._spalten = [s for s in self._spalten if s["id"] != spalte_id]
        self._spalten_zeilen_aufbauen()

    # ── Tab: OCR Transformation ──────────────────────────────────────────────

    def _transform_tab_aufbauen(self, parent):
        tk.Button(parent, text="+ Transformation hinzufügen", bg="#1a3a1a", fg="#2ea043",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._transformation_hinzufuegen).pack(anchor="w", pady=(4, 6))

        canvas = tk.Canvas(parent, bg="#2d2d2d", highlightthickness=0)
        scroll = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._transform_container = tk.Frame(canvas, bg="#2d2d2d")
        cw = canvas.create_window((0, 0), window=self._transform_container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._transform_container.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._transform_zeilen_aufbauen()

    def _transform_zeilen_aufbauen(self):
        for w in self._transform_container.winfo_children():
            w.destroy()

        if not self._transformationen:
            tk.Label(self._transform_container, text="Keine Transformationen definiert.",
                     bg="#2d2d2d", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=8)
            return

        for t in self._transformationen:
            self._transform_zeile_erstellen(t)

    def _transform_zeile_erstellen(self, t):
        block = tk.Frame(self._transform_container, bg="#1a1a1a", relief=tk.FLAT, bd=1)
        block.pack(fill=tk.X, pady=2, padx=2)

        # Zeile 1: Ausgabe-Name + OCR-Variable + Typ + Löschen
        zeile1 = tk.Frame(block, bg="#1a1a1a")
        zeile1.pack(fill=tk.X, padx=6, pady=(6, 2))

        tk.Label(zeile1, text="Name:", bg="#1a1a1a", fg="#888888",
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        name_var = tk.StringVar(value=t["name"])
        tk.Entry(zeile1, textvariable=name_var, bg="#252525", fg="#cccccc",
                 insertbackground="white", font=("Segoe UI", 8), relief=tk.FLAT,
                 bd=3, width=14).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(zeile1, text="OCR-Var:", bg="#1a1a1a", fg="#888888",
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        ocr_var = tk.StringVar(value=t["ocr_var"])
        ocr_optionen = [""] + self._ocr_vars
        ocr_menu = tk.OptionMenu(zeile1, ocr_var, *ocr_optionen)
        ocr_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                        relief=tk.FLAT, bd=0, width=14, highlightthickness=0,
                        activebackground="#3a3a3a", cursor="hand2")
        ocr_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        ocr_menu.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(zeile1, text="✕", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=4, cursor="hand2",
                  command=lambda tid=t["id"]: self._transformation_loeschen(tid)).pack(side=tk.RIGHT)

        # Zeile 2: Rohwert → Ausgabewert live
        zeile2 = tk.Frame(block, bg="#1a1a1a")
        zeile2.pack(fill=tk.X, padx=6, pady=(0, 6))

        tk.Label(zeile2, text="Rohwert:", bg="#1a1a1a", fg="#888888",
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        roh_lbl = tk.Label(zeile2, text="—", bg="#1a1a1a", fg="#ffca28",
                           font=("Consolas", 8), width=12, anchor="w")
        roh_lbl.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(zeile2, text="→", bg="#1a1a1a", fg="#555555",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(zeile2, text="Ausgabe:", bg="#1a1a1a", fg="#888888",
                 font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        aus_lbl = tk.Label(zeile2, text="—", bg="#1a1a1a", fg="#4fc3f7",
                           font=("Consolas", 8), width=12, anchor="w")
        aus_lbl.pack(side=tk.LEFT)

        # Live-Update Funktion
        def _live_update(*_, ov=ocr_var, rl=roh_lbl, al=aus_lbl, t_name=t["name"]):
            ocr_name = ov.get()
            rohwert = "—"
            if ocr_name and hasattr(self.bot, "app"):
                rohwert = self.bot.app.state.ocr_values.get(ocr_name) or \
                          self.bot.app.state.template_ocr_values.get(ocr_name) or "—"
            rl.config(text=str(rohwert))
            
            # Wenn Rohwert da ist: transformieren. Wenn weg: Cache zeigen.
            if rohwert not in (None, "", "—"):
                ausgabe = transformation_anwenden(rohwert, "einheit_zu_zahl")
            else:
                entry = self._db_cache.get(t_name, ("—", 0))
                ausgabe = entry[0]
            
            al.config(text=str(ausgabe))

        ocr_var.trace_add("write", _live_update)
        _live_update()  # Einmal sofort ausführen

        # Änderungen in lokaler Kopie merken
        def _on_aenderung(*_, tid=t["id"], nv=name_var, ov=ocr_var):
            neuer_name = nv.get().strip()
            neue_ocr = ov.get()
            for tr in self._transformationen:
                if tr["id"] == tid:
                    alter_name = tr["name"]
                    tr["name"] = neuer_name
                    tr["ocr_var"] = neue_ocr
                    # Sofort in DB schreiben
                    transformation_aktualisieren(tid, name=neuer_name, ocr_var=neue_ocr)
                    # Orig-Namen aktualisieren
                    self._orig_transform_namen[tid] = neuer_name
                    break

        for var in (name_var, ocr_var):
            var.trace_add("write", _on_aenderung)

    def _transformation_hinzufuegen(self):
        neue_id = transformation_hinzufuegen(self.liste["id"], "neu_transform", "", "einheit_zu_zahl")
        self._transformationen = transformationen_der_liste(self.liste["id"])
        self._transform_zeilen_aufbauen()

    def _transformation_loeschen(self, trans_id):
        transformation_loeschen(trans_id)
        self._transformationen = [t for t in self._transformationen if t["id"] != trans_id]
        self._transform_zeilen_aufbauen()

    # ── Buttons ──────────────────────────────────────────────────────────────

    def _buttons_aufbauen(self):
        tk.Frame(self.fenster, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=12, pady=(4, 0))
        btn_leiste = tk.Frame(self.fenster, bg="#252525")
        btn_leiste.pack(fill=tk.X, padx=12, pady=8)

        tk.Button(btn_leiste, text="✕ Liste löschen", bg="#3a1a1a", fg="#da3633",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=8, pady=4,
                  cursor="hand2", command=self._liste_loeschen).pack(side=tk.LEFT)

        tk.Button(btn_leiste, text="Abbrechen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=4,
                  cursor="hand2", command=self.fenster.destroy).pack(side=tk.RIGHT, padx=(4, 0))

        tk.Button(btn_leiste, text="✔ Speichern", bg="#2ea043", fg="white",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10, pady=4,
                  cursor="hand2", command=self._speichern).pack(side=tk.RIGHT)

    def _speichern(self):
        # Listen-Name + Intervall
        neuer_name = self._name_var.get().strip()
        if neuer_name and neuer_name != self.liste["name"]:
            liste_umbenennen(self.liste["id"], neuer_name)
        try:
            intervall = int(self._intervall_var.get())
            if intervall > 0:
                liste_intervall_setzen(self.liste["id"], intervall)
        except ValueError:
            pass

        # Umbenennungs-Map erstellen: alter Name → neuer Name (für Formel-Update)
        umbenennungen = {}
        for t in self._transformationen:
            alter = self._orig_transform_namen.get(t["id"])
            if alter and alter != t["name"]:
                umbenennungen[alter] = t["name"]
        for b in self._berechnungen:
            alter = self._orig_berech_namen.get(b["id"])
            if alter and alter != b["name"]:
                umbenennungen[alter] = b["name"]

        # Referenzen in Berechnungs-Formeln aktualisieren
        if umbenennungen:
            for b in self._berechnungen:
                geaendert = False
                for teil in b["formel_json"]:
                    if "var" in teil and teil["var"] in umbenennungen:
                        teil["var"] = umbenennungen[teil["var"]]
                        geaendert = True
                if geaendert:
                    berechnung_aktualisieren(b["id"], formel_json=b["formel_json"])

        # Spalten: ocr_var ebenfalls umbenennen falls betroffen
        for sp in self._spalten:
            if sp.get("ocr_var") in umbenennungen:
                sp["ocr_var"] = umbenennungen[sp["ocr_var"]]
                spalte_aktualisieren(sp["id"], ocr_var=sp["ocr_var"])

        # Cache-Keys umbenennen
        if umbenennungen:
            from core.daten_manager import cache_schreiben, cache_lesen
            alter_cache = cache_lesen(self.liste["id"])
            for alter, neu in umbenennungen.items():
                if alter in alter_cache:
                    cache_schreiben(self.liste["id"], neu, alter_cache[alter])

        self.fenster.destroy()
        if self.on_gespeichert:
            self.on_gespeichert()

    def _liste_loeschen(self):
        from tkinter import messagebox
        if messagebox.askyesno("Liste löschen",
                               f"Liste '{self.liste['name']}' wirklich löschen?\nAlle Daten gehen verloren.",
                               parent=self.fenster):
            liste_loeschen(self.liste["id"])
            self.fenster.destroy()
            if self.on_gespeichert:
                self.on_gespeichert()
