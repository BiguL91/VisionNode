import tkinter as tk

class StatePanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.state_labels = {}
        self.zeilen_frames = {}
        self.ausgewaehlt = None
        self.nur_aktive = False
        self._last_visible_keys = set()

        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        self.container = tk.Frame(self.parent, bg="#2d2d2d")
        self.container.pack(fill=tk.BOTH, expand=True)

        # Button-Leiste unter der Liste
        btn_frame = tk.Frame(self.parent, bg="#2d2d2d")
        btn_frame.pack(anchor="w", pady=(4, 2))

        tk.Button(btn_frame, text="✎ Umbenennen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._umbenennen).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(btn_frame, text="✕ Löschen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._loeschen).pack(side=tk.LEFT)

    def set_nur_aktive(self, val):
        if self.nur_aktive != val:
            self.nur_aktive = val
            self.aktualisieren()

    def _auswahl_setzen(self, name):
        """Markiert eine State-Zeile als ausgewählt."""
        # Vorherige Auswahl zurücksetzen
        if self.ausgewaehlt and self.ausgewaehlt in self.zeilen_frames:
            z_alt = self.zeilen_frames[self.ausgewaehlt]
            z_alt.config(bg="#1a1a1a")
            for child in z_alt.winfo_children():
                bg = child.cget("bg")
                if bg not in ("#2ea043", "#da3633"):
                    child.config(bg="#1a1a1a")

        self.ausgewaehlt = name

        # Neue Auswahl markieren
        if name and name in self.zeilen_frames:
            z_neu = self.zeilen_frames[name]
            z_neu.config(bg="#0d47a1")
            for child in z_neu.winfo_children():
                bg = child.cget("bg")
                if bg not in ("#2ea043", "#da3633"):
                    child.config(bg="#0d47a1")

    def aktualisieren(self):
        """Baut die Liste der Zustände komplett neu auf."""
        for widget in self.container.winfo_children():
            widget.destroy()

        self.state_labels = {}
        self.zeilen_frames = {}
        game_states = self.bot.app.state.game_states

        visible_keys = []
        for name in sorted(game_states.keys()):
            if not self.nur_aktive or game_states[name]:
                visible_keys.append(name)

        self._last_visible_keys = set(visible_keys)

        if not visible_keys:
            txt = "(Nur Aktive)" if self.nur_aktive else "(Keine Zustände definiert)"
            tk.Label(self.container, text=txt, bg="#2d2d2d", fg="#555555",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=5)
            return

        for name in visible_keys:
            value = game_states[name]
            ist_ausgewaehlt = (name == self.ausgewaehlt)
            hintergrund = "#0d47a1" if ist_ausgewaehlt else "#1a1a1a"

            z = tk.Frame(self.container, bg=hintergrund)
            z.pack(fill=tk.X, pady=1, padx=2)
            self.zeilen_frames[name] = z

            name_lbl = tk.Label(z, text=name, bg=hintergrund, fg="#cccccc",
                                font=("Segoe UI", 9), anchor="w", cursor="hand2")
            name_lbl.pack(side=tk.LEFT, padx=8, pady=4, fill=tk.X, expand=True)

            farbe = "#2ea043" if value else "#da3633"
            text = "TRUE" if value else "FALSE"

            lbl = tk.Label(z, text=text, bg=farbe, fg="white",
                           font=("Consolas", 8, "bold"), width=7, padx=4, cursor="hand2")
            lbl.pack(side=tk.RIGHT, padx=5)
            lbl.bind("<Button-1>", lambda e, n=name, v=value: self._toggle_state(n, v))

            # Klick auf Zeile/Name → Auswahl setzen
            z.bind("<Button-1>", lambda e, n=name: self._auswahl_setzen(n))
            name_lbl.bind("<Button-1>", lambda e, n=name: self._auswahl_setzen(n))

            self.state_labels[name] = (z, lbl)

    def _toggle_state(self, name, current_val):
        """Invertiert den Wert einer Variable manuell."""
        self.bot.app.state.set_game_state(name, not current_val)
        self.aktualisieren()

    def _umbenennen(self):
        """Ruft den Umbenennen-Dialog für die ausgewählte State-Variable auf."""
        if not self.ausgewaehlt:
            return
        self.bot._state_variable_umbenennen_dialog(self.ausgewaehlt)

    def _loeschen(self):
        """Löscht die ausgewählte State-Variable."""
        if not self.ausgewaehlt:
            return
        name = self.ausgewaehlt
        self.ausgewaehlt = None
        self.bot._state_variable_loeschen(name)

    def werte_aktualisieren(self, game_states):
        """Aktualisiert nur die Farben/Texte der bestehenden Labels."""
        current_visible = set()
        for n, v in game_states.items():
            if not self.nur_aktive or v:
                current_visible.add(n)

        # Falls sich die Menge der sichtbaren Keys geändert hat → Neuaufbau
        if current_visible != self._last_visible_keys:
            self.aktualisieren()
            return

        # Sonst nur Werte in bestehenden Labels updaten
        for name in current_visible:
            if name in self.state_labels:
                value = game_states[name]
                _, lbl = self.state_labels[name]
                farbe = "#2ea043" if value else "#da3633"
                text = "TRUE" if value else "FALSE"
                lbl.config(text=text, bg=farbe)
                lbl.bind("<Button-1>", lambda e, n=name, v=value: self._toggle_state(n, v))
