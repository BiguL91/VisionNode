import cv2
import numpy as np
import os
import torch
import torch.nn.functional as F
from collections import defaultdict
from PIL import Image

from engines.template_store import TemplateStore, TEMPLATES_ORDNER, SETTINGS_ORDNER, DELETED_ORDNER

class TemplateEngine:
    SETTINGS_DATEI = TemplateStore.SETTINGS_DATEI

    def __init__(self, matching_skalierung=0.5, referenz_groesse=None, log_func=None, log_enabled_func=None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.log_func = log_func
        self.log_enabled_func = log_enabled_func
        self._log(f"TemplateEngine: Nutze Device '{self.device}'")

        self.templates = {}
        self.settings  = {}
        self.matching_skalierung = matching_skalierung
        self.referenz_groesse    = referenz_groesse
        self._gpu_cache = {}

        # Store erhält Referenzen auf die eigenen Dicts
        self._store = TemplateStore(self.settings, self.templates, log_func, log_enabled_func)

        os.makedirs(TEMPLATES_ORDNER, exist_ok=True)
        os.makedirs(SETTINGS_ORDNER,  exist_ok=True)
        os.makedirs(DELETED_ORDNER,   exist_ok=True)
        self._store.konfigurationen_bereinigen()
        self._store._settings_laden()
        self._templates_laden()

    def _log(self, message):
        if self.log_func:
            if self.log_enabled_func and not self.log_enabled_func():
                return
            self.log_func(message)
        else:
            print(f"LOG: {message}")

    # ── Delegatoren → Store (keine GPU) ───────────────────────────────────────

    def get_kinder(self, gruppe_name):
        return self._store.get_kinder(gruppe_name)

    def get_gruppen(self, kategorie=None):
        return self._store.get_gruppen(kategorie)

    def konfigurationen_bereinigen(self):
        self._store.konfigurationen_bereinigen()

    def state_umbenennen_in_settings(self, alter_name, neuer_name):
        self._store.state_umbenennen_in_settings(alter_name, neuer_name)

    def state_loeschen_in_settings(self, name):
        self._store.state_loeschen_in_settings(name)

    def template_speichern(self, name, bild_pil, hintergrund_entfernen=True, ignore_regionen=None,
                           hintergrund_toleranz=30, gruppe=None, match_schwellwert=0.85,
                           scan_regions=None, condition_states=None, set_states=None, typ=None,
                           ist_state_template=False, kategorie=None, alter_name=None,
                           ausschnitt_form="box", search_only=False):
        self._store.template_speichern(
            name, bild_pil, hintergrund_entfernen, ignore_regionen, hintergrund_toleranz,
            gruppe, match_schwellwert, scan_regions, condition_states, set_states, typ,
            ist_state_template, kategorie, alter_name, ausschnitt_form, search_only
        )
        self._templates_laden()

    def template_umbenennen(self, alter_name, neuer_name, neue_gruppe=None):
        self._store.template_umbenennen(alter_name, neuer_name, neue_gruppe)
        self._templates_laden()

    def template_loeschen(self, name):
        self._store.template_loeschen(name)
        self._templates_laden()

    def gruppe_config_speichern(self, gruppe_name, condition_states, uebergeordnete_gruppe="",
                                kategorie=None, scan_regions=None, search_only=False):
        self._store.gruppe_config_speichern(
            gruppe_name, condition_states, uebergeordnete_gruppe, kategorie, scan_regions, search_only
        )
        self._templates_laden()

    def gruppe_config_loeschen(self, gruppe_name, mit_inhalt=False):
        self._store.gruppe_config_loeschen(gruppe_name, mit_inhalt)
        self._templates_laden()

    def gruppe_umbenennen(self, alter_name, neuer_name, neue_uebergeordnete_gruppe=None):
        self._store.gruppe_umbenennen(alter_name, neuer_name, neue_uebergeordnete_gruppe)
        self._templates_laden()

    # ── Template-Laden (brückt Dateisystem → GPU-Tensoren) ────────────────────

    def _templates_laden(self):
        self._store._settings_laden()
        self.templates.clear()
        self._gpu_cache.clear()
        if not os.path.exists(TEMPLATES_ORDNER):
            return

        for root, dirs, dateien in os.walk(TEMPLATES_ORDNER):
            dirs[:] = [d for d in dirs if not d.startswith('_')]
            for datei in dateien:
                if datei.endswith(".png"):
                    rel_pfad = os.path.relpath(root, TEMPLATES_ORDNER)
                    if rel_pfad == ".":
                        gruppe = None
                    else:
                        teile = rel_pfad.replace("\\", "/").split("/")
                        if teile[0] in {"state", "workflow"} and len(teile) >= 2:
                            gruppe = "/".join(teile[1:])
                        else:
                            gruppe = rel_pfad.replace("\\", "/")

                    name = datei[:-4]
                    pfad = os.path.join(root, datei)

                    img = cv2.imdecode(np.fromfile(pfad, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if img is None:
                        continue
                    h, w = img.shape[:2]

                    if img.shape[2] == 4:
                        alpha    = img[:, :, 3]
                        maske_np = np.where(alpha > 10, 1.0, 0.0).astype(np.float32)
                        bild_bgr = img[:, :, :3]
                        bbox     = self._maske_bbox((alpha > 10).astype(np.uint8))
                        if bbox:
                            bx, by, bw, bh = bbox
                            bild_bgr = bild_bgr[by:by+bh, bx:bx+bw]
                            maske_np = maske_np[by:by+bh, bx:bx+bw]
                    else:
                        maske_np = None
                        bild_bgr = img
                        bbox     = None

                    t_bild = torch.from_numpy(bild_bgr.transpose(2, 0, 1)).float().div(255.0).to(self.device).unsqueeze(0)
                    t_maske = (
                        torch.from_numpy(maske_np).float().to(self.device).unsqueeze(0).unsqueeze(0)
                        if maske_np is not None else None
                    )

                    self.templates[name] = {
                        "tensor":           t_bild,
                        "maske":            t_maske,
                        "orig_size":        (w, h),
                        "gruppe":           gruppe,
                        "pfad":             pfad,
                        "match_schwellwert": self.settings.get(name, {}).get("match_schwellwert", 0.85),
                        "scan_regions":     self.settings.get(name, {}).get("scan_regions", []),
                        "bbox":             bbox,
                    }
        self._log(f"TemplateEngine: {len(self.templates)} Templates geladen.")

    # ── Bild-Helfer ───────────────────────────────────────────────────────────

    def _hintergrund_maske_erstellen(self, bild_np, toleranz=30):
        return self._store._hintergrund_maske_erstellen(bild_np, toleranz)

    def _maske_bbox(self, maske):
        opak = np.count_nonzero(maske)
        if opak / maske.size > 0.70:
            return None
        zeilen  = np.any(maske > 0, axis=1)
        spalten = np.any(maske > 0, axis=0)
        if not zeilen.any():
            return None
        y0, y1 = np.where(zeilen)[0][[0, -1]]
        x0, x1 = np.where(spalten)[0][[0, -1]]
        return (int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))

    # ── Matching-Logik ────────────────────────────────────────────────────────

    @staticmethod
    def _condition_states_erfuellt(conditions, game_states, ignore_states=None):
        """Wertet condition_states gegen game_states aus. Unterstützt altes und neues Format."""
        if not conditions or game_states is None:
            return True

        def _wert_pruefen(k, v):
            if k == "[KEIN ANDERER ZUSTAND]":
                for s_name, s_val in game_states.items():
                    if s_val is True:
                        if ignore_states and s_name in ignore_states:
                            continue
                        if v: return False
                        else: return True
                return v
            return game_states.get(k) == v

        if isinstance(conditions, dict):
            return all(_wert_pruefen(k, v) for k, v in conditions.items())

        if not isinstance(conditions, list) or not conditions:
            return True

        first = conditions[0]

        if isinstance(first, dict) and ("states" in first or "connector" in first):
            result = None
            for group in conditions:
                connector = group.get("connector")
                states    = group.get("states", {})
                group_ok  = all(_wert_pruefen(k, v) for k, v in states.items())
                if result is None or connector is None or connector == "OR":
                    result = group_ok if result is None else (result or group_ok)
                else:
                    result = result and group_ok
            return bool(result)

        for group in conditions:
            if isinstance(group, dict) and all(_wert_pruefen(k, v) for k, v in group.items()):
                return True
        return False

    def _get_hierarchy_set_states(self, name_oder_pfad):
        """Sammelt alle set_states eines Templates/Pfades und seiner Eltern."""
        sets = set()
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad:
            leaf = name_oder_pfad.split("/")[-1]
            s    = self.settings.get(leaf, {})

        if s:
            sets.update(s.get("set_states", {}).keys())
            if "__" in name_oder_pfad:
                m_name = name_oder_pfad.split("__")[0]
                sets.update(self.settings.get(m_name, {}).get("set_states", {}).keys())

            current_path = s.get("gruppe", "")
            besucht = {name_oder_pfad}
            while current_path:
                teile = current_path.split("/")
                leaf  = teile[-1]
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
        """Prüft den nächsten Elternteil mit definierten Bedingungen in der Hierarchie."""
        if not pfad: return True
        current_path = pfad
        besucht = set()

        while current_path:
            teile = current_path.split("/")
            leaf  = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)

            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                conds = eintrag.get("condition_states", [])
                if conds:
                    my_hierarchy_sets = self._get_hierarchy_set_states(current_path)
                    if not self._condition_states_erfuellt(conds, game_states, ignore_states=my_hierarchy_sets):
                        return False
                    return True
                if len(teile) > 1:
                    current_path = "/".join(teile[:-1])
                else:
                    current_path = eintrag.get("gruppe", "")
            else:
                break
        return True

    def _get_effective_regions(self, name):
        """Gibt die Scan-Bereiche (ROI) für ein Template zurück (rekursive Vererbung)."""
        s = self.settings.get(name, {})
        if isinstance(s, dict) and s.get("scan_regions"):
            return s["scan_regions"]

        current_path = s.get("gruppe", "") if isinstance(s, dict) else ""
        besucht = {name}

        while current_path:
            teile = current_path.split("/")
            leaf  = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)

            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                if eintrag.get("scan_regions"):
                    return eintrag["scan_regions"]
                if len(teile) > 1:
                    current_path = "/".join(teile[:-1])
                else:
                    current_path = eintrag.get("gruppe", "")
            else:
                break
        return []

    def _is_search_only_recursive(self, name_oder_pfad):
        """Prüft ob ein Element oder seine Eltern-Kette 'search_only' ist."""
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad:
            leaf = name_oder_pfad.split("/")[-1]
            s    = self.settings.get(leaf, {})

        if s and s.get("search_only"):
            return True

        current_path = s.get("gruppe", "") if isinstance(s, dict) else ""
        besucht = {name_oder_pfad}
        while current_path:
            teile = current_path.split("/")
            leaf  = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)

            ps = self.settings.get(leaf, {})
            if isinstance(ps, dict):
                if ps.get("search_only"):
                    return True
                if len(teile) > 1:
                    current_path = "/".join(teile[:-1])
                else:
                    current_path = ps.get("gruppe", "")
            else:
                break
        return False

    def _get_gpu_template(self, name, s_eff):
        key = (name, s_eff)
        if key in self._gpu_cache:
            return self._gpu_cache[key]
        tpl = self.templates[name]
        t_orig, m_orig = tpl["tensor"], tpl["maske"]
        if s_eff == 1.0:
            t_s, m_s = t_orig, m_orig
        else:
            th = int(t_orig.shape[2] * s_eff)
            tw = int(t_orig.shape[3] * s_eff)
            t_s = F.interpolate(t_orig, size=(max(1, th), max(1, tw)), mode='bilinear', align_corners=False)
            m_s = F.interpolate(m_orig, size=(max(1, th), max(1, tw)), mode='nearest') if m_orig is not None else None

        if m_s is not None:
            m_3  = m_s.expand(1, 3, t_s.shape[2], t_s.shape[3])
            N    = m_3.sum() + 1e-5
            t_mean = (t_s * m_3).sum() / N
            t_zm   = (t_s - t_mean) * m_3
            t_norm = t_zm.pow(2).sum().sqrt()
            self._gpu_cache[key] = {"t_zm": t_zm, "m": m_3, "t_norm": t_norm, "N": N, "is_masked": True}
        else:
            N      = t_s.shape[1] * t_s.shape[2] * t_s.shape[3]
            t_mean = t_s.mean()
            t_zm   = t_s - t_mean
            t_norm = t_zm.pow(2).sum().sqrt()
            self._gpu_cache[key] = {"t_zm": t_zm, "t_norm": t_norm, "N": N, "is_masked": False}
        return self._gpu_cache[key]

    @torch.no_grad()
    def matches_suchen_np(self, screenshot_bgr, game_states=None, force_include=None):
        if not self.templates: return [], []
        img_gpu = torch.from_numpy(screenshot_bgr.transpose(2, 0, 1)).float().div(255.0).to(self.device).unsqueeze(0)
        ih, iw  = screenshot_bgr.shape[:2]
        s_base  = self.matching_skalierung
        ref     = self.referenz_groesse
        if ref is not None:
            norm_sx, norm_sy = iw / ref[0], ih / ref[1]
            s_eff, th_t, tw_t = s_base, max(1, int(ref[1]*s_base)), max(1, int(ref[0]*s_base))
        else:
            norm_sx = norm_sy = 1.0
            s_eff, th_t, tw_t = s_base, max(1, int(ih*s_base)), max(1, int(iw*s_base))
        img_m = F.interpolate(img_gpu, size=(th_t, tw_t), mode='bilinear', align_corners=False)

        fi_set = set()
        if force_include:
            namen_liste = [force_include] if isinstance(force_include, (str, type(None))) else force_include
            for n in (namen_liste or []):
                if n and isinstance(n, str):
                    basis = n.split("__")[0]
                    fi_set.add(basis)
                    tpl_s = self.settings.get(basis, {})
                    g_val = tpl_s.get("gruppe", "")
                    if g_val:
                        for g_teil in g_val.split("/"):
                            if g_teil: fi_set.add(g_teil)

        master_namen      = []
        kinder_nach_gruppe = defaultdict(list)
        for name, t in self.templates.items():
            tpl_settings = self.settings.get(name, {})
            conditions   = tpl_settings.get("condition_states", {})
            if not conditions and "__" in name:
                master_name = name.split("__")[0]
                conditions  = self.settings.get(master_name, {}).get("condition_states", {})

            basis_name   = name.split("__")[0]
            ist_erzwungen = basis_name in fi_set

            if not ist_erzwungen and t.get("gruppe"):
                for teil in t["gruppe"].split("/"):
                    if teil in fi_set:
                        ist_erzwungen = True
                        break

            if not ist_erzwungen and self._is_search_only_recursive(name):
                continue

            if game_states is not None and not ist_erzwungen:
                my_hierarchy_sets = self._get_hierarchy_set_states(name)
                if conditions and not self._condition_states_erfuellt(conditions, game_states, ignore_states=my_hierarchy_sets):
                    continue
                if t["gruppe"] and not self._eltern_conditions_pruefen(t["gruppe"], game_states):
                    continue

            g = t["gruppe"]
            parent_template = None
            if g:
                teile = g.split("/")
                for i in range(len(teile)):
                    pfad = "/".join(teile[:i+1])
                    if pfad in self.templates:
                        if pfad == name or name.startswith(pfad + "__"):
                            parent_template = None
                        else:
                            parent_template = pfad
                        break

            if parent_template:
                kinder_nach_gruppe[parent_template].append(name)
            else:
                master_namen.append(name)

        master_ergebnisse = self._batch_match(img_m, master_namen, s_eff, is_full_scan=True)
        for name in master_namen:
            regions = self._get_effective_regions(name)
            if regions:
                for reg in regions:
                    rx0, ry0, rx1, ry1 = reg
                    sx0, sy0 = int(rx0*s_eff), int(ry0*s_eff)
                    sx1, sy1 = int(rx1*s_eff), int(ry1*s_eff)
                    if sx1 > sx0 and sy1 > sy0:
                        roi_crop = img_m[:, :, sy0:sy1, sx0:sx1]
                        master_ergebnisse.extend(self._batch_match(roi_crop, [name], s_eff, offset=(sx0, sy0), is_full_scan=False))

        master_gefiltert   = self._nms(master_ergebnisse)
        final_results      = []
        treffer_pro_gruppe = defaultdict(list)
        for m in master_gefiltert:
            name = m[0]
            master_key = name
            if master_key not in kinder_nach_gruppe and "__" in master_key:
                master_key = master_key.split("__")[0]

            if master_key in kinder_nach_gruppe:
                treffer_pro_gruppe[master_key].append(m)
            else:
                final_results.append(m)

        for master_name, treffer_liste in treffer_pro_gruppe.items():
            kinder_namen = kinder_nach_gruppe[master_name]
            for m_treffer in treffer_liste:
                m_rx, m_ry, m_rw, m_rh = m_treffer[1], m_treffer[2], m_treffer[3], m_treffer[4]
                pad = 4
                x0 = max(0, int(m_rx*s_eff)-pad)
                y0 = max(0, int(m_ry*s_eff)-pad)
                x1 = min(tw_t, int((m_rx+m_rw)*s_eff)+pad)
                y1 = min(th_t, int((m_ry+m_rh)*s_eff)+pad)

                if x1 > x0 and y1 > y0:
                    crop  = img_m[:, :, y0:y1, x0:x1]
                    k_res = self._batch_match(crop, kinder_namen, s_eff, schwellwert_override=0.7, is_full_scan=False)
                    if k_res:
                        k_res.sort(key=lambda x: x[5], reverse=True)
                        best_k = k_res[0]
                        final_results.append([
                            best_k[0],
                            (x0/s_eff) + best_k[1],
                            (y0/s_eff) + best_k[2],
                            best_k[3],
                            best_k[4],
                            best_k[5],
                        ])
                    else:
                        final_results.append(m_treffer)

        output = []
        for name, rx_ref, ry_ref, rw_ref, rh_ref, score in final_results:
            d_name = name.split("__")[0]
            output.append((d_name, int(rx_ref*norm_sx), int(ry_ref*norm_sy), int(rw_ref*norm_sx), int(rh_ref*norm_sy), score, name))
        return self._nms(output), master_namen

    def _batch_match(self, img_tensor, template_namen, s_eff, schwellwert_override=None, offset=(0,0), is_full_scan=False):
        results = []
        if img_tensor.size(2) == 0 or img_tensor.size(3) == 0: return []
        th_t, tw_t = img_tensor.shape[2:]
        ox, oy     = offset
        img_sum_ch    = img_tensor.sum(dim=1, keepdim=True)
        img_sq_sum_ch = img_tensor.pow(2).sum(dim=1, keepdim=True)

        for name in template_namen:
            tpl_data = self.templates[name]

            if is_full_scan:
                eff_regions = self._get_effective_regions(name)
                if eff_regions:
                    continue

            s_limit = schwellwert_override if schwellwert_override is not None else tpl_data["match_schwellwert"]
            gd      = self._get_gpu_template(name, s_eff)
            t_zm, t_norm, N = gd["t_zm"], gd["t_norm"], gd["N"]
            th, tw = t_zm.shape[2:]
            if tw > tw_t or th > th_t: continue

            res = F.conv2d(img_tensor, t_zm, padding=0)
            if gd["is_masked"]:
                m       = gd["m"]
                I_sum   = F.conv2d(img_tensor, m, padding=0)
                I_sq_sum = F.conv2d(img_tensor.pow(2), m, padding=0)
                I_var   = I_sq_sum - (I_sum.pow(2) / N)
            else:
                I_sum   = F.avg_pool2d(img_sum_ch,    kernel_size=(th, tw), stride=1, divisor_override=1)
                I_sq_sum = F.avg_pool2d(img_sq_sum_ch, kernel_size=(th, tw), stride=1, divisor_override=1)
                I_var   = I_sq_sum - (I_sum.pow(2) / N)

            I_norm = torch.sqrt(torch.clamp(I_var, min=1e-5))
            scores = res.sum(dim=1, keepdim=True) / (I_norm * t_norm + 1e-6)
            mask   = (scores >= s_limit)
            if mask.any():
                if scores.size(2) > 1 and scores.size(3) > 1:
                    mask = mask & (scores == F.max_pool2d(scores, kernel_size=3, stride=1, padding=1))
                pts = torch.nonzero(mask.view(-1)).squeeze()
                if pts.numel() > 0:
                    if pts.dim() == 0: pts = pts.unsqueeze(0)
                    y_c = (pts // scores.size(3)).cpu().numpy()
                    x_c = (pts %  scores.size(3)).cpu().numpy()
                    s_v = np.atleast_1d(scores.view(-1)[pts].cpu().numpy())
                    for i in range(len(y_c)):
                        results.append([name, (x_c[i]+ox)/s_eff, (y_c[i]+oy)/s_eff, tw/s_eff, th/s_eff, float(s_v[i])])
        return results

    def _nms(self, matches):
        if not matches: return []
        matches.sort(key=lambda x: x[5], reverse=True)
        ergebnis = []
        for m in matches:
            cx, cy  = m[1] + m[3]/2, m[2] + m[4]/2
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
        gd   = self._get_gpu_template(name, 1.0)
        t_zm = gd["t_zm"].squeeze(0).cpu()
        std  = torch.std(t_zm)
        t_vis = torch.clamp((t_zm / (std * 6.0 + 1e-5)) + 0.5, 0, 1)
        img_np = (t_vis.numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
        if gd["is_masked"]:
            maske_np = (gd["m"].squeeze(0)[0].cpu().numpy() * 255).astype(np.uint8)
            r, g, b  = cv2.split(img_np)
            return Image.merge("RGBA", [Image.fromarray(c) for c in [r, g, b, maske_np]])
        return Image.fromarray(img_np, "RGB")
