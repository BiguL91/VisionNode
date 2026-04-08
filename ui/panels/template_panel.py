import tkinter as tk
from collections import defaultdict
from helpers import _template_farbe

class TemplatePanel:
    def __init__(self, parent, bot, filter_modus="all"):
        self.parent = parent
        self.bot = bot
        self.template_engine = bot.template_engine
        self.ocr_engine = bot.ocr_engine
        self.action_engine = bot.action_engine
        self.filter_modus = filter_modus
        
        self._setup_ui()
        self.aktualisieren()

    def _setup_ui(self):
        # Container
        self.frame = tk.Frame(self.parent, bg="#2d2d2d")
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Liste
        liste_frame = tk.Frame(self.frame, bg="#2d2d2d")
        liste_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(liste_frame, orient=tk.VERTICAL, bg="#3a3a3a",
                                  troughcolor="#1a1a1a", width=8)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.template_liste = tk.Listbox(liste_frame, bg="#2d2d2d", fg="#cccccc",
                                          selectbackground="#0d47a1", font=("Segoe UI", 9),
                                          relief=tk.FLAT, bd=0,
                                          yscrollcommand=scrollbar.set)
        self.template_liste.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.template_liste.yview)

        # Buttons Zeile 1
        zeile1 = tk.Frame(self.frame, bg="#2d2d2d")
        zeile1.pack(anchor="w", pady=(4, 2))

        tk.Button(zeile1, text="↺ Neu laden", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._neu_laden).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(zeile1, text="✎ Bearbeiten", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._bearbeiten).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(zeile1, text="✕ Löschen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._loeschen).pack(side=tk.LEFT)

        # Buttons Zeile 2
        zeile2 = tk.Frame(self.frame, bg="#2d2d2d")
        zeile2.pack(anchor="w", pady=(0, 0))

        tk.Button(zeile2, text="🔤 OCR", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._ocr_konfigurieren).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(zeile2, text="🖱 Klick", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._klick_konfigurieren).pack(side=tk.LEFT)

    def aktualisieren(self):
        """Aktualisiert die Template-Liste im Panel."""
        self.template_liste.delete(0, tk.END)
        if not self.template_engine.templates:
            self.template_liste.insert(tk.END, "  (Keine Templates)")
            return

        ocr_konfig = self.ocr_engine.template_ocr_konfigurationen()
        templates_mit_ocr = {v.get("template") for v in ocr_konfig.values()}
        klick_konfig = self.action_engine.klickzonen_laden()

        # Varianten zählen
        varianten_count = defaultdict(int)
        for t_name in self.template_engine.templates.keys():
            basis = t_name.split("__")[0]
            varianten_count[basis] += 1

        nach_gruppen = defaultdict(list)
        for name, t in self.template_engine.templates.items():
            if name.startswith("_") or "__" in name or (t["gruppe"] and t["gruppe"].startswith("temp_")):
                continue
                
            # Filter-Logik
            tpl_settings = self.template_engine.settings.get(name, {})
            hat_states = bool(tpl_settings.get("set_states"))
            
            if self.filter_modus == "state" and not hat_states:
                continue
            if self.filter_modus == "workflow" and hat_states:
                continue
                
            g = (t["gruppe"] or "").strip().replace("\\", "/")
            nach_gruppen[g].append(name)
        
        alle_gruppen = sorted(nach_gruppen.keys(), key=lambda x: (x != "", x.lower()))
        
        if not alle_gruppen or (len(alle_gruppen) == 1 and not nach_gruppen[alle_gruppen[0]]):
             self.template_liste.insert(tk.END, "  (Keine Einträge)")
             return

        for gruppe in alle_gruppen:
            if not gruppe:
                self.template_liste.insert(tk.END, "[Global]")
                self.template_liste.itemconfig(tk.END, fg="#888888")
                for name in sorted(nach_gruppen[""]):
                    v_info = f" ({varianten_count[name]})" if varianten_count[name] > 1 else ""
                    mark = ""
                    tpl_settings = self.template_engine.settings.get(name, {})
                    if tpl_settings.get("set_states"): mark += " 🚩"
                    if name in templates_mit_ocr: mark += " 🔤"
                    if name in klick_konfig:    mark += " 🖱"
                    self.template_liste.insert(tk.END, f"  {name}{v_info}{mark}")
            else:
                hat_master = gruppe in nach_gruppen[gruppe]
                mark = ""
                if hat_master:
                    tpl_settings = self.template_engine.settings.get(gruppe, {})
                    if tpl_settings.get("set_states"): mark += " 🚩"
                    if gruppe in templates_mit_ocr: mark += " 🔤"
                    if gruppe in klick_konfig:    mark += " 🖱"
                    v_info = f" ({varianten_count[gruppe]})" if varianten_count[gruppe] > 1 else ""
                    label = f"★ [{gruppe}]{v_info}{mark}"
                    self.template_liste.insert(tk.END, label)
                    self.template_liste.itemconfig(tk.END, fg="#ffca28")
                else:
                    self.template_liste.insert(tk.END, f"📁 [{gruppe}]")
                    self.template_liste.itemconfig(tk.END, fg="#888888")
                
                for name in sorted(nach_gruppen[gruppe]):
                    if name == gruppe: continue
                    v_info = f" ({varianten_count[name]})" if varianten_count[name] > 1 else ""
                    mark_k = ""
                    tpl_settings = self.template_engine.settings.get(name, {})
                    if tpl_settings.get("set_states"): mark_k += " 🚩"
                    if name in templates_mit_ocr: mark_k += " 🔤"
                    if name in klick_konfig:    mark_k += " 🖱"
                    self.template_liste.insert(tk.END, f"    └─ {name}{v_info}{mark_k}")
            
            if gruppe != alle_gruppen[-1]:
                self.template_liste.insert(tk.END, "")

    def _get_auswahl_name(self):
        """Extrahiert den sauberen Template-Namen aus der Listen-Auswahl."""
        import re
        auswahl = self.template_liste.curselection()
        if not auswahl: return None
        text = self.template_liste.get(auswahl[0])
        
        # 1. Icons und Präfixe entfernen
        clean_text = text.strip()
        for icon in ["🚩", "🔤", "🖱", "★", "📁", "└─"]:
            clean_text = clean_text.replace(icon, "")
        clean_text = clean_text.strip()
        
        # 2. Varianten-Anzahl am Ende entfernen (z.B. " (2)")
        clean_text = re.sub(r"\s\(\d+\)$", "", clean_text).strip()
        
        # 3. Eckige Klammern bei Master-Containern entfernen (z.B. "[Email]" -> "Email")
        if clean_text.startswith("[") and clean_text.endswith("]"):
            return clean_text[1:-1]
            
        if not clean_text or clean_text == "[Global]" or clean_text == "(Keine Einträge)":
            return None
            
        return clean_text

    def _neu_laden(self):
        self.template_engine._templates_laden()
        self.aktualisieren()
        anzahl = len(self.template_engine.templates)
        self.bot._log(f"Templates neu geladen: {anzahl} gefunden.")

    def _bearbeiten(self):
        name = self._get_auswahl_name()
        if not name: return
        self.bot._bearbeiten_name = name
        if not self.bot.einlern_modus:
            self.bot._einlern_modus_umschalten()
        self.bot.einlern_btn.config(text=f"✕ Abbrechen  [{name}]")

    def _loeschen(self):
        name = self._get_auswahl_name()
        if not name: return
        
        # Alle Varianten finden
        zu_loeschen = [t for t in self.template_engine.templates.keys() if t == name or t.startswith(f"{name}__")]
        
        for t_name in zu_loeschen:
            self.template_engine.template_loeschen(t_name)
            
        self.ocr_engine.template_ocr_alle_loeschen(name)
        self.action_engine.klickzone_loeschen(name)
        self.template_engine._templates_laden()
        self.bot.app.reload_templates()
        self.bot._log(f"Template und {len(zu_loeschen)-1} Variante(n) gelöscht: {name}")
        self.aktualisieren()
        self.bot._timer_panel_aktualisieren()

    def _ocr_konfigurieren(self):
        template_name = self._get_auswahl_name()
        if not template_name: 
            print("OCR Konfig: Kein Template ausgewählt.")
            return
            
        print(f"OCR Konfig: Öffne Dialog für {template_name}...")
        eintraege = self.bot._modus_dialog(template_name)
        
        if eintraege is None: 
            print("OCR Konfig: Dialog abgebrochen.")
            return
            
        print(f"OCR Konfig: Empfange {len(eintraege)} Einträge zum Speichern.")
        
        konfig = self.ocr_engine.template_ocr_konfigurationen()
        # Vorherige Einträge für dieses Template entfernen
        count_removed = 0
        for k, v in list(konfig.items()):
            if v.get("template") == template_name:
                self.ocr_engine.template_ocr_deaktivieren(k)
                count_removed += 1
        print(f"OCR Konfig: {count_removed} alte Einträge entfernt.")
        
        prefix = f"{template_name}_"
        for e in eintraege:
            # Jetzt mit bis zu 14 Elementen (inkl. Rand/Zoom)
            if len(e) >= 14:
                en, m, co, cu, cl, cr, con, br, sh, up, cf, tc, ct, dr = e
                key = en if en.startswith(prefix) else f"{prefix}{en}"
                self.ocr_engine.template_ocr_aktivieren(key, template_name, m, 
                                                         crop_oben=co, crop_unten=cu, 
                                                         crop_links=cl, crop_rechts=cr, 
                                                         contrast=con, brightness=br, 
                                                         sharpness=sh, upscale=up,
                                                         color_filter=cf, target_color=tc, 
                                                         color_tolerance=ct, dialog_rand=dr)
            elif len(e) == 13:
                en, m, co, cu, cl, cr, con, br, sh, up, cf, tc, ct = e
                key = en if en.startswith(prefix) else f"{prefix}{en}"
                self.ocr_engine.template_ocr_aktivieren(key, template_name, m, 
                                                         crop_oben=co, crop_unten=cu, 
                                                         crop_links=cl, crop_rechts=cr, 
                                                         contrast=con, brightness=br, 
                                                         sharpness=sh, upscale=up,
                                                         color_filter=cf, target_color=tc, 
                                                         color_tolerance=ct)
            else:
                # Fallback für ganz alte Einträge
                en, m, co, cu, cl, cr, con, br, sh, up = e[:10]
                key = en if en.startswith(prefix) else f"{prefix}{en}"
                self.ocr_engine.template_ocr_aktivieren(key, template_name, m, 
                                                         crop_oben=co, crop_unten=cu, 
                                                         crop_links=cl, crop_rechts=cr, 
                                                         contrast=con, brightness=br, 
                                                         sharpness=sh, upscale=up)
        
        print("OCR Konfig: Speichern abgeschlossen. Aktualisiere UI.")
        self.aktualisieren()
        self.bot._timer_panel_aktualisieren()

    def _klick_konfigurieren(self):
        name = self._get_auswahl_name()
        if not name: return
        ergebnis = self.bot._klickzonen_dialog(name)
        if ergebnis is None: return
        
        if ergebnis == "loeschen":
            self.action_engine.klickzone_loeschen(name)
        else:
            rx, ry = ergebnis
            self.action_engine.klickzone_speichern(name, rx, ry)
        self.aktualisieren()
