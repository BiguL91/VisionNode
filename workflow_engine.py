import json
import os

WORKFLOWS_DATEI = "workflows.json"
SCHEDULE_DATEI = "schedule.json"


class WorkflowEngine:
    def __init__(self):
        self.workflows = {}   # name -> [schritte]
        self.schedule = []    # [workflow_name, ...]
        self._laden()

    # ── Laden / Speichern ────────────────────────────────────────────────────

    def _laden(self):
        if os.path.exists(WORKFLOWS_DATEI):
            try:
                with open(WORKFLOWS_DATEI, "r", encoding="utf-8") as f:
                    self.workflows = json.load(f)
            except Exception:
                self.workflows = {}
        if os.path.exists(SCHEDULE_DATEI):
            try:
                with open(SCHEDULE_DATEI, "r", encoding="utf-8") as f:
                    self.schedule = json.load(f)
            except Exception:
                self.schedule = []

    def _workflows_speichern(self):
        with open(WORKFLOWS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.workflows, f, ensure_ascii=False, indent=2)

    def _schedule_speichern(self):
        with open(SCHEDULE_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.schedule, f, ensure_ascii=False, indent=2)

    # ── Workflows ────────────────────────────────────────────────────────────

    def workflow_speichern(self, name, schritte):
        self.workflows[name] = schritte
        self._workflows_speichern()

    def workflow_loeschen(self, name):
        self.workflows.pop(name, None)
        self.schedule = [s for s in self.schedule if s != name]
        self._workflows_speichern()
        self._schedule_speichern()

    def workflow_umbenennen(self, alter_name, neuer_name):
        if alter_name not in self.workflows:
            return
        self.workflows[neuer_name] = self.workflows.pop(alter_name)
        self.schedule = [neuer_name if s == alter_name else s for s in self.schedule]
        self._workflows_speichern()
        self._schedule_speichern()

    # ── Schedule ─────────────────────────────────────────────────────────────

    def schedule_hinzufuegen(self, name):
        if name in self.workflows:
            self.schedule.append(name)
            self._schedule_speichern()

    def schedule_entfernen(self, index):
        if 0 <= index < len(self.schedule):
            self.schedule.pop(index)
            self._schedule_speichern()

    def schedule_verschieben(self, index, richtung):
        """Verschiebt Eintrag um +1 (runter) oder -1 (hoch)."""
        ziel = index + richtung
        if 0 <= ziel < len(self.schedule):
            self.schedule[index], self.schedule[ziel] = self.schedule[ziel], self.schedule[index]
            self._schedule_speichern()

    # ── Ausführung ───────────────────────────────────────────────────────────

    def schritt_ausfuehren(self, schritt, action_engine, matches_func, ocr_func=None, log_func=None):
        """Führt einen einzelnen Schritt aus. Gibt True bei Erfolg zurück."""
        typ = schritt.get("typ")

        if typ == "suche":
            return action_engine.auf_template_warten(
                schritt["template"], matches_func,
                timeout=schritt.get("timeout", 10),
                intervall=0.3,
            )
        elif typ == "suche_optional":
            # Kein Fehler wenn nicht gefunden
            action_engine.auf_template_warten(
                schritt["template"], matches_func,
                timeout=schritt.get("timeout", 3),
                intervall=0.3,
            )
            return True
        elif typ == "klick":
            matches = matches_func()
            return action_engine.template_tippen(schritt["template"], matches,
                                                  log_func=log_func)
        elif typ == "warte":
            action_engine.warten(schritt.get("sekunden", 1.0))
            return True
        elif typ == "zurueck":
            action_engine.zurueck()
            return True
        elif typ == "home":
            action_engine.home()
            return True
        elif typ == "bedingung":
            if ocr_func is None:
                return False
            variable = schritt.get("variable", "")
            operator = schritt.get("operator", "=")
            soll = schritt.get("wert", "")
            ist = ocr_func().get(variable, "")
            try:
                a = float(str(ist).replace(",", "."))
                b = float(str(soll).replace(",", "."))
                if operator == ">":  return a > b
                if operator == "<":  return a < b
                if operator == ">=": return a >= b
                if operator == "<=": return a <= b
                if operator in ("=", "=="): return a == b
                if operator == "!=": return a != b
            except (ValueError, AttributeError):
                if operator in ("=", "=="): return str(ist) == str(soll)
                if operator == "!=": return str(ist) != str(soll)
            return False

        return False

    def workflow_ausfuehren(self, name, action_engine, matches_func, log_func=None, laeuft_func=None, ocr_func=None):
        """Führt einen Workflow aus. Gibt True bei Erfolg, False bei Fehler zurück."""
        schritte = self.workflows.get(name, [])
        for i, schritt in enumerate(schritte):
            # Abbruch wenn Bot gestoppt wurde
            if laeuft_func and not laeuft_func():
                return False
            typ = schritt.get("typ", "?")
            detail = schritt.get("template", schritt.get("sekunden", ""))
            if log_func:
                log_func(f"[{name}] Schritt {i + 1}/{len(schritte)}: {typ} {detail}")
            ok = self.schritt_ausfuehren(schritt, action_engine, matches_func, ocr_func=ocr_func, log_func=log_func)
            if not ok:
                if log_func:
                    log_func(f"[{name}] Schritt {i + 1} fehlgeschlagen – Workflow abgebrochen.")
                return False
        return True
