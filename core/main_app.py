import threading
import time
import os
import json
import cv2
import numpy as np
import win32gui
from PIL import Image
from typing import Optional, Dict, Any, List
from collections import defaultdict
import multiprocessing as mp

from template_engine import TemplateEngine
from ocr_engine import OCREngine
from action_engine import ActionEngine
from workflow_engine import WorkflowEngine
from core.bot_state import BotState
from helpers import (
    memu_fenster_finden, fenster_screenshot_mss,
    fenster_screenshot_wgc, wgc_starten, wgc_stoppen,
    MEMU_FENSTERTITEL
)

def _matching_subprocess(frame_q, result_q, reload_event):
    """Läuft in einem eigenen OS-Prozess."""
    import torch
    torch.set_num_threads(1)
    from template_engine import TemplateEngine
    engine = TemplateEngine()

    while True:
        if reload_event.is_set():
            engine._templates_laden()
            reload_event.clear()
        try:
            item = frame_q.get(timeout=0.5)
        except Exception: continue
        if item is None: break

        frame, ref_groesse, skala, states = item
        engine.referenz_groesse = ref_groesse
        engine.matching_skalierung = skala
        matches = engine.matches_suchen_np(frame, game_states=states)
        
        while not result_q.empty():
            try: result_q.get_nowait()
            except Exception: break
        try: result_q.put_nowait(matches)
        except Exception: pass

