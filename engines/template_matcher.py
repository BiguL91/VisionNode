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
        self._batch_cache: dict  = {}
        self._hierarchy_cache: dict = {}
        self._logic_cache: dict     = {}

    def _log(self, message):
        if self.log_func:
            if self.log_enabled_func and not self.log_enabled_func(): return
            self.log_func(message)

    def cache_leeren(self):
        self._gpu_cache.clear()
        self._batch_cache.clear()
        self._hierarchy_cache.clear()
        self._logic_cache.clear()

    # ── State/Conditions-Helfer ───────────────────────────────────────────────

    def _get_hierarchy_names(self, name_oder_pfad):
        if name_oder_pfad in self._hierarchy_cache: return self._hierarchy_cache[name_oder_pfad]
        namen = [name_oder_pfad.split("__")[0]]
        s = self.settings.get(namen[0], {})
        if not s and "/" in name_oder_pfad: 
            leaf = name_oder_pfad.split("/")[-1]
            s = self.settings.get(leaf, {}); 
            if leaf != namen[0]: namen.append(leaf)
        if s:
            curr, besucht = s.get("gruppe", ""), {name_oder_pfad}
            while curr:
                leaf = curr.split("/")[-1]
                if leaf in besucht: break
                besucht.add(leaf); namen.append(leaf)
                e = self.settings.get(leaf, {})
                curr = "/".join(curr.split("/")[:-1]) if (isinstance(e, dict) and len(curr.split("/")) > 1) else e.get("gruppe", "") if isinstance(e, dict) else ""
        res = list(dict.fromkeys(namen))
        self._hierarchy_cache[name_oder_pfad] = res
        return res

    def _is_search_only_recursive(self, name_oder_pfad):
        key = ("so", name_oder_pfad)
        if key in self._logic_cache: return self._logic_cache[key]
        basis = name_oder_pfad.split("__")[0]
        s = self.settings.get(basis, {}) or self.settings.get(name_oder_pfad.split("/")[-1], {})
        res = False
        if isinstance(s, dict) and s.get("search_only"): res = True
        else:
            curr, besucht = s.get("gruppe", "") if isinstance(s, dict) else "", {name_oder_pfad}
            while curr:
                leaf = curr.split("/")[-1]
                if leaf in besucht: break
                besucht.add(leaf); e = self.settings.get(leaf, {})
                if isinstance(e, dict):
                    if e.get("search_only"): res = True; break
                    curr = "/".join(curr.split("/")[:-1]) if len(curr.split("/")) > 1 else e.get("gruppe", "")
                else: break
        self._logic_cache[key] = res
        return res

    def _is_smart_recursive(self, name_oder_pfad):
        key = ("smart", name_oder_pfad)
        if key in self._logic_cache: return self._logic_cache[key]
        basis = name_oder_pfad.split("__")[0]
        s = self.settings.get(basis, {}) or self.settings.get(name_oder_pfad.split("/")[-1], {})
        res = False
        if isinstance(s, dict) and s.get("is_smart"): res = True
        else:
            curr, besucht = s.get("gruppe", "") if isinstance(s, dict) else "", {name_oder_pfad}
            while curr:
                leaf = curr.split("/")[-1]
                if leaf in besucht: break
                besucht.add(leaf); e = self.settings.get(leaf, {})
                if isinstance(e, dict):
                    if e.get("is_smart"): res = True; break
                    curr = "/".join(curr.split("/")[:-1]) if len(curr.split("/")) > 1 else e.get("gruppe", "")
                else: break
        self._logic_cache[key] = res
        return res
    
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
        basis = name_oder_pfad.split("__")[0]
        s = self.settings.get(basis, {})
        if not s and "/" in name_oder_pfad: s = self.settings.get(name_oder_pfad.split("/")[-1], {})
        if s:
            sets.update(s.get("set_states", {}).keys())
            curr, besucht = s.get("gruppe", ""), {name_oder_pfad}
            while curr:
                leaf = curr.split("/")[-1]
                if leaf in besucht: break
                besucht.add(leaf); ps = self.settings.get(leaf, {})
                if isinstance(ps, dict):
                    sets.update(ps.get("set_states", {}).keys())
                    curr = "/".join(curr.split("/")[:-1]) if len(curr.split("/")) > 1 else ps.get("gruppe", "")
                else: break
        return list(sets)

    def _eltern_conditions_pruefen(self, pfad, game_states):
        if not pfad or game_states is None: return True
        curr, besucht = pfad, set()
        while curr:
            teile = curr.split("/"); leaf = teile[-1]
            if leaf in besucht: break
            besucht.add(leaf)
            eintrag = self.settings.get(leaf, {})
            if isinstance(eintrag, dict):
                conds = eintrag.get("condition_states", [])
                if conds:
                    ign = self._get_hierarchy_set_states(curr)
                    if not self._condition_states_erfuellt(conds, game_states, ignore_states=ign):
                        return False
                if len(teile) > 1: curr = "/".join(teile[:-1])
                else: 
                    g = eintrag.get("gruppe", "")
                    curr = g if g and g != leaf else ""
            else: break
        return True

    def _get_effective_regions(self, name):
        basis = name.split("__")[0]
        s = self.settings.get(name, {})
        if not s or not s.get("scan_regions"):
            s = self.settings.get(basis, {})
            
        if isinstance(s, dict) and s.get("scan_regions"): 
            return s["scan_regions"]
            
        curr, besucht = s.get("gruppe", "") if isinstance(s, dict) else "", {name, basis}
        while curr:
            leaf = curr.split("/")[-1]
            if leaf in besucht: break
            besucht.add(leaf); e = self.settings.get(leaf, {})
            if isinstance(e, dict):
                if e.get("scan_regions"): return e["scan_regions"]
                curr = "/".join(curr.split("/")[:-1]) if len(curr.split("/")) > 1 else e.get("gruppe", "")
            else: break
        return []

    # ── GPU-Cache ─────────────────────────────────────────────────────────────

    def _get_gpu_template(self, name, s_eff):
        key = (name, s_eff)
        if key in self._gpu_cache: return self._gpu_cache[key]
        tpl = self.templates[name]
        t_orig, m_orig = tpl["tensor"], tpl["maske"]
        th, tw = (int(t_orig.shape[2]*s_eff), int(t_orig.shape[3]*s_eff))
        t_s = F.interpolate(t_orig, size=(max(1, th), max(1, tw)), mode='bilinear', align_corners=False) if s_eff != 1.0 else t_orig
        m_s = F.interpolate(m_orig, size=(max(1, th), max(1, tw)), mode='nearest') if m_orig is not None and s_eff != 1.0 else m_orig
        
        basis = name.split("__")[0]
        s = self.settings.get(name, {}) or self.settings.get(basis, {})
        thresh = s.get("match_schwellwert", 0.8)
        t_thresh = torch.tensor([thresh], device=self.device, dtype=torch.float32).view(1, 1, 1, 1)

        if m_s is not None:
            m_3 = m_s.expand(1, 3, t_s.shape[2], t_s.shape[3]); N = m_3.sum() + 1e-5
            t_zm = (t_s - ((t_s * m_3).sum() / N)) * m_3
            self._gpu_cache[key] = {
                "t_zm": t_zm, "m": m_3, 
                "t_norm": t_zm.pow(2).sum().sqrt().view(1, 1, 1, 1), 
                "N": torch.tensor([N], device=self.device, dtype=torch.float32).view(1, 1, 1, 1), 
                "threshold": t_thresh,
                "is_masked": True
            }
        else:
            N = float(t_s.numel()); t_zm = t_s - t_s.mean()
            self._gpu_cache[key] = {
                "t_zm": t_zm, 
                "t_norm": t_zm.pow(2).sum().sqrt().view(1, 1, 1, 1), 
                "N": torch.tensor([N], device=self.device, dtype=torch.float32).view(1, 1, 1, 1), 
                "threshold": t_thresh,
                "is_masked": False
            }
        return self._gpu_cache[key]

    # ── Matching ──────────────────────────────────────────────────────────────

    @torch.no_grad()
    def matches_suchen_np(self, screenshot_bgr, game_states=None, force_include=None):
        if not self.templates: return [], [], [], {}
        t_uint8 = torch.from_numpy(screenshot_bgr).to(self.device, non_blocking=True)
        img_gpu = t_uint8.permute(2, 0, 1).float().div(255.0).unsqueeze(0)
        ih, iw  = screenshot_bgr.shape[:2]; s_base = self.matching_skalierung; ref = self.referenz_groesse
        if ref: s_eff, th_t, tw_t = s_base, max(1, int(ref[1]*s_base)), max(1, int(ref[0]*s_base)); nx, ny = iw/ref[0], ih/ref[1]
        else: s_eff, th_t, tw_t = s_base, max(1, int(ih*s_base)), max(1, int(iw*s_base)); nx = ny = 1.0
        img_m = F.interpolate(img_gpu, size=(th_t, tw_t), mode='bilinear', align_corners=False)
        img_sum, img_sq = img_m.sum(dim=1, keepdim=True), img_m.pow(2).sum(dim=1, keepdim=True)

        scanned_regions, fi_set = [], set()
        if force_include:
            for n in ([force_include] if isinstance(force_include, (str, type(None))) else force_include or []):
                if n and isinstance(n, str):
                    fi_set.add(n.split("__")[0])
                    g = self.settings.get(n.split("__")[0], {}).get("gruppe", ""); [fi_set.add(gt) for gt in g.split("/") if gt]

        master_namen, kinder_nach_gruppe, templates_by_sz = [], defaultdict(list), defaultdict(list)
        for name, t in self.templates.items():
            basis = name.split("__")[0]
            erz = basis in fi_set or any(gt in fi_set for gt in (t.get("gruppe") or "").split("/") if gt)
            if not erz:
                if self._is_search_only_recursive(name): continue
                if game_states is not None:
                    tpl_s = self.settings.get(name, {}) or self.settings.get(basis, {})
                    c = tpl_s.get("condition_states")
                    if c and not self._condition_states_erfuellt(c, game_states, ignore_states=self._get_hierarchy_set_states(name)): continue
                    if t["gruppe"] and not self._eltern_conditions_pruefen(t["gruppe"], game_states): continue
            
            g, parent_tpl = t.get("gruppe"), None
            if g:
                teile = g.split("/")
                for i in range(len(teile)):
                    pfad = "/".join(teile[:i+1])
                    if pfad in self.templates and pfad != name and not name.startswith(pfad + "__"): parent_tpl = pfad; break
            
            if parent_tpl: kinder_nach_gruppe[parent_tpl].append(name)
            else:
                master_namen.append(name); gd = self._get_gpu_template(name, s_eff)
                if gd["t_zm"].shape[2] <= th_t and gd["t_zm"].shape[3] <= tw_t:
                    templates_by_sz[gd["t_zm"].shape[2:]].append((name, gd, self._get_effective_regions(name)))

        # 2. Master-Scan
        res_raw, search_stats = [], {}
        for t_sz, t_list in templates_by_sz.items():
            gh, gw = t_sz
            fs_tpls, roi_tasks = [], []
            for t_name, gd, regs in t_list:
                search_stats[t_name] = len(regs) if regs else 0
                if regs:
                    for r in regs:
                        sx0, sy0, sx1, sy1 = int(r[0]*s_eff), int(r[1]*s_eff), int(r[2]*s_eff), int(r[3]*s_eff)
                        if (sx1-sx0) < gw: sx1 = sx0 + gw
                        if (sy1-sy0) < gh: sy1 = sy0 + gh
                        if sx1 > tw_t: sx0 = max(0, sx0 - (sx1 - tw_t)); sx1 = tw_t
                        if sy1 > th_t: sy0 = max(0, sy0 - (sy1 - th_t)); sy1 = th_t
                        if (sx1-sx0) >= gw and (sy1-sy0) >= gh:
                            roi_tasks.append({"imgs": (img_m[:,:,sy0:sy1,sx0:sx1], img_sum[:,:,sy0:sy1,sx0:sx1], img_sq[:,:,sy0:sy1,sx0:sx1]), "name": t_name, "gd": gd, "offset": (sx0, sy0)})
                            scanned_regions.append([int(r[0]*nx), int(r[1]*ny), int(r[2]*nx), int(r[3]*ny)])
                else:
                    fs_tpls.append((t_name, gd))
                    scanned_regions.append([0, 0, iw, ih])

            if fs_tpls: res_raw.extend(self._batch_match_fixed_size(img_m, img_sum, img_sq, fs_tpls, s_eff))
            if roi_tasks:
                num_t = len(roi_tasks)
                max_h = max(t["imgs"][0].shape[2] for t in roi_tasks)
                max_w = max(t["imgs"][0].shape[3] for t in roi_tasks)
                
                b_imgs = torch.zeros((num_t, 3, max_h, max_w), device=self.device)
                b_s = torch.zeros((num_t, 1, max_h, max_w), device=self.device)
                b_q = torch.zeros((num_t, 1, max_h, max_w), device=self.device)
                tpl_l, off_l = [], []
                
                for i, task in enumerate(roi_tasks):
                    crop, crop_s, crop_q = task["imgs"]; ch, cw = crop.shape[2:]
                    b_imgs[i, :, :ch, :cw] = crop
                    b_s[i, :, :ch, :cw] = crop_s
                    b_q[i, :, :ch, :cw] = crop_q
                    tpl_l.append((task["name"], task["gd"])); off_l.append(task["offset"])       
                
                res_raw.extend(self._batch_match_fixed_size(b_imgs, b_s, b_q, tpl_l, s_eff, is_1to1=True, offsets=off_l))

        # 3. Unified Transfer & Kaskade
        res_cpu = res_raw # res_raw enthält bereits CPU-Floats durch Unified Transfer in _batch_match_fixed_size

        gefiltert, res_final = self._nms(res_cpu), []
        if not gefiltert: 
            return [], [], scanned_regions, search_stats
            
        k_tasks_by_sz = defaultdict(list)
        
        # Kinder-Daten vorab sammeln, um Python-Lookups in der Schleife zu minimieren
        all_k_names = set()
        for m in gefiltert:
            res_final.append(m); name = m[0]; m_basis = name.split("__")[0]
            kn = kinder_nach_gruppe.get(name) or kinder_nach_gruppe.get(m_basis)
            if kn: all_k_names.update(kn)
        
        k_data_map = {kn: self._get_gpu_template(kn, s_eff) for kn in all_k_names}
        
        for m in gefiltert:
            name = m[0]; m_basis = name.split("__")[0]
            k_names = kinder_nach_gruppe.get(name) or kinder_nach_gruppe.get(m_basis)        
            if not k_names: continue
            
            rx, ry, rw, rh = m[1], m[2], m[3], m[4]; pad = 4
            x0, y0, x1, y1 = max(0, int(rx*s_eff)-pad), max(0, int(ry*s_eff)-pad), min(tw_t, int((rx+rw)*s_eff)+pad), min(th_t, int((ry+rh)*s_eff)+pad)
            if x1 <= x0 or y1 <= y0: continue
            
            crop_info = (img_m[:,:,y0:y1,x0:x1], img_sum[:,:,y0:y1,x0:x1], img_sq[:,:,y0:y1,x0:x1])
            ch, cw = y1-y0, x1-x0
            
            for kn in k_names:
                kgd = k_data_map[kn]
                if kgd["t_zm"].shape[2] <= ch and kgd["t_zm"].shape[3] <= cw:      
                    k_tasks_by_sz[kgd["t_zm"].shape[2:]].append({"imgs": crop_info, "name": kn, "gd": kgd, "offset": (x0, y0)})

        for sz, k_tasks in k_tasks_by_sz.items():
            num_t = len(k_tasks)
            max_h = max(t["imgs"][0].shape[2] for t in k_tasks)
            max_w = max(t["imgs"][0].shape[3] for t in k_tasks)
            
            # PRE-ALLOCATED BATCH: Viel schneller als hunderte F.pad Aufrufe
            b_imgs = torch.zeros((num_t, 3, max_h, max_w), device=self.device)
            b_s = torch.zeros((num_t, 1, max_h, max_w), device=self.device)
            b_q = torch.zeros((num_t, 1, max_h, max_w), device=self.device)
            tpl_l, off_l = [], []
            
            for i, task in enumerate(k_tasks):
                crop, crop_s, crop_q = task["imgs"]; ch, cw = crop.shape[2:]
                b_imgs[i, :, :ch, :cw] = crop
                b_s[i, :, :ch, :cw] = crop_s
                b_q[i, :, :ch, :cw] = crop_q
                tpl_l.append((task["name"], task["gd"])); off_l.append(task["offset"])       
                
            k_raw = self._batch_match_fixed_size(b_imgs, b_s, b_q, tpl_l, s_eff, is_1to1=True, threshold=0.7, offsets=off_l)
            res_final.extend(k_raw)

        final = []
        for n, rx, ry, rw, rh, sc in self._nms(res_final): 
            final.append((n.split("__")[0], int(rx*nx), int(ry*ny), int(rw*nx), int(rh*ny), sc, n, self._get_hierarchy_names(n)))
        return final, sorted(list(set([m[0] for m in final]))), scanned_regions, search_stats

    def _batch_match_fixed_size(self, imgs, imgs_s, imgs_sq, tpls, s_eff, is_1to1=False, threshold=None, offsets=None):
        if not tpls or imgs.shape[0] == 0: return []
        num_tpl, (gh, gw) = len(tpls), tpls[0][1]["t_zm"].shape[2:]
        num_img = imgs.shape[0]

        # Verhindert unbegrenztes VRAM-Wachstum durch Cache-Einträge für verschiedene Template-Kombinationen
        if len(self._batch_cache) > 64:
            self._batch_cache.clear()

        if is_1to1:
            # ROI Turbo mit Batch-Caching
            b_key = ("roi", tuple([t[0] for t in tpls]))
            if b_key not in self._batch_cache:
                w = torch.cat([t[1]["t_zm"] for t in tpls]) 
                m_list = []
                for t in tpls:
                    if t[1]["is_masked"]: m_list.append(t[1]["m"])
                    else: m_list.append(torch.ones((1, 3, gh, gw), device=self.device))
                m_3ch = torch.cat(m_list)
                tn = torch.cat([t[1]["t_norm"] for t in tpls], dim=0).view(1, num_img, 1, 1)
                npix = torch.cat([t[1]["N"] for t in tpls], dim=0).view(1, num_img, 1, 1)
                lims = torch.cat([t[1]["threshold"] for t in tpls], dim=0).view(1, num_img, 1, 1)
                self._batch_cache[b_key] = (w, m_3ch, tn, npix, lims)
            w, m_3ch, tn, npix, limits = self._batch_cache[b_key]
            
            i_grouped = imgs.view(1, num_img * 3, imgs.shape[2], imgs.shape[3])
            res = F.conv2d(i_grouped, w, groups=num_img) 
            m_single = m_3ch[:, 0:1, :, :].view(num_img, 1, gh, gw)
            i_s = F.conv2d(imgs_s.view(1, num_img, imgs.shape[2], imgs.shape[3]), m_single, groups=num_img)
            i_q = F.conv2d(imgs_sq.view(1, num_img, imgs.shape[2], imgs.shape[3]), m_single, groups=num_img)
        else:
            # Fullscreen mit Batch-Caching
            b_key = ("fs", tuple([t[0] for t in tpls]))
            if b_key not in self._batch_cache:
                w = torch.stack([t[1]["t_zm"].squeeze(0) for t in tpls])
                m_list = [ (t[1]["m"].squeeze(0)[0:1] if t[1]["is_masked"] else None) for t in tpls]
                tn = torch.cat([t[1]["t_norm"] for t in tpls], dim=0).view(1, num_tpl, 1, 1)
                npix = torch.cat([t[1]["N"] for t in tpls], dim=0).view(1, num_tpl, 1, 1)
                lims = torch.cat([t[1]["threshold"] for t in tpls], dim=0).view(1, num_tpl, 1, 1)
                self._batch_cache[b_key] = (w, m_list, tn, npix, lims)
            w, m_list, tn, npix, limits = self._batch_cache[b_key]
            
            res = F.conv2d(imgs, w, padding=0)
            i_s_all = torch.zeros((1, num_tpl, res.shape[2], res.shape[3]), device=self.device)
            i_q_all = torch.zeros((1, num_tpl, res.shape[2], res.shape[3]), device=self.device)
            
            # Optimierte Helligkeits-Zuweisung (Vektorisiert)
            unmasked_idx = [i for i, m in enumerate(m_list) if m is None]
            if unmasked_idx:
                i_s_box = F.avg_pool2d(imgs_s, (gh, gw), stride=1, divisor_override=1)
                i_q_box = F.avg_pool2d(imgs_sq, (gh, gw), stride=1, divisor_override=1)
                i_s_all[:, unmasked_idx] = i_s_box; i_q_all[:, unmasked_idx] = i_q_box
            
            # Nur für Maskierte Templates conv2d aufrufen
            for i, m in enumerate(m_list):
                if m is not None:
                    i_s_all[:, i:i+1] = F.conv2d(imgs_s, m.unsqueeze(0), padding=0)
                    i_q_all[:, i:i+1] = F.conv2d(imgs_sq, m.unsqueeze(0), padding=0)
            i_s, i_q = i_s_all, i_q_all
            
        if threshold: limits = torch.ones_like(limits) * threshold
        i_var = i_q - (i_s.pow(2) / npix)
        scores = res / (torch.sqrt(torch.clamp(i_var, min=1e-5)) * tn + 1e-6)
        mask = (scores >= limits)
        if scores.numel() > 0 and scores.size(-2) > 1 and scores.size(-1) > 1:
            mp = F.max_pool2d(scores, 3, 1, 1); mask &= (scores == mp)
            
        pts = torch.nonzero(mask)
        if pts.numel() == 0: return []
        
        # GPU-Synchronisation vor CPU-Transfer (verhindert Heap-Corruption durch async GPU-Kernel)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        res_pts = pts.cpu().numpy()
        res_scores = scores[mask].cpu().numpy()
        
        res_list = []
        for k in range(res_pts.shape[0]):
            bi, ti, yi, xi = res_pts[k]
            name = tpls[ti][0]; ox, oy = offsets[ti if is_1to1 else bi] if offsets else (0, 0)
            # [name, x, y, w, h, score] -> Berechnung auf CPU (Zero-Sync)
            res_list.append([name, (float(xi) + ox)/s_eff, (float(yi) + oy)/s_eff, gw/s_eff, gh/s_eff, float(res_scores[k])])
        return res_list

    def _nms(self, matches):
        if not matches: return []
        # matches ist jetzt eine Liste von [name, x, y, w, h, score] wobei x, y, score bereits float (CPU) sind
        matches.sort(key=lambda x: x[5], reverse=True); ergebnis = []
        for m in matches:
            mx, my, mw, mh = m[1], m[2], m[3], m[4]
            cx, cy = mx + mw/2, my + mh/2
            doppelt = False
            for a in ergebnis:
                if a[0] == m[0]:
                    ax, ay, aw, ah = a[1], a[2], a[3], a[4]
                    if abs(cx - (ax + aw/2)) < mw*0.5 and abs(cy - (ay + ah/2)) < mh*0.5: 
                        doppelt = True; break
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
