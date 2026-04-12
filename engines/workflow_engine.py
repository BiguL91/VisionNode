import json
import os
import time

WORKFLOWS_DATEI = os.path.join("templates", "settings", "workflows.json")
MASTER_DATEI     = os.path.join("templates", "settings", "master_workflows.json")
SCHEDULE_DATEI  = os.path.join("templates", "settings", "schedule.json")

# Schutz gegen Endlosschleifen im Graphen
MAX_SCHRITTE = 1000


class WorkflowEngine:
    def __init__(self):
        self.workflows = {}        # name -> graph (Aktionen/Sub-Workflows)
        self.master_workflows = {} # name -> graph (Schrittketten/Orchestrator)
        self.aktiver_master = None # Name des aktuell gewählten Master-Flows
        self.schedule  = []        # (Legacy/Kompabilität)
        
        # ── SPS-Gedächtnis (Instanz-Daten für Selector/Master-Flows) ──────────
        # Struktur: { "node_id_port_name": {"last_run": 0, "runs": 0} }
        self.session_data = {}
        
        self._laden()

    # ── Laden / Speichern ────────────────────────────────────────────────────

    def _laden(self):
        if os.path.exists(WORKFLOWS_DATEI):
            try:
                with open(WORKFLOWS_DATEI, "r", encoding="utf-8") as f:
                    self.workflows = json.load(f)
            except Exception: self.workflows = {}
            
        if os.path.exists(MASTER_DATEI):
            try:
                with open(MASTER_DATEI, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Support für altes Format (nur dict) und neues Format (dict mit "aktiv" key)
                    if "workflows" in data:
                        self.master_workflows = data.get("workflows", {})
                        self.aktiver_master    = data.get("aktiv")
                    else:
                        self.master_workflows = data
            except Exception: self.master_workflows = {}

        if os.path.exists(SCHEDULE_DATEI):
            try:
                with open(SCHEDULE_DATEI, "r", encoding="utf-8") as f:
                    self.schedule = json.load(f)
            except Exception:
                self.schedule = []

    def _workflows_speichern(self):
        with open(WORKFLOWS_DATEI, "w", encoding="utf-8") as f:
            json.dump(self.workflows, f, ensure_ascii=False, indent=2)

    def _master_speichern(self):
        with open(MASTER_DATEI, "w", encoding="utf-8") as f:
            json.dump({
                "aktiv": self.aktiver_master,
                "workflows": self.master_workflows
            }, f, ensure_ascii=False, indent=2)

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
        self._workflows_speichern()

    # ── Master-Workflows ─────────────────────────────────────────────────────

    def master_speichern(self, name, graph):
        self.master_workflows[name] = graph
        self._master_speichern()

    def master_loeschen(self, name):
        self.master_workflows.pop(name, None)
        if self.aktiver_master == name:
            self.aktiver_master = None
        self._master_speichern()

    def master_umbenennen(self, alter_name, neuer_name):
        if alter_name not in self.master_workflows:
            return
        self.master_workflows[neuer_name] = self.master_workflows.pop(alter_name)
        if self.aktiver_master == alter_name:
            self.aktiver_master = neuer_name
        self._master_speichern()

    def master_aktiv_setzen(self, name):
        """Markiert einen Master-Flow als aktiv."""
        if name in self.master_workflows or name is None:
            self.aktiver_master = name
            self._master_speichern()

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

    def _node_ausfuehren(self, node, action_engine, matches_func, ocr_func=None, log_func=None, laeuft_func=None):
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
                log_func=log_func,
                laeuft_func=laeuft_func
            )
            return "success" if ok else "failure"

        elif typ == "suche_optional":
            # Läuft immer durch, auch wenn Template nicht gefunden
            action_engine.auf_template_warten(
                node["template"], matches_func,
                timeout=node.get("timeout", 3),
                intervall=0.3,
                log_func=log_func,
                laeuft_func=laeuft_func
            )
            return "out"

        elif typ == "klick":
            matches = matches_func()
            ok = action_engine.template_tippen(node["template"], matches, log_func=log_func)
            return "out" if ok else "failure"

        elif typ == "warten":
            sekunden = node.get("sekunden", 1.0)
            start_zeit = time.time()
            while time.time() - start_zeit < sekunden:
                if laeuft_func and not laeuft_func():
                    return None # Abbruch der Node-Ausführung
                
                rest = max(0.0, sekunden - (time.time() - start_zeit))
                if log_func:
                    log_func(f"__timer__{rest:.1f}")
                schlaf_zeit = min(0.1, rest)
                if schlaf_zeit > 0:
                    time.sleep(schlaf_zeit)
                else:
                    break
            return "out"

        elif typ == "zurueck":
            action_engine.zurueck()
            return "out"

        elif typ == "home":
            action_engine.home()
            return "out"

        elif typ == "call_workflow":
            wf_name = node.get("workflow")
            if not wf_name or wf_name not in self.workflows:
                if log_func:
                    log_func(f"!! Sub-Workflow '{wf_name}' nicht gefunden.")
                return "failure"
            
            # Rekursiver Aufruf mit Einrückung für das Log
            if log_func:
                log_func(f"===> Rufe Funktionsbaustein: [{wf_name}]")
            
            # Hilfsfunktion für eingerücktes Log
            def sub_log(m):
                if log_func: log_func(f"  | {m}")

            ok = self.workflow_ausfuehren(
                wf_name, action_engine, matches_func,
                log_func=sub_log, laeuft_func=laeuft_func, ocr_func=ocr_func
            )
            
            if log_func:
                status = "abgeschlossen" if ok else "FEHLGESCHLAGEN"
                log_func(f"<=== FB [{wf_name}] {status}.")
            
            return "done" if ok else "failure"

        elif typ == "priority_selector":
            ausgaenge = node.get("ausgaenge", [])
            for i, ausgang in enumerate(ausgaenge):
                port_name = ausgang.get("port", f"Prio {i+1}")
                
                # --- SPS Verriegelung (Interlock) ---
                key = f"{node.get('id')}_{port_name}"
                data = self.session_data.get(key, {"last_run": 0, "runs": 0})
                
                # 1. Cooldown prüfen
                cooldown = float(ausgang.get("cooldown", 0))
                rest_cd = cooldown - (time.time() - data["last_run"])
                if cooldown > 0 and rest_cd > 0:
                    if log_func: log_func(f"  [Selector] Pfad '{port_name}' gesperrt (CD: {rest_cd:.1f}s)")
                    continue
                
                # 2. Max. Folge-Starts prüfen
                max_runs = int(ausgang.get("max_runs", 0))
                if max_runs > 0 and data["runs"] >= max_runs:
                    if log_func: log_func(f"  [Selector] Pfad '{port_name}' gesperrt (Limit {max_runs} erreicht)")
                    continue
                
                # 3. Logik-Netzwerk prüfen
                logic_graph = ausgang.get("logic_graph")
                res = False
                if logic_graph:
                    res = self._logik_auswerten(logic_graph, ocr_func, matches_func)
                else:
                    # Fallback Logik (Single Cond)
                    var, op, soll = ausgang.get("variable", ""), ausgang.get("operator", "="), ausgang.get("wert", "")
                    if not var: res = True # Leere Bedingung = Immer WAHR
                    else:
                        ist = self._variable_auflösen(var, ocr_func)
                        if var.startswith("state::") or str(soll).lower() in ("true", "false", "wahr", "falsch"):
                            res = (self._wert_zu_bool(ist) == self._wert_zu_bool(soll))
                        else: res = self._check_bedingung(ist, op, soll)
                
                if res:
                    if log_func: log_func(f"  [Selector] ✓ Pfad '{port_name}' gewählt.")
                    # Gedächtnis aktualisieren
                    data["last_run"] = time.time()
                    data["runs"] += 1
                    self.session_data[key] = data
                    for a2 in ausgaenge:
                        p2 = a2.get("port")
                        if p2 != port_name:
                            key2 = f"{node.get('id')}_{p2}"
                            if key2 in self.session_data: self.session_data[key2]["runs"] = 0
                    return port_name
            
            if log_func: log_func("  [Selector] ➔ Nehme ELSE-Pfad.")
            return "else"

        elif typ == "bedingung":
            variable = node.get("variable", "")
            operator = node.get("operator", "=")
            soll     = node.get("wert", "")

            # Variable auflösen
            ist = self._variable_auflösen(variable, ocr_func)

            # ── Sonderfall: Boolean-Vergleich (für States) ───────────────────
            if variable.startswith("state::") or str(soll).lower() in ("true", "false", "wahr", "falsch"):
                ist_bool  = self._wert_zu_bool(ist)
                soll_bool = self._wert_zu_bool(soll)
                
                if operator in ("=", "=="): ergebnis = (ist_bool == soll_bool)
                elif operator == "!=":      ergebnis = (ist_bool != soll_bool)
                else:                       ergebnis = ist_bool # Fallback
                return "true" if ergebnis else "false"

            # ── Standard: Numerisch oder String ──────────────────────────────
            if self._check_bedingung(ist, operator, soll):
                return "true"
            return "false"

        return None  # Unbekannter Node-Typ

    def _logik_auswerten(self, graph, ocr_func, matches_func):
        """Berechnet das Ergebnis eines FUP-Logik-Netzwerks."""
        nodes = {n["id"]: n for n in graph.get("nodes", [])}
        conns = graph.get("connections", [])
        
        # Cache für berechnete Node-Ergebnisse
        memo = {}

        def _get_input_val(node_id, port_name):
            # Findet den Wert, der an einem Eingangs-Port anliegt
            for c in conns:
                if c["zu"] == node_id and c["port_zu"] == port_name:
                    return _eval_node(c["von"])
            return None

        def _eval_node(nid):
            if nid in memo: return memo[nid]
            n = nodes.get(nid)
            if not n: return False
            
            typ = n.get("typ")
            res = False
            
            if typ == "l_var": # Variable Input
                var = n.get("variable", "")
                res = self._variable_auflösen(var, ocr_func)
                if n.get("as_bool"): res = self._wert_zu_bool(res)
            
            elif typ == "l_match": # Template gefunden?
                tpl = n.get("template", "")
                matches = matches_func()
                res = any(m[0] == tpl for m in matches)
            
            elif typ == "l_const": # Konstante
                res = n.get("wert", "")
            
            elif typ == "l_and":
                v1 = self._wert_zu_bool(_get_input_val(nid, "in1"))
                v2 = self._wert_zu_bool(_get_input_val(nid, "in2"))
                res = v1 and v2
                
            elif typ == "l_or":
                v1 = self._wert_zu_bool(_get_input_val(nid, "in1"))
                v2 = self._wert_zu_bool(_get_input_val(nid, "in2"))
                res = v1 or v2
                
            elif typ == "l_not":
                v = self._wert_zu_bool(_get_input_val(nid, "in"))
                res = not v
                
            elif typ == "l_cmp":
                v1 = _get_input_val(nid, "in1")
                op = n.get("operator", "=")
                v2 = n.get("wert", "") # Entweder fester Wert...
                if not v2: v2 = _get_input_val(nid, "in2") # ...oder zweiter Input
                res = self._check_bedingung(v1, op, v2)
                
            elif typ == "l_result": # End-Knoten
                res = self._wert_zu_bool(_get_input_val(nid, "in"))

            memo[nid] = res
            return res

        # Das Ergebnis ist der Wert des "Result" Nodes
        result_node = next((n for n in nodes.values() if n["typ"] == "l_result"), None)
        if not result_node: return False
        return _eval_node(result_node["id"])

    def _check_bedingung(self, ist, operator, soll):
        """Hilfsmethode für numerische und String-Vergleiche."""
        try:
            a = float(str(ist).replace(",", "."))
            b = float(str(soll).replace(",", "."))
            if   operator == ">":          return a > b
            elif operator == "<":          return a < b
            elif operator == ">=":         return a >= b
            elif operator == "<=":         return a <= b
            elif operator in ("=", "=="):  return a == b
            elif operator == "!=":         return a != b
        except (ValueError, AttributeError):
            ist_str  = str(ist).lower()
            soll_str = str(soll).lower()
            if   operator in ("=", "=="): return ist_str == soll_str
            elif operator == "!=":        return ist_str != soll_str
        return False

    def _wert_zu_bool(self, wert):
        """Konvertiert verschiedene Formate (1, 'true', 'wahr', 'on') in echtes Boolean."""
        if isinstance(wert, bool):
            return wert
        s = str(wert).lower().strip()
        if s in ("1", "true", "wahr", "on", "yes", "ja", "x"):
            return True
        return False

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
                            log_func=None, laeuft_func=None, ocr_func=None, ist_master=False):
        """Traversiert den Workflow-Graphen ab dem Start-Node.
        Gibt True bei erfolgreichem Durchlauf zurück, False bei Fehler oder Abbruch.
        """
        # Graphen suchen (in Master- oder Normal-Liste)
        if ist_master:
            graph = self.master_workflows.get(name)
        else:
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
