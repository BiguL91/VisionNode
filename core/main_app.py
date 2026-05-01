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

from engines.template_engine import TemplateEngine
from engines.ocr_engine import OCREngine
from engines.action_engine import ActionEngine
from engines.workflow_engine import WorkflowEngine
from core.bot_state import BotState
from core.event_bus import bus
from core.data_worker import DataWorker
from core.helpers import (
    memu_fenster_finden, fenster_screenshot_mss,
    fenster_screenshot_wgc, wgc_starten, wgc_stoppen,
    MEMU_FENSTERTITEL, SharedFrameBuffer
)

def _matching_subprocess(frame_q, result_q, reload_event):
    """Läuft in einem eigenen OS-Prozess."""
    import torch
    import time
    torch.set_num_threads(1)
    from engines.template_engine import TemplateEngine
    from core.helpers import SharedFrameBuffer
    
    engine = TemplateEngine()
    shm_buffer = SharedFrameBuffer("bot_frame_buffer", create=False)

    while True:
        if reload_event.is_set():
            engine._templates_laden()
            reload_event.clear()
        try:
            item = frame_q.get(timeout=0.5)
        except Exception: continue
        if item is None: break

        # SHM-Modus: Item enthält (shape, dtype, ref_groesse, skala, states, force_include)
        if isinstance(item, tuple) and len(item) >= 5:
            shape, dtype, ref_groesse, skala, states = item[:5]
            force_include = item[5] if len(item) > 5 else None
            
            # Zero-Copy View aus SHM holen
            frame = shm_buffer.get_frame(shape, dtype)
        else:
            continue

        if frame is None: continue

        t_start = time.time()
        engine.referenz_groesse = ref_groesse
        engine.matching_skalierung = skala
        matches, master_namen, scanned_regions, search_stats = engine.matches_suchen_np(frame, game_states=states, force_include=force_include)
        
        # Exakte Zeitmessung für GPU (da matches_suchen_np asynchron sein kann bis zum .cpu() Aufruf)
        # torch.cuda.synchronize() stellt sicher, dass alle GPU-Befehle fertig sind.
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        ms = (time.time() - t_start) * 1000

        while not result_q.empty():
            try: result_q.get_nowait()
            except Exception: break
        try:
            # Wir packen alles in ein flaches Paket
            result_package = (matches, ms, scanned_regions, master_namen, search_stats)
            result_q.put_nowait(result_package)
        except Exception: pass
    
    shm_buffer.close()

