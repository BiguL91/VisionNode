"""
TemplateEngine — Orchestrator.
Delegiert Datei-I/O an TemplateStore, GPU-Matching an TemplateMatcher.
Öffentliche API bleibt identisch für alle Aufrufer.
"""
import cv2
import numpy as np
import os
import torch
from PIL import Image

from engines.template_store   import TemplateStore,   TEMPLATES_ORDNER, SETTINGS_ORDNER, DELETED_ORDNER
from engines.template_matcher import TemplateMatcher


class TemplateEngine:
    SETTINGS_DATEI = TemplateStore.SETTINGS_DATEI

    def __init__(self, matching_skalierung=0.5, referenz_groesse=None, log_func=None, log_enabled_func=None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.log_func         = log_func
        self.log_enabled_func = log_enabled_func
        self._log(f"TemplateEngine: Nutze Device '{self.device}'")

        self.templates = {}
        self.settings  = {}
        self._matching_skalierung = matching_skalierung
        self._referenz_groesse    = referenz_groesse

        self._store   = TemplateStore(self.settings, self.templates, log_func, log_enabled_func)
        self._matcher = TemplateMatcher(
            self.templates, self.settings, self.device,
            self._matching_skalierung, self._referenz_groesse, log_func, log_enabled_func
        )

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

    # ── Template-Laden (brückt Dateisystem → GPU-Tensoren) ────────────────────

    def _templates_laden(self):
        self._store._settings_laden()
        self.templates.clear()
        self._matcher.cache_leeren()
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
                        "tensor":            t_bild,
                        "maske":             t_maske,
                        "orig_size":         (img.shape[1], img.shape[0]),
                        "gruppe":            gruppe,
                        "pfad":              pfad,
                        "match_schwellwert": self.settings.get(name, {}).get("match_schwellwert", 0.85),
                        "scan_regions":      self.settings.get(name, {}).get("scan_regions", []),
                        "bbox":              bbox,
                    }
        self._log(f"TemplateEngine: {len(self.templates)} Templates geladen.")

    # ── Bild-Helfer ───────────────────────────────────────────────────────────

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

    def _hintergrund_maske_erstellen(self, bild_np, toleranz=30):
        return self._store._hintergrund_maske_erstellen(bild_np, toleranz)

    # ── Delegatoren → Store ───────────────────────────────────────────────────

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
                           ausschnitt_form="box", search_only=False, is_smart=False):
        self._store.template_speichern(
            name, bild_pil, hintergrund_entfernen, ignore_regionen, hintergrund_toleranz,
            gruppe, match_schwellwert, scan_regions, condition_states, set_states, typ,
            ist_state_template, kategorie, alter_name, ausschnitt_form, search_only, is_smart
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

    @property
    def matching_skalierung(self):
        return self._matching_skalierung

    @matching_skalierung.setter
    def matching_skalierung(self, v):
        self._matching_skalierung = v
        if hasattr(self, '_matcher'):
            self._matcher.matching_skalierung = v

    @property
    def referenz_groesse(self):
        return self._referenz_groesse

    @referenz_groesse.setter
    def referenz_groesse(self, v):
        self._referenz_groesse = v
        if hasattr(self, '_matcher'):
            self._matcher.referenz_groesse = v

    @property
    def _gpu_cache(self):
        return self._matcher._gpu_cache

    # ── Delegatoren → Matcher ─────────────────────────────────────────────────

    def _get_hierarchy_set_states(self, name_oder_pfad):
        return self._matcher._get_hierarchy_set_states(name_oder_pfad)

    def _is_smart_recursive(self, name_oder_pfad):
        return self._matcher._is_smart_recursive(name_oder_pfad)

    def get_hierarchy_names(self, name_oder_pfad):
        return self._matcher.get_hierarchy_names(name_oder_pfad)

    def _condition_states_erfuellt(self, conditions, game_states, ignore_states=None):
        return self._matcher._condition_states_erfuellt(conditions, game_states, ignore_states)

    def _settings_speichern(self):
        self._store._settings_speichern()

    def matches_suchen_np(self, screenshot_bgr, game_states=None, force_include=None):
        return self._matcher.matches_suchen_np(screenshot_bgr, game_states, force_include)

    def get_mathematik_vorschau(self, name):
        return self._matcher.get_mathematik_vorschau(name)
