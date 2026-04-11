"""Lädt alle QSS-Dateien aus dem style/ Ordner und gibt sie kombiniert zurück."""
import os

_STYLE_DIR = os.path.join(os.path.dirname(__file__), "style")

# Reihenfolge ist wichtig: base zuerst, dann spezifische (CSS-Kaskade)
_ORDER = ["base", "scrollbars", "buttons", "inputs", "tables", "panels", "dialogs"]


def load() -> str:
    parts = []
    # Zuerst die definierten Dateien in Reihenfolge
    for name in _ORDER:
        path = os.path.join(_STYLE_DIR, f"{name}.qss")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                parts.append(f.read())
    # Danach alle übrigen .qss Dateien (z.B. community themes)
    ordered = {f"{n}.qss" for n in _ORDER}
    for fname in sorted(os.listdir(_STYLE_DIR)):
        if fname.endswith(".qss") and fname not in ordered:
            with open(os.path.join(_STYLE_DIR, fname), encoding="utf-8") as f:
                parts.append(f.read())
    return "\n".join(parts)