class TilesBotApp:
    """Die Logik-Zentrale des Bots (Engine-Management & Loops)."""
    
    def __init__(self, log_callback=None, ui_update_callback=None):
        self.state = BotState()
        self.log_callback = log_callback
        self.ui_update_callback = ui_update_callback
        
        # Shared Memory für Screenshots (40MB für bis zu 4K BGR)
        self.shm_buffer = SharedFrameBuffer("bot_frame_buffer", size_mb=40, create=True)
        
        # Einstellungen
        self.settings_path = os.path.join("templates", "settings", "settings.json")
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
        self.action_engine = ActionEngine(log_func=self._log)
        self.workflow_engine = WorkflowEngine()
        self.workflow_engine.node_delay = self.settings.get("workflow_node_delay", 0.5)
        self.data_worker = DataWorker()
        
        # Logging-Status für Klicks setzen
        self.action_engine.log_enabled = self.settings.get("log_klick_koordinaten", False)
        
        self.action_engine.verbinden()
        self.action_engine.chrome_top    = self.settings.get("memu_chrome_top",    32)
        self.action_engine.chrome_left   = self.settings.get("memu_chrome_left",    0)
        self.action_engine.chrome_right  = self.settings.get("memu_chrome_right",  40)
        self.action_engine.chrome_bottom = self.settings.get("memu_chrome_bottom",  0)

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
        self._last_gpu_masters = []

    def _states_initialisieren(self):
        """Setzt alle bekannten State-Variablen aus Template-Settings auf False."""
        count = 0
        for t_settings in self.template_engine.settings.values():
            if not isinstance(t_settings, dict):
                continue
            for name in t_settings.get("set_states", {}).keys():
                if name and name not in self.state.game_states:
                    self.state.game_states[name] = False
                    count += 1
        if count > 0:
            self._log(f"[App] {count} State-Variablen aus Templates initialisiert.")

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
            "log_daten_berechnungen": False,
            "log_gpu_templates": False,
            "uebergang_schwellwert": 200,
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

        # Initiale Events senden, damit UI-Panels sich füllen
        self._log(f"[App] Sende initiale Events ({len(self.state.game_states)} States)...")
        bus.publish("state.changed", self.state.game_states, sender="App")
        bus.publish("templates.changed", sender="App")
        bus.publish("workflow.config.changed", sender="App")
        bus.publish("workflow.active.changed", self.workflow_engine.aktiver_master, sender="App")

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
        
        # Shared Memory aufräumen
        if hasattr(self, "shm_buffer"):
            self.shm_buffer.close()
            self.shm_buffer.unlink()

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
                    # Screenshot in den Shared Memory Puffer schreiben (Zero-Copy View)
                    self.shm_buffer.write_frame(frame)
                    
                    self.current_screenshot_np = frame
                    self.action_engine.fenstergroesse_setzen(frame.shape[1], frame.shape[0])
                    bus.publish("frame.captured", frame, sender="Capture")
                
                time.sleep(intervall)
        wgc_stoppen()

    def _matching_loop(self):
        self.matching_proc = mp.Process(
            target=_matching_subprocess,
            args=(self.frame_q, self.result_q, self.matching_reload_event),
            daemon=True
        )
        self.matching_proc.start()
        
        last_sent_frame = None
        
        while self.state.capture_active:
            if self.current_screenshot_np is not None:
                try:
                    current_f = self.current_screenshot_np
                    # Wir schicken nur noch Metadaten + Spielzustand.
                    # Das Bild liegt bereits im Shared Memory.
                    self.frame_q.put_nowait((
                        current_f.shape,
                        current_f.dtype,
                        self.template_engine.referenz_groesse,
                        self.template_engine.matching_skalierung,
                        self.state.get_all_game_states(),
                        self.state.force_include
                    ))
                    last_sent_frame = current_f
                    t_start = time.time()
                except Exception: t_start = None
            else:
                t_start = None

            try:
                res_package = self.result_q.get(timeout=0.1)
                
                # Neues flaches Format: (matches, ms, scanned_regions, master_namen, search_stats)
                if isinstance(res_package, tuple) and len(res_package) >= 3:
                    matches, ms_sub, scanned_regions = res_package[:3]
                    master_namen = res_package[3] if len(res_package) > 3 else []
                    search_stats = res_package[4] if len(res_package) > 4 else {}
                else:
                    # Fallback für alte/andere Formate
                    matches, ms_sub, scanned_regions, master_namen, search_stats = [], 0, [], [], {}

                # Wenn wir ein Ergebnis haben, gehört es zum last_sent_frame
                if last_sent_frame is not None:
                    self.state.last_processed_frame = last_sent_frame

                # Gescannt Regionen für UI-Debug
                self.state.scanned_regions = scanned_regions
                self.state.active_search_stats = search_stats
                bus.publish("matching.stats", search_stats, sender="Matching")

                if master_namen and self.settings.get("log_gpu_templates", False):
                    m_set = sorted(set(master_namen))
                    if m_set != self._last_gpu_masters:
                        self._last_gpu_masters = m_set
                        m_str = ", ".join(m_set)
                        self._log(f"[GPU] Scanne {len(m_set)} Master: {m_str}")

                # ... (State Automatisierung bleibt gleich)
                gefundene_p_namen = {m[6] for m in matches}
                neue_states = self.state.get_all_game_states()
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
                    # Helle Übergangsframes (z.B. weiße Ladescreen) ignorieren
                    schwellwert = self.settings.get("uebergang_schwellwert", 200)
                    frame_zu_hell = False
                    if schwellwert > 0 and self.current_screenshot_np is not None:
                        # Performance: Downsampling für Helligkeitscheck (20x20 Gitter reicht völlig)
                        frame_zu_hell = self.current_screenshot_np[::20, ::20].mean() > schwellwert
                    
                    if not frame_zu_hell:
                        self.state.game_states = neue_states
                        bus.publish("state.changed", neue_states, sender="Matching")

                # Nach dem State-Update: Matches gegen die NEUEN States filtern.
                # Verhindert, dass Treffer aus dem gleichen Frame aktiv bleiben,
                # obwohl ihre condition_states durch den State-Update nicht mehr erfüllt sind.
                fi_bases = {n.split("__")[0] for n in self.state.force_include if n}
                aktive_matches = []
                for m in matches:
                    m_name = m[6]
                    if m_name.split("__")[0] in fi_bases:
                        aktive_matches.append(m)
                        continue
                    conds = self.template_engine.settings.get(m_name, {}).get("condition_states", [])
                    ignore = self.template_engine._get_hierarchy_set_states(m_name)
                    if self.template_engine._condition_states_erfuellt(conds, neue_states, ignore_states=ignore):
                        aktive_matches.append(m)
                
                self.state.active_matches = aktive_matches
                bus.publish("matches.found", aktive_matches, sender="Matching")

                if self.settings.get("log_matching", False):
                    self._log(f"[Matching] {len(aktive_matches)} Treffer in {ms_sub:.1f}ms")
            except Exception as e:
                # Kurzer Sleep bei Fehlern/Timeout, um CPU zu schonen
                time.sleep(0.01)
                if self.settings.get("log_matching", False) and not isinstance(e, mp.queues.Empty):
                    self._log(f"Matching-Loop Fehler: {e}")
            
            # Kein fixer Sleep mehr am Ende, um maximale FPS zu erreichen.
            # Die Loop wird durch result_q.get(timeout=0.1) gebremst.

    def _ocr_loop(self):
        while self.state.capture_active:
            try:
                intervall = self.settings.get("ocr_intervall", 0.5)
                if self.current_screenshot_np is not None:
                    # Konvertierung für OCR (PIL benötigt)
                    frame_rgb = cv2.cvtColor(self.current_screenshot_np, cv2.COLOR_BGR2RGB)
                    self.current_screenshot_pil = Image.fromarray(frame_rgb)
                    
                    # Debug-Filter aus Einstellungen synchronisieren
                    self.ocr_engine.debug_filter = "Alle" if self.settings.get("log_ocr_debug", False) else "Aus"

                    # Feste Regionen
                    if self.ocr_engine.regionen:
                        self.state.ocr_values = self.ocr_engine.alle_scannen(self.current_screenshot_pil)
                    
                    # Template OCR (mit Varianten-Support)
                    ocr_konfig = self.ocr_engine.template_ocr_konfigurationen()
                    
                    # Wir fangen frisch an, damit Werte von verschwundenen Templates "wegfallen"
                    neue_t_ocr = {}
                    
                    # 1. Gruppen-Konfigurationen vorbereiten
                    konf_nach_template = defaultdict(list)
                    for entry_name, k in ocr_konfig.items():
                        konf_nach_template[k.get("template")].append((entry_name, k))

                    # Track entries we've already processed so lower-scoring matches don't overwrite the best match
                    processed_entries = set()
                    smart_counters = defaultdict(int)

                    # 2. Nur die aktuell gefundenen Templates scannen
                    for match in self.state.active_matches:
                        d_name, p_name = match[0], match[6] if len(match) > 6 else match[0]
                        hierarchie_namen = match[7] if len(match) > 7 else [p_name]
                        
                        # Prüfen ob dieses Template oder ein Parent "Smart" ist
                        is_smart = any(
                            self.template_engine.settings.get(h, {}).get("is_smart", False)
                            for h in hierarchie_namen
                        )
                        
                        passende = []
                        for h_name in hierarchie_namen:
                            passende.extend(konf_nach_template.get(h_name, []))
                        
                        # Duplikate in passende vermeiden (falls durch Hierarchie doppelt)
                        passende_gefiltert = []
                        gesehene_entries = set()
                        for entry_name, k in passende:
                            if entry_name not in gesehene_entries:
                                passende_gefiltert.append((entry_name, k))
                                gesehene_entries.add(entry_name)
                        
                        for entry_name, k in passende_gefiltert:
                            if not is_smart and entry_name in processed_entries:
                                continue
                                
                            if is_smart:
                                smart_counters[entry_name] += 1
                                idx = smart_counters[entry_name]
                                indexed_name = f"{entry_name}_{idx}"

                                wert = self.ocr_engine.template_match_scannen(
                                    self.current_screenshot_pil, entry_name, match,
                                    debug_name=indexed_name
                                )
                                neue_t_ocr[indexed_name] = wert
                            else:
                                wert = self.ocr_engine.template_match_scannen(
                                    self.current_screenshot_pil, entry_name, match
                                )
                                neue_t_ocr[entry_name] = wert
                                processed_entries.add(entry_name)
                    
                    self.state.template_ocr_values = neue_t_ocr
                    bus.publish("ocr.results", self.state.get_all_ocr(), sender="OCR")

                    # Logging bei Wertänderungen
                    if self.settings.get("log_variablen", True):
                        alle_aktuell = self.state.get_all_ocr()
                        for name, wert in alle_aktuell.items():
                            if wert and wert != self.state.last_logged_ocr.get(name):
                                self._log(f"[OCR] {name}: {wert}")
                                self.state.last_logged_ocr[name] = wert
            except Exception as e:
                self._log(f"OCR-Loop Fehler: {e}")
            
            time.sleep(intervall)

    def _scheduler_loop(self):
        def log_wrapper(msg):
            if self.settings.get("log_workflow", True):
                self._log(msg)

        while self.state.capture_active:
            try:
                if not self.state.running:
                    time.sleep(0.5)
                    continue
                
                master_name = self.workflow_engine.aktiver_master
                if not master_name:
                    log_wrapper("[Bot] Kein aktiver Master-Flow (Schrittkette) gewählt.")
                    self.state.running = False
                    continue

                log_wrapper(f"[Bot] Starte Schrittkette: {master_name}")
                
                def state_func(cmd, val):
                    if cmd == "add_force_include":
                        if val and val not in self.state.force_include:
                            self.state.force_include.append(val)
                    elif cmd == "remove_force_include":
                        if val in self.state.force_include:
                            self.state.force_include.remove(val)
                    elif cmd == "set_force_include": # Legacy / Einzelwert
                        self.state.force_include = [val] if val else []

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
                    state_func=state_func,
                    ist_master=True
                )
                
                if self.state.running:
                    log_wrapper(f"[Bot] Schrittkette '{master_name}' beendet. Neustart in 1s...")
                    time.sleep(1.0)
            except Exception as e:
                self._log(f"Scheduler-Loop Fehler: {e}")
                time.sleep(1.0)
