import tkinter as tk

class StatePanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.state_labels = {}
        self.nur_aktive = False
        self._last_visible_keys = set()
        
        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        self.container = tk.Frame(self.parent, bg="#2d2d2d")
        self.container.pack(fill=tk.BOTH, expand=True)

    def set_nur_aktive(self, val):
        if self.nur_aktive != val:
            self.nur_aktive = val
            self.aktualisieren()

    def aktualisieren(self):
        """Baut die Liste der Zustände komplett neu auf."""
        for widget in self.container.winfo_children():
            widget.destroy()
        
        self.state_labels = {}
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
            z = tk.Frame(self.container, bg="#1a1a1a")
            z.pack(fill=tk.X, pady=1, padx=2)
            
            tk.Label(z, text=name, bg="#1a1a1a", fg="#cccccc", 
                     font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=8, pady=4)
            
            farbe = "#2ea043" if value else "#da3633"
            text = "TRUE" if value else "FALSE"
            
            lbl = tk.Label(z, text=text, bg=farbe, fg="white", 
                           font=("Consolas", 8, "bold"), width=7, padx=4, cursor="hand2")
            lbl.pack(side=tk.RIGHT, padx=5)
            lbl.bind("<Button-1>", lambda e, n=name, v=value: self._toggle_state(n, v))
            
            self.state_labels[name] = (z, lbl)

    def _toggle_state(self, name, current_val):
        """Invertiert den Wert einer Variable manuell."""
        self.bot.app.state.set_game_state(name, not current_val)
        # Wir erzwingen hier ein sofortiges UI-Update
        self.aktualisieren()

    def werte_aktualisieren(self, game_states):
        """Aktualisiert nur die Farben/Texte der bestehenden Labels."""
        # Bestimme welche Keys aktuell sichtbar sein sollten
        current_visible = set()
        for n, v in game_states.items():
            if not self.nur_aktive or v:
                current_visible.add(n)
        
        # Falls sich die Menge der sichtbaren Keys geändert hat -> Neuaufbau
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
                # Klick-Event aktualisieren
                lbl.bind("<Button-1>", lambda e, n=name, v=value: self._toggle_state(n, v))
