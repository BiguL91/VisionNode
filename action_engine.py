import subprocess
import time
import json
import os

# ADB-Pfad und MEMUPlayer-Standardport
ADB_PFAD = r"C:\platform-tools\adb.exe"
ADB_GERAET = "127.0.0.1:21503"
KLICKZONEN_DATEI = "template_klicks.json"


class ActionEngine:
    def __init__(self, adb_pfad=ADB_PFAD, geraet=ADB_GERAET):
        self.adb_pfad = adb_pfad
        self.geraet = geraet
        # Android-Auflösung (wird beim ersten Verbinden abgefragt)
        self.android_breite = 1920
        self.android_hoehe = 1080
        # MEMUPlayer-Fenstergröße (wird vom Bot gesetzt)
        self.fenster_breite = 1
        self.fenster_hoehe = 1
        self._klickzonen_cache = None  # Wird beim ersten Zugriff geladen

    def _adb(self, *args):
        """Führt einen ADB-Befehl aus und gibt stdout zurück."""
        ergebnis = subprocess.run(
            [self.adb_pfad, "-s", self.geraet] + list(args),
            capture_output=True, text=True, timeout=5
        )
        return ergebnis.stdout.strip()

    def verbinden(self):
        """Verbindet mit MEMUPlayer per ADB und liest Android-Auflösung."""
        self._adb("connect", self.geraet)
        aufloesung = self._adb("shell", "wm", "size")
        # "Physical size: 1920x1080"
        for teil in aufloesung.split():
            if "x" in teil:
                try:
                    w, h = teil.split("x")
                    self.android_breite = int(w)
                    self.android_hoehe = int(h)
                except ValueError:
                    pass
        return self.android_breite, self.android_hoehe

    def fenstergroesse_setzen(self, breite, hoehe):
        """Setzt die aktuelle MEMUPlayer-Fenstergröße für die Koordinatenumrechnung."""
        self.fenster_breite = breite
        self.fenster_hoehe = hoehe

    def _umrechnen(self, x, y):
        """Rechnet MEMUPlayer-Fenster-Koordinaten in Android-Koordinaten um.
        Erkennt Orientierung automatisch: Portrait-Fenster → kurze Android-Seite als Breite."""
        if self.fenster_hoehe > self.fenster_breite:
            # Portrait-Modus
            android_w = min(self.android_breite, self.android_hoehe)
            android_h = max(self.android_breite, self.android_hoehe)
        else:
            # Landscape-Modus
            android_w = max(self.android_breite, self.android_hoehe)
            android_h = min(self.android_breite, self.android_hoehe)
        ax = int(x / self.fenster_breite * android_w)
        ay = int(y / self.fenster_hoehe * android_h)
        return ax, ay

    # ── Aktionen ─────────────────────────────────────────────────────────────

    def tippen(self, x, y, umrechnen=True):
        """Tippt an Position (x, y). Koordinaten in Fenster-px oder Android-px."""
        if umrechnen:
            x, y = self._umrechnen(x, y)
        self._adb("shell", "input", "tap", str(x), str(y))

    def wischen(self, x1, y1, x2, y2, dauer_ms=300, umrechnen=True):
        """Wischt von (x1,y1) nach (x2,y2)."""
        if umrechnen:
            x1, y1 = self._umrechnen(x1, y1)
            x2, y2 = self._umrechnen(x2, y2)
        self._adb("shell", "input", "swipe",
                  str(x1), str(y1), str(x2), str(y2), str(dauer_ms))

    def zurueck(self):
        """Drückt den Zurück-Button."""
        self._adb("shell", "input", "keyevent", "4")

    def home(self):
        """Drückt den Home-Button."""
        self._adb("shell", "input", "keyevent", "3")

    def warten(self, sekunden):
        """Wartet eine bestimmte Zeit."""
        time.sleep(sekunden)

    def auf_template_warten(self, template_name, matches_func,
                             timeout=10.0, intervall=0.2, log_func=None, laeuft_func=None):
        """Wartet bis ein Template erkannt wird. Gibt True zurück wenn gefunden.
        matches_func: Funktion die aktuelle Match-Liste zurückgibt
        """
        ende = time.time() + timeout
        while time.time() < ende:
            if laeuft_func and not laeuft_func():
                return False
            
            rest = max(0.0, ende - time.time())
            if log_func:
                log_func(f"__timer__{rest:.1f}")
            
            matches = matches_func()
            if any(m[0] == template_name for m in matches):
                return True
            time.sleep(intervall)
        return False

    def auf_template_verschwinden_warten(self, template_name, matches_func,
                                          timeout=10.0, intervall=0.2):
        """Wartet bis ein Template nicht mehr erkannt wird."""
        ende = time.time() + timeout
        while time.time() < ende:
            matches = matches_func()
            if not any(m[0] == template_name for m in matches):
                return True
            time.sleep(intervall)
        return False

    def template_tippen(self, template_name, matches, umrechnen=True, log_func=None):
        """Tippt auf die konfigurierte Klickzone eines erkannten Templates.
        Ohne Klickzone: Mitte des Match-Bereichs.
        matches: aktuelle Match-Liste [(name, x, y, w, h, score, phys_name), ...]
        Gibt True zurück wenn Template gefunden und getippt."""
        for match in matches:
            if match[0] == template_name:
                # Entpacke nur die relevanten Teile (die ersten 6)
                _, mx, my, mw, mh, _ = match[:6]
                klick_x, klick_y = self.klickpunkt_berechnen(template_name, mx, my, mw, mh)
                ax, ay = self._umrechnen(klick_x, klick_y) if umrechnen else (klick_x, klick_y)
                if log_func:
                    log_func(f"[Klick] Match: ({mx},{my}) {mw}x{mh}px | "
                             f"Klick-Fenster: ({klick_x},{klick_y}) | "
                             f"ADB: ({ax},{ay}) | "
                             f"Fenster: {self.fenster_breite}x{self.fenster_hoehe} → "
                             f"Android: {self.android_breite}x{self.android_hoehe}")
                self.tippen(klick_x, klick_y, umrechnen=umrechnen)
                return True
        return False

    # ── Klickzonen ───────────────────────────────────────────────────────────

    def klickzonen_laden(self):
        """Gibt Klickzonen-Konfigurationen zurück (gecacht, kein Disk-Zugriff pro Klick)."""
        if self._klickzonen_cache is None:
            self._klickzonen_cache = self._klickzonen_von_disk()
        return self._klickzonen_cache

    def _klickzonen_von_disk(self):
        """Liest Klickzonen-JSON von Disk."""
        if os.path.exists(KLICKZONEN_DATEI):
            try:
                with open(KLICKZONEN_DATEI, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _klickzonen_auf_disk(self, konfig):
        """Schreibt Klickzonen-JSON auf Disk und aktualisiert Cache."""
        with open(KLICKZONEN_DATEI, "w", encoding="utf-8") as f:
            json.dump(konfig, f, ensure_ascii=False, indent=2)
        self._klickzonen_cache = konfig

    def klickzone_speichern(self, template_name, rel_x, rel_y):
        """Speichert Klickzone für ein Template (relative Koordinaten in %)."""
        konfig = dict(self.klickzonen_laden())
        konfig[template_name] = {"klick_rel_x": rel_x, "klick_rel_y": rel_y}
        self._klickzonen_auf_disk(konfig)

    def klickzone_loeschen(self, template_name):
        """Entfernt die Klickzone eines Templates."""
        konfig = dict(self.klickzonen_laden())
        konfig.pop(template_name, None)
        self._klickzonen_auf_disk(konfig)

    def klickpunkt_berechnen(self, template_name, match_x, match_y, match_w, match_h):
        """Berechnet den absoluten Klickpunkt aus Match-Position + Klickzone."""
        konfig = self.klickzonen_laden()
        if template_name in konfig:
            k = konfig[template_name]
            rel_x = k.get("klick_rel_x", 50)
            rel_y = k.get("klick_rel_y", 50)
        else:
            rel_x, rel_y = 50, 50  # Standard: Mitte
        klick_x = int(match_x + match_w * rel_x / 100)
        klick_y = int(match_y + match_h * rel_y / 100)
        return klick_x, klick_y