class TilesBotApp:
    """Die Logik-Zentrale des Bots (Engine-Management & Loops)."""
    
    def __init__(self, log_callback=None, ui_update_callback=None):
        self.state = BotState()
        self.log_callback = log_callback
        self.ui_update_callback = ui_update_callback
        
        # Einstellungen
        self.settings_path = "settings.json"
        self.settings = self._load_settings()
        
        # Engines
        ref_b = self.settings.get("referenz_breite")
        ref_h = self.settings.get("referenz_hoehe")
        self.template_engine = TemplateEngine(
            matching_skalierung=self.settings.get("matching_skalierung", 0.5),
            referenz_groesse=(ref_b, ref_h) if ref_b and ref_h else None,
            log_func=self._log,
            log_enabled_func=lambda: self.settings.get("log_dateitransfers", True)
        )
        self.ocr_engine = OCREngine()
        self.action_engine = ActionEngine()
        self.workflow_engine = WorkflowEngine()
        self.action_engine.verbinden()

        # Alle bekannten State-Variablen aus Template-Settings mit False vorbelegen
        self._states_initialisieren()
        
        # Screenshots
        self.current_screenshot_np = None
        self.current_screenshot_pil = None
        
        # Threading
        self.stop_event = threading.Event()
        self.matching_reload_event = mp.Event()
        self.matching_proc = None
        self.frame_q = mp.Queue(maxsize=1)
        self.result_q = mp.Queue(maxsize=2)

    def _states_initialisieren(self):
        """Setzt alle bekannten State-Variablen aus Template-Settings auf False."""
        for t_settings in self.template_engine.settings.values():
            if not isinstance(t_settings, dict):
                continue
            for name in t_settings.get("set_states", {}).keys():
                if name and name not in self.state.game_states:
                    self.state.game_states[name] = False

    def _log(self, msg):
        if self.log_callback: self.log_callback(msg)
        else: print(f"[Bot] {msg}")

    def _load_settings(self) -> Dict[str, Any]:
        defaults = {
            "display_fps": 30,
            "ocr_intervall": 0.5,
            "matching_skalierung": 0.5,
            "log_variablen": True,
            "log_workflow": True,
            "log_ocr_debug": False,
            "log_matching": False,
            "log_capture": False,
            "log_daten_berechnungen": False
        }
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    defaults.update(data)
            except Exception: pass
        return defaults

    def save_settings(self):
        self.settings["matching_skalierung"] = self.template_engine.matching_skalierung
        if self.template_engine.referenz_groesse:
            self.settings["referenz_breite"] = self.template_engine.referenz_groesse[0]
            self.settings["referenz_hoehe"] = self.template_engine.referenz_groesse[1]
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)

    def find_memu(self):
        hwnd = memu_fenster_finden()
        if hwnd:
            self.state.memu_hwnd = hwnd
            self._log(f"MEMUPlayer gefunden: {hwnd}")
            return True
        return False

    def start(self):
        """Startet alle Hintergrund-Loops."""
        self.state.capture_active = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._matching_loop, daemon=True).start()
        threading.Thread(target=self._ocr_loop, daemon=True).start()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()

    def stop_bot(self): self.state.running = False
    def start_bot(self): self.state.running = True

    def reload_templates(self):
        """Signalisiert dem Matching-Subprozess, Templates neu zu laden."""
        self.matching_reload_event.set()
        # Auch lokal neu laden (für Metadaten/Settings)
        self.template_engine._templates_laden()

    def shutdown(self):
        """Beendet alle Hintergrundprozesse."""
        self.state.capture_active = False
        self.state.running = False
        if self.matching_proc:
            self.frame_q.put(None)
            self.matching_proc.join(timeout=1.0)
            self.matching_proc.terminate()

    def _capture_loop(self):
        import mss
        wgc_aktiv = False
        try:
            wgc_starten(MEMU_FENSTERTITEL)
            wgc_aktiv = True
            self._log("Capture: WGC aktiv.")
        except Exception as e:
            self._log(f"Capture: WGC nicht verfügbar ({e}) - nutze mss")

        with mss.mss() as sct:
            while self.state.capture_active:
                fps = self.settings.get("display_fps", 60)
                intervall = 1.0 / max(fps, 1)
                
                # Check window robustness
                if self.state.memu_hwnd:
                    if not win32gui.IsWindow(self.state.memu_hwnd):
                        self._log("MEMUPlayer Fenster verloren.")
                        self.state.memu_hwnd = None
                
                frame = None
                if wgc_aktiv:
                    frame = fenster_screenshot_wgc()
                if frame is None and self.state.memu_hwnd:
                    frame, b, h = fenster_screenshot_mss(self.state.memu_hwnd, sct)
                
                if frame is not None:
                    self.current_screenshot_np = frame
                    self.action_engine.fenstergroesse_setzen(frame.shape[1], frame.shape[0])
                
                time.sleep(intervall)
        wgc_stoppen()

    def _matching_loop(self):
        self.matching_proc = mp.Process(
            target=_matching_subprocess,
            args=(self.frame_q, self.result_q, self.matching_reload_event),
            daemon=True
        )
        self.matching_proc.start()
        
        while self.state.capture_active:
            if self.current_screenshot_np is not None:
                try:
                    # Wir schicken den aktuellen Spielzustand mit
                    self.frame_q.put_nowait((
                        self.current_screenshot_np,
                        self.template_engine.referenz_groesse,
                        self.template_engine.matching_skalierung,
                        self.state.game_states.copy()
                    ))
                    t_start = time.time()
                except Exception: t_start = None
            else:
                t_start = None
            
            try:
                matches = self.result_q.get(timeout=0.1)

                # --- State Automatisierung ---
                gefundene_p_namen = {m[6] for m in matches}
                neue_states = self.state.game_states.copy()
                changed = False

                for p_name, t_settings in self.template_engine.settings.items():
                    if not isinstance(t_settings, dict): continue
                    set_states = t_settings.get("set_states", {})
                    if not set_states: continue

                    # Variante gefunden zählt auch als Master gefunden
                    basis = p_name.split("__")[0]
                    variante_gefunden = any(
                        n == p_name or n.startswith(f"{basis}__")
                        for n in gefundene_p_namen
                    )
                    if variante_gefunden:
                        for s_name, val in set_states.items():
                            if neue_states.get(s_name) != val:
                                neue_states[s_name] = val
                                changed = True
                                if self.settings.get("log_variablen", True):
                                    self._log(f"[State] {s_name} -> {val} (aktiv: {p_name})")
                    else:
                        for s_name, val in set_states.items():
                            andere_quelle = any(
                                self.template_engine.settings.get(o, {}).get("set_states", {}).get(s_name) == val
                                or self.template_engine.settings.get(o.split("__")[0], {}).get("set_states", {}).get(s_name) == val
                                for o in gefundene_p_namen
                            )
                            if not andere_quelle and neue_states.get(s_name) == val:
                                neue_states[s_name] = not val
                                changed = True
                                if self.settings.get("log_variablen", True):
                                    self._log(f"[State] {s_name} -> {neue_states[s_name]} (verloren: {p_name})")

                if changed:
                    self.state.game_states = neue_states

                # Nach dem State-Update: Matches gegen die NEUEN States filtern.
                # Verhindert, dass Treffer aus dem gleichen Frame aktiv bleiben,
                # obwohl ihre condition_states durch den State-Update nicht mehr erfüllt sind.
                aktive_matches = [
                    m for m in matches
                    if self.template_engine._condition_states_erfuellt(
                        self.template_engine.settings.get(m[6], {}).get("condition_states", []),
                        neue_states
                    )
                ]
                self.state.active_matches = aktive_matches

                if t_start and self.settings.get("log_matching", False):
                    ms = (time.time() - t_start) * 1000
                    self._log(f"[Matching] {len(aktive_matches)} Treffer in {ms:.1f}ms")
            except Exception: pass
            time.sleep(0.05)

    def _ocr_loop(self):
        while self.state.capture_active:
            intervall = self.settings.get("ocr_intervall", 0.5)
            if self.current_screenshot_np is not None:
                # Konvertierung für OCR (PIL benötigt)
                frame_rgb = cv2.cvtColor(self.current_screenshot_np, cv2.COLOR_BGR2RGB)
                self.current_screenshot_pil = Image.fromarray(frame_rgb)
                
                # Feste Regionen
                if self.ocr_engine.regionen:
                    self.state.ocr_values = self.ocr_engine.alle_scannen(self.current_screenshot_pil)
                
                # Template OCR (mit Varianten-Support)
                ocr_konfig = self.ocr_engine.template_ocr_konfigurationen()
                
                # Wir fangen frisch an, damit Werte von verschwundenen Templates "wegfallen"
                neue_t_ocr = {}
                
                # Alle aktuell gefundenen Basis-Namen
                gefundene_basis_namen = {m[0] for m in self.state.active_matches}
                
                # 1. Gruppen-Konfigurationen vorbereiten
                konf_nach_template = defaultdict(list)
                for entry_name, k in ocr_konfig.items():
                    konf_nach_template[k.get("template")].append((entry_name, k))

                # Track entries we've already processed so lower-scoring matches don't overwrite the best match
                processed_entries = set()

                # 2. Nur die aktuell gefundenen Templates scannen
                for match in self.state.active_matches:
                    d_name, p_name = match[0], match[6] if len(match) > 6 else match[0]
                    
                    passende = konf_nach_template.get(p_name, [])
                    if not passende and p_name != d_name:
                        passende = konf_nach_template.get(d_name, [])
                    
                    for entry_name, k in passende:
                        if entry_name in processed_entries:
                            continue
                            
                        wert = self.ocr_engine.template_match_scannen(
                            self.current_screenshot_pil, entry_name, match
                        )
                        neue_t_ocr[entry_name] = wert
                        processed_entries.add(entry_name)
                
                # 3. Optional: Werte von Templates entfernen, die gar nicht mehr da sind
                # Wir machen das hier NICHT hart, damit Werte im Log/Workflow stabil bleiben.
                # Falls gewünscht, könnte man hier ein 'Cleanup' für nicht gefundene Templates machen.
                
                self.state.template_ocr_values = neue_t_ocr

                # Logging bei Wertänderungen
                if self.settings.get("log_variablen", True):
                    alle_aktuell = self.state.get_all_ocr()
                    for name, wert in alle_aktuell.items():
                        if wert and wert != self.state.last_logged_ocr.get(name):
                            self._log(f"[OCR] {name}: {wert}")
                            self.state.last_logged_ocr[name] = wert
            
            time.sleep(intervall)

    def _scheduler_loop(self):
        def log_wrapper(msg):
            if self.settings.get("log_workflow", True):
                self._log(msg)

        while self.state.capture_active:
            if not self.state.running:
                time.sleep(0.5)
                continue
            
            master_name = self.workflow_engine.aktiver_master
            if not master_name:
                log_wrapper("[Bot] Kein aktiver Master-Flow (Schrittkette) gewählt.")
                self.state.running = False
                continue

            log_wrapper(f"[Bot] Starte Schrittkette: {master_name}")
            
            # Die Engine führt nun den Master-Flow aus.
            # Da dieser oft selbst ein Loop ist, läuft er bis zum Ende oder bis Stop gedrückt wird.
            self.workflow_engine.workflow_ausfuehren(
                master_name, self.action_engine,
                lambda: self.state.active_matches,
                log_func=log_wrapper,
                laeuft_func=lambda: self.state.running,
                ocr_func=lambda: {
                    **self.state.get_all_ocr(),
                    **{f"__state__{k}": ("true" if v else "false")
                       for k, v in self.state.game_states.items()},
                },
                ist_master=True # Neuer Parameter um Master-spezifische Dinge zu triggern
            )
            
            if self.state.running:
                log_wrapper(f"[Bot] Schrittkette '{master_name}' beendet. Neustart in 1s...")
                time.sleep(1.0)
