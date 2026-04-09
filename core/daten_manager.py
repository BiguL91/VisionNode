import sqlite3
import os
import time

DB_PFAD = os.path.join(os.path.dirname(__file__), "..", "daten_listen.db")


def _verbinden():
    """Öffnet eine Verbindung zur SQLite-Datenbank."""
    conn = sqlite3.connect(os.path.abspath(DB_PFAD))
    conn.row_factory = sqlite3.Row
    return conn


def datenbank_initialisieren():
    """Erstellt alle Tabellen falls noch nicht vorhanden."""
    with _verbinden() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listen (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT NOT NULL UNIQUE,
                update_intervall  INTEGER NOT NULL DEFAULT 30
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spalten (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                listen_id INTEGER NOT NULL REFERENCES listen(id) ON DELETE CASCADE,
                name      TEXT NOT NULL,
                typ       TEXT NOT NULL DEFAULT 'zahl',
                ocr_var   TEXT,
                formel    TEXT,
                position  INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS zeilen (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                listen_id INTEGER NOT NULL REFERENCES listen(id) ON DELETE CASCADE,
                name      TEXT NOT NULL,
                position  INTEGER NOT NULL DEFAULT 0,
                UNIQUE(listen_id, name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transformationen (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                listen_id   INTEGER NOT NULL REFERENCES listen(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                ocr_var     TEXT NOT NULL,
                typ         TEXT NOT NULL DEFAULT 'einheit_zu_zahl',
                UNIQUE(listen_id, name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS berechnungen (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                listen_id   INTEGER NOT NULL REFERENCES listen(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                formel_json TEXT NOT NULL DEFAULT '[]',
                typ         TEXT NOT NULL DEFAULT 'ausgabe',
                UNIQUE(listen_id, name)
            )
        """)
        # typ-Spalte nachrüsten falls DB schon existiert
        try:
            conn.execute("ALTER TABLE berechnungen ADD COLUMN typ TEXT NOT NULL DEFAULT 'ausgabe'")
            conn.commit()
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS werte_cache (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                listen_id      INTEGER NOT NULL REFERENCES listen(id) ON DELETE CASCADE,
                var_name       TEXT NOT NULL,
                wert           TEXT,
                gespeichert_am REAL,
                UNIQUE(listen_id, var_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eintraege (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                listen_id   INTEGER NOT NULL REFERENCES listen(id) ON DELETE CASCADE,
                zeile_name  TEXT NOT NULL,
                spalte_id   INTEGER NOT NULL REFERENCES spalten(id) ON DELETE CASCADE,
                wert        TEXT,
                gescant_am  REAL,
                UNIQUE(listen_id, zeile_name, spalte_id)
            )
        """)
        conn.commit()


# ── Listen ──────────────────────────────────────────────────────────────────

def liste_erstellen(name, update_intervall=30):
    """Legt eine neue Liste an. Gibt die ID zurück."""
    with _verbinden() as conn:
        cur = conn.execute(
            "INSERT INTO listen (name, update_intervall) VALUES (?, ?)",
            (name, update_intervall)
        )
        conn.commit()
        return cur.lastrowid


def liste_umbenennen(listen_id, neuer_name):
    with _verbinden() as conn:
        conn.execute("UPDATE listen SET name=? WHERE id=?", (neuer_name, listen_id))
        conn.commit()


def liste_intervall_setzen(listen_id, sekunden):
    with _verbinden() as conn:
        conn.execute("UPDATE listen SET update_intervall=? WHERE id=?", (sekunden, listen_id))
        conn.commit()


def liste_loeschen(listen_id):
    with _verbinden() as conn:
        conn.execute("DELETE FROM listen WHERE id=?", (listen_id,))
        conn.commit()


def alle_listen():
    """Gibt alle Listen zurück als Liste von dicts."""
    with _verbinden() as conn:
        rows = conn.execute("SELECT * FROM listen ORDER BY id").fetchall()
        return [dict(r) for r in rows]


# ── Zeilen ──────────────────────────────────────────────────────────────────

def zeile_hinzufuegen(listen_id, name):
    """Legt eine neue Zeile an. Gibt die ID zurück."""
    with _verbinden() as conn:
        pos = conn.execute(
            "SELECT COUNT(*) FROM zeilen WHERE listen_id=?", (listen_id,)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT OR IGNORE INTO zeilen (listen_id, name, position) VALUES (?,?,?)",
            (listen_id, name, pos)
        )
        conn.commit()
        return cur.lastrowid


def zeile_umbenennen(zeile_id, neuer_name):
    with _verbinden() as conn:
        conn.execute("UPDATE zeilen SET name=? WHERE id=?", (neuer_name, zeile_id))
        conn.commit()


def zeile_loeschen(zeile_id):
    with _verbinden() as conn:
        # Zugehörige Einträge werden über zeile_name referenziert → manuell löschen
        zeile = conn.execute("SELECT listen_id, name FROM zeilen WHERE id=?", (zeile_id,)).fetchone()
        if zeile:
            conn.execute(
                "DELETE FROM eintraege WHERE listen_id=? AND zeile_name=?",
                (zeile["listen_id"], zeile["name"])
            )
        conn.execute("DELETE FROM zeilen WHERE id=?", (zeile_id,))
        conn.commit()


def zeilen_der_liste(listen_id):
    """Gibt alle Zeilen einer Liste sortiert nach Position zurück."""
    with _verbinden() as conn:
        rows = conn.execute(
            "SELECT * FROM zeilen WHERE listen_id=? ORDER BY position", (listen_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Spalten ─────────────────────────────────────────────────────────────────

def spalte_hinzufuegen(listen_id, name, typ="zahl", ocr_var=None, formel=None):
    """Fügt eine Spalte zur Liste hinzu. Gibt die Spalten-ID zurück."""
    with _verbinden() as conn:
        pos = conn.execute(
            "SELECT COUNT(*) FROM spalten WHERE listen_id=?", (listen_id,)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO spalten (listen_id, name, typ, ocr_var, formel, position) VALUES (?,?,?,?,?,?)",
            (listen_id, name, typ, ocr_var, formel, pos)
        )
        conn.commit()
        return cur.lastrowid


def spalte_aktualisieren(spalte_id, name=None, typ=None, ocr_var=None, formel=None):
    """Aktualisiert einzelne Felder einer Spalte."""
    with _verbinden() as conn:
        if name is not None:
            conn.execute("UPDATE spalten SET name=? WHERE id=?", (name, spalte_id))
        if typ is not None:
            conn.execute("UPDATE spalten SET typ=? WHERE id=?", (typ, spalte_id))
        if ocr_var is not None:
            conn.execute("UPDATE spalten SET ocr_var=? WHERE id=?", (ocr_var, spalte_id))
        if formel is not None:
            conn.execute("UPDATE spalten SET formel=? WHERE id=?", (formel, spalte_id))
        conn.commit()


def spalte_loeschen(spalte_id):
    with _verbinden() as conn:
        conn.execute("DELETE FROM spalten WHERE id=?", (spalte_id,))
        conn.commit()


def spalten_der_liste(listen_id):
    """Gibt alle Spalten einer Liste sortiert nach Position zurück."""
    with _verbinden() as conn:
        rows = conn.execute(
            "SELECT * FROM spalten WHERE listen_id=? ORDER BY position", (listen_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Einträge (Werte schreiben/lesen) ────────────────────────────────────────

def wert_schreiben(listen_id, zeile_name, spalte_id, wert):
    """Schreibt einen Wert in die Datenbank (upsert). Setzt Timestamp auf jetzt."""
    jetzt = time.time()
    with _verbinden() as conn:
        conn.execute("""
            INSERT INTO eintraege (listen_id, zeile_name, spalte_id, wert, gescant_am)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(listen_id, zeile_name, spalte_id)
            DO UPDATE SET wert=excluded.wert, gescant_am=excluded.gescant_am
        """, (listen_id, zeile_name, spalte_id, str(wert), jetzt))
        conn.commit()


def liste_lesen(listen_id):
    """
    Gibt alle Einträge einer Liste zurück.
    Rückgabe: Liste von dicts mit zeile_name + allen Spaltenwerten + gescant_am.
    """
    spalten = spalten_der_liste(listen_id)
    if not spalten:
        return []

    with _verbinden() as conn:
        rows = conn.execute(
            "SELECT * FROM eintraege WHERE listen_id=?", (listen_id,)
        ).fetchall()

    # Gruppieren nach zeile_name
    zeilen = {}
    for row in rows:
        zn = row["zeile_name"]
        if zn not in zeilen:
            zeilen[zn] = {"zeile_name": zn, "gescant_am": row["gescant_am"]}
        # Spaltenname ermitteln
        for sp in spalten:
            if sp["id"] == row["spalte_id"]:
                zeilen[zn][sp["name"]] = row["wert"]
                zeilen[zn]["gescant_am"] = max(zeilen[zn]["gescant_am"], row["gescant_am"] or 0)
                break

    return list(zeilen.values())


def berechneten_wert_ermitteln(zeile, spalte, alle_zeilen_werte):
    """
    Berechnet einen Formel-Wert zur Laufzeit.
    Formel: 'vorrat + prod * elapsed_h'
    Verfügbare Variablen: alle Spaltenwerte der Zeile + 'elapsed_h' (Stunden seit letztem Scan).
    """
    formel = spalte.get("formel", "")
    if not formel:
        return ""
    try:
        elapsed_s = time.time() - (zeile.get("gescant_am") or time.time())
        elapsed_h = elapsed_s / 3600.0
        kontext = {k: _zu_zahl(v) for k, v in alle_zeilen_werte.items()}
        kontext["elapsed_h"] = elapsed_h
        kontext["elapsed_s"] = elapsed_s
        ergebnis = eval(formel, {"__builtins__": {}}, kontext)  # noqa: S307
        return str(round(ergebnis, 2))
    except Exception:
        return "?"


def _zu_zahl(wert):
    """Versucht einen String in float umzuwandeln."""
    try:
        return float(str(wert).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


# ── Werte-Cache ─────────────────────────────────────────────────────────────

def cache_schreiben(listen_id, var_name, wert):
    """Speichert einen Wert im Cache (upsert). Ungültige Werte werden ignoriert."""
    if str(wert) in ("", "—", "?") or wert is None:
        return

    with _verbinden() as conn:
        conn.execute("""
            INSERT INTO werte_cache (listen_id, var_name, wert, gespeichert_am)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(listen_id, var_name)
            DO UPDATE SET wert=excluded.wert, gespeichert_am=excluded.gespeichert_am
        """, (listen_id, var_name, str(wert), time.time()))
        conn.commit()


def cache_lesen(listen_id):
    """Gibt alle gecachten Werte einer Liste als dict zurück: var_name → wert."""
    with _verbinden() as conn:
        rows = conn.execute(
            "SELECT var_name, wert FROM werte_cache WHERE listen_id=?", (listen_id,)
        ).fetchall()
    return {r["var_name"]: r["wert"] for r in rows}


# ── Berechnungen ────────────────────────────────────────────────────────────

def berechnung_hinzufuegen(listen_id, name, typ="ausgabe"):
    """Legt eine neue leere Berechnung an. Gibt die ID zurück."""
    import json
    with _verbinden() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO berechnungen (listen_id, name, formel_json, typ) VALUES (?,?,?,?)",
            (listen_id, name, json.dumps([{"var": ""}]), typ)
        )
        conn.commit()
        return cur.lastrowid


def berechnung_aktualisieren(berech_id, name=None, formel_json=None, typ=None):
    import json
    with _verbinden() as conn:
        if name is not None:
            conn.execute("UPDATE berechnungen SET name=? WHERE id=?", (name, berech_id))
        if formel_json is not None:
            conn.execute("UPDATE berechnungen SET formel_json=? WHERE id=?",
                         (json.dumps(formel_json), berech_id))
        if typ is not None:
            conn.execute("UPDATE berechnungen SET typ=? WHERE id=?", (typ, berech_id))
        conn.commit()


def berechnung_loeschen(berech_id):
    with _verbinden() as conn:
        conn.execute("DELETE FROM berechnungen WHERE id=?", (berech_id,))
        conn.commit()


def berechnungen_der_liste(listen_id):
    """Gibt alle Berechnungen einer Liste zurück."""
    import json
    with _verbinden() as conn:
        rows = conn.execute(
            "SELECT * FROM berechnungen WHERE listen_id=? ORDER BY id", (listen_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["formel_json"] = json.loads(d["formel_json"])
        except Exception:
            d["formel_json"] = [{"var": ""}]
        result.append(d)
    return result


def berechnung_auswerten(formel_json, verfuegbare_werte, update_intervall=30):
    """
    Wertet eine Formel aus.
    Gibt den Ergebnis-String zurück oder "?" bei Fehlern/fehlenden Variablen.
    """
    if not formel_json:
        return "—"

    ausdruck_teile = []
    for teil in formel_json:
        if "op" in teil:
            ausdruck_teile.append(teil["op"])
        elif "var" in teil:
            var_name = teil["var"]
            if var_name == "update_intervall":
                ausdruck_teile.append(str(update_intervall))
            elif var_name == "":
                return "?"
            else:
                wert = verfuegbare_werte.get(var_name)
                # Strikte Prüfung: Wenn eine Variable fehlt oder ungültig ist,
                # kann die gesamte Formel nicht berechnet werden.
                if str(wert) in ("", "—", "?") or wert is None:
                    return "?"
                try:
                    ausdruck_teile.append(str(float(str(wert).replace(",", "."))))
                except (ValueError, TypeError):
                    return "?"
        elif "zahl" in teil:
            ausdruck_teile.append(str(teil["zahl"]))

    if not ausdruck_teile:
        return "?"

    ausdruck = " ".join(ausdruck_teile)
    try:
        ergebnis = eval(ausdruck, {"__builtins__": {}}, {})  # noqa: S307
        if ergebnis == int(ergebnis):
            return str(int(ergebnis))
        return str(round(ergebnis, 2))
    except Exception:
        return "?"


# ── Transformationen ─────────────────────────────────────────────────────────

def transformation_hinzufuegen(listen_id, name, ocr_var, typ="einheit_zu_zahl"):
    """Legt eine neue Transformation an. Gibt die ID zurück."""
    with _verbinden() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO transformationen (listen_id, name, ocr_var, typ) VALUES (?,?,?,?)",
            (listen_id, name, ocr_var, typ)
        )
        conn.commit()
        return cur.lastrowid


def transformation_aktualisieren(trans_id, name=None, ocr_var=None, typ=None):
    with _verbinden() as conn:
        if name is not None:
            conn.execute("UPDATE transformationen SET name=? WHERE id=?", (name, trans_id))
        if ocr_var is not None:
            conn.execute("UPDATE transformationen SET ocr_var=? WHERE id=?", (ocr_var, trans_id))
        if typ is not None:
            conn.execute("UPDATE transformationen SET typ=? WHERE id=?", (typ, trans_id))
        conn.commit()


def transformation_loeschen(trans_id):
    with _verbinden() as conn:
        conn.execute("DELETE FROM transformationen WHERE id=?", (trans_id,))
        conn.commit()


def transformationen_der_liste(listen_id):
    """Gibt alle Transformationen einer Liste zurück."""
    with _verbinden() as conn:
        rows = conn.execute(
            "SELECT * FROM transformationen WHERE listen_id=? ORDER BY id", (listen_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def transformation_anwenden(rohwert, typ):
    """
    Wendet eine Transformation auf einen Rohwert an.
    Gibt den transformierten Wert als String zurück.
    """
    if rohwert is None:
        return "—"
    rohwert = str(rohwert).strip()

    if typ == "einheit_zu_zahl":
        return _einheit_zu_zahl(rohwert)

    return rohwert


def _einheit_zu_zahl(text):
    """
    Wandelt Spielwerte mit Einheit in Zahlen um.
    Beispiele: "23.97Mio." → "23970000", "1.5K" → "1500", "450" → "450"
    """
    import re
    if not text:
        return "—"

    # 1. Zahl und Einheit trennen
    # Wir suchen nach der ersten Zahl (inkl. Vorzeichen, Trennern) 
    # und dem was danach kommt (die Einheit)
    match = re.search(r"([+-]?[\d,.]+)\s*([a-zA-Z.]+)?", text)
    if not match:
        return text

    num_str = match.group(1)
    unit_str = (match.group(2) or "").upper().rstrip(".")

    # 2. Number-String bereinigen
    # Wenn sowohl Punkt als auch Komma vorkommen:
    if "." in num_str and "," in num_str:
        # Der letzte ist wahrscheinlich der Dezimaltrenner
        if num_str.rfind(".") > num_str.rfind(","):
            num_str = num_str.replace(",", "")  # Komma ist Tausender
        else:
            num_str = num_str.replace(".", "")  # Punkt ist Tausender
            num_str = num_str.replace(",", ".")  # Komma zu Punkt
    # Wenn nur ein Typ vorkommt, aber mehrfach (Tausendertrenner):
    elif num_str.count(".") > 1:
        num_str = num_str.replace(".", "")
    elif num_str.count(",") > 1:
        num_str = num_str.replace(",", "")
    # Wenn nur einer vorkommt, und zwar einmal:
    # Bei Spielwerten wie "27,10" ist das Komma fast immer der Dezimaltrenner
    else:
        num_str = num_str.replace(",", ".")

    try:
        zahl = float(num_str)
    except ValueError:
        return text

    # 3. Faktor anwenden
    faktoren = {
        "K": 1_000,
        "T": 1_000,
        "M": 1_000_000,
        "MIO": 1_000_000,
        "MRD": 1_000_000_000,
        "B": 1_000_000_000,
    }

    faktor = faktoren.get(unit_str, 1)
    ergebnis = zahl * faktor

    # Ganzzahl wenn möglich
    if ergebnis == int(ergebnis):
        return str(int(ergebnis))
    return str(round(ergebnis, 2))
