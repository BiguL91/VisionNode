import time
import queue
import logging
import threading
from collections import defaultdict
from core.event_bus import bus
from core.daten_manager import (
    alle_listen, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen
)

logger = logging.getLogger("DataWorker")

class DataWorker:
    """
    Verarbeitet OCR-Ergebnisse asynchron im Hintergrund.
    on_ocr_results wird auf dem GUI-Thread aufgerufen und reiht nur Daten ein.
    Die eigentliche Verarbeitung (SQLite-Queries) läuft im _processing_loop Thread.
    """
    def __init__(self):
        self._queue = queue.Queue(maxsize=2)
        bus.subscribe("ocr.results", self.on_ocr_results)

        self._last_ocr = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._thread.start()

        logger.info("DataWorker initialisiert.")

    def on_ocr_results(self, event):
        """Wird auf dem GUI-Thread aufgerufen — nur Daten einreihen, nie verarbeiten."""
        ocr_roh = event.data
        if ocr_roh is None:
            return
        # Alten Eintrag verwerfen falls Queue voll (immer neuestes nehmen)
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(ocr_roh)
        except queue.Full:
            pass

    def _processing_loop(self):
        """Background-Thread: Verarbeitung + Heartbeat (kein GUI-Thread-Kontakt)."""
        while not self._stop_event.is_set():
            try:
                # Warte auf neue OCR-Daten, max 1.5s (Heartbeat-Intervall für Timer)
                ocr_roh = self._queue.get(timeout=1.5)
                self._last_ocr = ocr_roh
            except queue.Empty:
                # Kein neues OCR → Heartbeat mit letzten bekannten Werten
                ocr_roh = self._last_ocr

            try:
                self.process_all_listen(ocr_roh)
            except Exception as e:
                logger.error(f"Fehler im DataWorker: {e}")

    def process_all_listen(self, ocr_roh):
        """Verarbeitet alle konfigurierten Daten-Listen (läuft im Background-Thread)."""
        jetzt = time.time()
        try:
            listen = alle_listen()
        except Exception:
            return

        for l in listen:
            try:
                self._process_einzelne_liste(l, ocr_roh, jetzt)
            except Exception as e:
                logger.error(f"Fehler bei Verarbeitung von Liste '{l.get('name')}': {e}")

        # Signal an UI: Daten sind frisch (wird von Background-Thread gepublisht
        # → EventBus routet es via QueuedConnection sicher zum GUI-Thread)
        bus.publish("data.updated", sender="DataWorker")

    def _process_einzelne_liste(self, l, ocr_roh, jetzt):
        lid = l["id"]
        transformationen = transformationen_der_liste(lid)
        berechnungen = berechnungen_der_liste(lid)
        db_cache = cache_lesen(lid)

        arbeits_werte = {k: v for k, v in db_cache.items()}
        neue_cache_werte = {}

        # 1. Timer-Logik für Listen vom Typ 'timer'
        if l.get("typ") == "timer":
            for var_name, entry in db_cache.items():
                if var_name.endswith("._deadline"):
                    t_name = var_name.replace("._deadline", "").replace("Timer.", "")
                    try:
                        rest = max(0, int(float(entry[0]) - jetzt))
                        arbeits_werte[t_name] = (str(rest), jetzt)
                        neue_cache_werte[t_name] = str(rest)
                    except (ValueError, TypeError):
                        pass

        # 2. Live-OCR zu Cache
        ausgabe_namen = {t["name"] for t in transformationen} | {b["name"] for b in berechnungen}
        for name, val in ocr_roh.items():
            if name in ausgabe_namen:
                continue
            if val not in (None, "", "—"):
                arbeits_werte[name] = (val, jetzt)
                neue_cache_werte[name] = val

        # 3. Transformationen anwenden
        for t in transformationen:
            rohwert = ocr_roh.get(t["ocr_var"])
            if rohwert not in (None, "", "—"):
                wert = transformation_anwenden(rohwert, t["typ"])
                if wert not in ("", "—", "?"):
                    arbeits_werte[t["name"]] = (wert, jetzt)
                    neue_cache_werte[t["name"]] = wert
                    if t["typ"] == "timer":
                        try:
                            deadline = jetzt + float(wert)
                            neue_cache_werte[f"Timer.{t['name']}._deadline"] = str(deadline)
                            arbeits_werte[f"Timer.{t['name']}._deadline"] = (str(deadline), jetzt)
                        except (ValueError, TypeError):
                            pass
            elif t["typ"] == "timer":
                de_key = f"Timer.{t['name']}._deadline"
                if de_key in db_cache:
                    de_val = db_cache[de_key][0]
                    try:
                        rest = max(0, int(float(de_val) - jetzt))
                        arbeits_werte[t["name"]] = (str(rest), jetzt)
                        neue_cache_werte[t["name"]] = str(rest)
                    except (ValueError, TypeError):
                        pass

        # 4. Berechnungen auswerten
        berech_sortiert = (
            [b for b in berechnungen if b.get("typ") == "zwischen"] +
            [b for b in berechnungen if b.get("typ") != "zwischen"]
        )
        for b in berech_sortiert:
            if not b["formel_json"]:
                continue
            ergebnis = berechnung_auswerten(b["formel_json"], arbeits_werte, l.get("update_intervall", 30))
            if ergebnis not in ("?", "—"):
                arbeits_werte[b["name"]] = (ergebnis, jetzt)
                neue_cache_werte[b["name"]] = ergebnis

        # 5. Alle Änderungen gesammelt schreiben
        for var_name, wert in neue_cache_werte.items():
            cache_schreiben(lid, var_name, wert)
