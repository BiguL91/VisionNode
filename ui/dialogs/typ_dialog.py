import tkinter as tk


class TypDialog:
    """
    2-stufiger Dialog beim Erstellen eines neuen Elements.
    Stufe 1: Kategorie wählen (Workflow / State)
    Stufe 2: Typ wählen (Aktive Gruppe / Passive Gruppe / Template)
    callback(typ, kategorie) wird am Ende aufgerufen.
    """

    KATEGORIEN = [
        {
            "key": "workflow",
            "label": "Workflow Template",
            "icon": "⚙",
            "farbe": "#55ff88",
            "beschreibung": "Führt Aktionen aus (Klicks, Abläufe).\nWird im Workflow-Panel angezeigt.",
        },
        {
            "key": "state",
            "label": "State Template",
            "icon": "🚩",
            "farbe": "#ff7043",
            "beschreibung": "Erkennt einen Spielzustand und setzt einen Game-State.\nWird im State-Panel angezeigt.",
        },
    ]

    TYPEN = [
        {
            "key": "aktiv_gruppe",
            "label": "Aktive Gruppe",
            "icon": "★",
            "farbe": "#ffca28",
            "beschreibung": "Hat ein Bild, erkennt sich selbst als Gruppe.\nKind-Templates können zugeordnet werden.",
        },
        {
            "key": "passiv_gruppe",
            "label": "Passive Gruppe",
            "icon": "📦",
            "farbe": "#7a9abf",
            "beschreibung": "Kein Bild, nur Bedingungen.\nOrganisiert andere Templates/Gruppen.",
        },
        {
            "key": "template",
            "label": "Template",
            "icon": "◻",
            "farbe": "#cccccc",
            "beschreibung": "Normales Erkennungs-Template.\nGehört zu einer Gruppe.",
        },
    ]

    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self._kategorie = None
        self._typ = None

        self.fenster = tk.Toplevel(parent)
        self.fenster.title("Neues Element erstellen")
        self.fenster.configure(bg="#2d2d2d")
        self.fenster.resizable(False, False)
        self.fenster.grab_set()

        self._stufe1_bauen()
        self._zentrieren()

    def _zentrieren(self):
        self.fenster.update_idletasks()
        pw = self.parent.winfo_rootx() + self.parent.winfo_width() // 2
        ph = self.parent.winfo_rooty() + self.parent.winfo_height() // 2
        w = self.fenster.winfo_width()
        h = self.fenster.winfo_height()
        self.fenster.geometry(f"+{pw - w // 2}+{ph - h // 2}")

    def _leeren(self):
        for w in self.fenster.winfo_children():
            w.destroy()

    def _stufe1_bauen(self):
        self._leeren()
        tk.Label(self.fenster, text="Welche Kategorie?",
                 bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11, "bold")
                 ).pack(padx=24, pady=(18, 12))

        for k in self.KATEGORIEN:
            self._karte_bauen(k, lambda key=k["key"]: self._kategorie_gewaehlt(key))

        tk.Button(self.fenster, text="Abbrechen",
                  bg="#3a3a3a", fg="#aaaaaa", relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self.fenster.destroy).pack(pady=(8, 16))

    def _kategorie_gewaehlt(self, kategorie):
        self._kategorie = kategorie
        self._stufe2_bauen()

    def _stufe2_bauen(self):
        self._leeren()

        # Header mit Zurück-Button
        kopf = tk.Frame(self.fenster, bg="#2d2d2d")
        kopf.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Button(kopf, text="← Zurück", bg="#2d2d2d", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                  command=self._stufe1_bauen).pack(side=tk.LEFT)
        kategorie_label = "Workflow Template" if self._kategorie == "workflow" else "State Template"
        farbe = "#55ff88" if self._kategorie == "workflow" else "#ff7043"
        tk.Label(kopf, text=f"⚙ {kategorie_label}" if self._kategorie == "workflow" else f"🚩 {kategorie_label}",
                 bg="#2d2d2d", fg=farbe, font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

        tk.Label(self.fenster, text="Welchen Typ?",
                 bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11, "bold")
                 ).pack(padx=24, pady=(4, 12))

        for t in self.TYPEN:
            self._karte_bauen(t, lambda key=t["key"]: self._typ_gewaehlt(key))

        tk.Button(self.fenster, text="Abbrechen",
                  bg="#3a3a3a", fg="#aaaaaa", relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self.fenster.destroy).pack(pady=(8, 16))

        self._zentrieren()

    PASSIV_ARTEN = [
        {
            "key": "master",
            "label": "Master Gruppe",
            "icon": "◈",
            "farbe": "#7a9abf",
            "beschreibung": "Eigenständige Gruppe ohne übergeordnete Gruppe.\nTop-Level-Organisationseinheit.",
        },
        {
            "key": "untergeordnet",
            "label": "Untergeordnete Gruppe",
            "icon": "↳",
            "farbe": "#9abf7a",
            "beschreibung": "Gehört zu einer bestehenden Gruppe.\nWird ihr untergeordnet zugewiesen.",
        },
    ]

    def _typ_gewaehlt(self, typ):
        self._typ = typ
        if typ == "passiv_gruppe":
            self._stufe3_bauen()
        else:
            self.fenster.destroy()
            self.callback(typ, self._kategorie)

    def _stufe3_bauen(self):
        self._leeren()

        kopf = tk.Frame(self.fenster, bg="#2d2d2d")
        kopf.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Button(kopf, text="← Zurück", bg="#2d2d2d", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                  command=self._stufe2_bauen).pack(side=tk.LEFT)
        tk.Label(kopf, text="📦 Passive Gruppe",
                 bg="#2d2d2d", fg="#7a9abf", font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

        tk.Label(self.fenster, text="Welche Art?",
                 bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11, "bold")
                 ).pack(padx=24, pady=(4, 12))

        for a in self.PASSIV_ARTEN:
            self._karte_bauen(a, lambda key=a["key"]: self._passiv_art_gewaehlt(key))

        tk.Button(self.fenster, text="Abbrechen",
                  bg="#3a3a3a", fg="#aaaaaa", relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self.fenster.destroy).pack(pady=(8, 16))

        self._zentrieren()

    def _passiv_art_gewaehlt(self, art):
        self.fenster.destroy()
        self.callback(self._typ, self._kategorie, {"art": art})

    def _karte_bauen(self, t, aktion):
        rahmen = tk.Frame(self.fenster, bg="#3a3a3a", cursor="hand2")
        rahmen.pack(fill=tk.X, padx=16, pady=4)

        def _alle_bg(widget, farbe):
            try: widget.configure(bg=farbe)
            except Exception: pass
            for child in widget.winfo_children():
                _alle_bg(child, farbe)

        def _alle_binden(widget):
            widget.bind("<Button-1>", lambda e: aktion())
            widget.bind("<Enter>", lambda e: _alle_bg(rahmen, "#4a4a4a"))
            widget.bind("<Leave>", lambda e: _alle_bg(rahmen, "#3a3a3a"))
            for child in widget.winfo_children():
                _alle_binden(child)

        innen = tk.Frame(rahmen, bg="#3a3a3a", padx=12, pady=8)
        innen.pack(fill=tk.X)

        kopf = tk.Frame(innen, bg="#3a3a3a")
        kopf.pack(anchor="w")

        tk.Label(kopf, text=t["icon"], bg="#3a3a3a", fg=t["farbe"],
                 font=("Segoe UI", 13), cursor="hand2").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(kopf, text=t["label"], bg="#3a3a3a", fg=t["farbe"],
                 font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side=tk.LEFT)

        tk.Label(innen, text=t["beschreibung"], bg="#3a3a3a", fg="#888888",
                 font=("Segoe UI", 8), justify="left", anchor="w", cursor="hand2"
                 ).pack(anchor="w", padx=(30, 0))

        self.fenster.update_idletasks()
        _alle_binden(rahmen)
