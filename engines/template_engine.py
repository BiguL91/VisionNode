import cv2
import numpy as np
import os
import json
import torch
import torch.nn.functional as F
import time
import shutil
from PIL import Image
from collections import defaultdict

TEMPLATES_ORDNER = "templates"
SETTINGS_ORDNER = os.path.join(TEMPLATES_ORDNER, "settings")
SETTINGS_DATEI = os.path.join(SETTINGS_ORDNER, "template_settings.json")
DELETED_ORDNER = os.path.join(TEMPLATES_ORDNER, "_deleted")

class TemplateEngine:
    SETTINGS_DATEI = SETTINGS_DATEI

    def __init__(self, matching_skalierung=0.5, referenz_groesse=None, log_func=None, log_enabled_func=None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.log_func = log_func
        self.log_enabled_func = log_enabled_func
        self._log(f"TemplateEngine: Nutze Device '{self.device}'")
        
        self.templates = {}
        self.settings = {}
        self.matching_skalierung = matching_skalierung
        self.referenz_groesse = referenz_groesse
        self._gpu_cache = {}
        
        os.makedirs(TEMPLATES_ORDNER, exist_ok=True)
        os.makedirs(SETTINGS_ORDNER, exist_ok=True)
        os.makedirs(DELETED_ORDNER, exist_ok=True)
        self.konfigurationen_bereinigen()
        self._settings_laden()
        self._templates_laden()

    def _log(self, message):
        if self.log_func:
            if self.log_enabled_func and not self.log_enabled_func():
                return
            self.log_func(message)
        else:
            print(f"LOG: {message}")

    def get_kinder(self, gruppe_name):
        """Gibt alle Templates zurück, die zu dieser Gruppe oder ihren Untergruppen gehören."""
        vollpfad = self._gruppe_vollpfad(gruppe_name)
        kinder = []
        for k, v in self.settings.items():
            if not isinstance(v, dict) or k == gruppe_name: continue
            g = v.get("gruppe", "")
            # Entweder direkt in der Gruppe oder in einer Untergruppe
            if g == vollpfad or g.startswith(vollpfad + "/"):
                kinder.append(k)
        return sorted(list(set(kinder)))

    def _backup_zu_deleted(self, pfad):
        """Verschiebt eine Datei in den _deleted Ordner statt sie zu löschen."""
        if not pfad or not os.path.exists(pfad): 
            return
        try:
            bn = os.path.basename(pfad)
            ts = time.strftime("%Y%m%d_%H%M%S")
            # Sicherstellen dass Zielordner existiert
            os.makedirs(DELETED_ORDNER, exist_ok=True)
            
            ziel = os.path.join(DELETED_ORDNER, f"{ts}_{bn}")
            shutil.move(pfad, ziel)
            self._log(f"  Backup: {bn} -> _deleted/")
        except Exception as e:
            self._log(f"  Backup-Fehler ({os.path.basename(pfad)}): {e}")
            try: 
                os.remove(pfad) 
                self._log(f"  Datei stattdessen gelöscht (Backup fehlgeschlagen).")
            except: pass

    def konfigurationen_bereinigen(self):
        if not os.path.exists(TEMPLATES_ORDNER): return

        aktuelle_pngs = set()
        for root, dirs, dateien in os.walk(TEMPLATES_ORDNER):
            # _deleted Ordner beim Scannen ignorieren
            if "_deleted" in dirs:
                dirs.remove("_deleted")
            for f in dateien:
                if f.endswith(".png"): aktuelle_pngs.add(f[:-4])

        settings_pfad = os.path.join(SETTINGS_ORDNER, "template_settings.json")
        gueltige_keys = set(aktuelle_pngs)
        
        # Passive Gruppen validieren (Ordner muss existieren)
        if os.path.exists(settings_pfad):
            try:
                with open(settings_pfad, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    def get_ordnerpfad(g_name, s):
                        kat = s.get("kategorie", "workflow")
                        parent = s.get("gruppe", "")
                        if parent and parent != g_name:
                            return os.path.join(TEMPLATES_ORDNER, kat, *parent.split("/"), g_name)
                        return os.path.join(TEMPLATES_ORDNER, kat, g_name)

                    for k, v in data.items():
                        if isinstance(v, dict) and v.get("typ") == "passiv_gruppe":
                            ordner = get_ordnerpfad(k, v)
                            if os.path.isdir(ordner):
                                gueltige_keys.add(k)
            except Exception:
                pass

        json_dateien = [
            os.path.join(SETTINGS_ORDNER, "template_settings.json"),
            os.path.join(SETTINGS_ORDNER, "template_farben.json"),
            os.path.join(SETTINGS_ORDNER, "template_klicks.json")
        ]
        for datei in json_dateien:
            if os.path.exists(datei):
                try:
                    with open(datei, "r", encoding="utf-8") as f: data = json.load(f)
                    neu = {}
                    for k, v in data.items():
                        if k.startswith("_"): # Interne Keys behalten
                            neu[k] = v
                        elif k in gueltige_keys:
                            neu[k] = v
                            
                    if len(neu) != len(data):
                        with open(datei, "w", encoding="utf-8") as f: json.dump(neu, f, indent=2, ensure_ascii=False)
                except Exception: pass
        
        ocr_path = os.path.join(SETTINGS_ORDNER, "template_ocr.json")
        if os.path.exists(ocr_path):
            try:
                with open(ocr_path, "r", encoding="utf-8") as f: data = json.load(f)
                neu = {k: v for k, v in data.items() if v.get("template") in aktuelle_pngs}
                if len(neu) != len(data):
                    with open(ocr_path, "w", encoding="utf-8") as f: json.dump(neu, f, indent=2, ensure_ascii=False)
            except Exception: pass

    def _settings_laden(self):
        if os.path.exists(SETTINGS_DATEI):
            try:
                with open(SETTINGS_DATEI, "r", encoding="utf-8") as f: self.settings = json.load(f)
            except Exception: self.settings = {}

    def _settings_speichern(self, neu_laden=False):
        """Speichert die aktuellen Template-Einstellungen."""
        try:
            with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            if neu_laden:
                self._templates_laden()
        except Exception as e:
            self._log(f"Fehler beim Speichern der Template-Settings: {e}")

    def state_umbenennen_in_settings(self, alter_name, neuer_name):
        """Aktualisiert alle Referenzen auf einen State-Namen in den Template-Einstellungen."""
        for t_settings in self.settings.values():
            if not isinstance(t_settings, dict):
                continue
            # Bedingungen aktualisieren
            for cond in t_settings.get("condition_states", []):
                if isinstance(cond, dict) and "states" in cond:
                    if alter_name in cond["states"]:
                        cond["states"][neuer_name] = cond["states"].pop(alter_name)
            # Set-States aktualisieren
            ss = t_settings.get("set_states", {})
            if isinstance(ss, dict) and alter_name in ss:
                ss[neuer_name] = ss.pop(alter_name)
        self._settings_speichern()

    def state_loeschen_in_settings(self, name):
        """Entfernt alle Referenzen auf einen State-Namen aus den Template-Einstellungen."""
        for t_settings in self.settings.values():
            if not isinstance(t_settings, dict):
                continue
            # Bedingungen entfernen
            for cond in t_settings.get("condition_states", []):
                if isinstance(cond, dict) and "states" in cond:
                    cond["states"].pop(name, None)
            # Set-States entfernen
            t_settings.get("set_states", {}).pop(name, None)
        self._settings_speichern()

    def _templates_laden(self):
        self._settings_laden()
        self.templates = {}
        self._gpu_cache = {}
        if not os.path.exists(TEMPLATES_ORDNER): return
        
        for root, dirs, dateien in os.walk(TEMPLATES_ORDNER):
            dirs[:] = [d for d in dirs if not d.startswith('_')]
            for datei in dateien:
                if datei.endswith(".png"):
                    rel_pfad = os.path.relpath(root, TEMPLATES_ORDNER)
                    if rel_pfad == ".":
                        gruppe = None
                    else:
                        teile = rel_pfad.replace("\\", "/").split("/")
                        # Kategorie-Ordner (state/workflow) wird übersprungen
                        if teile[0] in {"state", "workflow"} and len(teile) >= 2:
                            gruppe = "/".join(teile[1:])
                        else:
                            gruppe = rel_pfad.replace("\\", "/")
                    
                    name = datei[:-4]
                    pfad = os.path.join(root, datei)
                    
                    img = cv2.imdecode(np.fromfile(pfad, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if img is None: continue
                    h, w = img.shape[:2]
                    
                    if img.shape[2] == 4:
                        alpha = img[:, :, 3]
                        maske_np = np.where(alpha > 10, 1.0, 0.0).astype(np.float32)
                        bild_bgr = img[:, :, :3]
                        bbox = self._maske_bbox((alpha > 10).astype(np.uint8))
                        if bbox:
                            bx, by, bw, bh = bbox
                            bild_bgr = bild_bgr[by:by+bh, bx:bx+bw]
                            maske_np = maske_np[by:by+bh, bx:bx+bw]
                    else:
                        maske_np = None
                        bild_bgr = img
                        bbox = None

                    t_bild = torch.from_numpy(bild_bgr.transpose(2, 0, 1)).float().div(255.0).to(self.device).unsqueeze(0)
                    t_maske = torch.from_numpy(maske_np).float().to(self.device).unsqueeze(0).unsqueeze(0) if maske_np is not None else None

                    self.templates[name] = {
                        "tensor": t_bild,
                        "maske": t_maske,
                        "orig_size": (w, h),
                        "gruppe": gruppe,
                        "pfad": pfad,
                        "match_schwellwert": self.settings.get(name, {}).get("match_schwellwert", 0.85),
                        "scan_regions": self.settings.get(name, {}).get("scan_regions", []),
                        "bbox": bbox
                    }
        self._log(f"TemplateEngine: {len(self.templates)} Templates geladen.")

    def _gruppe_vollpfad(self, gruppe_name):
        """Vollpfad einer Gruppe. settings["gruppe"] = Vollpfad des Elternteils (oder leer)."""
        s = self.settings.get(gruppe_name, {})
        if not s: return gruppe_name
        parent = s.get("gruppe", "")
        if parent and parent != gruppe_name:
            return f"{parent}/{gruppe_name}"
        return gruppe_name

    def _gruppe_ordnerpfad(self, gruppe_name):
        """Disk-Pfad einer Gruppe. aktiv_gruppe: gruppe==eigener_name → ignorieren."""
        s = self.settings.get(gruppe_name, {})
        kat = s.get("kategorie", "workflow")
        parent = s.get("gruppe", "")
        if parent and parent != gruppe_name:
            return os.path.join(TEMPLATES_ORDNER, kat, *parent.split("/"), gruppe_name)
        return os.path.join(TEMPLATES_ORDNER, kat, gruppe_name)

    def get_gruppen(self, kategorie=None):
        """Gibt Vollpfade aller Gruppen zurück — optional gefiltert nach Kategorie."""
        gruppen = set()
        
        # 1. Alle aus Settings (Aktiv + Passiv)
        for k, v in self.settings.items():
            if not isinstance(v, dict): continue
            typ = v.get("typ")
            if typ not in ("aktiv_gruppe", "passiv_gruppe"):
                continue
            
            # Kategorie Filter
            if kategorie and v.get("kategorie") != kategorie:
                continue
                
            gruppen.add(self._gruppe_vollpfad(k))

        # 2. Backup aus Templates (Dateisystem)
        for name, t in self.templates.items():
            g = t.get("gruppe")
            if not g: continue
            
            # Kategorie über Pfad prüfen
            if kategorie:
                pfad = t.get("pfad", "")
                rel = os.path.relpath(pfad, TEMPLATES_ORDNER).replace("\\", "/")
                if not rel.startswith(f"{kategorie}/"):
                    continue

            gruppen.add(g)

        return sorted(g for g in gruppen if g)

    @staticmethod
    def _condition_states_erfuellt(conditions, game_states, ignore_states=None):
        """Wertet condition_states gegen game_states aus. Unterstützt altes und neues Format."""
        if not conditions or game_states is None:
            return True

        def _wert_pruefen(k, v):
            if k == "[KEIN ANDERER ZUSTAND]":
                # Prüfe ob IRGENDEIN ANDERER State True ist
                for s_name, s_val in game_states.items():
                    if s_val is True:
                        if ignore_states and s_name in ignore_states:
                            continue
                        # Ein anderer State ist True -> Bedingung [KEIN ANDERER] == True ist NICHT erfüllt
                        if v: return False
                        else: return True
                # Kein anderer State ist True -> Bedingung [KEIN ANDERER] == True ist erfüllt
                return v
            return game_states.get(k) == v

        # Altes Format (dict): {"Map": True} → einfaches AND
        if isinstance(conditions, dict):
            return all(_wert_pruefen(k, v) for k, v in conditions.items())

        if not isinstance(conditions, list) or not conditions:
            return True

        first = conditions[0]

        # Neues Format: [{"connector": ..., "states": {...}}, ...]
        if isinstance(first, dict) and ("states" in first or "connector" in first):
            result = None
            for group in conditions:
                connector = group.get("connector")  # None | "OR" | "AND"
                states = group.get("states", {})
                group_ok = all(_wert_pruefen(k, v) for k, v in states.items())
                if result is None or connector is None or connector == "OR":
                    result = group_ok if result is None else (result or group_ok)
                else:  # AND
                    result = result and group_ok
            return bool(result)

        # Altes Listen-Format: [{"Map": True}, {"Statd": True}] → OR zwischen Gruppen
        for group in conditions:
            if isinstance(group, dict) and all(_wert_pruefen(k, v) for k, v in group.items()):
                return True
        return False

    def _get_hierarchy_set_states(self, name_oder_pfad):
        """Sammelt alle set_states eines Templates/Pfades und seiner Eltern."""
        sets = set()
        # 1. Start-Punkt prüfen (kann Template-Name oder Gruppen-Pfad sein)
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad:
            # Es ist ein Pfad, nimm das letzte Element
            leaf = name_oder_pfad.split("/")[-1]
            s = self.settings.get(leaf, {})
        
        if s:
            sets.update(s.get("set_states", {}).keys())
            # Falls es ein Template-Name war, auch Master-States bei Varianten prüfen
            if "__" in name_oder_pfad:
                m_name = name_oder_pfad.split("__")[0]
                sets.update(self.settings.get(m_name, {}).get("set_states", {}).keys())
            
            # 2. Eltern-Kette nach oben
            current_path = s.get("gruppe", "")
            besucht = {name_oder_pfad}
            while current_path:
                teile = current_path.split("/")
                leaf = teile[-1]
                if leaf in besucht: break
                besucht.add(leaf)
                
                ps = self.settings.get(leaf, {})
                if isinstance(ps, dict):
                    sets.update(ps.get("set_states", {}).keys())
                    if len(teile) > 1:
                        current_path = "/".join(teile[:-1])
                    else:
                        current_path = ps.get("gruppe", "")
                else:
                    break
        return list(sets)

    def _eltern_conditions_pruefen(self, pfad, game_states):
        """Prüft Bedingungen aller Eltern-Ebenen rekursiv über einen Vollpfad."""
        if not pfad: return True
        current_path = pfad
        besucht = set()
        
        while current_path:
            teile = current_path.split("/")
            leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            
            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                conds = eintrag.get("condition_states", [])
                if conds:
                    # Für [KEIN ANDERER ZUSTAND] müssen wir alle Zustände ignorieren,
                    # die in DIESER Hierarchie (von diesem Blatt abwärts) gesetzt werden.
                    my_hierarchy_sets = self._get_hierarchy_set_states(current_path)
                    if not self._condition_states_erfuellt(conds, game_states, ignore_states=my_hierarchy_sets):
                        return False
                
                # Nächste Ebene im Pfad nach oben (z.B. A/B/C -> A/B)
                if len(teile) > 1:
                    current_path = "/".join(teile[:-1])
                else:
                    # Ende des Pfades erreicht, schauen ob Root-Master noch ein Parent hat
                    current_path = eintrag.get("gruppe", "")
            else:
                break
        return True

    def _get_effective_regions(self, name):
        """Gibt die Scan-Bereiche (ROI) für ein Template zurück (rekursive Vererbung)."""
        # 1. Das Template selbst prüfen
        s = self.settings.get(name, {})
        if isinstance(s, dict) and s.get("scan_regions"):
            return s["scan_regions"]
        
        # 2. Eltern-Hierarchie über den Pfad abklappern
        current_path = s.get("gruppe", "") if isinstance(s, dict) else ""
        besucht = {name}
        
        while current_path:
            teile = current_path.split("/")
            leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            
            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                if eintrag.get("scan_regions"):
                    return eintrag["scan_regions"]
                
                # Eine Ebene höher gehen
                if len(teile) > 1:
                    current_path = "/".join(teile[:-1])
                else:
                    current_path = eintrag.get("gruppe", "")
            else:
                break
        return []

    def _hintergrund_maske_erstellen(self, bild_np, toleranz=30):
        h, w = bild_np.shape[:2]
        ecken = np.array([bild_np[0,0], bild_np[0,w-1], bild_np[h-1,0], bild_np[h-1,w-1]], dtype=np.float32)
        hintergrundfarbe = np.mean(ecken, axis=0).astype(np.uint8)
        diff = np.abs(bild_np.astype(np.int32) - hintergrundfarbe.astype(np.int32))
        return np.where(np.all(diff <= toleranz, axis=2), 0, 255).astype(np.uint8)

    def _maske_bbox(self, maske):
        opak = np.count_nonzero(maske)
        if opak / maske.size > 0.70: return None
        zeilen = np.any(maske > 0, axis=1)
        spalten = np.any(maske > 0, axis=0)
        if not zeilen.any(): return None
        y0, y1 = np.where(zeilen)[0][[0, -1]]
        x0, x1 = np.where(spalten)[0][[0, -1]]
        return (int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))

    def template_speichern(self, name, bild_pil, hintergrund_entfernen=True, ignore_regionen=None, hintergrund_toleranz=30, gruppe=None, match_schwellwert=0.85, scan_regions=None, condition_states=None, set_states=None, typ=None, ist_state_template=False, kategorie=None, alter_name=None, ausschnitt_form="box"):
        bild_np = np.array(bild_pil.convert("RGB"))

        basis_name = name.split("__")[0]
        # Ein Master (aktiv_gruppe) darf sich nicht selbst als Gruppe haben.
        g_name = gruppe if gruppe and gruppe != name else ""

        # Kategorie früh bestimmen (wird für Pfad-Aufbau benötigt)
        if not kategorie:
            bestehend = self.settings.get(name, {})
            kategorie = bestehend.get("kategorie", "workflow")

        # Ordnerpfad bestimmen
        if typ == "aktiv_gruppe":
            # Wenn es ein Master ist, ist sein Ordner der eigene Name (unter dem Parent)
            if g_name:
                ordner = os.path.join(TEMPLATES_ORDNER, kategorie, *g_name.split("/"), basis_name)
            else:
                ordner = os.path.join(TEMPLATES_ORDNER, kategorie, basis_name)
        else:
            # Ein normales Template liegt im Ordner seiner Gruppe
            if g_name:
                ordner = self._gruppe_ordnerpfad(g_name.split("/")[-1] if "/" in g_name else g_name)
            else:
                ordner = os.path.join(TEMPLATES_ORDNER, kategorie)
        
        os.makedirs(ordner, exist_ok=True)
        pfad = os.path.join(ordner, f"{name}.png")

        # Altes Template an anderer Stelle löschen?
        # Entweder über den neuen Namen (falls Pfadwechsel) oder über alter_name (falls Rename)
        zu_loeschen_namen = {name}
        if alter_name: zu_loeschen_namen.add(alter_name)
        
        for an in zu_loeschen_namen:
            if an in self.templates:
                alter_pfad = self.templates[an]["pfad"]
                if os.path.exists(alter_pfad) and os.path.abspath(alter_pfad) != os.path.abspath(pfad):
                    try: 
                        os.remove(alter_pfad)
                        alt_dir = os.path.dirname(alter_pfad)
                        if os.path.exists(alt_dir) and not os.listdir(alt_dir): os.rmdir(alt_dir)
                    except: pass
                # Wenn es ein Rename war, den alten Key aus den internen Strukturen entfernen
                if an != name:
                    self.settings.pop(an, None)
                    self.templates.pop(an, None)

        # Maske erstellen
        if hintergrund_entfernen:
            maske = self._hintergrund_maske_erstellen(bild_np, toleranz=hintergrund_toleranz)
            if ignore_regionen:
                for r in ignore_regionen:
                    ix0, iy0, ix1, iy1 = [int(v) for v in r[:4]]
                    f = r[4] if len(r) > 4 else "box"
                    if f == "kreis":
                        cx, cy = (ix0 + ix1) // 2, (iy0 + iy1) // 2
                        rx, ry = abs(ix1 - ix0) // 2, abs(iy1 - iy0) // 2
                        cv2.ellipse(maske, (cx, cy), (rx, ry), 0, 0, 360, 0, -1)
                    else:
                        maske[max(0,iy0):iy1, max(0,ix0):ix1] = 0
            bild_rgba = np.dstack([bild_np, maske])
            bild_speichern = Image.fromarray(bild_rgba, "RGBA")
        else:
            bild_speichern = bild_pil.convert("RGBA")
            if ignore_regionen:
                arr = np.array(bild_speichern)
                h, w = arr.shape[:2]
                mask_alpha = arr[:, :, 3]
                for r in ignore_regionen:
                    ix0, iy0, ix1, iy1 = [int(v) for v in r[:4]]
                    f = r[4] if len(r) > 4 else "box"
                    if f == "kreis":
                        cx, cy = (ix0 + ix1) // 2, (iy0 + iy1) // 2
                        rx, ry = abs(ix1 - ix0) // 2, abs(iy1 - iy0) // 2
                        cv2.ellipse(mask_alpha, (cx, cy), (rx, ry), 0, 0, 360, 0, -1)
                    else:
                        mask_alpha[max(0,iy0):min(h,iy1), max(0,ix0):min(w,ix1)] = 0
                arr[:, :, 3] = mask_alpha
                bild_speichern = Image.fromarray(arr, "RGBA")

        bild_speichern.save(pfad)
        
        # Typ ableiten falls nicht angegeben
        if not typ:
            bestehend = self.settings.get(name, {})
            typ = bestehend.get("typ") or ("aktiv_gruppe" if g_name == basis_name else "template")

        # Metadaten speichern
        self.settings[name] = {
            "hg_entfernen": bool(hintergrund_entfernen),
            "hg_toleranz": int(hintergrund_toleranz),
            "ignore_regionen": [list(r) for r in ignore_regionen] if ignore_regionen else [],
            "gruppe": g_name,
            "match_schwellwert": float(match_schwellwert),
            "scan_regions": [list(r) for r in scan_regions] if scan_regions else [],
            "condition_states": condition_states or {},
            "set_states": set_states or {},
            "typ": typ,
            "kategorie": kategorie,
            "ausschnitt_form": ausschnitt_form,
        }
        self._settings_speichern(neu_laden=True)

    def template_umbenennen(self, alter_name, neuer_name, neue_gruppe=None):
        """Benennt ein Template und alle seine Varianten um oder verschiebt sie."""
        alter_basis = alter_name.split("__")[0]
        neuer_basis = neuer_name.split("__")[0]

        varianten = [t for t in self.templates.keys() if t == alter_basis or t.startswith(f"{alter_basis}__")]
        self._log(f"Template umbenennen: '{alter_basis}' → '{neuer_basis}' ({len(varianten)} Varianten)")

        for v_alt in varianten:
            suffix = v_alt[len(alter_basis):]
            v_neu = f"{neuer_basis}{suffix}"
            if v_alt not in self.templates: continue

            alt_pfad = self.templates[v_alt]["pfad"]
            g_name = neue_gruppe if neue_gruppe else neuer_basis  # Vollpfad der Gruppe
            kat = self.settings.get(v_alt, {}).get("kategorie", "workflow")
            g_key = g_name.split("/")[-1]  # Kurzname = Settings-Key
            if g_key in self.settings:
                neu_ordner = self._gruppe_ordnerpfad(g_key)
            else:
                neu_ordner = os.path.join(TEMPLATES_ORDNER, kat, g_name)
            os.makedirs(neu_ordner, exist_ok=True)
            neu_pfad = os.path.join(neu_ordner, f"{v_neu}.png")

            if os.path.exists(alt_pfad):
                try:
                    if os.path.exists(neu_pfad) and os.path.abspath(alt_pfad) != os.path.abspath(neu_pfad):
                        os.remove(neu_pfad)
                    os.rename(alt_pfad, neu_pfad)
                    self._log(f"  Verschoben: {os.path.basename(alt_pfad)} → {v_neu}.png")
                    alt_dir = os.path.dirname(alt_pfad)
                    if os.path.exists(alt_dir) and not os.listdir(alt_dir): os.rmdir(alt_dir)
                except Exception as e:
                    self._log(f"  Fehler bei {v_alt}: {e}")

            if v_alt in self.settings:
                self.settings[v_neu] = self.settings.pop(v_alt)
                self.settings[v_neu]["gruppe"] = g_name

        # Kinder-Cascade: Templates/Gruppen deren gruppe == alter_basis updaten
        for k, v in list(self.settings.items()):
            if not isinstance(v, dict): continue
            g = v.get("gruppe", "")
            if g == alter_basis:
                self.settings[k]["gruppe"] = neue_gruppe if neue_gruppe else neuer_basis
            elif g.startswith(alter_basis + "/"):
                suffix = g[len(alter_basis):]
                self.settings[k]["gruppe"] = (neue_gruppe if neue_gruppe else neuer_basis) + suffix

        self._settings_speichern(neu_laden=True)

    def gruppe_umbenennen(self, alter_name, neuer_name, neue_uebergeordnete_gruppe=None):
        """Benennt eine Gruppe um oder verschiebt sie: verschiebt Ordner + cascadiert Vollpfade."""
        alter_vollpfad = self._gruppe_vollpfad(alter_name)
        alter_ordner = self._gruppe_ordnerpfad(alter_name)

        if neue_uebergeordnete_gruppe is not None:
            parent = neue_uebergeordnete_gruppe
        else:
            parent = self.settings.get(alter_name, {}).get("gruppe", "")

        # Ein Master hat sich selbst als Gruppe (oder leer)
        if parent == alter_name or parent is None:
            parent = ""

        neuer_vollpfad = f"{parent}/{neuer_name}" if parent else neuer_name
        # Ziel-Ordner bestimmen
        s = self.settings.get(alter_name, {})
        kat = s.get("kategorie", "workflow")
        if parent:
            neuer_ordner = os.path.join(TEMPLATES_ORDNER, kat, *parent.split("/"), neuer_name)
        else:
            neuer_ordner = os.path.join(TEMPLATES_ORDNER, kat, neuer_name)

        self._log(f"Gruppe verschieben/umbenennen: '{alter_vollpfad}' → '{neuer_vollpfad}'")
        self._log(f"  Verschiebe: '{os.path.basename(alter_ordner)}' → '{neuer_name}'")

        if os.path.exists(alter_ordner):
            try:
                os.makedirs(os.path.dirname(neuer_ordner) or ".", exist_ok=True)
                os.rename(alter_ordner, neuer_ordner)
                self._log(f"  Ordner verschoben: {alter_ordner} → {neuer_ordner}")
                
                # Wichtig: Alle Dateien im neuen Ordner, die nach dem alten Master benannt sind, umbenennen
                # (Damit sie nicht als neue Kinder im neuen Ordner auftauchen)
                if os.path.exists(neuer_ordner):
                    alter_basis = alter_name.split("__")[0]
                    neuer_basis = neuer_name.split("__")[0]
                    for datei in os.listdir(neuer_ordner):
                        if datei.endswith(".png"):
                            d_name = datei[:-4]
                            if d_name == alter_basis or d_name.startswith(f"{alter_basis}__"):
                                suffix = d_name[len(alter_basis):]
                                neu_d_name = f"{neuer_basis}{suffix}.png"
                                os.rename(os.path.join(neuer_ordner, datei), 
                                          os.path.join(neuer_ordner, neu_d_name))
                                self._log(f"  Datei umbenannt: {datei} → {neu_d_name}")
            except Exception as e:
                self._log(f"  Ordner-Fehler: {e}")

        # Cascade: alle Einträge deren "gruppe" den alten Vollpfad enthält aktualisieren
        for k, v in list(self.settings.items()):
            if not isinstance(v, dict): continue
            g = v.get("gruppe", "")
            
            # Falls das Template selbst zum Master gehört (Varianten), auch den Key umbenennen
            basis_k = k.split("__")[0]
            if basis_k == alter_name:
                suffix = k[len(basis_k):]
                neu_k = neuer_name + suffix
                self.settings[neu_k] = self.settings.pop(k)
                self.settings[neu_k]["gruppe"] = neuer_vollpfad # wird unten nochmal verfeinert falls nötig
                self._log(f"  Eintrag (Variante) umbenannt: '{k}' → '{neu_k}'")
                continue

            if g == alter_vollpfad:
                self._log(f"  Update Pfad: '{k}' (Gruppe: {neuer_vollpfad})")
                self.settings[k]["gruppe"] = neuer_vollpfad
            elif g.startswith(alter_vollpfad + "/"):
                neu_g = neuer_vollpfad + g[len(alter_vollpfad):]
                self._log(f"  Update Pfad (Deep): '{k}' (Gruppe: {neu_g})")
                self.settings[k]["gruppe"] = neu_g

        # Gruppe-Key selbst umbenennen (falls noch nicht durch Varianten-Loop geschehen)
        if alter_name in self.settings:
            self.settings[neuer_name] = self.settings.pop(alter_name)
            # Wichtig: Ein Master hat entweder "" oder sich selbst als Gruppe.
            self.settings[neuer_name]["gruppe"] = neuer_vollpfad if parent else ""
            self._log(f"  Eintrag umbenannt: '{alter_name}' → '{neuer_name}'")

        self._settings_speichern(neu_laden=True)

    def _ordner_aufraumen(self, ordner):
        """Löscht leere Ordner rekursiv bis zum templates/-Wurzelordner."""
        basis = os.path.abspath(TEMPLATES_ORDNER)
        pfad = os.path.abspath(ordner)
        while pfad != basis:
            if os.path.exists(pfad) and not os.listdir(pfad):
                try: os.rmdir(pfad)
                except: break
            else:
                break
            pfad = os.path.dirname(pfad)

    def template_loeschen(self, name):
        if name not in self.templates: return
        pfad = self.templates[name]["pfad"]
        self._backup_zu_deleted(pfad)
        self._ordner_aufraumen(os.path.dirname(pfad))
            
        self.templates.pop(name, None)
        self.settings.pop(name, None)
        self._settings_speichern(neu_laden=True)

    def gruppe_config_speichern(self, gruppe_name, condition_states, uebergeordnete_gruppe="", kategorie=None, scan_regions=None):
        """Speichert eine passive Gruppe (kein Bild, nur Bedingungen) und legt den Ordner an."""
        bestehend = self.settings.get(gruppe_name, {})
        kat = kategorie or bestehend.get("kategorie", "workflow")

        # Ein Master darf sich nicht selbst als Gruppe haben (führt zu Endlos-Pfaden/unsichtbaren Containern)
        g_val = uebergeordnete_gruppe or ""
        if g_val == gruppe_name:
            g_val = ""

        self.settings[gruppe_name] = {
            "typ": "passiv_gruppe",
            "gruppe": g_val,
            "condition_states": condition_states,
            "kategorie": kat,
            "scan_regions": [list(r) for r in scan_regions] if scan_regions else [],
        }
        # Ordner nach Settings-Update bauen (Hierarchie wird über _gruppe_ordnerpfad aufgelöst)
        ordner = self._gruppe_ordnerpfad(gruppe_name)
        os.makedirs(ordner, exist_ok=True)
        self._settings_speichern(neu_laden=True)

    def gruppe_config_loeschen(self, gruppe_name, mit_inhalt=False):
        """Entfernt eine Gruppe und löscht optional alle enthaltenen Templates."""
        if gruppe_name in self.settings:
            typ = self.settings[gruppe_name].get("typ")
            if typ in ("passiv_gruppe", "aktiv_gruppe"):
                ordner = self._gruppe_ordnerpfad(gruppe_name)
                
                if mit_inhalt:
                    kinder = self.get_kinder(gruppe_name)
                    for kind in kinder:
                        if kind in self.templates:
                            self._backup_zu_deleted(self.templates[kind]["pfad"])
                        self.settings.pop(kind, None)
                        self.templates.pop(kind, None)
                    
                    # Wenn es ein aktiver Master war, hat er selbst ein Bild im Ordner
                    basis = gruppe_name.split("__")[0]
                    master_pfad = os.path.join(ordner, f"{basis}.png")
                    if os.path.exists(master_pfad):
                        self._backup_zu_deleted(master_pfad)

                self.settings.pop(gruppe_name, None)
                self._settings_speichern(neu_laden=False)
                
                if mit_inhalt and os.path.exists(ordner):
                    try: shutil.rmtree(ordner)
                    except: pass
                else:
                    self._ordner_aufraumen(ordner)
                
        self._templates_laden()

    def _get_gpu_template(self, name, s_eff):
        key = (name, s_eff)
        if key in self._gpu_cache: return self._gpu_cache[key]
        tpl = self.templates[name]
        t_orig, m_orig = tpl["tensor"], tpl["maske"]
        if s_eff == 1.0:
            t_s, m_s = t_orig, m_orig
        else:
            th, tw = int(t_orig.shape[2]*s_eff), int(t_orig.shape[3]*s_eff)
            t_s = F.interpolate(t_orig, size=(max(1,th), max(1,tw)), mode='bilinear', align_corners=False)
            m_s = F.interpolate(m_orig, size=(max(1,th), max(1,tw)), mode='nearest') if m_orig is not None else None
        
        if m_s is not None:
            m_3 = m_s.expand(1, 3, t_s.shape[2], t_s.shape[3])
            N = m_3.sum() + 1e-5
            t_mean = (t_s * m_3).sum() / N
            t_zm = (t_s - t_mean) * m_3
            t_norm = t_zm.pow(2).sum().sqrt()
            self._gpu_cache[key] = {"t_zm": t_zm, "m": m_3, "t_norm": t_norm, "N": N, "is_masked": True}
        else:
            N = t_s.shape[1] * t_s.shape[2] * t_s.shape[3]
            t_mean = t_s.mean()
            t_zm = t_s - t_mean
            t_norm = t_zm.pow(2).sum().sqrt()
            self._gpu_cache[key] = {"t_zm": t_zm, "t_norm": t_norm, "N": N, "is_masked": False}
        return self._gpu_cache[key]

    @torch.no_grad()
    def matches_suchen_np(self, screenshot_bgr, game_states=None, editor_fokus=None):
        if not self.templates: return [], []
        img_gpu = torch.from_numpy(screenshot_bgr.transpose(2, 0, 1)).float().div(255.0).to(self.device).unsqueeze(0)
        ih, iw = screenshot_bgr.shape[:2]
        s_base = self.matching_skalierung
        ref = self.referenz_groesse
        if ref is not None:
            norm_sx, norm_sy = iw / ref[0], ih / ref[1]
            s_eff, th_t, tw_t = s_base, max(1, int(ref[1]*s_base)), max(1, int(ref[0]*s_base))
        else:
            norm_sx = norm_sy = 1.0
            s_eff, th_t, tw_t = s_base, max(1, int(ih*s_base)), max(1, int(iw*s_base))
        img_m = F.interpolate(img_gpu, size=(th_t, tw_t), mode='bilinear', align_corners=False)
        
        # Master und Kinder trennen
        master_namen = []
        kinder_nach_gruppe = defaultdict(list)
        for name, t in self.templates.items():
            # Check Game State Conditions (UND / ODER Kombi)
            # Varianten erben condition_states vom Master, falls keine eigenen definiert
            tpl_settings = self.settings.get(name, {})
            conditions = tpl_settings.get("condition_states", {})
            if not conditions and "__" in name:
                master_name = name.split("__")[0]
                conditions = self.settings.get(master_name, {}).get("condition_states", {})
            
            # Fokus im Editor: Bedingungen für dieses Template und seine Varianten ignorieren
            ist_fokus = False
            if editor_fokus:
                basis_fokus = editor_fokus.split("__")[0]
                basis_name = name.split("__")[0]
                if basis_name == basis_fokus:
                    ist_fokus = True

            if game_states is not None and not ist_fokus:
                # Eigenen gesetzte Zustände sammeln (Hierarchie-weit!), 
                # damit sie beim [KEIN ANDERER] Check ignoriert werden.
                my_hierarchy_sets = self._get_hierarchy_set_states(name)
                
                if conditions and not self._condition_states_erfuellt(conditions, game_states, ignore_states=my_hierarchy_sets):
                    continue
                # Eltern-Kette prüfen (passive Gruppen, hierarchisch)
                if t["gruppe"] and not self._eltern_conditions_pruefen(t["gruppe"], game_states):
                    continue

            g = t["gruppe"]
            # Ein Template ist ein Master, wenn es keine aktive übergeordnete Gruppe hat.
            # Wenn es eine Gruppe hat, prüfen wir ob IRGENDEIN Teil des Pfades ein eigenes Template ist.
            parent_template = None
            if g:
                teile = g.split("/")
                for i in range(len(teile)):
                    pfad = "/".join(teile[:i+1])
                    if pfad in self.templates:
                        # Wenn wir selbst dieser Pfad sind (oder eine Variante davon), sind wir der Master
                        if pfad == name or name.startswith(pfad + "__"):
                            parent_template = None
                        else:
                            parent_template = pfad
                        break
            
            if parent_template:
                kinder_nach_gruppe[parent_template].append(name)
            else:
                master_namen.append(name)
        
        # Master suchen (Full-Screen) - ROIs hier überspringen
        master_ergebnisse = self._batch_match(img_m, master_namen, s_eff, is_full_scan=True)
        # ROI Matching für Master (🎯) - Hier NIEMALS überspringen
        for name in master_namen:
            # ROI Vererbung nutzen
            regions = self._get_effective_regions(name)
            if regions:
                for reg in regions:
                    rx0, ry0, rx1, ry1 = reg
                    sx0, sy0, sx1, sy1 = int(rx0*s_eff), int(ry0*s_eff), int(rx1*s_eff), int(ry1*s_eff)
                    if sx1 > sx0 and sy1 > sy0:
                        roi_crop = img_m[:, :, sy0:sy1, sx0:sx1]
                        master_ergebnisse.extend(self._batch_match(roi_crop, [name], s_eff, offset=(sx0, sy0), is_full_scan=False))

        master_gefiltert = self._nms(master_ergebnisse)
        final_results = []
        treffer_pro_gruppe = defaultdict(list)
        for m in master_gefiltert:
            name = m[0]
            # WICHTIG: Wir müssen prüfen, ob dieser Master (oder sein Basisname bei Varianten) Kinder hat
            master_key = name
            if master_key not in kinder_nach_gruppe and "__" in master_key:
                master_key = master_key.split("__")[0]
            
            if master_key in kinder_nach_gruppe:
                # Wir ordnen den Treffer der Gruppe des Basis-Masters zu
                treffer_pro_gruppe[master_key].append(m)
            else:
                final_results.append(m)
        
        # 5. Dynamische ROI-Vererbung (Master-Kind): Kinder in gefundenen Master-Instanzen suchen
        for master_name, treffer_liste in treffer_pro_gruppe.items():
            # master_name ist hier der Basisname (z.B. 'Icon_Rechteck')
            kinder_namen = kinder_nach_gruppe[master_name]
            for m_treffer in treffer_liste:
                # Koordinaten des gefundenen Masters auf dem Referenz-System (iw, ih)
                m_rx, m_ry, m_rw, m_rh = m_treffer[1], m_treffer[2], m_treffer[3], m_treffer[4]
                
                # Wir berechnen den Crop-Bereich auf img_m (Padding hinzufügen!)
                # WICHTIG: x0/y0 sind auf der GPU-Skalierung (img_m)
                pad = 4
                x0, y0 = max(0, int(m_rx*s_eff)-pad), max(0, int(m_ry*s_eff)-pad)
                x1, y1 = min(tw_t, int((m_rx+m_rw)*s_eff)+pad), min(th_t, int((m_ry+m_rh)*s_eff)+pad)
                
                if x1 > x0 and y1 > y0:
                    crop = img_m[:, :, y0:y1, x0:x1]
                    # Suche Kinder im Crop (Dynamischer ROI) - Hier NIEMALS überspringen!
                    k_res = self._batch_match(crop, kinder_namen, s_eff, schwellwert_override=0.7, is_full_scan=False)
                    if k_res:
                        # Bestes Kind gewinnt (NMS innerhalb der Gruppe)
                        k_res.sort(key=lambda x: x[5], reverse=True)
                        best_k = k_res[0]
                        # Koordinaten-Zusammenführung (beide müssen im Referenz-System sein!)
                        final_results.append([
                            best_k[0], 
                            (x0/s_eff) + best_k[1], 
                            (y0/s_eff) + best_k[2], 
                            best_k[3], 
                            best_k[4], 
                            best_k[5]
                        ])
                    else:
                        # Falls kein Kind gefunden wurde, bleibt der Master als Treffer stehen
                        final_results.append(m_treffer)

        output = []
        for name, rx_ref, ry_ref, rw_ref, rh_ref, score in final_results:
            d_name = name.split("__")[0]
            # Wir geben den Anzeigenamen, Koordinaten, Score UND den echten physikalischen Namen zurück
            output.append((d_name, int(rx_ref*norm_sx), int(ry_ref*norm_sy), int(rw_ref*norm_sx), int(rh_ref*norm_sy), score, name))
        return self._nms(output), master_namen


    def _batch_match(self, img_tensor, template_namen, s_eff, schwellwert_override=None, offset=(0,0), is_full_scan=False):
        results = []
        if img_tensor.size(2) == 0 or img_tensor.size(3) == 0: return []
        th_t, tw_t = img_tensor.shape[2:]
        ox, oy = offset
        img_sum_ch = img_tensor.sum(dim=1, keepdim=True)
        img_sq_sum_ch = img_tensor.pow(2).sum(dim=1, keepdim=True)
        
        for name in template_namen:
            tpl_data = self.templates[name]
            
            # ROI Vererbung nur beim Full-Screen-Scan überspringen!
            # In einem Crop (is_full_scan=False) müssen wir ALLES suchen.
            if is_full_scan:
                eff_regions = self._get_effective_regions(name)
                if eff_regions:
                    continue
            
            s_limit = schwellwert_override if schwellwert_override is not None else tpl_data["match_schwellwert"]
            gd = self._get_gpu_template(name, s_eff)
            t_zm, t_norm, N = gd["t_zm"], gd["t_norm"], gd["N"]
            th, tw = t_zm.shape[2:]
            if tw > tw_t or th > th_t: continue
            
            res = F.conv2d(img_tensor, t_zm, padding=0)
            if gd["is_masked"]:
                m = gd["m"]
                I_sum = F.conv2d(img_tensor, m, padding=0)
                I_sq_sum = F.conv2d(img_tensor.pow(2), m, padding=0)
                I_var = I_sq_sum - (I_sum.pow(2) / N)
            else:
                I_sum = F.avg_pool2d(img_sum_ch, kernel_size=(th, tw), stride=1, divisor_override=1)
                I_sq_sum = F.avg_pool2d(img_sq_sum_ch, kernel_size=(th, tw), stride=1, divisor_override=1)
                I_var = I_sq_sum - (I_sum.pow(2) / N)
            
            I_norm = torch.sqrt(torch.clamp(I_var, min=1e-5))
            scores = res.sum(dim=1, keepdim=True) / (I_norm * t_norm + 1e-6)
            mask = (scores >= s_limit)
            if mask.any():
                if scores.size(2) > 1 and scores.size(3) > 1:
                    mask = mask & (scores == F.max_pool2d(scores, kernel_size=3, stride=1, padding=1))
                pts = torch.nonzero(mask.view(-1)).squeeze()
                if pts.numel() > 0:
                    if pts.dim() == 0: pts = pts.unsqueeze(0)
                    y_c = (pts // scores.size(3)).cpu().numpy()
                    x_c = (pts % scores.size(3)).cpu().numpy()
                    s_v = scores.view(-1)[pts].cpu().numpy()
                    s_v = np.atleast_1d(s_v)
                    for i in range(len(y_c)):
                        results.append([name, (x_c[i]+ox)/s_eff, (y_c[i]+oy)/s_eff, tw/s_eff, th/s_eff, float(s_v[i])])
        return results

    def _nms(self, matches):
        if not matches: return []
        matches.sort(key=lambda x: x[5], reverse=True)
        ergebnis = []
        for m in matches:
            cx, cy = m[1] + m[3]/2, m[2] + m[4]/2
            doppelt = False
            for a in ergebnis:
                if a[0] == m[0]:
                    acx, acy = a[1] + a[3]/2, a[2] + a[4]/2
                    if abs(cx - acx) < m[3]*0.5 and abs(cy - acy) < m[4]*0.5:
                        doppelt = True; break
            if not doppelt: ergebnis.append(m)
        return ergebnis

    def get_mathematik_vorschau(self, name):
        if name not in self.templates: return None
        gd = self._get_gpu_template(name, 1.0)
        t_zm = gd["t_zm"].squeeze(0).cpu()
        std = torch.std(t_zm)
        t_vis = torch.clamp((t_zm / (std * 6.0 + 1e-5)) + 0.5, 0, 1)
        img_np = (t_vis.numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
        if gd["is_masked"]:
            maske_np = (gd["m"].squeeze(0)[0].cpu().numpy() * 255).astype(np.uint8)
            r, g, b = cv2.split(img_np)
            return Image.merge("RGBA", [Image.fromarray(r), Image.fromarray(g), Image.fromarray(b), Image.fromarray(maske_np)])
        return Image.fromarray(img_np, "RGB")
