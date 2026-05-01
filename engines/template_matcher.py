"""
Template-Matcher — GPU-Matching-Logik.
Kein Datei-I/O. Nutzt templates- und settings-Referenzen vom TemplateEngine.
"""
import numpy as np
import torch
import torch.nn.functional as F
from collections import defaultdict
from PIL import Image
import cv2


class TemplateMatcher:

    def __init__(self, templates: dict, settings: dict, device,
                 matching_skalierung: float, referenz_groesse,
                 log_func=None, log_enabled_func=None):
        self.templates           = templates
        self.settings            = settings
        self.device              = device
        self.matching_skalierung = matching_skalierung
        self.referenz_groesse    = referenz_groesse
        self.log_func            = log_func
        self.log_enabled_func    = log_enabled_func
        self._gpu_cache: dict    = {}

    def cache_leeren(self):
        self._gpu_cache.clear()

    # ── State/Conditions-Helfer ───────────────────────────────────────────────

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
                    current_path = "/".join(teile[:-1]) if len(teile) > 1 else ps.get("gruppe", "")
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
                    my_sets = self._get_hierarchy_set_states(current_path)
                    if not self._condition_states_erfuellt(conds, game_states, ignore_states=my_sets):
                        return False
                    return True
                current_path = "/".join(teile[:-1]) if len(teile) > 1 else eintrag.get("gruppe", "")
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
                current_path = "/".join(teile[:-1]) if len(teile) > 1 else eintrag.get("gruppe", "")
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
                current_path = "/".join(teile[:-1]) if len(teile) > 1 else ps.get("gruppe", "")
            else:
                break
        return False

    def _is_smart_recursive(self, name_oder_pfad):
        """Prüft ob ein Element oder seine Eltern-Kette 'is_smart' ist."""
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad:
            leaf = name_oder_pfad.split("/")[-1]
            s    = self.settings.get(leaf, {})

        if s and s.get("is_smart"):
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
                if ps.get("is_smart"):
                    return True
                current_path = "/".join(teile[:-1]) if len(teile) > 1 else ps.get("gruppe", "")
            else:
                break
        return False

    def get_hierarchy_names(self, name_oder_pfad):
        """Gibt eine Liste von Namen zurück (Self + Eltern)."""
        namen = []
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        namen.append(basis_name)

        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad:
            leaf = name_oder_pfad.split("/")[-1]
            s    = self.settings.get(leaf, {})
            if leaf != basis_name:
                namen.append(leaf)

        if s:
            current_path = s.get("gruppe", "")
            besucht = {name_oder_pfad}
            while current_path:
                teile = current_path.split("/")
                leaf  = teile[-1]
                if leaf in besucht: break
                besucht.add(leaf)
                namen.append(leaf)
                ps = self.settings.get(leaf, {})
                if isinstance(ps, dict):
                    current_path = "/".join(teile[:-1]) if len(teile) > 1 else ps.get("gruppe", "")
                else:
                    break
        return list(dict.fromkeys(namen)) # Duplikate vermeiden

    # ── GPU-Cache ─────────────────────────────────────────────────────────────

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
            m_3    = m_s.expand(1, 3, t_s.shape[2], t_s.shape[3])
            N      = m_3.sum() + 1e-5
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

    # ── Matching ──────────────────────────────────────────────────────────────

    @torch.no_grad()
    def matches_suchen_np(self, screenshot_bgr, game_states=None, force_include=None):
        if not self.templates: return [], []
        
        # 1. Rohes uint8-Array zur GPU schieben (kleinste Datenmenge)
        # screenshot_bgr ist (H, W, 3)
        t_uint8 = torch.from_numpy(screenshot_bgr).pin_memory().to(self.device, non_blocking=True)
        
        # 2. Konvertierung und Permutation ERST AUF DER GPU (blitzschnell)
        # (H, W, 3) uint8 -> (1, 3, H, W) float32 [0..1]
        img_gpu = t_uint8.permute(2, 0, 1).float().div(255.0).unsqueeze(0)
        
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
                    g_val = self.settings.get(basis, {}).get("gruppe", "")
                    if g_val:
                        for g_teil in g_val.split("/"):
                            if g_teil: fi_set.add(g_teil)

        master_namen       = []
        kinder_nach_gruppe = defaultdict(list)
        for name, t in self.templates.items():
            tpl_settings = self.settings.get(name, {})
            conditions   = tpl_settings.get("condition_states", {})
            if not conditions and "__" in name:
                conditions = self.settings.get(name.split("__")[0], {}).get("condition_states", {})

            basis_name    = name.split("__")[0]
            ist_erzwungen = basis_name in fi_set

            if not ist_erzwungen and t.get("gruppe"):
                for teil in t["gruppe"].split("/"):
                    if teil in fi_set:
                        ist_erzwungen = True
                        break

            if not ist_erzwungen and self._is_search_only_recursive(name):
                continue

            if game_states is not None and not ist_erzwungen:
                my_sets = self._get_hierarchy_set_states(name)
                if conditions and not self._condition_states_erfuellt(conditions, game_states, ignore_states=my_sets):
                    continue
                if t["gruppe"] and not self._eltern_conditions_pruefen(t["gruppe"], game_states):
                    continue

            parent_template = None
            g = t["gruppe"]
            if g:
                for i, _ in enumerate(g.split("/")):
                    pfad = "/".join(g.split("/")[:i+1])
                    if pfad in self.templates:
                        parent_template = None if (pfad == name or name.startswith(pfad + "__")) else pfad
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
            name       = m[0]
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
                # Master IMMER hinzufügen
                final_results.append(m_treffer)
                
                m_rx, m_ry, m_rw, m_rh = m_treffer[1], m_treffer[2], m_treffer[3], m_treffer[4]
                pad = 4
                x0  = max(0, int(m_rx*s_eff)-pad)
                y0  = max(0, int(m_ry*s_eff)-pad)
                x1  = min(tw_t, int((m_rx+m_rw)*s_eff)+pad)
                y1  = min(th_t, int((m_ry+m_rh)*s_eff)+pad)
                if x1 > x0 and y1 > y0:
                    crop  = img_m[:, :, y0:y1, x0:x1]
                    # Suche nach Kindern innerhalb des Master-Ausschnitts
                    k_res = self._batch_match(crop, kinder_namen, s_eff, schwellwert_override=0.7, is_full_scan=False)
                    
                    if k_res:
                        # Wir nehmen alle gefundenen Kinder (NMS filtert sie später global)
                        for best_k in k_res:
                            final_results.append([
                                best_k[0],
                                (x0/s_eff) + best_k[1],
                                (y0/s_eff) + best_k[2],
                                best_k[3], best_k[4], best_k[5],
                            ])

        output = []
        for name, rx_ref, ry_ref, rw_ref, rh_ref, score in final_results:
            d_name = name.split("__")[0]
            hierarchy = self.get_hierarchy_names(name)
            output.append((
                d_name, 
                int(rx_ref*norm_sx), int(ry_ref*norm_sy), 
                int(rw_ref*norm_sx), int(rh_ref*norm_sy), 
                score, 
                name,
                hierarchy
            ))
        return self._nms(output), master_namen

    def _batch_match(self, img_tensor, template_namen, s_eff, schwellwert_override=None, offset=(0,0), is_full_scan=False):
        results = []
        if img_tensor.size(2) == 0 or img_tensor.size(3) == 0: return []
        th_t, tw_t    = img_tensor.shape[2:]
        ox, oy        = offset
        img_sum_ch    = img_tensor.sum(dim=1, keepdim=True)
        img_sq_sum_ch = img_tensor.pow(2).sum(dim=1, keepdim=True)

        for name in template_namen:
            tpl_data = self.templates[name]
            if is_full_scan and self._get_effective_regions(name):
                continue

            s_limit     = schwellwert_override if schwellwert_override is not None else tpl_data["match_schwellwert"]
            gd          = self._get_gpu_template(name, s_eff)
            t_zm, t_norm, N = gd["t_zm"], gd["t_norm"], gd["N"]
            th, tw = t_zm.shape[2:]
            if tw > tw_t or th > th_t: continue

            res = F.conv2d(img_tensor, t_zm, padding=0)
            if gd["is_masked"]:
                m        = gd["m"]
                I_sum    = F.conv2d(img_tensor,          m, padding=0)
                I_sq_sum = F.conv2d(img_tensor.pow(2),   m, padding=0)
            else:
                I_sum    = F.avg_pool2d(img_sum_ch,    kernel_size=(th, tw), stride=1, divisor_override=1)
                I_sq_sum = F.avg_pool2d(img_sq_sum_ch, kernel_size=(th, tw), stride=1, divisor_override=1)
            I_var  = I_sq_sum - (I_sum.pow(2) / N)
            I_norm = torch.sqrt(torch.clamp(I_var, min=1e-5))
            scores = res.sum(dim=1, keepdim=True) / (I_norm * t_norm + 1e-6)
            mask   = scores >= s_limit
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

    # ── Visualisierung ────────────────────────────────────────────────────────

    def get_mathematik_vorschau(self, name):
        if name not in self.templates: return None
        gd    = self._get_gpu_template(name, 1.0)
        t_zm  = gd["t_zm"].squeeze(0).cpu()
        std   = torch.std(t_zm)
        t_vis = torch.clamp((t_zm / (std * 6.0 + 1e-5)) + 0.5, 0, 1)
        img_np = (t_vis.numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
        if gd["is_masked"]:
            maske_np = (gd["m"].squeeze(0)[0].cpu().numpy() * 255).astype(np.uint8)
            r, g, b  = cv2.split(img_np)
            return Image.merge("RGBA", [Image.fromarray(c) for c in [r, g, b, maske_np]])
        return Image.fromarray(img_np, "RGB")
