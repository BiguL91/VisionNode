import json
import os

WORKFLOWS_DATEI = "workflows.json"
SCHEDULE_DATEI  = "schedule.json"

# Schutz gegen Endlosschleifen im Graphen
MAX_SCHRITTE = 1000


class WorkflowEngine:
    def __init__(self):
        self.workflows = {}   # name -> {"nodes": [...], "connections": [...]}
        self.schedule  = []   # [workflow_name, ...]
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

    def workflow_speichern(self, name, graph):
        """Speichert einen Workflow-Graphen.
        graph = {"nodes": [...], "connections": [...]}
        """
        self.workflows[name] = graph
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

    # ── Node ausführen ───────────────────────────────────────────────────────

    def _node_ausfuehren(self, node, action_engine, matches_func, ocr_func=None, log_func=None):
        """Führt einen einzelnen Node aus.
        Gibt den Namen des ausgehenden Ports zurück (z.B. "out", "success", "failure", "true", "false").
        Gibt None zurück bei unbekanntem Typ.
        """
        typ = node.get("typ")

        if typ == "start":
            return "out"

        elif typ == "suche":
            ok = action_engine.auf_template_warten(
                node["template"], matches_func,
                timeout=node.get("timeout", 10),
                intervall=0.3,
            )
            return "success" if ok else "failure"

        elif typ == "suche_optional":
            # Läuft immer durch, auch wenn Template nicht gefunden
            action_engine.auf_template_warten(
                node["template"], matches_func,
                timeout=node.get("timeout", 3),
                intervall=0.3,
            )
            return "out"

        elif typ == "klick":
            matches = matches_func()
            ok = action_engine.template_tippen(node["template"], matches, log_func=log_func)
            return "out" if ok else "failure"

        elif typ == "warten":
            action_engine.warten(node.get("sekunden", 1.0))
            return "out"

        elif typ == "zurueck":
            action_engine.zurueck()
            return "out"

        elif typ == "home":
            action_engine.home()
            return "out"

        elif typ == "bedingung":
            variable = node.get("variable", "")
            operator = node.get("operator", "=")
            soll     = node.get("wert", "")

            # Variable auflösen (Prefix-Format: "state::name", "ocr::name", "db::Liste::Var")
            ist = self._variable_auflösen(variable, ocr_func)

            ergebnis = False
            try:
                a = float(str(ist).replace(",", "."))
                b = float(str(soll).replace(",", "."))
                if   operator == ">":          ergebnis = a > b
                elif operator == "<":          ergebnis = a < b
                elif operator == ">=":         ergebnis = a >= b
                elif operator == "<=":         ergebnis = a <= b
                elif operator in ("=", "=="):  ergebnis = a == b
                elif operator == "!=":         ergebnis = a != b
            except (ValueError, AttributeError):
                ist_str  = str(ist).lower()
                soll_str = str(soll).lower()
                if   operator in ("=", "=="): ergebnis = ist_str == soll_str
                elif operator == "!=":        ergebnis = ist_str != soll_str
            return "true" if ergebnis else "false"

        return None  # Unbekannter Node-Typ

    def _variable_auflösen(self, variable, ocr_func):
        """Löst einen Variablen-Namen (ggf. mit Prefix) zum aktuellen Wert auf.

        Formate:
            "state::Name"       → game_state (True/False → "true"/"false")
            "ocr::Name"         → OCR-Wert
            "db::Liste::Var"    → Werte-Cache aus Daten-Listen-DB
            "Name"              → Legacy: direkt aus ocr_func (Rückwärtskompatibilität)
        """
        if not variable:
            return ""

        if variable.startswith("state::"):
            name = variable[7:]
            if ocr_func is None:
                return ""
            # Game States werden von main_app als "__state__<name>" in ocr_func injiziert
            return ocr_func().get(f"__state__{name}", "")

        if variable.startswith("ocr::"):
            name = variable[5:]
            if ocr_func is None:
                return ""
            return ocr_func().get(name, "")

        if variable.startswith("db::"):
            teile = variable[4:].split("::", 1)
            if len(teile) != 2:
                return ""
            listen_name, var_name = teile
            try:
                from core import daten_manager as dm
                listen = dm.alle_listen()
                for liste in listen:
                    if liste["name"] == listen_name:
                        cache = dm.cache_lesen(liste["id"])
                        eintrag = cache.get(var_name)
                        if eintrag is not None:
                            return eintrag[0] if isinstance(eintrag, (tuple, list)) else str(eintrag)
            except Exception:
                pass
            return ""

        # Legacy: kein Prefix → direkt OCR
        if ocr_func is None:
            return ""
        return ocr_func().get(variable, "")

    # ── Graph-Traversierung ──────────────────────────────────────────────────

    def _naechsten_node(self, node_id, port_aus, nodes_index, connections):
        """Findet den Ziel-Node für eine Verbindung (node_id + port_aus)."""
        for conn in connections:
            if conn["von"] == node_id and conn["port_aus"] == port_aus:
                return nodes_index.get(conn["zu"])
        return None

    def workflow_ausfuehren(self, name, action_engine, matches_func,
                            log_func=None, laeuft_func=None, ocr_func=None):
        """Traversiert den Workflow-Graphen ab dem Start-Node.
        Gibt True bei erfolgreichem Durchlauf zurück, False bei Fehler oder Abbruch.
        """
        graph = self.workflows.get(name)
        if not graph:
            if log_func:
                log_func(f"[{name}] Workflow nicht gefunden.")
            return False

        nodes       = graph.get("nodes", [])
        connections = graph.get("connections", [])

        # Schnellzugriff id → node
        nodes_index = {n["id"]: n for n in nodes}

        # Start-Node suchen
        start_node = next((n for n in nodes if n.get("typ") == "start"), None)
        if not start_node:
            if log_func:
                log_func(f"[{name}] Kein Start-Node vorhanden – Abbruch.")
            return False

        aktueller_node  = start_node
        schritt_zaehler = 0

        while aktueller_node is not None:

            # Bot-Stopp-Signal prüfen
            if laeuft_func and not laeuft_func():
                return False

            # Endlosschleifen abfangen
            schritt_zaehler += 1
            if schritt_zaehler > MAX_SCHRITTE:
                if log_func:
                    log_func(f"[{name}] Limit von {MAX_SCHRITTE} Schritten erreicht – Abbruch.")
                return False

            typ     = aktueller_node.get("typ", "?")
            node_id = aktueller_node.get("id", "?")

            # Log-Ausgabe (Start-Node überspringen, ist uninteressant)
            if log_func and typ != "start":
                detail = aktueller_node.get("template", aktueller_node.get("sekunden", ""))
                log_func(f"[{name}] {node_id} ({typ}): {detail}")

            # Node ausführen → ausgehenden Port ermitteln
            port_aus = self._node_ausfuehren(
                aktueller_node, action_engine, matches_func,
                ocr_func=ocr_func, log_func=log_func
            )

            if port_aus is None:
                if log_func:
                    log_func(f"[{name}] Node '{node_id}': unbekannter Typ '{typ}' – Abbruch.")
                return False

            # Nächsten Node über Verbindung suchen
            aktueller_node = self._naechsten_node(node_id, port_aus, nodes_index, connections)

        # Kein Folge-Node mehr → Workflow abgeschlossen
        if log_func:
            log_func(f"[{name}] Workflow '{name}' abgeschlossen.")
        return True
