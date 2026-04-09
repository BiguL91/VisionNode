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
