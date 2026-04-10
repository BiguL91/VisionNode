import tkinter as tk
import threading
import time
import json
import os
import cv2
from PIL import Image, ImageTk

from core.main_app import TilesBotApp
from ui_panels import PanelsMixin
from ui_dialoge import DialogeMixin
from einlern import EinlernMixin
from helpers import _template_farbe

APP_CONFIG_DATEI = "app_config.json"

class TilesBot(PanelsMixin, DialogeMixin, EinlernMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("Ai-Bot")
        self.root.configure(bg="#1e1e1e")
        self._fenster_automatisch_skaliert = False

        # Core App initialisieren
        self.app = TilesBotApp(log_callback=self._log)
        
        # Abwärtskompatibilität für Mixins (Shortcuts zu den Engines)
        self.template_engine = self.app.template_engine
        self.ocr_engine = self.app.ocr_engine
        self.action_engine = self.app.action_engine
        self.workflow_engine = self.app.workflow_engine
        self.einstellungen = self.app.settings

        # UI State
        self.einlern_modus = False
        self._bearbeiten_name = None
        self._aktueller_ausschnitt = None
        self._einlern_dialog_fenster = None
        self._einlern_vorschau_callback = None
        self.ocr_modus = False
        self._nur_aktive_variablen = False
        self._ocr_konfig_callback = None
        
        # Zeichnen State
        self._vorschau_foto = None
        self.auswahl_start = None
        self.auswahl_rect_id = None

        self._gui_aufbauen()
        self._fenster_groesse_initialisieren()
        self._canvas_maus_binden()
        
        # Start Sequenz
        if self.app.find_memu():
            self.app.start()
            self._start_display_loop()
        else:
            self._log("MEMUPlayer nicht gefunden. Bitte starten.")
            self._check_memu_retry()

    def _check_memu_retry(self):
        if self.app.find_memu():
            self.app.start()
            self._start_display_loop()
        else:
            self.root.after(3000, self._check_memu_retry)

    def _gui_aufbauen(self):
        haupt = tk.Frame(self.root, bg="#1e1e1e")
        haupt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Spalte 1 (links): Workflows & Schedule
        spalte_links = tk.Frame(haupt, bg="#1e1e1e", width=260)
        spalte_links.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 4))
        spalte_links.pack_propagate(False)

        self._aktiver_template_panel = None
        self._panel_erstellen(spalte_links, "WORKFLOWS", self._workflows_panel, expand=True)

        # Mitte: Live-Vorschau (flexibel)
        mitte = tk.Frame(haupt, bg="#2d2d2d", relief=tk.FLAT, bd=1)
        mitte.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        self.vorschau_canvas = tk.Canvas(mitte, bg="#1a1a1a", highlightthickness=0)
        self.vorschau_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.canvas_bild_id = self.vorschau_canvas.create_image(0, 0, anchor="nw", tags="bild")
        self.canvas_status_id = self.vorschau_canvas.create_text(
            0, 0, text="Suche MEMUPlayer...", fill="#555555",
            font=("Segoe UI", 11), anchor="center", tags="status"
        )

        # Spalte 2 (rechts): Templates, OCR, State, Log
        spalte_rechts1 = tk.Frame(haupt, bg="#1e1e1e", width=320)
        spalte_rechts1.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 4))
        spalte_rechts1.pack_propagate(False)

        self._panel_erstellen(spalte_rechts1, "WORKFLOW TEMPLATES", self._templates_panel, expand=True,
                              kopf_extra=self._workflow_templates_kopf_extra)
        self._panel_erstellen(spalte_rechts1, "STATE TEMPLATES", self._state_templates_panel)
        self._template_buttons_bereich(spalte_rechts1)
        self._panel_erstellen(spalte_rechts1, "OCR VARIABLEN", self._ocr_panel,
                              kopf_extra=self._variablen_kopf_extra)
        self._panel_erstellen(spalte_rechts1, "STATE VARIABLEN", self._state_panel,
                              kopf_extra=self._state_kopf_extra)
        self._panel_erstellen(spalte_rechts1, "LOG", self._log_panel, expand=True)

        # Spalte 3 (ganz rechts): Daten-Listen
        spalte_rechts2 = tk.Frame(haupt, bg="#1e1e1e", width=280)
        spalte_rechts2.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 0))
        spalte_rechts2.pack_propagate(False)

        self._panel_erstellen(spalte_rechts2, "DATEN-LISTEN", self._daten_panel, expand=True)

        # Unten: Buttons
        leiste = tk.Frame(self.root, bg="#252525", height=45)
        leiste.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.start_btn = tk.Button(leiste, text="▶ Start", bg="#2ea043", fg="white", 
                                   font=("Segoe UI", 9, "bold"), relief=tk.FLAT, 
                                   padx=15, pady=5, command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=10)

        self.stop_btn = tk.Button(leiste, text="■ Stop", bg="#da3633", fg="white", 
                                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, 
                                  padx=15, pady=5, state=tk.DISABLED, command=self._stop)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Rechte Buttons
        tk.Button(leiste, text="Einstellungen", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 9), 
                  relief=tk.FLAT, padx=10, command=self._einstellungen_dialog).pack(side=tk.RIGHT, padx=5)
        
        self.debug_btn = tk.Button(leiste, text="● Debug Aus", bg="#3a3a3a", fg="#555555", font=("Segoe UI", 9), 
                                   relief=tk.FLAT, padx=10, command=self._debug_umschalten)
        self.debug_btn.pack(side=tk.RIGHT, padx=5)

        # Button existiert für Status-Updates (einlern.py), wird aber nicht angezeigt
        self.einlern_btn = tk.Button(leiste, text="+ Template", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 9),
                                     relief=tk.FLAT, padx=10, command=self._einlern_modus_umschalten)

        self.snapshot_btn = tk.Button(leiste, text="📸 Snapshot", bg="#3a3a3a", fg="#cccccc",
                                      font=("Segoe UI", 9), relief=tk.FLAT, padx=12,
                                      cursor="hand2", command=self._snapshot_erstellen)
        self.snapshot_btn.pack(side=tk.RIGHT, padx=5)

        self.ocr_btn = tk.Button(leiste, text="+ OCR-Region", bg="#3a3a3a", fg="#cccccc",
                                 font=("Segoe UI", 9), relief=tk.FLAT, padx=10,
                                 cursor="hand2", command=self._ocr_modus_umschalten)
        self.ocr_btn.pack(side=tk.RIGHT, padx=5)

        tk.Button(leiste, text="?", bg="#3a3a3a", fg="#555555",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=8,
                  cursor="hand2", command=self._legende_zeigen).pack(side=tk.RIGHT, padx=(0, 2))

        self.status_label = tk.Label(leiste, text="● Bereit", bg="#252525", fg="#888888", font=("Segoe UI", 9))
        self.status_label.pack(side=tk.LEFT, padx=20)

    def _legende_zeigen(self):
        import tkinter as tk
        win = tk.Toplevel(self.root)
        win.title("Legende")
        win.configure(bg="#2d2d2d")
        win.resizable(False, False)
        win.grab_set()

        eintraege = [
            ("TYPEN", None, None),
            ("★  [Name]",   "#ffca28", "Aktive Gruppe — hat Bild, erkennt sich selbst als Gruppe"),
            ("📦 [Name]",   "#7a9abf", "Passive Gruppe — kein Bild, nur Bedingungen"),
            ("📁 [Name]",   "#888888", "Ordner — Gruppe ohne eigenes Master-Template"),
            ("    └─ Name", "#cccccc", "Kind-Template — gehört zur übergeordneten Gruppe"),
            ("", None, None),
            ("MARKIERUNGEN", None, None),
            ("🚩", "#ff7043", "State Template — setzt einen Game-State wenn erkannt"),
            ("🔤", "#55aaff", "OCR konfiguriert"),
            ("🖱",  "#ff6600", "Klick-Zone konfiguriert"),
            ("⚙",  "#aaaaaa", "Gruppen-Bedingungen konfiguriert"),
            ("(2)", "#888888", "Anzahl der Varianten (z.B. Name__2, Name__3)"),
        ]

        tk.Label(win, text="Symbol-Legende", bg="#2d2d2d", fg="#ffffff",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(14, 8))

        for symbol, farbe, beschreibung in eintraege:
            if beschreibung is None:
                if symbol:
                    tk.Label(win, text=symbol, bg="#2d2d2d", fg="#555555",
                             font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=20, pady=(6, 2))
                else:
                    tk.Frame(win, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=20, pady=4)
                continue
            zeile = tk.Frame(win, bg="#2d2d2d")
            zeile.pack(fill=tk.X, padx=20, pady=1)
            tk.Label(zeile, text=symbol, bg="#2d2d2d", fg=farbe,
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side=tk.LEFT)
            tk.Label(zeile, text=beschreibung, bg="#2d2d2d", fg="#888888",
                     font=("Segoe UI", 8), anchor="w").pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(win, text="Schließen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=4,
                  cursor="hand2", command=win.destroy).pack(pady=(10, 14))

    def _start(self):
        self.app.start_bot()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._status_setzen("● Bot läuft", "#2ea043")
        self._log("Bot gestartet.")

    def _stop(self):
        self.app.stop_bot()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._status_setzen("● Gestoppt", "#888888")
        self._log("Bot gestoppt.")

    def _snapshot_erstellen(self):
        snap_np = self.app.current_screenshot_np
        if snap_np is None: return
        from tkinter import simpledialog
        name = simpledialog.askstring("Snapshot", "Name für Snapshot (z.B. MAIN_Menü):")
        if name:
            os.makedirs("snapshots", exist_ok=True)
            pfad = os.path.join("snapshots", f"{name}.png")
            cv2.imwrite(pfad, snap_np)
            self._log(f"Snapshot gespeichert: {pfad}")

    def _start_display_loop(self):
        self._display_timer()

    def _display_timer(self):
        if not self.app.state.capture_active: return
        
        fps = self.einstellungen.get("display_fps", 30)
        
        frame = self.app.current_screenshot_np
        if frame is not None:
            self._update_preview(frame)
            
            # Struktur-Update für Variablen (bei Neuerkennungen oder Wegfall)
            match_namen = set()
            for m in self.app.state.active_matches:
                match_namen.add(m[0])
                if len(m) > 6: match_namen.add(m[6])
            
            if not hasattr(self, "_letzte_match_namen") or self._letzte_match_namen != match_namen:
                self._letzte_match_namen = match_namen
                self._timer_panel_aktualisieren()

            # Werte-Update
            self._timer_werte_aktualisieren(self.app.state.ocr_values)
            self._template_ocr_werte_aktualisieren(self.app.state.template_ocr_values)
            self._state_werte_aktualisieren(self.app.state.game_states)
            
        self.root.after(1000 // fps, self._display_timer)

    def _update_preview(self, frame_bgr):
        cb = self.vorschau_canvas.winfo_width()
        ch = self.vorschau_canvas.winfo_height()
        if cb < 50 or ch < 10: return

        h_orig, w_orig = frame_bgr.shape[:2]

        # Beim ersten Frame: Fensterbreite so anpassen dass Canvas = Bildbreite
        if not self._fenster_automatisch_skaliert:
            self._fenster_automatisch_skaliert = True
            delta = w_orig - cb
            if abs(delta) > 10:
                neue_breite = self.root.winfo_width() + delta
                self.root.geometry(f"{neue_breite}x{self.root.winfo_height()}")
        skala = min(cb / w_orig, ch / h_orig)
        anzeige_b, anzeige_h = int(w_orig * skala), int(h_orig * skala)
        
        # Scale & Convert
        frame_klein = cv2.resize(frame_bgr, (anzeige_b, anzeige_h), interpolation=cv2.INTER_AREA)
        frame_rgb = cv2.cvtColor(frame_klein, cv2.COLOR_BGR2RGB)
        bild_pil = Image.fromarray(frame_rgb)
        
        offset_x = (cb - anzeige_b) // 2
        offset_y = (ch - anzeige_h) // 2
        
        # State für Mixins updaten
        self.bild_offset_x = offset_x
        self.bild_offset_y = offset_y
        self.bild_skalierung_x = skala
        self.bild_skalierung_y = skala
        self.aktueller_screenshot = self.app.current_screenshot_pil

        if not self._vorschau_foto or self._vorschau_foto.width() != anzeige_b:
            self._vorschau_foto = ImageTk.PhotoImage(bild_pil)
        else:
            self._vorschau_foto.paste(bild_pil)
        
        self.vorschau_canvas.itemconfig(self.canvas_bild_id, image=self._vorschau_foto)
        self.vorschau_canvas.coords(self.canvas_bild_id, offset_x, offset_y)
        self.vorschau_canvas.itemconfig(self.canvas_status_id, text="")
        
        # Overlays zeichnen
        self.vorschau_canvas.delete("match")
        
        # 1. Globale OCR
        for r_name, r_data in self.ocr_engine.regionen.items():
            rx = offset_x + r_data["x"] * skala
            ry = offset_y + r_data["y"] * skala
            rw, rh = r_data["breite"] * skala, r_data["hoehe"] * skala
            self.vorschau_canvas.create_rectangle(rx, ry, rx+rw, ry+rh, outline="#ffca28", dash=(2,2), tags="match")
            val = self.app.state.ocr_values.get(r_name, "")
            self.vorschau_canvas.create_text(rx+2, ry+2, text=f"{r_name}: {val}", fill="#ffca28", font=("Segoe UI", 7), anchor="nw", tags="match")

        # 2. Template-OCR Konfiguration vorbereiten
        ocr_konf = self.ocr_engine.template_ocr_konfigurationen()
        ocr_by_template = {}
        for en, k in ocr_konf.items():
            ocr_by_template.setdefault(k.get("template", en), []).append(k)

        # 3. Matches und deren OCR-Bereiche zeichnen
        for match in self.app.state.active_matches:
            name, mx, my, mw, mh, score = match[:6]
            # ... Rest des Codes ...
            farbe = _template_farbe(name)
            cx, cy = offset_x + mx * skala, offset_y + my * skala
            cw, ch = mw * skala, mh * skala
            
            # Haupt-Match Rahmen
            self.vorschau_canvas.create_rectangle(cx, cy, cx+cw, cy+ch, outline=farbe, width=2, tags="match")
            
            label = f"{name} {score:.2f}"
            for ocr_name, ocr_val in self.app.state.template_ocr_values.items():
                if ocr_name.startswith(f"{name}_") or ocr_name == name:
                    if ocr_val: label += f"  [{ocr_val}]"
            self.vorschau_canvas.create_text(cx+2, cy-10, text=label, fill=farbe, font=("Segoe UI", 7), anchor="nw", tags="match")

            # OCR-Crop-Bereiche (Cyan)
            for k in ocr_by_template.get(name, []):
                cl = k.get("crop_links",  0) / 100
                co = k.get("crop_oben",   0) / 100
                cr = k.get("crop_rechts", 0) / 100
                cu = k.get("crop_unten",  0) / 100
                
                # Relativ zur Match-Bbox zeichnen
                rcx = cx + cl * cw
                rcy = cy + co * ch
                rcw = cw * (1 - cl - cr)
                rch = ch * (1 - co - cu)
                
                self.vorschau_canvas.create_rectangle(
                    rcx, rcy, rcx + rcw, rcy + rch,
                    outline="#00bcd4", width=1, dash=(2, 2), tags="match"
                )

    def _debug_umschalten(self):
        if self.ocr_engine.debug_filter == "Aus":
            self.ocr_engine.debug_filter = "Alle"
            self.debug_btn.config(text="● Debug An", bg="#1a3a1a", fg="#2ea043")
        else:
            self.ocr_engine.debug_filter = "Aus"
            self.debug_btn.config(text="● Debug Aus", bg="#3a3a3a", fg="#555555")

    def _state_variable_hinzufuegen_dialog(self):
        """Öffnet einen kleinen Dialog zum Hinzufügen einer neuen State-Variable."""
        d = tk.Toplevel(self.root)
        d.title("Zustand hinzufügen")
        d.geometry("300x180")
        d.configure(bg="#2d2d2d")
        d.transient(self.root)
        d.grab_set()

        # Center on screen
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 150
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 90
        d.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(d, text="Name der Variable:", bg="#2d2d2d", fg="#cccccc", 
                 font=("Segoe UI", 9)).pack(pady=(20, 5))
        
        name_var = tk.StringVar()
        entry = tk.Entry(d, textvariable=name_var, bg="#1a1a1a", fg="#ffffff", 
                         insertbackground="white", font=("Segoe UI", 10), relief=tk.FLAT, bd=4)
        entry.pack(padx=30, fill=tk.X)
        entry.focus()
        entry.bind("<Return>", lambda e: add())

        val_var = tk.BooleanVar(value=False)
        tk.Checkbutton(d, text="Startwert: TRUE", variable=val_var, bg="#2d2d2d", fg="#cccccc", 
                       selectcolor="#1a1a1a", activebackground="#2d2d2d", font=("Segoe UI", 9)).pack(pady=10)

        def add():
            n = name_var.get().strip()
            if not n: return
            self.app.state.set_game_state(n, val_var.get())
            self._state_panel_aktualisieren()
            d.destroy()

        tk.Button(d, text="Hinzufügen", bg="#2ea043", fg="white", relief=tk.FLAT, 
                  padx=15, pady=5, font=("Segoe UI", 9, "bold"), command=add).pack(pady=5)

    def _state_variable_umbenennen_dialog(self, alter_name):
        """Öffnet einen Dialog zum Umbenennen einer State-Variable."""
        d = tk.Toplevel(self.root)
        d.title("Zustand umbenennen")
        d.geometry("300x150")
        d.configure(bg="#2d2d2d")
        d.transient(self.root)
        d.grab_set()

        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 150
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
        d.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(d, text="Neuer Name:", bg="#2d2d2d", fg="#cccccc",
                 font=("Segoe UI", 9)).pack(pady=(20, 5))

        name_var = tk.StringVar(value=alter_name)
        entry = tk.Entry(d, textvariable=name_var, bg="#1a1a1a", fg="#ffffff",
                         insertbackground="white", font=("Segoe UI", 10), relief=tk.FLAT, bd=4)
        entry.pack(padx=30, fill=tk.X)
        entry.focus()
        entry.select_range(0, tk.END)
        entry.bind("<Return>", lambda e: umbenennen())

        def umbenennen():
            neuer_name = name_var.get().strip()
            if not neuer_name or neuer_name == alter_name:
                d.destroy()
                return

            # Laufzeit-State umbenennen
            alter_wert = self.app.state.game_states.pop(alter_name, False)
            self.app.state.game_states[neuer_name] = alter_wert

            # In allen Template-Settings condition_states und set_states aktualisieren
            for t_settings in self.template_engine.settings.values():
                if not isinstance(t_settings, dict): continue
                # condition_states: Liste von Dicts (OR-Gruppen mit AND-Bedingungen)
                conds = t_settings.get("condition_states", [])
                if isinstance(conds, list):
                    for gruppe in conds:
                        if isinstance(gruppe, dict) and alter_name in gruppe:
                            gruppe[neuer_name] = gruppe.pop(alter_name)
                elif isinstance(conds, dict) and alter_name in conds:
                    conds[neuer_name] = conds.pop(alter_name)

                # set_states: einfaches Dict {state_name: bool}
                ss = t_settings.get("set_states", {})
                if isinstance(ss, dict) and alter_name in ss:
                    ss[neuer_name] = ss.pop(alter_name)

            # Settings auf Disk speichern
            import json
            with open("template_settings.json", "w", encoding="utf-8") as f:
                json.dump(self.template_engine.settings, f, indent=2, ensure_ascii=False)

            # State-Panel im State-Panel die Auswahl auf den neuen Namen setzen
            if hasattr(self, "state_panel"):
                self.state_panel.ausgewaehlt = neuer_name

            self._state_panel_aktualisieren()
            self._log(f"State-Variable umbenannt: {alter_name} → {neuer_name}")
            d.destroy()

        tk.Button(d, text="Umbenennen", bg="#2ea043", fg="white", relief=tk.FLAT,
                  padx=15, pady=5, font=("Segoe UI", 9, "bold"), command=umbenennen).pack(pady=10)

    def _state_variable_loeschen(self, name):
        """Löscht eine State-Variable und entfernt alle Referenzen aus Template-Settings."""
        import json

        # Aus Laufzeit-State entfernen
        self.app.state.game_states.pop(name, None)

        # Aus allen Template-Settings entfernen
        for t_settings in self.template_engine.settings.values():
            if not isinstance(t_settings, dict): continue
            # condition_states
            conds = t_settings.get("condition_states", [])
            if isinstance(conds, list):
                for gruppe in conds:
                    if isinstance(gruppe, dict):
                        gruppe.pop(name, None)
            elif isinstance(conds, dict):
                conds.pop(name, None)

            # set_states
            ss = t_settings.get("set_states", {})
            if isinstance(ss, dict):
                ss.pop(name, None)

        # Settings auf Disk speichern
        with open("template_settings.json", "w", encoding="utf-8") as f:
            json.dump(self.template_engine.settings, f, indent=2, ensure_ascii=False)

        self._state_panel_aktualisieren()
        self._log(f"State-Variable gelöscht: {name}")

    def _fenster_groesse_initialisieren(self):
        """Stellt die Fenstergröße beim Start ein: gespeicherte Geometrie oder Max-Höhe."""
        self.root.update_idletasks()
        try:
            with open(APP_CONFIG_DATEI, "r", encoding="utf-8") as f:
                config = json.load(f)
            geo = config.get("fenster_geometrie")
            if geo:
                self.root.geometry(geo)
                self._fenster_automatisch_skaliert = True  # gespeicherte Geometrie → nicht nochmal anpassen
                return
        except Exception:
            pass
        # Kein gespeicherter Zustand: Fenster auf Max-Bildschirmhöhe setzen
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"1150x{screen_h}")

    def _fenster_geometrie_speichern(self):
        """Speichert Fenstergröße und -position in app_config.json."""
        try:
            config = {}
            if os.path.exists(APP_CONFIG_DATEI):
                with open(APP_CONFIG_DATEI, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["fenster_geometrie"] = self.root.geometry()
            with open(APP_CONFIG_DATEI, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def beenden(self):
        self._fenster_geometrie_speichern()
        self.app.shutdown()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TilesBot(root)
    root.protocol("WM_DELETE_WINDOW", app.beenden)
    root.mainloop()
