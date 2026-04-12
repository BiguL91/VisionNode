"""
Sprach-System für TilesBot.

Verwendung:
    import lang
    lang.load("de")          # einmalig beim Start
    lang.t("btn_save")       # → "Speichern"
    lang.t("state_delete_confirm", name="foo")  # → '"foo" wirklich löschen?'
"""
import json
import os

_LANG_DIR = os.path.dirname(__file__)
_strings: dict = {}
_current: str = "de"


def load(code: str = "de") -> None:
    """Lädt die Sprachdatei. Fällt auf 'de' zurück wenn nicht gefunden."""
    global _strings, _current
    path = os.path.join(_LANG_DIR, f"{code}.json")
    if not os.path.exists(path):
        path = os.path.join(_LANG_DIR, "de.json")
        code = "de"
    with open(path, encoding="utf-8") as f:
        _strings = json.load(f)
    _current = code


def t(key: str, **kwargs) -> str:
    """Gibt den übersetzten String zurück. Fallback: der Key selbst."""
    text = _strings.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def current() -> str:
    """Gibt den aktuellen Sprachcode zurück (z.B. 'de', 'en')."""
    return _current


def available() -> list[str]:
    """Gibt alle verfügbaren Sprachcodes zurück."""
    codes = []
    for fname in os.listdir(_LANG_DIR):
        if fname.endswith(".json") and not fname.startswith("_"):
            codes.append(fname[:-5])
    # community Unterordner
    community_dir = os.path.join(_LANG_DIR, "community")
    if os.path.isdir(community_dir):
        for fname in os.listdir(community_dir):
            if fname.endswith(".json"):
                codes.append(f"community/{fname[:-5]}")
    return sorted(codes)


# Standardmäßig Deutsch laden
load("de")
