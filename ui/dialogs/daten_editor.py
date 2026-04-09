import tkinter as tk
from core.daten_manager import (
    spalten_der_liste, spalte_hinzufuegen, spalte_aktualisieren, spalte_loeschen,
    zeilen_der_liste, zeile_hinzufuegen, zeile_umbenennen, zeile_loeschen,
    liste_umbenennen, liste_intervall_setzen, liste_loeschen
)


class DatenListeEditor:
    def __init__(self, parent, bot, liste, on_gespeichert=None):
        self.parent = parent
        self.bot = bot
        self.liste = liste
        self.on_gespeichert = on_gespeichert

        self._spalten = spalten_der_liste(liste["id"])
        self._zeilen = zeilen_der_liste(liste["id"])
        self._ocr_vars = self._ocr_vars_laden()

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

        for key, label in [("zeilen", "Zeilen"), ("spalten", "Spalten")]:
            btn = tk.Button(tab_leiste, text=label, font=("Segoe UI", 9),
                            relief=tk.FLAT, padx=14, pady=4, cursor="hand2",
                            command=lambda k=key: self._tab_wechseln(k))
            btn.pack(side=tk.LEFT, padx=(0, 2))
            self._tab_btns[key] = btn

        self._tab_wechseln("zeilen")

    def _tab_wechseln(self, key):
        self._aktiver_tab.set(key)
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.config(bg="#3a3a3a", fg="#ffffff")
            else:
                btn.config(bg="#252525", fg="#666666")

        for w in self._tab_inhalt.winfo_children():
            w.destroy()

        if key == "zeilen":
            self._zeilen_tab_aufbauen(self._tab_inhalt)
        else:
            self._spalten_tab_aufbauen(self._tab_inhalt)

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
                        zz["name"] = nv.get()
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
        for text, breite in [("Name", 15), ("Typ", 10), ("OCR-Variable", 20), ("", 3)]:
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

        ocr_var = tk.StringVar(value=sp.get("ocr_var") or "")
        ocr_optionen = [""] + self._ocr_vars
        ocr_menu = tk.OptionMenu(zeile, ocr_var, *ocr_optionen if ocr_optionen else [""])
        ocr_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                        relief=tk.FLAT, bd=0, width=18, highlightthickness=0,
                        activebackground="#3a3a3a", cursor="hand2")
        ocr_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        ocr_menu.pack(side=tk.LEFT, padx=2)

        tk.Button(zeile, text="✕", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=4, cursor="hand2",
                  command=lambda sid=sp["id"]: self._spalte_loeschen(sid)).pack(side=tk.LEFT, padx=(4, 2))

        def _on_aenderung(*_, sid=sp["id"], nv=name_var, tv=typ_var, ov=ocr_var):
            for s in self._spalten:
                if s["id"] == sid:
                    s["name"] = nv.get()
                    s["typ"] = tv.get()
                    s["ocr_var"] = ov.get() or None
                    break

        for var in (name_var, typ_var, ocr_var):
            var.trace_add("write", _on_aenderung)

    def _spalte_hinzufuegen(self):
        spalte_hinzufuegen(self.liste["id"], "Neu", typ="zahl")
        self._spalten = spalten_der_liste(self.liste["id"])
        self._spalten_zeilen_aufbauen()

    def _spalte_loeschen(self, spalte_id):
        spalte_loeschen(spalte_id)
        self._spalten = [s for s in self._spalten if s["id"] != spalte_id]
        self._spalten_zeilen_aufbauen()

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

        # Zeilen-Namen in DB schreiben
        for z in self._zeilen:
            zeile_umbenennen(z["id"], z["name"])

        # Spalten-Änderungen in DB schreiben
        for sp in self._spalten:
            spalte_aktualisieren(
                sp["id"],
                name=sp["name"],
                typ=sp["typ"],
                ocr_var=sp.get("ocr_var")
            )

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
