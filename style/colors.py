"""Zentrale Farb-Konstanten für QPainter-Code.
QSS kann keine Python-Variablen lesen — diese Datei ist der einzige Ort
wo Farben für custom paintEvent-Methoden definiert werden.
"""

# ── Canvas ────────────────────────────────────────────────────────────────────
CANVAS_BG = "#1a1a1a"
NODE_BG    = "#2a2a2a"

# ── Node-Typ-Farben (Workflow-Editor) ─────────────────────────────────────────
NODE_FARBEN = {
    "start":             "#2ea043",
    "suche":             "#1e88e5",
    "suche_optional":    "#00897b",
    "klick":             "#fb8c00",
    "warten":            "#546e7a",
    "zurueck":           "#8e24aa",
    "home":              "#8e24aa",
    "bedingung":         "#f9a825",
    "call_workflow":     "#673ab7",
    "priority_selector": "#fbc02d",
    "set_timer":         "#e91e63",
    "set_value":         "#d81b60",
    "loop":              "#00796b",
    "suche_klick":       "#039be5",
}

# ── Port-Farben (Workflow-Editor & FUP) ───────────────────────────────────────
PORT_FARBEN = {
    "out":     "#aaaaaa",
    "success": "#4caf50",
    "failure": "#ef5350",
    "true":    "#4caf50",
    "false":   "#ef5350",
    "done":    "#9c27b0",
    "else":    "#ff5722",
    "in":      "#777777",
    "body":    "#42a5f5",
}
