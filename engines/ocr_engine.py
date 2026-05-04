import json
import os
import re
import cv2
import numpy as np
import threading
from PIL import Image

_BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_REGIONEN_DATEI = os.path.join(_BASE_DIR, "templates", "settings", "ocr_regionen.json")
TEMPLATE_OCR_DATEI = os.path.join(_BASE_DIR, "templates", "settings", "template_ocr.json")
_DEBUG_DIR         = os.path.join(_BASE_DIR, "debug")


class OCREngine:
    def __init__(self):
        # name -> {"x": int, "y": int, "breite": int, "hoehe": int, "modus": str}
        self.regionen = {}
        self.debug_filter = "Aus"  # "Aus", "Alle" oder Name der Region
        self._template_ocr_cache = None
        # IPC zum OCR-Subprocess (wird von VisionNodeApp gesetzt)
        self._ocr_req_q = None
        self._ocr_resp_q = None
        self._ocr_ready_event = None
        self._ocr_lock = threading.Lock()

        self._regionen_laden()
        self._template_ocr_laden() # Sofort laden

        # Debug-Ordner sicherstellen
        os.makedirs(_DEBUG_DIR, exist_ok=True)
    def _regionen_laden(self):
        """Lädt gespeicherte OCR-Regionen aus der JSON-Datei."""
        if os.path.exists(OCR_REGIONEN_DATEI):
            try:
                with open(OCR_REGIONEN_DATEI, "r", encoding="utf-8") as f:
                    self.regionen = json.load(f)
            except Exception:
                self.regionen = {}

    def _regionen_speichern(self):
        """Speichert alle OCR-Regionen in die JSON-Datei."""
        with open(OCR_REGIONEN_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.regionen, f, ensure_ascii=False, indent=2)

    def region_hinzufuegen(self, name, x, y, breite, hoehe, modus="Timer"):
        """Fügt eine neue OCR-Region hinzu und speichert sie."""
        self.regionen[name] = {"x": x, "y": y, "breite": breite, "hoehe": hoehe, "modus": modus}
        self._regionen_speichern()

    def region_loeschen(self, name):
        """Löscht eine OCR-Region."""
        self.regionen.pop(name, None)
        self._regionen_speichern()

    def template_match_scannen(self, screenshot_pil, entry_name, match_coords, debug_name=None):
        """Scant eine Template-OCR-Region basierend auf Match-Koordinaten (mit Varianten-Fallback)."""
        ocr_konf = self.template_ocr_konfigurationen()
        konfig = ocr_konf.get(entry_name)
        if not konfig:
            return ""

        # Format von match_coords: (display_name, x, y, w, h, score, phys_name)
        mx, my, mw, mh = match_coords[1], match_coords[2], match_coords[3], match_coords[4]

        region = {
            "name": debug_name or entry_name,
            "x": mx, "y": my, "breite": mw, "hoehe": mh,
            "modus": konfig["modus"],
            "crop_oben":   konfig.get("crop_oben", 0),
            "crop_unten":  konfig.get("crop_unten", 0),
            "crop_links":  konfig.get("crop_links", 0),
            "crop_rechts": konfig.get("crop_rechts", 0),
            "contrast":    konfig.get("contrast", 1.0),
            "brightness":  konfig.get("brightness", 0),
            "sharpness":   konfig.get("sharpness", 1.0),
            "upscale":     konfig.get("upscale", 5.0),
            "color_filter": konfig.get("color_filter", False),
            "target_color": konfig.get("target_color", [255, 255, 255]),
            "color_tolerance": konfig.get("color_tolerance", 30),
            "korrekturen": konfig.get("korrekturen", []),
            "decoder":    konfig.get("decoder", "greedy"),
            "beamWidth":  konfig.get("beamWidth", 5),
            "blocklist":  konfig.get("blocklist", ""),
        }
        return self.region_scannen(screenshot_pil, region)

    def region_scannen(self, screenshot_pil, region, debug=False):
        """Scannt eine Region mit EasyOCR. Unterstützt Expansion über den Match-Bereich hinaus."""
        name = region.get("name", "ocr_debug")
        
        # Basis-Koordinaten des Matches
        mx = region["x"]
        my = region["y"]
        mw = region["breite"]
        mh = region["hoehe"]
        modus = region.get("modus", "Text")

        # Prozentuale Offsets (können negativ sein!)
        co = region.get("crop_oben",   0)
        cu = region.get("crop_unten",  0)
        cl = region.get("crop_links",  0)
        cr = region.get("crop_rechts", 0)

        # Absolute Ziel-Koordinaten berechnen (relativ zur Match-Größe)
        abs_x0 = mx + int(mw * cl / 100)
        abs_y0 = my + int(mh * co / 100)
        abs_x1 = mx + mw - int(mw * cr / 100)
        abs_y1 = my + mh - int(mh * cu / 100)

        # Sicherheits-Check: Innerhalb der Screenshot-Grenzen bleiben
        sw, sh = screenshot_pil.size
        abs_x0 = max(0, min(sw-1, abs_x0))
        abs_y0 = max(0, min(sh-1, abs_y0))
        abs_x1 = max(0, min(sw, abs_x1))
        abs_y1 = max(0, min(sh, abs_y1))

        if abs_x1 <= abs_x0 or abs_y1 <= abs_y0:
            return ("", (0,0,0,0, None)) if debug else ""

        # Zuschneiden
        ausschnitt_pil = screenshot_pil.crop((abs_x0, abs_y0, abs_x1, abs_y1))
        
        # 2. In NumPy-Array konvertieren
        ausschnitt_np = np.array(ausschnitt_pil)
        if len(ausschnitt_np.shape) == 3:
            ausschnitt_cv = cv2.cvtColor(ausschnitt_np, cv2.COLOR_RGB2BGR)
        else:
            ausschnitt_cv = ausschnitt_np

        # 3. Vorbereitung (Optimiert für EasyOCR)
        upscale    = region.get("upscale", 5.0)
        contrast   = region.get("contrast", 1.0)
        brightness = region.get("brightness", 0)
        sharpness  = region.get("sharpness", 1.0)
        
        color_filter = region.get("color_filter", False)
        target_color = region.get("target_color", [255, 255, 255]) # RGB
        color_tol    = region.get("color_tolerance", 30)

        # Upscaling
        roi_resized = cv2.resize(ausschnitt_cv, (0, 0), fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
        rh, rw = roi_resized.shape[:2]

        # Kreis-Maskierung falls gewünscht
        if region.get("ausschnitt_form") == "kreis":
            mask_kreis = np.zeros((rh, rw), dtype=np.uint8)
            cv2.ellipse(mask_kreis, (rw // 2, rh // 2), (rw // 2, rh // 2), 0, 0, 360, 255, -1)
            # Alles außerhalb des Kreises weiß machen (für OCR Hintergrund)
            bg = np.full_like(roi_resized, 255)
            roi_resized = cv2.bitwise_and(roi_resized, roi_resized, mask=mask_kreis)
            inv_mask = cv2.bitwise_not(mask_kreis)
            roi_white_bg = cv2.bitwise_and(bg, bg, mask=inv_mask)
            roi_resized = cv2.add(roi_resized, roi_white_bg)

        # Kontrast und Helligkeit IMMER anwenden (bevor gefiltert wird)
        roi_resized = cv2.convertScaleAbs(roi_resized, alpha=contrast, beta=brightness)

        if color_filter:
            # Farbbasierte Filterung auf dem bereits kontrastoptimierten Bild
            target_bgr = np.array([target_color[2], target_color[1], target_color[0]])
            lower = np.clip(target_bgr - color_tol, 0, 255)
            upper = np.clip(target_bgr + color_tol, 0, 255)
            
            mask = cv2.inRange(roi_resized, lower, upper)
            thresh = cv2.bitwise_not(mask)
        else:
            # Standard Graustufen + OTSU
            grau = cv2.cvtColor(roi_resized, cv2.COLOR_BGR2GRAY)

            if sharpness > 0:
                s = sharpness
                kernel = np.array([[-s, -s, -s], [-s, 8*s + 1, -s], [-s, -s, -s]])
                grau = cv2.filter2D(grau, -1, kernel)

            avg_bright = np.mean(grau)
            std_dev = np.std(grau)
            
            adaptive_threshold = region.get("adaptive_threshold", modus in ["Timer", "Zahl"])
            
            if adaptive_threshold:
                # Adaptives Thresholding ist viel robuster gegen transparente Hintergründe/Fortschrittsbalken.
                # Es berechnet Schwellwerte lokal in kleinen Blöcken.
                thresh = cv2.adaptiveThreshold(grau, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                              cv2.THRESH_BINARY, 11, 2)
                # Falls Text hell auf dunkel ist (Standard bei Timern), invertieren.
                # Adaptiv liefert Schwarz auf Weiß, wenn wir Weiß auf Schwarz wollen (für EasyOCR Padding).
                if avg_bright < 127:
                    thresh = cv2.bitwise_not(thresh)
                
                # Morphologie: Zeichen leicht fetter machen (schließt Lücken durch Transparenz).
                # Erode auf Schwarz-auf-Weiß Bild macht die schwarzen Zeichen breiter.
                if modus == "Timer":
                    kernel = np.ones((2,2), np.uint8)
                    thresh = cv2.erode(thresh, kernel, iterations=1)
            else:
                # Standard OTSU für normalen Text
                if std_dev < 5:
                    thresh = np.full_like(grau, 255)
                else:
                    _, thresh = cv2.threshold(grau, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    if avg_bright < 127: # Hell auf Dunkel
                        thresh = cv2.bitwise_not(thresh)
            
        # Noise reduction (Bei Zahlen/Timern vorsichtiger)
        blur_k = 3 if modus == "Text" else 1
        if blur_k > 1:
            thresh = cv2.medianBlur(thresh, blur_k)

        # Padding (Weißer Rand)
        ocr_input = cv2.copyMakeBorder(thresh, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

        # Debug-Bild speichern
        if self.debug_filter != "Aus":
            if self.debug_filter == "Alle" or name == self.debug_filter:
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
                cv2.imwrite(os.path.join(_DEBUG_DIR, f"{safe_name}.png"), ocr_input)

        # 4. EasyOCR ausführen
        allowlist = None
        if modus == "Zahl":
            allowlist = "0123456789+"
        elif modus == "Timer":
            allowlist = "0123456789:TtdD. "

        decoder   = region.get("decoder", "greedy")
        beamWidth = region.get("beamWidth", 5)
        # blocklist nur wenn kein allowlist aktiv (EasyOCR ignoriert blocklist sonst)
        blocklist = None
        if allowlist is None:
            bl = region.get("blocklist", "")
            if bl:
                blocklist = bl

        readtext_kwargs = {"allowlist": allowlist, "decoder": decoder}
        if decoder == "beamsearch":
            readtext_kwargs["beamWidth"] = beamWidth
        if blocklist:
            readtext_kwargs["blocklist"] = blocklist

        # Im Debug-Modus geben wir (Text, Koordinaten, Debug-Bild) zurück
        debug_info = (abs_x0, abs_y0, abs_x1, abs_y1, ocr_input.copy()) if debug else None

        if self._ocr_req_q is None or self._ocr_ready_event is None:
            return ("", debug_info) if debug else ""

        try:
            with self._ocr_lock:
                if not self._ocr_ready_event.wait(timeout=30.0):
                    return ("", debug_info) if debug else ""
                self._ocr_req_q.put((ocr_input, readtext_kwargs))
                status, payload = self._ocr_resp_q.get(timeout=15.0)

            if status != "ok":
                if debug:
                    return f"[Fehler: {payload}]", debug_info
                return f"[Fehler: {payload}]"

            ergebnisse = payload
            text_teile = []
            for res in ergebnisse:
                if res[2] >= 0.35:
                    box, text, conf = res
                    text_teile.append(text)

            text = " ".join(text_teile)
            ergebnis = self._bereinigen(text, modus)

            for korr in region.get("korrekturen", []):
                von = korr.get("von", "")
                zu  = korr.get("zu", "")
                if von:
                    ergebnis = ergebnis.replace(von, zu)

            if debug:
                return ergebnis, debug_info
            return ergebnis
        except Exception as e:
            if debug:
                return f"[Fehler: {e}]", debug_info
            return f"[Fehler: {e}]"

    def _bereinigen(self, text, modus):
        """Bereinigt OCR-Text je nach Modus mit Regex."""
        if modus == "Timer":
            # 1. Tage (T/d) isolieren: Wir stellen sicher, dass Tage erkannt werden (z.B. 2T. 12:44 oder 2T 12:44)
            # Suche nach [Zahl][T/d], optional mit Punkt danach
            t = text.strip()
            tage_match = re.search(r"(\d+)\s*[TtdD]\.?\s*", t)
            tage_str = ""
            if tage_match:
                tage_str = f"{tage_match.group(1)}T "
                # Rest-Text nach den Tagen für die Zeit-Suche nutzen
                t = t[tage_match.end():]

            # 2. Bekannte OCR-Fehler bei Trennern im Zeit-Teil korrigieren
            t = t.replace(".", ":").replace(";", ":").replace(",", ":").replace("-", ":")

            # 3. Zeit suchen: Erkennt HH:MM:SS oder MM:SS (bis zu 3 Segmente)
            zeit_match = re.search(r"(\d{1,2}:)?(\d{1,2}:)?\d{1,2}:\d{2}", t)
            if zeit_match:
                return (tage_str + zeit_match.group(0)).strip().upper()

            # Fallback: Falls wir nur Tage haben (z.B. "4T")
            if tage_str:
                return tage_str.strip().upper()
            return ""

        elif modus == "Zahl":
            # Unterstützt jetzt auch Vorzeichen wie +100
            m = re.search(r"[+-]?\d+", text)
            return m.group(0) if m else ""
        else:
            # Modus "Text": Radikale Sprach-Säuberung
            # Behalte nur Lateinische Zeichen, Umlaute, Ziffern und gängige Sonderzeichen.
            # Kyrillisch etc. wird hierdurch entfernt.
            gesaeubert = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß.,!?:;()\[\]{} \-+*/=%&@#_]", "", text)
            return gesaeubert.strip()

    def alle_scannen(self, screenshot_pil):
        """Scannt alle definierten Regionen und gibt Ergebnisse direkt zurück."""
        ergebnisse = {}
        for name, region in self.regionen.items():
            region["name"] = name
            ergebnisse[name] = self.region_scannen(screenshot_pil, region)
        return ergebnisse

    # ── Template-gebundene OCR ───────────────────────────────────────────────

    def _template_ocr_laden(self):
        """Lädt Template-OCR-Konfigurationen aus JSON (gecacht)."""
        if self._template_ocr_cache is None:
            if os.path.exists(TEMPLATE_OCR_DATEI):
                try:
                    with open(TEMPLATE_OCR_DATEI, "r", encoding="utf-8") as f:
                        self._template_ocr_cache = json.load(f)
                except Exception:
                    self._template_ocr_cache = {}
            else:
                self._template_ocr_cache = {}
        return self._template_ocr_cache

    def _template_ocr_speichern(self, konfigurationen):
        """Speichert Template-OCR-Konfigurationen als JSON und aktualisiert Cache."""
        with open(TEMPLATE_OCR_DATEI, "w", encoding="utf-8") as f:
            json.dump(konfigurationen, f, ensure_ascii=False, indent=2)
        self._template_ocr_cache = konfigurationen

    def template_ocr_aktivieren(self, eintrag_name, template_name, modus,
                                crop_oben=0, crop_unten=0, crop_links=0, crop_rechts=0,
                                contrast=1.0, brightness=0, sharpness=1.0, upscale=5.0,
                                color_filter=False, target_color=[255, 255, 255], color_tolerance=30,
                                dialog_rand=0, ausschnitt_form="box"):
        """Fügt einen benannten OCR-Eintrag für ein Template hinzu."""
        konfig = self._template_ocr_laden()
        konfig[eintrag_name] = {
            "template":    template_name,
            "modus":       modus,
            "crop_oben":   crop_oben,
            "crop_unten":  crop_unten,
            "crop_links":  crop_links,
            "crop_rechts": crop_rechts,
            "contrast":    contrast,
            "brightness":  brightness,
            "sharpness":   sharpness,
            "upscale":     upscale,
            "color_filter": color_filter,
            "target_color": target_color,
            "color_tolerance": color_tolerance,
            "dialog_rand": dialog_rand,
            "ausschnitt_form": ausschnitt_form
        }
        self._template_ocr_speichern(konfig)

    def template_ocr_deaktivieren(self, eintrag_name):
        """Entfernt einen OCR-Eintrag."""
        konfig = self._template_ocr_laden()
        konfig.pop(eintrag_name, None)
        self._template_ocr_speichern(konfig)

    def template_ocr_umbenennen(self, alter_name, neuer_name):
        """Benennt alle OCR-Einträge eines Templates um (template-Feld + Entry-Key)."""
        konfig = self._template_ocr_laden()
        neu_konfig = {}
        for key, cfg in konfig.items():
            if cfg.get("template") == alter_name:
                cfg = dict(cfg)
                cfg["template"] = neuer_name
                suffix = key[len(alter_name)+1:] if key.startswith(alter_name + "_") else key
                key = f"{neuer_name}_{suffix}"
            neu_konfig[key] = cfg
        self._template_ocr_speichern(neu_konfig)

    def template_ocr_alle_loeschen(self, template_name):
        """Löscht alle OCR-Einträge, die zu einem bestimmten Template gehören."""
        konfig = self._template_ocr_laden()
        # Einträge finden, bei denen das Feld 'template' übereinstimmt
        zu_loeschen = [k for k, v in konfig.items() if v.get("template") == template_name]
        for k in zu_loeschen:
            konfig.pop(k)
        self._template_ocr_speichern(konfig)

    def template_ocr_konfigurationen(self):
        """Gibt alle aktiven Template-OCR-Konfigurationen zurück."""
        return self._template_ocr_laden()

    def match_scannen(self, screenshot_pil, x, y, breite, hoehe, modus, name="match_ocr", **kwargs):
        """Scannt einen erkannten Match-Bereich direkt.
        x, y, breite, hoehe in MEMUPlayer-Koordinaten.
        """
        region = {
            "name": name, "x": x, "y": y, "breite": breite, "hoehe": hoehe, "modus": modus,
            "crop_oben":   kwargs.get("crop_oben", 0),
            "crop_unten":  kwargs.get("crop_unten", 0),
            "crop_links":  kwargs.get("crop_links", 0),
            "crop_rechts": kwargs.get("crop_rechts", 0),
            "contrast":    kwargs.get("contrast", 1.0),
            "brightness":  kwargs.get("brightness", 0),
            "sharpness":   kwargs.get("sharpness", 1.0),
            "upscale":     kwargs.get("upscale", 5.0),
        }
        return self.region_scannen(screenshot_pil, region)
