import cv2
import numpy as np
import os
import json
import torch
import torch.nn.functional as F
from PIL import Image
from collections import defaultdict

TEMPLATES_ORDNER = "templates"
SETTINGS_DATEI = "template_settings.json"

class TemplateEngine:
    def __init__(self, matching_skalierung=0.5, referenz_groesse=None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"TemplateEngine: Nutze Device '{self.device}'")
        
        self.templates = {}
        self.settings = {}
        self.matching_skalierung = matching_skalierung
        self.referenz_groesse = referenz_groesse
        self._gpu_cache = {}
        
        os.makedirs(TEMPLATES_ORDNER, exist_ok=True)
        self.konfigurationen_bereinigen()
        self._settings_laden()
        self._templates_laden()

    def konfigurationen_bereinigen(self):
        if not os.path.exists(TEMPLATES_ORDNER): return

        aktuelle_pngs = set()
        for root, _, dateien in os.walk(TEMPLATES_ORDNER):
            for f in dateien:
                if f.endswith(".png"): aktuelle_pngs.add(f[:-4])

        json_dateien = ["template_settings.json", "template_farben.json", "template_klicks.json"]
        for datei in json_dateien:
            if os.path.exists(datei):
                try:
                    with open(datei, "r", encoding="utf-8") as f: data = json.load(f)
                    neu = {k: v for k, v in data.items() if
                           k.startswith("_") or
                           k in aktuelle_pngs or
                           k.startswith("__gruppe__") or
                           (isinstance(v, dict) and v.get("typ") in ("passiv_gruppe", "aktiv_gruppe", "template", "state_template"))}
                    if len(neu) != len(data):
                        with open(datei, "w", encoding="utf-8") as f: json.dump(neu, f, indent=2, ensure_ascii=False)
                except Exception: pass
        
        if os.path.exists("template_ocr.json"):
            try:
                with open("template_ocr.json", "r", encoding="utf-8") as f: data = json.load(f)
                neu = {k: v for k, v in data.items() if v.get("template") in aktuelle_pngs}
                if len(neu) != len(data):
                    with open("template_ocr.json", "w", encoding="utf-8") as f: json.dump(neu, f, indent=2, ensure_ascii=False)
            except Exception: pass

    def _settings_laden(self):
        if os.path.exists(SETTINGS_DATEI):
            try:
                with open(SETTINGS_DATEI, "r", encoding="utf-8") as f: self.settings = json.load(f)
            except Exception: self.settings = {}
        self._settings_migrieren()

    def _settings_migrieren(self):
        """Einmalige Migration auf Typ-System v2. Schreibt Backup vor dem ersten Speichern."""
        if self.settings.get("_migrated_v2"):
            return

        import shutil
        if os.path.exists(SETTINGS_DATEI):
            try: shutil.copy2(SETTINGS_DATEI, SETTINGS_DATEI + ".bak")
            except Exception: pass

        neu = {}
        for k, v in self.settings.items():
            if not isinstance(v, dict):
                neu[k] = v
                continue
            if k.startswith("_"):
                neu[k] = v
                continue

            # Alte passive Gruppen: __gruppe__Name → Name mit typ
            if k.startswith("__gruppe__"):
                name = k[len("__gruppe__"):]
                if name and name not in neu:
                    eintrag = dict(v)
                    eintrag["typ"] = "passiv_gruppe"
                    eintrag.setdefault("gruppe", "")
                    neu[name] = eintrag
                continue

            eintrag = dict(v)
            if not eintrag.get("typ"):
                if eintrag.get("gruppe") == k:
                    eintrag["typ"] = "aktiv_gruppe"
                else:
                    eintrag["typ"] = "template"

            # ist_state_template Flag für bestehende Templates mit set_states
            if eintrag.get("set_states") and not eintrag.get("ist_state_template"):
                eintrag["ist_state_template"] = True

            neu[k] = eintrag

        neu["_migrated_v2"] = True
        self.settings = neu
        with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)

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
                    gruppe = None if rel_pfad == "." else rel_pfad.replace("\\", "/")
                    
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
        print(f"TemplateEngine: {len(self.templates)} Templates geladen.")

    def get_gruppen(self):
        """Gibt eine Liste aller existierenden Gruppen zurück (aktiv + passiv)."""
        gruppen = set()

        # 1. Ordner auf der Festplatte (aktiv_gruppe)
        if os.path.exists(TEMPLATES_ORDNER):
            try:
                for root, dirs, _ in os.walk(TEMPLATES_ORDNER):
                    dirs[:] = [d for d in dirs if not d.startswith('_')]
                    for d in dirs:
                        rel = os.path.relpath(os.path.join(root, d), TEMPLATES_ORDNER).replace("\\", "/")
                        gruppen.add(rel)
            except Exception: pass

        # 2. Aus geladenen Templates
        for t in self.templates.values():
            if t["gruppe"]: gruppen.add(t["gruppe"])

        # 3. Passive Gruppen (settings-Einträge mit typ="passiv_gruppe")
        for k, v in self.settings.items():
            if isinstance(v, dict) and v.get("typ") == "passiv_gruppe":
                gruppen.add(k)
            # Rückwärtskompatibilität: altes __gruppe__ Format
            elif k.startswith("__gruppe__"):
                gruppen.add(k[len("__gruppe__"):])

        return sorted(g for g in gruppen if g)

    @staticmethod
    def _condition_states_erfuellt(conditions, game_states):
        """Wertet condition_states gegen game_states aus. Unterstützt altes und neues Format."""
        if not conditions:
            return True

        # Altes Format (dict): {"Map": True} → einfaches AND
        if isinstance(conditions, dict):
            return all(game_states.get(k) == v for k, v in conditions.items())

        if not isinstance(conditions, list) or not conditions:
            return True

        first = conditions[0]

        # Neues Format: [{"connector": ..., "states": {...}}, ...]
        if isinstance(first, dict) and ("states" in first or "connector" in first):
            result = None
            for group in conditions:
                connector = group.get("connector")  # None | "OR" | "AND"
                states = group.get("states", {})
                group_ok = all(game_states.get(k) == v for k, v in states.items())
                if result is None or connector is None or connector == "OR":
                    result = group_ok if result is None else (result or group_ok)
                else:  # AND
                    result = result and group_ok
            return bool(result)

        # Altes Listen-Format: [{"Map": True}, {"Statd": True}] → OR zwischen Gruppen
        for group in conditions:
            if isinstance(group, dict) and all(game_states.get(k) == v for k, v in group.items()):
                return True
        return False

    def _eltern_conditions_pruefen(self, gruppe_pfad, game_states):
        """Prüft Bedingungen aller Eltern-Ebenen eines Gruppe-Pfads (hierarchisch)."""
        if not gruppe_pfad:
            return True
        teile = gruppe_pfad.split("/")
        for i in range(len(teile)):
            pfad = "/".join(teile[:i + 1])
            eintrag = self.settings.get(pfad, {})
            if not isinstance(eintrag, dict):
                continue
            conds = eintrag.get("condition_states", [])
            if conds and not self._condition_states_erfuellt(conds, game_states):
                return False
            # Rückwärtskompatibilität: altes __gruppe__ Format
            alt_conds = self.settings.get(f"__gruppe__{pfad}", {}).get("condition_states", [])
            if alt_conds and not self._condition_states_erfuellt(alt_conds, game_states):
                return False
        return True

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

    def template_speichern(self, name, bild_pil, hintergrund_entfernen=True, ignore_regionen=None, hintergrund_toleranz=30, gruppe=None, match_schwellwert=0.85, scan_regions=None, condition_states=None, set_states=None, typ=None, ist_state_template=False):
        bild_np = np.array(bild_pil.convert("RGB"))

        basis_name = name.split("__")[0]
        # aktiv_gruppe: Gruppe ist immer der eigene Name
        if typ == "aktiv_gruppe":
            g_name = basis_name
        else:
            g_name = gruppe if gruppe else basis_name

        # Hierarchischer Pfad: "UI/Button" → templates/UI/Button/
        ordner = os.path.join(TEMPLATES_ORDNER, *g_name.split("/"))
        os.makedirs(ordner, exist_ok=True)

        pfad = os.path.join(ordner, f"{name}.png")

        # Altes Template an anderer Stelle löschen?
        if name in self.templates:
            alter_pfad = self.templates[name]["pfad"]
            if os.path.exists(alter_pfad) and os.path.abspath(alter_pfad) != os.path.abspath(pfad):
                try: 
                    os.remove(alter_pfad)
                    alt_dir = os.path.dirname(alter_pfad)
                    if os.path.exists(alt_dir) and not os.listdir(alt_dir): os.rmdir(alt_dir)
                except: pass

        # Maske erstellen
        if hintergrund_entfernen:
            maske = self._hintergrund_maske_erstellen(bild_np, toleranz=hintergrund_toleranz)
            if ignore_regionen:
                for (ix0, iy0, ix1, iy1) in ignore_regionen:
                    maske[max(0,int(iy0)):int(iy1), max(0,int(ix0)):int(ix1)] = 0
            bild_rgba = np.dstack([bild_np, maske])
            bild_speichern = Image.fromarray(bild_rgba, "RGBA")
        else:
            bild_speichern = bild_pil.convert("RGBA")
            if ignore_regionen:
                arr = np.array(bild_speichern)
                h, w = arr.shape[:2]
                for (x0, y0, x1, y1) in ignore_regionen:
                    arr[max(0,int(y0)):min(h,int(y1)), max(0,int(x0)):min(w,int(x1)), 3] = 0
                bild_speichern = Image.fromarray(arr, "RGBA")

        bild_speichern.save(pfad)
        
        # Typ ableiten falls nicht angegeben
        if not typ:
            bestehend = self.settings.get(name, {})
            typ = bestehend.get("typ") or ("aktiv_gruppe" if g_name == basis_name else "template")

        # ist_state_template: explizit oder aus set_states ableiten
        _ist_state = ist_state_template or bool(set_states) or self.settings.get(name, {}).get("ist_state_template", False)

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
            "ist_state_template": _ist_state,
        }
        with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)
            
        self._templates_laden()

    def template_umbenennen(self, alter_name, neuer_name, neue_gruppe=None):
        """Benennt ein Template und alle seine Varianten um oder verschiebt sie."""
        alter_basis = alter_name.split("__")[0]
        neuer_basis = neuer_name.split("__")[0]

        varianten = [t for t in self.templates.keys() if t == alter_basis or t.startswith(f"{alter_basis}__")]

        for v_alt in varianten:
            suffix = v_alt[len(alter_basis):]
            v_neu = f"{neuer_basis}{suffix}"
            if v_alt not in self.templates: continue

            alt_pfad = self.templates[v_alt]["pfad"]
            g_name = neue_gruppe if neue_gruppe else neuer_basis
            neu_ordner = os.path.join(TEMPLATES_ORDNER, *g_name.split("/"))
            os.makedirs(neu_ordner, exist_ok=True)
            neu_pfad = os.path.join(neu_ordner, f"{v_neu}.png")

            if os.path.exists(alt_pfad):
                try:
                    if os.path.exists(neu_pfad) and os.path.abspath(alt_pfad) != os.path.abspath(neu_pfad):
                        os.remove(neu_pfad)
                    os.rename(alt_pfad, neu_pfad)
                    alt_dir = os.path.dirname(alt_pfad)
                    if os.path.exists(alt_dir) and not os.listdir(alt_dir): os.rmdir(alt_dir)
                except: pass

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

        with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)
        self._templates_laden()

    def gruppe_umbenennen(self, alter_pfad, neuer_pfad):
        """Benennt eine Gruppe um: verschiebt Ordner + aktualisiert alle Settings-Einträge."""
        alter_ordner = os.path.join(TEMPLATES_ORDNER, *alter_pfad.split("/"))
        neuer_ordner = os.path.join(TEMPLATES_ORDNER, *neuer_pfad.split("/"))

        if os.path.exists(alter_ordner):
            try:
                os.makedirs(os.path.dirname(neuer_ordner) or ".", exist_ok=True)
                os.rename(alter_ordner, neuer_ordner)
            except Exception as e:
                print(f"gruppe_umbenennen: Ordner-Fehler: {e}")

        # Settings-Einträge cascadieren
        for k, v in list(self.settings.items()):
            if not isinstance(v, dict): continue
            g = v.get("gruppe", "")
            if g == alter_pfad:
                self.settings[k]["gruppe"] = neuer_pfad
            elif g.startswith(alter_pfad + "/"):
                self.settings[k]["gruppe"] = neuer_pfad + g[len(alter_pfad):]

        # Gruppe-Key selbst umbenennen (passiv_gruppe oder aktiv_gruppe)
        if alter_pfad in self.settings:
            self.settings[neuer_pfad] = self.settings.pop(alter_pfad)
            if self.settings[neuer_pfad].get("typ") == "aktiv_gruppe":
                self.settings[neuer_pfad]["gruppe"] = neuer_pfad

        with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)
        self._templates_laden()

    def template_loeschen(self, name):
        if name not in self.templates: return
        pfad = self.templates[name]["pfad"]
        if os.path.exists(pfad): os.remove(pfad)
        
        # Ordner aufräumen
        ordner = os.path.dirname(pfad)
        if os.path.exists(ordner) and not os.listdir(ordner):
            try: os.rmdir(ordner)
            except: pass
            
        self.templates.pop(name, None)
        self.settings.pop(name, None)
        with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)
        self._gpu_cache = {}

    def gruppe_config_speichern(self, gruppe_name, condition_states, uebergeordnete_gruppe=""):
        """Speichert eine passive Gruppe (kein Bild, nur Bedingungen)."""
        bestehend = self.settings.get(gruppe_name, {})
        self.settings[gruppe_name] = {
            "typ": "passiv_gruppe",
            "gruppe": uebergeordnete_gruppe or bestehend.get("gruppe", ""),
            "condition_states": condition_states,
        }
        with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)

    def gruppe_config_loeschen(self, gruppe_name):
        """Entfernt eine passive Gruppe."""
        # Neues Format: plain key
        entfernt = False
        if gruppe_name in self.settings and self.settings[gruppe_name].get("typ") == "passiv_gruppe":
            del self.settings[gruppe_name]
            entfernt = True
        # Rückwärtskompatibilität: altes __gruppe__ Format
        alt_key = f"__gruppe__{gruppe_name}"
        if alt_key in self.settings:
            del self.settings[alt_key]
            entfernt = True
        if entfernt:
            with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)

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
    def matches_suchen_np(self, screenshot_bgr, game_states=None):
        if not self.templates: return []
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
            
            if game_states is not None:
                if conditions and not self._condition_states_erfuellt(conditions, game_states):
                    continue
                # Eltern-Kette prüfen (passive Gruppen, hierarchisch)
                if t["gruppe"] and not self._eltern_conditions_pruefen(t["gruppe"], game_states):
                    continue

            g = t["gruppe"]
            # Ein Template ist ein Master, wenn es keine Gruppe hat, 
            # sein Name der Gruppe entspricht oder mit {Gruppe}__ beginnt (Varianten)
            if g is None or name == g or name.startswith(f"{g}__"):
                master_namen.append(name)
            else:
                kinder_nach_gruppe[g].append(name)
        
        # Master suchen
        master_ergebnisse = self._batch_match(img_m, master_namen, s_eff)
        # ROI Matching für Master
        for name in master_namen:
            regions = self.templates[name].get("scan_regions")
            if regions:
                for reg in regions:
                    rx0, ry0, rx1, ry1 = reg
                    sx0, sy0, sx1, sy1 = int(rx0*s_eff), int(ry0*s_eff), int(rx1*s_eff), int(ry1*s_eff)
                    if sx1 > sx0 and sy1 > sy0:
                        roi_crop = img_m[:, :, sy0:sy1, sx0:sx1]
                        master_ergebnisse.extend(self._batch_match(roi_crop, [name], s_eff, offset=(sx0, sy0)))

        master_gefiltert = self._nms(master_ergebnisse)
        final_results = []
        treffer_pro_gruppe = defaultdict(list)
        for m in master_gefiltert:
            name, rx, ry, rw, rh, score = m
            gruppe = self.templates[name]["gruppe"]
            if gruppe in kinder_nach_gruppe: treffer_pro_gruppe[gruppe].append(m)
            else: final_results.append(m)
        
        for gruppe, treffer_liste in treffer_pro_gruppe.items():
            kinder_namen = kinder_nach_gruppe[gruppe]
            for m_treffer in treffer_liste:
                m_rx, m_ry = m_treffer[1], m_treffer[2]
                pad = 4
                x0, y0 = max(0, int(m_rx*s_eff)-pad), max(0, int(m_ry*s_eff)-pad)
                x1, y1 = min(tw_t, int((m_rx+m_treffer[3])*s_eff)+pad), min(th_t, int((m_ry+m_treffer[4])*s_eff)+pad)
                if x1 > x0 and y1 > y0:
                    crop = img_m[:, :, y0:y1, x0:x1]
                    k_res = self._batch_match(crop, kinder_namen, s_eff, schwellwert_override=0.7)
                    if k_res:
                        k_res.sort(key=lambda x: x[5], reverse=True)
                        best_k = k_res[0]
                        final_results.append([best_k[0], (x0/s_eff)+best_k[1], (y0/s_eff)+best_k[2], best_k[3], best_k[4], best_k[5]])
                    else: final_results.append(m_treffer)

        output = []
        for name, rx_ref, ry_ref, rw_ref, rh_ref, score in final_results:
            d_name = name.split("__")[0]
            # Wir geben den Anzeigenamen, Koordinaten, Score UND den echten physikalischen Namen zurück
            output.append((d_name, int(rx_ref*norm_sx), int(ry_ref*norm_sy), int(rw_ref*norm_sx), int(rh_ref*norm_sy), score, name))
        return self._nms(output)


    def _batch_match(self, img_tensor, template_namen, s_eff, schwellwert_override=None, offset=(0,0)):
        results = []
        if img_tensor.size(2) == 0 or img_tensor.size(3) == 0: return []
        th_t, tw_t = img_tensor.shape[2:]
        ox, oy = offset
        img_sum_ch = img_tensor.sum(dim=1, keepdim=True)
        img_sq_sum_ch = img_tensor.pow(2).sum(dim=1, keepdim=True)
        
        for name in template_namen:
            tpl_data = self.templates[name]
            if ox == 0 and oy == 0 and tpl_data.get("scan_regions") and name in template_namen: continue
            
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
