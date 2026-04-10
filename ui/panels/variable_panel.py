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
        self._ocr_letzter_wert_zeit = {} 
        self._letzte_aktive_templates = set()
        
        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        self.container = tk.Frame(self.parent, bg="#2d2d2d")
        self.container.pack(fill=tk.BOTH, expand=True)
        
        # Header with Toggle
        self.header_extra = tk.Frame(self.container, bg="#2d2d2d")

    def set_nur_aktive(self, nur_aktive):
        self._nur_aktive_variablen = nur_aktive
        self.aktualisieren()

    def aktualisieren(self):
        for widget in self.container.winfo_children():
            widget.destroy()
        
        self.timer_eintraege = {}
        self.gruppen_frames = {} 
        m_farbe = {"Timer": "#42a5f5", "Zahl": "#ffca28", "Text": "#aaaaaa"}
        hat = False
        
        # 1. Feste Regionen
        if self.ocr_engine.regionen:
            hat = True
            self.gruppen_frames["_feste_"] = self._gruppe_erstellen("Feste Regionen", "#888888", 
                                   [(n, n, r.get("modus", "Text"), lambda _n=n: self.bot._ocr_region_loeschen(_n)) 
                                    for n, r in self.ocr_engine.regionen.items()], m_farbe)
        
        # 2. Template OCR
        konf = self.ocr_engine.template_ocr_konfigurationen()
        grp = {}
        for en, k in konf.items():
            grp.setdefault(k.get("template", en), []).append(
                (en, en, k.get("modus", "Text"), lambda _n=en: self.bot._template_ocr_aus_panel_loeschen(_n))
            )
            
        akt = set()
        if hasattr(self.bot, "app"):
            for m in self.bot.app.state.active_matches:
                akt.add(m[0])
                if len(m) > 6: akt.add(m[6])
        
        self._letzte_aktive_templates = akt

        for tn, ents in grp.items():
            if self._nur_aktive_variablen and tn not in akt:
                continue
            hat = True
            self.gruppen_frames[tn] = self._gruppe_erstellen(tn, _template_farbe(tn), ents, m_farbe)
            
        if not hat:
            tk.Label(self.container, text="(Keine Variablen)", bg="#2d2d2d", fg="#555555", 
                     font=("Segoe UI", 9)).pack(anchor="w", padx=8)

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

    def werte_aktualisieren(self, w):
        jetzt = time.time()
        
        # 1. OCR-Zeitstempel aktualisieren (Gedächtnis für "Hysterese")
        for n, t in w.items():
            if t and t not in ("", "—", "-"):
                self._ocr_letzter_wert_zeit[n] = jetzt
        
        # 2. Menge der aktuell gefundenen Templates ermitteln
        aktuelle_matches = set()
        if hasattr(self.bot, "app"):
            for m in self.bot.app.state.active_matches:
                aktuelle_matches.add(m[0])
                if len(m) > 6: aktuelle_matches.add(m[6])
        
        # 3. Struktur-Check: Falls ein ganz neues Icon auftaucht, UI neu aufbauen
        if self._nur_aktive_variablen:
            letzte = getattr(self, "_letzte_aktive_templates", set())
            if not aktuelle_matches.issubset(letzte):
                self.aktualisieren()
                return

        # 4. Werte setzen
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

        # 5. Dynamisches Ein/Ausblenden der Gruppen (Surgical Fix für "Email")
        if self._nur_aktive_variablen:
            konf = self.ocr_engine.template_ocr_konfigurationen()
            for tn, frame in self.gruppen_frames.items():
                if tn == "_feste_": continue
                
                ist_gematcht = tn in aktuelle_matches
                hat_kürzlich_wert = False
                
                relevant_ocrs = [en for en, k in konf.items() if k.get("template") == tn]
                if not relevant_ocrs:
                    hat_kürzlich_wert = True # Icons ohne OCR bleiben immer da
                else:
                    for en in relevant_ocrs:
                        # Wenn innerhalb der letzten 2.0 Sekunden ein Wert da war -> bleiben
                        if jetzt - self._ocr_letzter_wert_zeit.get(en, 0) < 2.0:
                            hat_kürzlich_wert = True
                            break
                
                if ist_gematcht and hat_kürzlich_wert:
                    if not frame.winfo_viewable():
                        frame.pack(fill=tk.X, pady=3, padx=2)
                else:
                    if frame.winfo_viewable():
                        frame.pack_forget()
