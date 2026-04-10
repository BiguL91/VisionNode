import tkinter as tk
from tkinter import ttk, messagebox


class GruppeEditor:
    """Konfiguriert Bedingungen für eine Dummy-Gruppe (condition_states ohne eigenes Template)."""

    def __init__(self, parent, bot, gruppe_name, on_save=None):
        self.bot = bot
        self.gruppe_name = gruppe_name
        self.on_save = on_save

        self.fenster = tk.Toplevel(parent)
        self.fenster.title(f"Gruppe konfigurieren: {gruppe_name}")
        self.fenster.configure(bg="#2d2d2d")
        self.fenster.grab_set()
        self.fenster.resizable(True, True)
        self.fenster.minsize(520, 400)

        # Bestehende Konfiguration laden (neues Format: plain key, altes: __gruppe__ prefix)
        gespeichert = self.bot.template_engine.settings.get(gruppe_name, {})
        if not gespeichert or gespeichert.get("typ") not in ("passiv_gruppe", "aktiv_gruppe"):
            gespeichert = self.bot.template_engine.settings.get(f"__gruppe__{gruppe_name}", {})
        self._condition_states = self._migrate(gespeichert.get("condition_states", []))

        self._aufbauen()

    @staticmethod
    def _migrate(raw):
        if not raw:
            return []
        if isinstance(raw, dict):
            return [{"connector": None, "states": raw}]
        first = raw[0] if raw else {}
        if isinstance(first, dict) and ("states" in first or "connector" in first):
            return list(raw)
        return []

    def _aufbauen(self):
        try:
            bekannte = sorted(self.bot.app.state.game_states.keys())
        except Exception:
            bekannte = []

        # Header
        tk.Label(self.fenster,
                 text=f"Bedingungen für Gruppe \"{self.gruppe_name}\"",
                 bg="#2d2d2d", fg="#ffca28",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(14, 2))
        tk.Label(self.fenster,
                 text="Alle Templates in dieser Gruppe sind nur aktiv wenn diese Bedingungen erfüllt sind.\n"
                      "AND innerhalb einer Gruppe, Gruppen können AND oder OR verknüpft werden.",
                 bg="#2d2d2d", fg="#666666", font=("Segoe UI", 8),
                 justify="left").pack(anchor="w", padx=20, pady=(0, 8))

        gruppen_container = tk.Frame(self.fenster, bg="#2d2d2d")
        gruppen_container.pack(fill=tk.BOTH, expand=True, padx=20)

        gruppen = []

        def refresh_first_connector():
            for i, g in enumerate(gruppen):
                cf = g.get("connector_frame")
                if cf:
                    if i == 0:
                        cf.pack_forget()

        def gruppe_loeschen(g):
            gruppen.remove(g)
            g["wrapper"].destroy()
            refresh_first_connector()

        def zeile_in_gruppe_bauen(g, state_name="", state_val=True):
            zf = g["zeilen_frame"]
            z = tk.Frame(zf, bg="#1a1a1a")
            z.pack(fill=tk.X, pady=2)
            n_var = tk.StringVar(value=state_name)
            v_var = tk.BooleanVar(value=state_val)
            ttk.Combobox(z, textvariable=n_var, values=bekannte, width=22,
                         font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(6, 4), pady=4)
            tk.Checkbutton(z, text="True", variable=v_var, bg="#1a1a1a", fg="#cccccc",
                           selectcolor="#2d2d2d", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 4))
            t = (z, n_var, v_var)
            g["zeilen"].append(t)
            tk.Button(z, text="✕", bg="#1a1a1a", fg="#da3633", relief=tk.FLAT, font=("Segoe UI", 10),
                      command=lambda ref=t: (g["zeilen"].remove(ref) if ref in g["zeilen"] else None,
                                            z.destroy())).pack(side=tk.RIGHT, padx=6)

        def gruppe_bauen(gruppe_data):
            wrapper = tk.Frame(gruppen_container, bg="#2d2d2d")
            wrapper.pack(fill=tk.X, pady=(0, 2))

            g = {"wrapper": wrapper, "connector_frame": None, "connector_var": None, "zeilen": []}

            conn_frame = tk.Frame(wrapper, bg="#2d2d2d")
            g["connector_frame"] = conn_frame
            cv = tk.StringVar(value=gruppe_data.get("connector") or "OR")
            g["connector_var"] = cv
            tk.Label(conn_frame, text="Verknüpfung:", bg="#2d2d2d", fg="#888888",
                     font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 8))
            for txt, clr in [("AND", "#55aaff"), ("OR", "#ffca28")]:
                tk.Radiobutton(conn_frame, text=txt, variable=cv, value=txt,
                               bg="#2d2d2d", fg=clr, selectcolor="#1a1a1a",
                               activebackground="#2d2d2d",
                               font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=4)
            conn_frame.pack(fill=tk.X, pady=(8, 3))

            nr = len(gruppen) + 1
            box = tk.Frame(wrapper, bg="#1a1a1a", bd=1, relief=tk.SOLID,
                           highlightbackground="#3a3a3a", highlightthickness=1)
            box.pack(fill=tk.X)
            g["box"] = box

            header = tk.Frame(box, bg="#252525")
            header.pack(fill=tk.X)
            tk.Label(header, text=f"  Gruppe {nr}", bg="#252525", fg="#888888",
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, pady=5)
            tk.Button(header, text="Gruppe löschen", bg="#252525", fg="#da3633",
                      font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                      command=lambda ref=g: gruppe_loeschen(ref)).pack(side=tk.RIGHT, padx=8, pady=3)

            zeilen_frame = tk.Frame(box, bg="#1a1a1a")
            zeilen_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
            g["zeilen_frame"] = zeilen_frame

            for sn, sv in gruppe_data.get("states", {}).items():
                zeile_in_gruppe_bauen(g, sn, sv)

            tk.Button(box, text="+ Bedingung hinzufügen", bg="#1a1a1a", fg="#aaaaaa",
                      font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                      command=lambda ref=g: zeile_in_gruppe_bauen(ref)).pack(anchor="w", padx=8, pady=6)

            gruppen.append(g)
            refresh_first_connector()

        daten = self._condition_states if self._condition_states else [{"connector": None, "states": {}}]
        for gd in daten:
            gruppe_bauen(gd)

        tk.Button(gruppen_container, text="＋ Neue Gruppe hinzufügen",
                  bg="#1a3a5a", fg="#55aaff", font=("Segoe UI", 9), relief=tk.FLAT,
                  padx=10, pady=4, cursor="hand2",
                  command=lambda: gruppe_bauen({"connector": "OR", "states": {}})
                  ).pack(anchor="w", pady=(8, 0))

        # Buttons
        tk.Frame(self.fenster, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=20, pady=(14, 0))
        btn_f = tk.Frame(self.fenster, bg="#2d2d2d")
        btn_f.pack(fill=tk.X, padx=20, pady=12)

        def speichern():
            conditions = []
            for g in gruppen:
                states = {}
                for _, n_var, v_var in g["zeilen"]:
                    n = n_var.get().strip()
                    if n:
                        states[n] = v_var.get()
                if states:
                    conditions.append({
                        "connector": g["connector_var"].get() if g["connector_var"] else None,
                        "states": states,
                    })
            if conditions:
                conditions[0]["connector"] = None

            self.bot.template_engine.gruppe_config_speichern(self.gruppe_name, conditions)
            if self.on_save:
                self.on_save()
            self.fenster.destroy()

        def loeschen():
            if messagebox.askyesno("Konfiguration löschen",
                                   f"Gruppen-Konfiguration für \"{self.gruppe_name}\" wirklich löschen?",
                                   parent=self.fenster):
                self.bot.template_engine.gruppe_config_loeschen(self.gruppe_name)
                if self.on_save:
                    self.on_save()
                self.fenster.destroy()

        tk.Button(btn_f, text="Speichern", bg="#1a5a2a", fg="#55ff88",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=14, pady=5,
                  cursor="hand2", command=speichern).pack(side=tk.LEFT)

        tk.Button(btn_f, text="Konfiguration löschen", bg="#3a3a3a", fg="#da3633",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=5,
                  cursor="hand2", command=loeschen).pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(btn_f, text="Schließen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=5,
                  cursor="hand2", command=self.fenster.destroy).pack(side=tk.RIGHT)
