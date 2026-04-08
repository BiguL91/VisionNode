import tkinter as tk
from tkinter import ttk, messagebox

class LogicEditor:
    def __init__(self, parent, condition_states, set_states, available_vars=None):
        self.window = tk.Toplevel(parent)
        self.window.title("Erweiterte Template-Logik")
        self.window.geometry("500x650")
        self.window.configure(bg="#2d2d2d")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        # Daten-Normalisierung: condition_states immer als Liste von Dicts
        if isinstance(condition_states, dict):
            self.condition_groups = [dict(condition_states)] if condition_states else []
        else:
            self.condition_groups = [dict(g) for group in (condition_states or []) for g in [group]] if condition_states else []
            
        # Falls leer, eine leere Gruppe starten
        if not self.condition_groups:
            self.condition_groups = []

        self.set_states = dict(set_states or {})
        self.available_vars = sorted(list(available_vars or []))
        
        self.result = None
        self._setup_ui()

    def _setup_ui(self):
        # 1. Footer Buttons zuerst (Fest unten)
        footer = tk.Frame(self.window, bg="#252525", height=60)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)

        tk.Button(footer, text=" Speichern & Schließen ", bg="#2ea043", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=20, pady=8, cursor="hand2", command=self._confirm).pack(side=tk.RIGHT, padx=15)
        
        tk.Button(footer, text=" Abbrechen ", bg="#3a3a3a", fg="#aaaaaa", font=("Segoe UI", 10),
                  relief=tk.FLAT, padx=15, pady=8, cursor="hand2", command=self.window.destroy).pack(side=tk.RIGHT)

        # 2. Haupt-Scroll-Bereich (nimmt den Rest ein)
        container = tk.Frame(self.window, bg="#2d2d2d")
        container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        main_canvas = tk.Canvas(container, bg="#2d2d2d", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=main_canvas.yview)
        self.scroll_frame = tk.Frame(main_canvas, bg="#2d2d2d")

        self.scroll_frame.bind("<Configure>", lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all")))
        main_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw", width=480)
        main_canvas.configure(yscrollcommand=scrollbar.set)

        main_canvas.pack(side="left", fill="both", expand=True, padx=(10,0))
        scrollbar.pack(side="right", fill="y")

        # Mausrad-Scrolling
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._render_all()

    def _render_all(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # --- BEDINGUNGEN ---
        tk.Label(self.scroll_frame, text="SCANNEN NUR WENN...", bg="#2d2d2d", fg="#00bcd4", 
                 font=("Segoe UI", 10, "bold")).pack(fill=tk.X, pady=(15, 10))

        if not self.condition_groups:
            tk.Label(self.scroll_frame, text="(Keine Bedingungen - Template wird immer gescannt)", 
                     bg="#2d2d2d", fg="#666666", font=("Segoe UI", 9, "italic")).pack(pady=10)
        else:
            for idx, group in enumerate(self.condition_groups):
                if idx > 0:
                    tk.Label(self.scroll_frame, text="— ODER —", bg="#2d2d2d", fg="#ff9800", 
                             font=("Segoe UI", 9, "bold")).pack(pady=5)
                
                g_frame = tk.Frame(self.scroll_frame, bg="#1a1a1a", bd=1, padx=10, pady=10)
                g_frame.pack(fill=tk.X, padx=10, pady=5)
                
                header = tk.Frame(g_frame, bg="#1a1a1a")
                header.pack(fill=tk.X)
                tk.Label(header, text=f"Gruppe {idx+1} (UND)", bg="#1a1a1a", fg="#888888", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
                tk.Button(header, text="Gruppe löschen", bg="#1a1a1a", fg="#da3633", font=("Segoe UI", 7), relief=tk.FLAT, 
                          command=lambda i=idx: self._remove_group(i)).pack(side=tk.RIGHT)

                # Variablen in dieser Gruppe
                if not group:
                    tk.Label(g_frame, text="Leere Gruppe (wird ignoriert)", bg="#1a1a1a", fg="#444444", font=("Segoe UI", 8)).pack(pady=5)
                else:
                    for name, val in group.items():
                        row = tk.Frame(g_frame, bg="#252525")
                        row.pack(fill=tk.X, pady=1)
                        tk.Label(row, text=name, bg="#252525", fg="#cccccc", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=5)
                        
                        farbe = "#2ea043" if val else "#da3633"
                        btn = tk.Button(row, text="TRUE" if val else "FALSE", bg=farbe, fg="white", 
                                        font=("Consolas", 8, "bold"), width=6, relief=tk.FLAT,
                                        command=lambda i=idx, n=name, v=val: self._toggle_cond(i, n, v))
                        btn.pack(side=tk.RIGHT, padx=5)
                        tk.Button(row, text="✕", bg="#252525", fg="#555555", relief=tk.FLAT,
                                  command=lambda i=idx, n=name: self._remove_cond(i, n)).pack(side=tk.RIGHT)

                tk.Button(g_frame, text="+ Variable zu dieser Gruppe", bg="#333333", fg="#aaaaaa", font=("Segoe UI", 8), 
                          relief=tk.FLAT, pady=2, command=lambda i=idx: self._add_var_to_group(i)).pack(fill=tk.X, pady=(5,0))

        tk.Button(self.scroll_frame, text=" ➕ Neue ODER-Gruppe hinzufügen ", bg="#3a3a3a", fg="#00bcd4", 
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, pady=8, command=self._add_group).pack(fill=tk.X, padx=10, pady=15)

        # --- AKTIONEN ---
        tk.Frame(self.scroll_frame, bg="#3a3a3a", height=1).pack(fill=tk.X, pady=20)
        tk.Label(self.scroll_frame, text="BEI FUND SETZE...", bg="#2d2d2d", fg="#2ea043", 
                 font=("Segoe UI", 10, "bold")).pack(fill=tk.X, pady=(0, 10))

        a_frame = tk.Frame(self.scroll_frame, bg="#1a1a1a", bd=1, padx=10, pady=10)
        a_frame.pack(fill=tk.X, padx=10, pady=5)

        if not self.set_states:
            tk.Label(a_frame, text="(Keine Aktionen)", bg="#1a1a1a", fg="#555555", font=("Segoe UI", 8, "italic")).pack(pady=10)
        else:
            for name, val in self.set_states.items():
                row = tk.Frame(a_frame, bg="#252525")
                row.pack(fill=tk.X, pady=1)
                tk.Label(row, text=name, bg="#252525", fg="#cccccc", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=5)
                
                farbe = "#2ea043" if val else "#da3633"
                btn = tk.Button(row, text="TRUE" if val else "FALSE", bg=farbe, fg="white", 
                                font=("Consolas", 8, "bold"), width=6, relief=tk.FLAT,
                                command=lambda n=name, v=val: self._toggle_set(n, v))
                btn.pack(side=tk.RIGHT, padx=5)
                tk.Button(row, text="✕", bg="#252525", fg="#555555", relief=tk.FLAT,
                          command=lambda n=name: self._remove_set(n)).pack(side=tk.RIGHT)

        tk.Button(a_frame, text="+ Status-Aktion hinzufügen", bg="#333333", fg="#aaaaaa", font=("Segoe UI", 8), 
                  relief=tk.FLAT, pady=2, command=self._add_action).pack(fill=tk.X, pady=(5,0))

        # Padding unten
        tk.Frame(self.scroll_frame, bg="#2d2d2d", height=100).pack()

    # --- Logik Methoden ---
    def _add_group(self):
        self.condition_groups.append({})
        self._render_all()

    def _remove_group(self, idx):
        self.condition_groups.pop(idx)
        self._render_all()

    def _add_var_to_group(self, group_idx):
        self._add_var_dialog(lambda n, t: self._finalize_add(group_idx, n, t))

    def _finalize_add(self, group_idx, name, typ):
        if group_idx is not None:
            self.condition_groups[group_idx][name] = True
        else:
            self.set_states[name] = True
        self._render_all()

    def _toggle_cond(self, g_idx, name, val):
        self.condition_groups[g_idx][name] = not val
        self._render_all()

    def _remove_cond(self, g_idx, name):
        del self.condition_groups[g_idx][name]
        self._render_all()

    def _add_action(self):
        self._add_var_dialog(lambda n, t: self._finalize_add(None, n, t))

    def _toggle_set(self, name, val):
        self.set_states[name] = not val
        self._render_all()

    def _remove_set(self, name):
        del self.set_states[name]
        self._render_all()

    def _add_var_dialog(self, callback):
        d = tk.Toplevel(self.window)
        d.title("Variable wählen")
        d.geometry("300x180")
        d.configure(bg="#2d2d2d")
        d.transient(self.window)
        d.grab_set()

        # Positionieren
        x = self.window.winfo_x() + 100
        y = self.window.winfo_y() + 150
        d.geometry(f"+{x}+{y}")

        tk.Label(d, text="Name der Variable:", bg="#2d2d2d", fg="#cccccc", font=("Segoe UI", 9)).pack(pady=(20, 5))
        name_var = tk.StringVar()
        combo = ttk.Combobox(d, textvariable=name_var, values=self.available_vars, font=("Segoe UI", 10))
        combo.pack(padx=30, fill=tk.X)
        combo.focus()

        def ok():
            n = name_var.get().strip()
            if n: 
                callback(n, None)
                d.destroy()
        
        combo.bind("<Return>", lambda e: ok())
        tk.Button(d, text=" OK / Hinzufügen ", bg="#2ea043", fg="white", font=("Segoe UI", 9, "bold"), 
                  relief=tk.FLAT, padx=20, pady=8, command=ok).pack(pady=20)

    def _confirm(self):
        # Leere Gruppen filtern
        final_groups = [g for g in self.condition_groups if g]
        # Falls nur eine Gruppe da ist, als Dict speichern (Kompatibilität), sonst als Liste
        result_cond = final_groups if len(final_groups) > 1 else (final_groups[0] if final_groups else {})
        
        self.result = (result_cond, self.set_states)
        self.window.destroy()
