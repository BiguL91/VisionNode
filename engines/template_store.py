"""
Template-Store — Datei-I/O und Settings-Persistenz.
Kein GPU-Code, kein Matching. Liest/schreibt Dateisystem und JSON-Einstellungen.
Wird vom TemplateEngine als interner Delegator genutzt.
"""
import os
import json
import shutil
import time
import cv2
import numpy as np
from PIL import Image

TEMPLATES_ORDNER = "templates"
SETTINGS_ORDNER  = os.path.join(TEMPLATES_ORDNER, "settings")
SETTINGS_DATEI   = os.path.join(SETTINGS_ORDNER, "template_settings.json")
DELETED_ORDNER   = os.path.join(TEMPLATES_ORDNER, "_deleted")


class TemplateStore:
    SETTINGS_DATEI = SETTINGS_DATEI

    def __init__(self, settings: dict, templates: dict, log_func=None, log_enabled_func=None):
        # Beides sind Referenzen auf die Engine-Dicts — Änderungen sind sofort sichtbar
        self.settings = settings
        self.templates = templates
        self.log_func = log_func
        self.log_enabled_func = log_enabled_func

    def _log(self, message):
        if self.log_func:
            if self.log_enabled_func and not self.log_enabled_func():
                return
            self.log_func(message)
        else:
            print(f"LOG: {message}")

    # ── Settings ──────────────────────────────────────────────────────────────

    def _settings_laden(self):
        """Lädt template_settings.json in self.settings."""
        if os.path.exists(SETTINGS_DATEI):
            try:
                with open(SETTINGS_DATEI, "r", encoding="utf-8") as f:
                    geladen = json.load(f)
                self.settings.clear()
                self.settings.update(geladen)
            except Exception:
                pass

    def _settings_speichern(self):
        """Schreibt self.settings auf Disk. Kein Reload — Engine ist dafür zuständig."""
        try:
            with open(SETTINGS_DATEI, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Fehler beim Speichern der Template-Settings: {e}")

    def state_umbenennen_in_settings(self, alter_name, neuer_name):
        """Aktualisiert alle Referenzen auf einen State-Namen in den Template-Einstellungen."""
        for t_settings in self.settings.values():
            if not isinstance(t_settings, dict):
                continue
            for cond in t_settings.get("condition_states", []):
                if isinstance(cond, dict) and "states" in cond:
                    if alter_name in cond["states"]:
                        cond["states"][neuer_name] = cond["states"].pop(alter_name)
            ss = t_settings.get("set_states", {})
            if isinstance(ss, dict) and alter_name in ss:
                ss[neuer_name] = ss.pop(alter_name)
        self._settings_speichern()

    def state_loeschen_in_settings(self, name):
        """Entfernt alle Referenzen auf einen State-Namen aus den Template-Einstellungen."""
        for t_settings in self.settings.values():
            if not isinstance(t_settings, dict):
                continue
            for cond in t_settings.get("condition_states", []):
                if isinstance(cond, dict) and "states" in cond:
                    cond["states"].pop(name, None)
            t_settings.get("set_states", {}).pop(name, None)
        self._settings_speichern()

    # ── Bereinigung ───────────────────────────────────────────────────────────

    def konfigurationen_bereinigen(self):
        if not os.path.exists(TEMPLATES_ORDNER):
            return

        aktuelle_pngs = set()
        for root, dirs, dateien in os.walk(TEMPLATES_ORDNER):
            if "_deleted" in dirs:
                dirs.remove("_deleted")
            for f in dateien:
                if f.endswith(".png"):
                    aktuelle_pngs.add(f[:-4])

        settings_pfad = os.path.join(SETTINGS_ORDNER, "template_settings.json")
        gueltige_keys = set(aktuelle_pngs)

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
                    with open(datei, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    neu = {}
                    for k, v in data.items():
                        if k.startswith("_"):
                            neu[k] = v
                        elif k in gueltige_keys:
                            neu[k] = v
                    if len(neu) != len(data):
                        with open(datei, "w", encoding="utf-8") as f:
                            json.dump(neu, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

        ocr_path = os.path.join(SETTINGS_ORDNER, "template_ocr.json")
        if os.path.exists(ocr_path):
            try:
                with open(ocr_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                neu = {k: v for k, v in data.items() if v.get("template") in aktuelle_pngs}
                if len(neu) != len(data):
                    with open(ocr_path, "w", encoding="utf-8") as f:
                        json.dump(neu, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    # ── Pfad-Helfer ───────────────────────────────────────────────────────────

    def _gruppe_vollpfad(self, gruppe_name):
        """Vollpfad einer Gruppe. settings['gruppe'] = Vollpfad des Elternteils (oder leer)."""
        s = self.settings.get(gruppe_name, {})
        if not s:
            return gruppe_name
        parent = s.get("gruppe", "")
        if parent and parent != gruppe_name:
            return f"{parent}/{gruppe_name}"
        return gruppe_name

    def _gruppe_ordnerpfad(self, gruppe_name):
        """Disk-Pfad einer Gruppe."""
        s = self.settings.get(gruppe_name, {})
        kat = s.get("kategorie", "workflow")
        parent = s.get("gruppe", "")
        if parent and parent != gruppe_name:
            return os.path.join(TEMPLATES_ORDNER, kat, *parent.split("/"), gruppe_name)
        return os.path.join(TEMPLATES_ORDNER, kat, gruppe_name)

    # ── Gruppen-Abfragen ──────────────────────────────────────────────────────

    def get_kinder(self, gruppe_name):
        """Gibt alle Templates zurück, die zu dieser Gruppe oder ihren Untergruppen gehören."""
        vollpfad = self._gruppe_vollpfad(gruppe_name)
        kinder = []
        for k, v in self.settings.items():
            if not isinstance(v, dict) or k == gruppe_name:
                continue
            g = v.get("gruppe", "")
            if g == vollpfad or g.startswith(vollpfad + "/"):
                kinder.append(k)
        return sorted(list(set(kinder)))

    def get_gruppen(self, kategorie=None):
        """Gibt Vollpfade aller Gruppen zurück — optional gefiltert nach Kategorie."""
        gruppen = set()

        for k, v in self.settings.items():
            if not isinstance(v, dict):
                continue
            typ = v.get("typ")
            if typ not in ("aktiv_gruppe", "passiv_gruppe"):
                continue
            if kategorie and v.get("kategorie") != kategorie:
                continue
            gruppen.add(self._gruppe_vollpfad(k))

        for name, t in self.templates.items():
            g = t.get("gruppe")
            if not g:
                continue
            if kategorie:
                pfad = t.get("pfad", "")
                rel = os.path.relpath(pfad, TEMPLATES_ORDNER).replace("\\", "/")
                if not rel.startswith(f"{kategorie}/"):
                    continue
            gruppen.add(g)

        return sorted(g for g in gruppen if g)

    # ── Datei-Helfer ──────────────────────────────────────────────────────────

    def _backup_zu_deleted(self, pfad):
        """Verschiebt eine Datei in den _deleted-Ordner statt sie zu löschen."""
        if not pfad or not os.path.exists(pfad):
            return
        try:
            bn = os.path.basename(pfad)
            ts = time.strftime("%Y%m%d_%H%M%S")
            os.makedirs(DELETED_ORDNER, exist_ok=True)
            ziel = os.path.join(DELETED_ORDNER, f"{ts}_{bn}")
            shutil.move(pfad, ziel)
            self._log(f"  Backup: {bn} -> _deleted/")
        except Exception as e:
            self._log(f"  Backup-Fehler ({os.path.basename(pfad)}): {e}")
            try:
                os.remove(pfad)
                self._log(f"  Datei stattdessen gelöscht (Backup fehlgeschlagen).")
            except Exception:
                pass

    def _ordner_aufraumen(self, ordner):
        """Löscht leere Ordner rekursiv bis zum templates/-Wurzelordner."""
        basis = os.path.abspath(TEMPLATES_ORDNER)
        pfad = os.path.abspath(ordner)
        while pfad != basis:
            if os.path.exists(pfad) and not os.listdir(pfad):
                try:
                    os.rmdir(pfad)
                except Exception:
                    break
            else:
                break
            pfad = os.path.dirname(pfad)

    # ── Template-I/O ──────────────────────────────────────────────────────────

    def _hintergrund_maske_erstellen(self, bild_np, toleranz=30):
        h, w = bild_np.shape[:2]
        ecken = np.array([bild_np[0, 0], bild_np[0, w-1], bild_np[h-1, 0], bild_np[h-1, w-1]], dtype=np.float32)
        hintergrundfarbe = np.mean(ecken, axis=0).astype(np.uint8)
        diff = np.abs(bild_np.astype(np.int32) - hintergrundfarbe.astype(np.int32))
        return np.where(np.all(diff <= toleranz, axis=2), 0, 255).astype(np.uint8)

    def template_speichern(self, name, bild_pil, hintergrund_entfernen=True, ignore_regionen=None,
                           hintergrund_toleranz=30, gruppe=None, match_schwellwert=0.85,
                           scan_regions=None, condition_states=None, set_states=None, typ=None,
                           ist_state_template=False, kategorie=None, alter_name=None,
                           ausschnitt_form="box", search_only=False, is_smart=False):
        bild_np = np.array(bild_pil.convert("RGB"))
        basis_name = name.split("__")[0]
        g_name = gruppe if gruppe and gruppe != name else ""

        if not kategorie:
            bestehend = self.settings.get(name, {})
            kategorie = bestehend.get("kategorie", "workflow")

        if typ == "aktiv_gruppe":
            if g_name:
                ordner = os.path.join(TEMPLATES_ORDNER, kategorie, *g_name.split("/"), basis_name)
            else:
                ordner = os.path.join(TEMPLATES_ORDNER, kategorie, basis_name)
        else:
            if g_name:
                ordner = self._gruppe_ordnerpfad(g_name.split("/")[-1] if "/" in g_name else g_name)
            else:
                ordner = os.path.join(TEMPLATES_ORDNER, kategorie)

        os.makedirs(ordner, exist_ok=True)
        pfad = os.path.join(ordner, f"{name}.png")

        zu_loeschen_namen = {name}
        if alter_name:
            zu_loeschen_namen.add(alter_name)

        for an in zu_loeschen_namen:
            if an in self.templates:
                alter_pfad = self.templates[an]["pfad"]
                if os.path.exists(alter_pfad) and os.path.abspath(alter_pfad) != os.path.abspath(pfad):
                    try:
                        os.remove(alter_pfad)
                        alt_dir = os.path.dirname(alter_pfad)
                        if os.path.exists(alt_dir) and not os.listdir(alt_dir):
                            os.rmdir(alt_dir)
                    except Exception:
                        pass
                if an != name:
                    self.settings.pop(an, None)
                    self.templates.pop(an, None)

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
                        maske[max(0, iy0):iy1, max(0, ix0):ix1] = 0
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
                        mask_alpha[max(0, iy0):min(h, iy1), max(0, ix0):min(w, ix1)] = 0
                arr[:, :, 3] = mask_alpha
                bild_speichern = Image.fromarray(arr, "RGBA")

        bild_speichern.save(pfad)

        if not typ:
            bestehend = self.settings.get(name, {})
            typ = bestehend.get("typ") or ("aktiv_gruppe" if g_name == basis_name else "template")

        self.settings[name] = {
            "hg_entfernen":     bool(hintergrund_entfernen),
            "hg_toleranz":      int(hintergrund_toleranz),
            "ignore_regionen":  [list(r) for r in ignore_regionen] if ignore_regionen else [],
            "gruppe":           g_name,
            "match_schwellwert": float(match_schwellwert),
            "scan_regions":     [list(r) for r in scan_regions] if scan_regions else [],
            "condition_states": condition_states or {},
            "set_states":       set_states or {},
            "typ":              typ,
            "kategorie":        kategorie,
            "ausschnitt_form":  ausschnitt_form,
            "search_only":      bool(search_only),
            "is_smart":         bool(is_smart),
        }
        self._settings_speichern()

    def template_umbenennen(self, alter_name, neuer_name, neue_gruppe=None):
        """Benennt ein Template und alle seine Varianten um oder verschiebt sie."""
        alter_basis = alter_name.split("__")[0]
        neuer_basis = neuer_name.split("__")[0]

        varianten = [t for t in self.templates.keys() if t == alter_basis or t.startswith(f"{alter_basis}__")]
        self._log(f"Template umbenennen: '{alter_basis}' → '{neuer_basis}' ({len(varianten)} Varianten)")

        for v_alt in varianten:
            suffix = v_alt[len(alter_basis):]
            v_neu = f"{neuer_basis}{suffix}"
            if v_alt not in self.templates:
                continue

            alt_pfad = self.templates[v_alt]["pfad"]
            g_name = neue_gruppe if neue_gruppe else neuer_basis
            kat = self.settings.get(v_alt, {}).get("kategorie", "workflow")
            g_key = g_name.split("/")[-1]
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
                    if os.path.exists(alt_dir) and not os.listdir(alt_dir):
                        os.rmdir(alt_dir)
                except Exception as e:
                    self._log(f"  Fehler bei {v_alt}: {e}")

            if v_alt in self.settings:
                self.settings[v_neu] = self.settings.pop(v_alt)
                self.settings[v_neu]["gruppe"] = g_name

        for k, v in list(self.settings.items()):
            if not isinstance(v, dict):
                continue
            g = v.get("gruppe", "")
            if g == alter_basis:
                self.settings[k]["gruppe"] = neue_gruppe if neue_gruppe else neuer_basis
            elif g.startswith(alter_basis + "/"):
                suffix = g[len(alter_basis):]
                self.settings[k]["gruppe"] = (neue_gruppe if neue_gruppe else neuer_basis) + suffix

        self._settings_speichern()

    def template_loeschen(self, name):
        if name not in self.templates:
            return
        pfad = self.templates[name]["pfad"]
        self._backup_zu_deleted(pfad)
        self._ordner_aufraumen(os.path.dirname(pfad))
        self.templates.pop(name, None)
        self.settings.pop(name, None)
        self._settings_speichern()

    def gruppe_config_speichern(self, gruppe_name, condition_states, uebergeordnete_gruppe="",
                                kategorie=None, scan_regions=None, search_only=False):
        """Speichert eine passive Gruppe (kein Bild, nur Bedingungen) und legt den Ordner an."""
        bestehend = self.settings.get(gruppe_name, {})
        kat = kategorie or bestehend.get("kategorie", "workflow")
        g_val = uebergeordnete_gruppe or ""
        if g_val == gruppe_name:
            g_val = ""

        self.settings[gruppe_name] = {
            "typ":              "passiv_gruppe",
            "gruppe":           g_val,
            "condition_states": condition_states,
            "kategorie":        kat,
            "scan_regions":     [list(r) for r in scan_regions] if scan_regions else [],
            "search_only":      bool(search_only),
        }
        ordner = self._gruppe_ordnerpfad(gruppe_name)
        os.makedirs(ordner, exist_ok=True)
        self._settings_speichern()

    def gruppe_config_loeschen(self, gruppe_name, mit_inhalt=False):
        """Entfernt eine Gruppe und löscht optional alle enthaltenen Templates."""
        if gruppe_name not in self.settings:
            return
        typ = self.settings[gruppe_name].get("typ")
        if typ not in ("passiv_gruppe", "aktiv_gruppe"):
            return

        ordner = self._gruppe_ordnerpfad(gruppe_name)

        if mit_inhalt:
            kinder = self.get_kinder(gruppe_name)
            for kind in kinder:
                if kind in self.templates:
                    self._backup_zu_deleted(self.templates[kind]["pfad"])
                self.settings.pop(kind, None)
                self.templates.pop(kind, None)

            basis = gruppe_name.split("__")[0]
            master_pfad = os.path.join(ordner, f"{basis}.png")
            if os.path.exists(master_pfad):
                self._backup_zu_deleted(master_pfad)

        self.settings.pop(gruppe_name, None)
        self._settings_speichern()

        if mit_inhalt and os.path.exists(ordner):
            try:
                shutil.rmtree(ordner)
            except Exception:
                pass
        else:
            self._ordner_aufraumen(ordner)

    def gruppe_umbenennen(self, alter_name, neuer_name, neue_uebergeordnete_gruppe=None):
        """Benennt eine Gruppe um oder verschiebt sie: verschiebt Ordner + cascadiert Vollpfade."""
        alter_vollpfad = self._gruppe_vollpfad(alter_name)
        alter_ordner   = self._gruppe_ordnerpfad(alter_name)

        if neue_uebergeordnete_gruppe is not None:
            parent = neue_uebergeordnete_gruppe
        else:
            parent = self.settings.get(alter_name, {}).get("gruppe", "")

        if parent == alter_name or parent is None:
            parent = ""

        neuer_vollpfad = f"{parent}/{neuer_name}" if parent else neuer_name
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

                if os.path.exists(neuer_ordner):
                    alter_basis = alter_name.split("__")[0]
                    neuer_basis = neuer_name.split("__")[0]
                    for datei in os.listdir(neuer_ordner):
                        if datei.endswith(".png"):
                            d_name = datei[:-4]
                            if d_name == alter_basis or d_name.startswith(f"{alter_basis}__"):
                                suffix = d_name[len(alter_basis):]
                                neu_d_name = f"{neuer_basis}{suffix}.png"
                                os.rename(
                                    os.path.join(neuer_ordner, datei),
                                    os.path.join(neuer_ordner, neu_d_name)
                                )
                                self._log(f"  Datei umbenannt: {datei} → {neu_d_name}")
            except Exception as e:
                self._log(f"  Ordner-Fehler: {e}")

        for k, v in list(self.settings.items()):
            if not isinstance(v, dict):
                continue
            g = v.get("gruppe", "")

            basis_k = k.split("__")[0]
            if basis_k == alter_name:
                suffix = k[len(basis_k):]
                neu_k = neuer_name + suffix
                self.settings[neu_k] = self.settings.pop(k)
                self.settings[neu_k]["gruppe"] = neuer_vollpfad
                self._log(f"  Eintrag (Variante) umbenannt: '{k}' → '{neu_k}'")
                continue

            if g == alter_vollpfad:
                self._log(f"  Update Pfad: '{k}' (Gruppe: {neuer_vollpfad})")
                self.settings[k]["gruppe"] = neuer_vollpfad
            elif g.startswith(alter_vollpfad + "/"):
                neu_g = neuer_vollpfad + g[len(alter_vollpfad):]
                self._log(f"  Update Pfad (Deep): '{k}' (Gruppe: {neu_g})")
                self.settings[k]["gruppe"] = neu_g

        if alter_name in self.settings:
            self.settings[neuer_name] = self.settings.pop(alter_name)
            self.settings[neuer_name]["gruppe"] = neuer_vollpfad if parent else ""
            self._log(f"  Eintrag umbenannt: '{alter_name}' → '{neuer_name}'")

        self._settings_speichern()
