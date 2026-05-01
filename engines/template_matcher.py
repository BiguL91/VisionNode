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
        self._batch_cache: dict  = {} # Cache für fixierte Batch-Tensoren

    def cache_leeren(self):
        self._gpu_cache.clear()
        self._batch_cache.clear()

    # ── State/Conditions-Helfer ───────────────────────────────────────────────

    @staticmethod
    def _condition_states_erfuellt(conditions, game_states, ignore_states=None):
        if not conditions or game_states is None: return True
        def _wert_pruefen(k, v):
            if k == "[KEIN ANDERER ZUSTAND]":
                for s_name, s_val in game_states.items():
                    if s_val is True:
                        if ignore_states and s_name in ignore_states: continue
                        return not v
                return v
            return game_states.get(k) == v
        if isinstance(conditions, dict):
            return all(_wert_pruefen(k, v) for k, v in conditions.items())
        if not isinstance(conditions, list) or not conditions: return True
        first = conditions[0]
        if isinstance(first, dict) and ("states" in first or "connector" in first):
            result = None
            for group in conditions:
                connector, states = group.get("connector"), group.get("states", {})
                group_ok = all(_wert_pruefen(k, v) for k, v in states.items())
                if result is None or connector is None or connector == "OR":
                    result = group_ok if result is None else (result or group_ok)
                else: result = result and group_ok
            return bool(result)
        for group in conditions:
            if isinstance(group, dict) and all(_wert_pruefen(k, v) for k, v in group.items()): return True
        return False

    def _get_hierarchy_set_states(self, name_oder_pfad):
        sets = set()
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad: s = self.settings.get(name_oder_pfad.split("/")[-1], {})
        if s:
            sets.update(s.get("set_states", {}).keys())
            if "__" in name_oder_pfad: sets.update(self.settings.get(name_oder_pfad.split("__")[0], {}).get("set_states", {}).keys())
            current_path, besucht = s.get("gruppe", ""), {name_oder_pfad}
            while current_path:
                teile = current_path.split("/"); leaf = teile[-1]
                if leaf in besucht: break
                besucht.add(leaf)
                ps = self.settings.get(leaf, {})
                if isinstance(ps, dict):
                    sets.update(ps.get("set_states", {}).keys())
                    current_path = "/".join(teile[:-1]) if len(teile) > 1 else ps.get("gruppe", "")
                else: break
        return list(sets)

    def _eltern_conditions_pruefen(self, pfad, game_states):
        if not pfad: return True
        current_path, besucht = pfad, set()
        while current_path:
            teile = current_path.split("/"); leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                conds = eintrag.get("condition_states", [])
                if conds:
                    my_sets = self._get_hierarchy_set_states(current_path)
                    return self._condition_states_erfuellt(conds, game_states, ignore_states=my_sets)
                current_path = "/".join(teile[:-1]) if len(teile) > 1 else eintrag.get("gruppe", "")
            else: break
        return True

    def _get_effective_regions(self, name):
        s = self.settings.get(name, {})
        if isinstance(s, dict) and s.get("scan_regions"): return s["scan_regions"]
        current_path, besucht = s.get("gruppe", "") if isinstance(s, dict) else "", {name}
        while current_path:
            teile = current_path.split("/"); leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                if eintrag.get("scan_regions"): return eintrag["scan_regions"]
                current_path = "/".join(teile[:-1]) if len(teile) > 1 else eintrag.get("gruppe", "")
            else: break
        return []

    def _is_search_only_recursive(self, name_oder_pfad):
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad: s = self.settings.get(name_oder_pfad.split("/")[-1], {})
        if s and s.get("search_only"): return True
        current_path, besucht = s.get("gruppe", "") if isinstance(s, dict) else "", {name_oder_pfad}
        while current_path:
            teile = current_path.split("/"); leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            ps = self.settings.get(leaf, {})
            if isinstance(ps, dict) and ps.get("search_only"): return True
            current_path = "/".join(teile[:-1]) if (isinstance(ps, dict) and len(teile) > 1) else ps.get("gruppe", "") if isinstance(ps, dict) else ""
        return False

    def _is_smart_recursive(self, name_oder_pfad):
        basis_name = name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad
        s = self.settings.get(basis_name, {})
        if not s and "/" in name_oder_pfad: s = self.settings.get(name_oder_pfad.split("/")[-1], {})
        if s and s.get("is_smart"): return True
        current_path, besucht = s.get("gruppe", "") if isinstance(s, dict) else "", {name_oder_pfad}
        while current_path:
            teile = current_path.split("/"); leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            ps = self.settings.get(leaf, {})
            if isinstance(ps, dict) and ps.get("is_smart"): return True
            current_path = "/".join(teile[:-1]) if (isinstance(ps, dict) and len(teile) > 1) else ps.get("gruppe", "") if isinstance(ps, dict) else ""
        return False

    def get_hierarchy_names(self, name_oder_pfad):
        namen = [name_oder_pfad.split("__")[0] if "__" in name_oder_pfad else name_oder_pfad]
        s = self.settings.get(namen[0], {})
        if not s and "/" in name_oder_pfad:
            leaf = name_oder_pfad.split("/")[-1]
            s = self.settings.get(leaf, {}); 
            if leaf != namen[0]: namen.append(leaf)
        if s:
            current_path, besucht = s.get("gruppe", ""), {name_oder_pfad}
            while current_path:
                teile = current_path.split("/"); leaf = teile[-1]
                if leaf in besucht: break
                besucht.add(leaf); namen.append(leaf)
                ps = self.settings.get(leaf, {})
                current_path = "/".join(teile[:-1]) if (isinstance(ps, dict) and len(teile) > 1) else ps.get("gruppe", "") if isinstance(ps, dict) else ""
        return list(dict.fromkeys(namen))

    # ── GPU-Cache ─────────────────────────────────────────────────────────────

    def _get_gpu_template(self, name, s_eff):
        key = (name, s_eff)
        if key in self._gpu_cache: return self._gpu_cache[key]
        tpl = self.templates[name]
        t_orig, m_orig = tpl["tensor"], tpl["maske"]
        th, tw = (int(t_orig.shape[2]*s_eff), int(t_orig.shape[3]*s_eff)) if s_eff != 1.0 else t_orig.shape[2:]
        t_s = F.interpolate(t_orig, size=(max(1, th), max(1, tw)), mode='bilinear', align_corners=False) if s_eff != 1.0 else t_orig
        m_s = F.interpolate(m_orig, size=(max(1, th), max(1, tw)), mode='nearest') if m_orig is not None and s_eff != 1.0 else m_orig
        if m_s is not None:
            m_3 = m_s.expand(1, 3, t_s.shape[2], t_s.shape[3]); N = m_3.sum() + 1e-5
            t_mean = (t_s * m_3).sum() / N; t_zm = (t_s - t_mean) * m_3
            self._gpu_cache[key] = {"t_zm": t_zm, "m": m_3, "t_norm": t_zm.pow(2).sum().sqrt(), "N": N, "is_masked": True}
        else:
            N = t_s.numel() / 3; t_mean = t_s.mean(); t_zm = t_s - t_mean
            self._gpu_cache[key] = {"t_zm": t_zm, "t_norm": t_zm.pow(2).sum().sqrt(), "N": N, "is_masked": False}
        return self._gpu_cache[key]

    # ── Matching ──────────────────────────────────────────────────────────────

    @torch.no_grad()
    def matches_suchen_np(self, screenshot_bgr, game_states=None, force_include=None):
        if not self.templates: return [], []
        t_uint8 = torch.from_numpy(screenshot_bgr).pin_memory().to(self.device, non_blocking=True)
        img_gpu = t_uint8.permute(2, 0, 1).float().div(255.0).unsqueeze(0)
        ih, iw  = screenshot_bgr.shape[:2]; s_base = self.matching_skalierung; ref = self.referenz_groesse
        if ref: s_eff, th_t, tw_t = s_base, max(1, int(ref[1]*s_base)), max(1, int(ref[0]*s_base)); nx, ny = iw/ref[0], ih/ref[1]
        else: s_eff, th_t, tw_t = s_base, max(1, int(ih*s_base)), max(1, int(iw*s_base)); nx = ny = 1.0
        img_m = F.interpolate(img_gpu, size=(th_t, tw_t), mode='bilinear', align_corners=False)
        img_sum, img_sq = img_m.sum(dim=1, keepdim=True), img_m.pow(2).sum(dim=1, keepdim=True)

        fi_set = set()
        if force_include:
            for n in ([force_include] if isinstance(force_include, (str, type(None))) else force_include or []):
                if n and isinstance(n, str):
                    b = n.split("__")[0]; fi_set.add(b)
                    g = self.settings.get(b, {}).get("gruppe", ""); [fi_set.add(gt) for gt in g.split("/") if gt]

        master_nach_groesse = defaultdict(list)
        for name, t in self.templates.items():
            tpl_s = self.settings.get(name, {})
            conds = tpl_s.get("condition_states", {}) or self.settings.get(name.split("__")[0], {}).get("condition_states", {})
            basis = name.split("__")[0]; erz = basis in fi_set or any(gt in fi_set for gt in (t.get("gruppe") or "").split("/") if gt)
            if not erz and self._is_search_only_recursive(name): continue
            if game_states and not erz:
                if conds and not self._condition_states_erfuellt(conds, game_states, ignore_states=self._get_hierarchy_set_states(name)): continue
                if t["gruppe"] and not self._eltern_conditions_pruefen(t["gruppe"], game_states): continue
            
            g = t.get("gruppe"); is_child = False
            if g:
                for i in range(len(g.split("/"))):
                    p = "/".join(g.split("/")[:i+1])
                    if p in self.templates and p != name and not name.startswith(p + "__"): is_child = True; break
            if not is_child and not self._get_effective_regions(name):
                gd = self._get_gpu_template(name, s_eff); master_nach_groesse[gd["t_zm"].shape[2:]].append((name, gd))

        master_ergebnisse = []
        for sz, tpls in master_nach_groesse.items(): master_ergebnisse.extend(self._batch_match_fixed_size(img_m, img_sum, img_sq, tpls, s_eff))

        for name, t in self.templates.items():
            regs = self._get_effective_regions(name)
            if regs:
                basis = name.split("__")[0]
                if not (basis in fi_set or self._is_search_only_recursive(name) or (game_states and self._condition_states_erfuellt(self.settings.get(name, {}).get("condition_states", []), game_states))): continue
                gd = self._get_gpu_template(name, s_eff); gh, gw = gd["t_zm"].shape[2:]
                for r in regs:
                    sx0, sy0, sx1, sy1 = int(r[0]*s_eff), int(r[1]*s_eff), int(r[2]*s_eff), int(r[3]*s_eff)
                    if (sx1-sx0) >= gw and (sy1-sy0) >= gh:
                        master_ergebnisse.extend(self._batch_match_fixed_size(img_m[:,:,sy0:sy1,sx0:sx1], img_sum[:,:,sy0:sy1,sx0:sx1], img_sq[:,:,sy0:sy1,sx0:sx1], [(name, gd)], s_eff, offset=(sx0, sy0)))

        master_gefiltert, results, grp_hits, kids_map = self._nms(master_ergebnisse), [], defaultdict(list), defaultdict(list)
        for name, t in self.templates.items():
            g = t.get("gruppe")
            if g:
                for i in range(len(g.split("/"))):
                    p = "/".join(g.split("/")[:i+1])
                    if p in self.templates and p != name and not name.startswith(p + "__"): kids_map[p].append(name); break

        for m in master_gefiltert:
            k = m[0].split("__")[0] if (m[0].split("__")[0] in kids_map or m[0] in kids_map) else m[0]
            if k in kids_map: grp_hits[k].append(m)
            else: results.append(m)

        for m_name, hits in grp_hits.items():
            k_names = kids_map[m_name]
            for h in hits:
                results.append(h); rx, ry, rw, rh = h[1], h[2], h[3], h[4]; pad = 4
                x0, y0, x1, y1 = max(0, int(rx*s_eff)-pad), max(0, int(ry*s_eff)-pad), min(tw_t, int((rx+rw)*s_eff)+pad), min(th_t, int((ry+rh)*s_eff)+pad)
                if x1 > x0 and y1 > y0:
                    cr, cs, cq = img_m[:,:,y0:y1,x0:x1], img_sum[:,:,y0:y1,x0:x1], img_sq[:,:,y0:y1,x0:x1]
                    k_tpls = defaultdict(list)
                    for kn in k_names: kgd = self._get_gpu_template(kn, s_eff); k_tpls[kgd["t_zm"].shape[2:]].append((kn, kgd))
                    for ksz, kl in k_tpls.items(): results.extend(self._batch_match_fixed_size(cr, cs, cq, kl, s_eff, 0.7, (x0,y0)))

        final = []
        for n, rx, ry, rw, rh, sc in self._nms(results):
            final.append((n.split("__")[0], int(rx*nx), int(ry*ny), int(rw*nx), int(rh*ny), sc, n, self.get_hierarchy_names(n)))
        return final, sorted(list(set([m[0] for m in final])))

    def _batch_match_fixed_size(self, img, img_s, img_sq, tpls, s_eff, threshold=None, offset=(0,0)):
        if not tpls: return []
        num, (gh, gw) = len(tpls), tpls[0][1]["t_zm"].shape[2:]
        
        # Fast-Path für Einzel-Templates (z.B. ROIs) ohne Maske
        if num == 1 and not tpls[0][1]["is_masked"]:
            res = F.conv2d(img, tpls[0][1]["t_zm"], padding=0)
            i_s = F.avg_pool2d(img_s, (gh, gw), stride=1, divisor_override=1)
            i_q = F.avg_pool2d(img_sq, (gh, gw), stride=1, divisor_override=1)
            i_var = i_q - (i_s.pow(2) / tpls[0][1]["N"])
            scores = res / (torch.sqrt(torch.clamp(i_var, min=1e-5)) * tpls[0][1]["t_norm"] + 1e-6)
        else:
            # Batch-Cache nutzen um Allokations-Overhead zu vermeiden
            b_key = tuple([t[0] for t in tpls])
            if b_key not in self._batch_cache:
                w = torch.stack([t[1]["t_zm"].squeeze(0) for t in tpls])
                m = torch.stack([(t[1]["m"].squeeze(0)[0:1] if t[1]["is_masked"] else torch.ones((1, gh, gw), device=self.device)) for t in tpls])
                tn = torch.tensor([t[1]["t_norm"] for t in tpls], device=self.device).view(num, 1, 1)
                npix = torch.tensor([t[1]["N"] for t in tpls], device=self.device).view(num, 1, 1)
                self._batch_cache[b_key] = (w, m, tn, npix)
            w, m, tn, npix = self._batch_cache[b_key]
            res = F.conv2d(img, w, padding=0).squeeze(0)
            i_s, i_q = F.conv2d(img_s, m, padding=0).squeeze(0), F.conv2d(img_sq, m, padding=0).squeeze(0)
            i_var = i_q - (i_s.pow(2) / npix)
            scores = res / (torch.sqrt(torch.clamp(i_var, min=1e-5)) * tn + 1e-6)

        results = []
        for i in range(num):
            s_map = scores[i] if scores.dim() > 2 else scores.squeeze(0)
            lim = threshold or self.settings[tpls[i][0]]["match_schwellwert"]
            mask = s_map >= lim
            if mask.any():
                if s_map.size(0) > 1 and s_map.size(1) > 1:
                    mp = F.max_pool2d(s_map.unsqueeze(0).unsqueeze(0), 3, 1, 1).squeeze()
                    if mp.dim() == 0: mp = mp.unsqueeze(0)
                    mask &= (s_map == mp)
                pts = torch.nonzero(mask)
                if pts.numel() > 0:
                    y_c, x_c, s_v = pts[:,0].cpu().numpy(), pts[:,1].cpu().numpy(), s_map[mask].cpu().numpy()
                    for j in range(len(y_c)): results.append([tpls[i][0], (x_c[j]+offset[0])/s_eff, (y_c[j]+offset[1])/s_eff, gw/s_eff, gh/s_eff, float(s_v[j])])
        return results

    def _nms(self, matches):
        if not matches: return []
        matches.sort(key=lambda x: x[5], reverse=True); ergebnis = []
        for m in matches:
            cx, cy, doppelt = m[1]+m[3]/2, m[2]+m[4]/2, False
            for a in ergebnis:
                if a[0] == m[0]:
                    if abs(cx-(a[1]+a[3]/2)) < m[3]*0.5 and abs(cy-(a[2]+a[4]/2)) < m[4]*0.5: doppelt = True; break
            if not doppelt: ergebnis.append(m)
        return ergebnis

    def get_mathematik_vorschau(self, name):
        if name not in self.templates: return None
        gd = self._get_gpu_template(name, 1.0); t_zm = gd["t_zm"].squeeze(0).cpu()
        t_vis = torch.clamp((t_zm / (torch.std(t_zm) * 6.0 + 1e-5)) + 0.5, 0, 1)
        img_np = (t_vis.numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
        if gd["is_masked"]:
            maske_np = (gd["m"].squeeze(0)[0].cpu().numpy() * 255).astype(np.uint8)
            r, g, b = cv2.split(img_np); return Image.merge("RGBA", [Image.fromarray(c) for c in [r, g, b, maske_np]])
        return Image.fromarray(img_np, "RGB")
