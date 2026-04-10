import tkinter as tk


class TypDialog:
    """Kleiner Modal-Dialog zur Auswahl des Template-Typs beim Erstellen."""

    TYPEN = [
        {
            "key": "aktiv_gruppe",
            "label": "Aktive Gruppe",
            "icon": "★",
            "farbe": "#ffca28",
            "beschreibung": "Hat ein Bild, erkennt sich selbst als Gruppe.\nKindtemplates können ihr zugeordnet werden.",
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
        {
            "key": "state_template",
            "label": "State Template",
            "icon": "🚩",
            "farbe": "#ff7043",
            "beschreibung": "Erkennt etwas und setzt einen Game-State.\nStrukturell identisch mit Template.",
        },
    ]

    def __init__(self, parent, callback):
        """
        callback(typ: str) wird aufgerufen mit einem der keys aus TYPEN.
        Dialog schließt sich danach automatisch.
        """
        self.callback = callback

        self.fenster = tk.Toplevel(parent)
        self.fenster.title("Neues Element erstellen")
        self.fenster.configure(bg="#2d2d2d")
        self.fenster.resizable(False, False)
        self.fenster.grab_set()

        self._aufbauen()
        self.fenster.update_idletasks()

        # Zentrieren über Parent
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.fenster.winfo_width()
        h = self.fenster.winfo_height()
        self.fenster.geometry(f"+{pw - w // 2}+{ph - h // 2}")

    def _aufbauen(self):
        tk.Label(self.fenster, text="Was möchtest du erstellen?",
                 bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11, "bold")
                 ).pack(padx=24, pady=(18, 12))

        for t in self.TYPEN:
            self._karte_bauen(t)

        tk.Button(self.fenster, text="Abbrechen",
                  bg="#3a3a3a", fg="#aaaaaa", relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self.fenster.destroy
                  ).pack(pady=(8, 16))

    def _karte_bauen(self, t):
        rahmen = tk.Frame(self.fenster, bg="#3a3a3a", cursor="hand2")
        rahmen.pack(fill=tk.X, padx=16, pady=4)

        def waehlen(key=t["key"]):
            self.fenster.destroy()
            self.callback(key)

        def hover_an(e):
            _alle_bg(rahmen, "#4a4a4a")

        def hover_ab(e):
            _alle_bg(rahmen, "#3a3a3a")

        def _alle_bg(widget, farbe):
            try: widget.configure(bg=farbe)
            except Exception: pass
            for child in widget.winfo_children():
                _alle_bg(child, farbe)

        def _alle_binden(widget):
            widget.bind("<Button-1>", lambda e: waehlen())
            widget.bind("<Enter>", hover_an)
            widget.bind("<Leave>", hover_ab)
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

        # Alle Widgets nach dem Aufbau binden
        self.fenster.update_idletasks()
        _alle_binden(rahmen)
