import tkinter as tk
import time
from helpers import _template_farbe

class VariablePanel:
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.ocr_engine = bot.ocr_engine

        self._nur_aktive_variablen = False
        self.timer_eintraege = {}
        self.gruppen_frames = {}
        self.gruppen_reihenfolge = []
        self._ocr_letzter_wert_zeit = {}
        self._letzte_ocr_konfig_keys = None

        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        outer = tk.Frame(self.parent, bg="#2d2d2d")
        outer.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(outer, bg="#2d2d2d", highlightthickness=0)
        self._scrollbar = tk.Scrollbar(outer, orient="vertical",
                                       command=self._canvas.yview,
                                       bg="#3a3a3a", troughcolor="#1a1a1a",
                                       activebackground="#555555", width=8)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.container = tk.Frame(self._canvas, bg="#2d2d2d")
        self._canvas_window = self._canvas.create_window((0, 0), window=self.container, anchor="nw")

        self.container.bind("<Configure>", self._on_container_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel nur aktiv wenn Maus über Canvas
        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all("<MouseWheel>"))

        self.header_extra = tk.Frame(self.container, bg="#2d2d2d")

    def _on_container_configure(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def set_nur_aktive(self, nur_aktive):
        self._nur_aktive_variablen = nur_aktive
        self._sichtbarkeit_aktualisieren(self._aktuelle_matches(), time.time())

    def _aktuelle_matches(self):
        akt = set()
        if hasattr(self.bot, "app"):
            for m in self.bot.app.state.active_matches:
                akt.add(m[0])
                if len(m) > 6: akt.add(m[6])
        return akt

    def aktualisieren(self):
        """Vollständiger Rebuild der UI-Struktur – nur bei strukturellen Änderungen."""
        for widget in self.container.winfo_children():
            widget.destroy()

        self.timer_eintraege = {}
        self.gruppen_frames = {}
        self.gruppen_reihenfolge = []
        m_farbe = {"Timer": "#42a5f5", "Zahl": "#ffca28", "Text": "#aaaaaa"}
        hat = False

        # 1. Feste Regionen
        if self.ocr_engine.regionen:
            hat = True
            frame = self._gruppe_erstellen("Feste Regionen", "#888888",
                                   [(n, n, r.get("modus", "Text"), lambda _n=n: self.bot._ocr_region_loeschen(_n))
                                    for n, r in self.ocr_engine.regionen.items()], m_farbe)
            self.gruppen_frames["_feste_"] = frame
            self.gruppen_reihenfolge.append("_feste_")

        # 2. Template OCR – ALLE Gruppen erstellen (auch inaktive)
        konf = self.ocr_engine.template_ocr_konfigurationen()
        grp = {}
        for en, k in konf.items():
            grp.setdefault(k.get("template", en), []).append(
                (en, en, k.get("modus", "Text"), lambda _n=en: self.bot._template_ocr_aus_panel_loeschen(_n))
            )

        self._letzte_ocr_konfig_keys = set(konf.keys())

        for tn, ents in grp.items():
            hat = True
            frame = self._gruppe_erstellen(tn, _template_farbe(tn), ents, m_farbe)
            self.gruppen_frames[tn] = frame
            self.gruppen_reihenfolge.append(tn)

        if not hat:
            tk.Label(self.container, text="(Keine Variablen)", bg="#2d2d2d", fg="#555555",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=8)

        self._sichtbarkeit_aktualisieren(self._aktuelle_matches(), time.time())

    def _gruppe_erstellen(self, gn, f, ents, mf):
        g = tk.Frame(self.container, bg="#1a1a1a")
        g.pack(fill=tk.X, pady=3, padx=2)
        tk.Frame(g, bg=f, width=3).pack(side=tk.LEFT, fill=tk.Y)
        inh = tk.Frame(g, bg="#1a1a1a")
        inh.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        k = tk.Frame(inh, bg="#1a1a1a")
        k.pack(fill=tk.X, padx=(6, 4), pady=(4, 2))
        tk.Label(k, text=gn, bg="#1a1a1a", fg=f, font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        tk.Frame(inh, bg="#2d2d2d", height=1).pack(fill=tk.X, padx=4)

        gs = [("Consolas", 18, "bold"), ("Consolas", 13, "bold"), ("Consolas", 10, "bold")]

        for s, an, m, lc in ents:
            z = tk.Frame(inh, bg="#1a1a1a")
            z.pack(fill=tk.X, padx=(6, 4), pady=2)
            l = tk.Frame(z, bg="#1a1a1a")
            l.pack(side=tk.LEFT, fill=tk.Y)
            tk.Label(l, text=f"[{m}]", bg="#1a1a1a", fg=mf.get(m, "#aaa"), font=("Segoe UI", 7)).pack(anchor="w")
            tk.Label(l, text=an, bg="#1a1a1a", fg="#888888", font=("Segoe UI", 8)).pack(anchor="w")
            tk.Button(z, text="✕", bg="#1a1a1a", fg="#333333", font=("Segoe UI", 7),
                      relief=tk.FLAT, cursor="hand2", command=lc).pack(side=tk.RIGHT)

            idx = [0]
            wl = tk.Label(z, text="–", bg="#1a1a1a", fg="#ffffff", font=gs[0], anchor="e")
            wl.pack(side=tk.RIGHT, padx=4, fill=tk.X, expand=True)

            def sw(e, _l=wl, _i=idx):
                _i[0] = (_i[0] + 1) % 3
                _l.config(font=gs[_i[0]])

            wl.bind("<Double-Button-1>", sw)
            self.timer_eintraege[s] = wl
        return g

    def _soll_sichtbar(self, tn, aktuelle_matches, jetzt):
        if tn == "_feste_":
            return True
        if not self._nur_aktive_variablen:
            return True
        if tn not in aktuelle_matches:
            return False
        konf = self.ocr_engine.template_ocr_konfigurationen()
        relevant_ocrs = [en for en, k in konf.items() if k.get("template") == tn]
        if not relevant_ocrs:
            return True
        return any(jetzt - self._ocr_letzter_wert_zeit.get(en, 0) < 2.0 for en in relevant_ocrs)

    def _sichtbarkeit_aktualisieren(self, aktuelle_matches, jetzt):
        """Blendet Gruppen ein/aus – behält dabei die korrekte Reihenfolge."""
        soll = {tn for tn in self.gruppen_reihenfolge if self._soll_sichtbar(tn, aktuelle_matches, jetzt)}
        ist  = {tn for tn in self.gruppen_reihenfolge
                if tn in self.gruppen_frames and self.gruppen_frames[tn].winfo_ismapped()}

        if soll == ist:
            return

        for tn in self.gruppen_reihenfolge:
            frame = self.gruppen_frames.get(tn)
            if frame:
                frame.pack_forget()

        for tn in self.gruppen_reihenfolge:
            if tn in soll:
                frame = self.gruppen_frames.get(tn)
                if frame:
                    frame.pack(fill=tk.X, pady=3, padx=2)

    def werte_aktualisieren(self, w):
        jetzt = time.time()

        for n, t in w.items():
            if t and t not in ("", "—", "-"):
                self._ocr_letzter_wert_zeit[n] = jetzt

        aktuelle_konf_keys = set(self.ocr_engine.template_ocr_konfigurationen().keys())
        if aktuelle_konf_keys != self._letzte_ocr_konfig_keys:
            self.aktualisieren()
            return

        for n in self.timer_eintraege:
            if n not in w:
                self.timer_eintraege[n].config(text="–", fg="#555555")

        for n, t in w.items():
            if n in self.timer_eintraege:
                val = t if t else "–"
                self.timer_eintraege[n].config(
                    text=val,
                    fg="#ffffff" if val != "–" else "#888888"
                )

        self._sichtbarkeit_aktualisieren(self._aktuelle_matches(), jetzt)
