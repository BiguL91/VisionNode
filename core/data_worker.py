import time
import logging
from collections import defaultdict
from core.event_bus import bus
from core.daten_manager import (
    alle_listen, transformationen_der_liste, transformation_anwenden,
    berechnungen_der_liste, berechnung_auswerten, cache_schreiben, cache_lesen
)

logger = logging.getLogger("DataWorker")

class DataWorker:
    """
    Verarbeitet OCR-Ergebnisse asynchron.
    Führt Transformationen und Berechnungen durch und aktualisiert den Cache.
    """
    def __init__(self):
        bus.subscribe("ocr.results", self.on_ocr_results)
        logger.info("DataWorker initialisiert und auf ocr.results abonniert.")

    def on_ocr_results(self, event):
        """Wird aufgerufen, wenn neue OCR-Ergebnisse vorliegen."""
        ocr_roh = event.data
        if not ocr_roh:
            return
        self.process_all_listen(ocr_roh)

    def process_all_listen(self, ocr_roh):
        """Verarbeitet alle konfigurierten Daten-Listen."""
        jetzt = time.time()
        try:
            listen = alle_listen()
        except Exception as e:
            logger.error(f"Fehler beim Laden der Listen: {e}")
            return

        for l in listen:
            try:
                self._process_einzelne_liste(l, ocr_roh, jetzt)
            except Exception as e:
                logger.error(f"Fehler bei Verarbeitung von Liste '{l.get('name')}': {e}")

        # Signal an UI/andere Engines: Daten sind frisch
        bus.publish("data.updated", sender="DataWorker")

    def _process_einzelne_liste(self, l, ocr_roh, jetzt):
        lid = l["id"]
        transformationen = transformationen_der_liste(lid)
        berechnungen = berechnungen_der_liste(lid)
        db_cache = cache_lesen(lid)
        
        # Arbeits-Dict für Berechnungen (var_name -> (wert, timestamp))
        arbeits_werte = {k: v for k, v in db_cache.items()}
        neue_cache_werte = {}
        
        # 1. Timer-Logik für Listen vom Typ 'timer'
        if l.get("typ") == "timer":
            # Wir suchen im Cache nach Deadlines
            for var_name, entry in db_cache.items():
                if var_name.endswith("._deadline"):
                    t_name = var_name.replace("._deadline", "").replace("Timer.", "")
                    try:
                        rest = max(0, int(float(entry[0]) - jetzt))
                        arbeits_werte[t_name] = (str(rest), jetzt)
                        neue_cache_werte[t_name] = str(rest)
                    except (ValueError, TypeError):
                        pass

        # 2. Live-OCR zu Cache (nur wenn keine Transformation/Berechnung mit gleichem Namen existiert)
        ausgabe_namen = {t["name"] for t in transformationen} | {b["name"] for b in berechnungen}
        for name, val in ocr_roh.items():
            if name in ausgabe_namen:
                continue
            if val not in (None, "", "—"):
                # Nur bei Änderung loggen/speichern? Hier erstmal immer für timestamp-Aktualität
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
                    # Spezialfall Timer: Deadline setzen
                    if t["typ"] == "timer":
                        try:
                            deadline = jetzt + float(wert)
                            neue_cache_werte[f"Timer.{t['name']}._deadline"] = str(deadline)
                            arbeits_werte[f"Timer.{t['name']}._deadline"] = (str(deadline), jetzt)
                        except (ValueError, TypeError):
                            pass
            elif t["typ"] == "timer":
                # Fallback: Timer aus Deadline weiterlaufen lassen
                de_key = f"Timer.{t['name']}._deadline"
                if de_key in db_cache:
                    de_val = db_cache[de_key][0]
                    try:
                        rest = max(0, int(float(de_val) - jetzt))
                        arbeits_werte[t["name"]] = (str(rest), jetzt)
                        neue_cache_werte[t["name"]] = str(rest)
                    except (ValueError, TypeError):
                        pass

        # 4. Berechnungen (Formeln) auswerten
        # Wir sortieren "Zwischenberechnungen" nach vorne, damit sie in Endergebnissen genutzt werden können
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

        # 5. Alle Änderungen gesammelt in den Cache schreiben
        for var_name, wert in neue_cache_werte.items():
            # Nur schreiben, wenn Wert sich geändert hat oder ein gewisses Intervall vergangen ist?
            # Da cache_schreiben ein Upsert ist, ist es sicher.
            cache_schreiben(lid, var_name, wert)
