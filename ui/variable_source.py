"""
Zentrale Datenquelle für alle Variable-Picker im UI.

get_picker_data(bot)  → strukturiertes Dict mit allen wählbaren Variablen
build_var_menu(...)   → füllt ein QMenu aus diesem Dict
display_name(...)     → kurzen Anzeige-Namen aus gespeichertem Wert ermitteln
"""
from __future__ import annotations


def _resolve_bot(bot):
    """Gibt immer die TilesBotApp-Instanz zurück, egal ob bot das Fenster oder die App ist."""
    if bot is None:
        return None
    if hasattr(bot, "app"):
        return bot.app
    return bot


def get_picker_data(bot) -> dict:
    """
    Gibt alle wählbaren Variablen strukturiert zurück.

    Rückgabe:
        {
            "state":        [name, ...]
            "ocr_template": { kategorie: { template: [(display, entry_key), ...] } }
            "db_global":    { liste: [(display, stored_key), ...] }   # Timer-Listen
            "db_standard":  { liste: [var_name, ...] }                # Daten-Listen
        }
    """
    bot = _resolve_bot(bot)

    data: dict = {
        "state":        [],
        "ocr_template": {},
        "db_global":    {},
        "db_standard":  {},
    }

    # ── State ────────────────────────────────────────────────────────────────
    try:
        data["state"] = sorted(bot.state.game_states.keys(), key=str.casefold)
    except Exception:
        pass

    # ── OCR Template (gruppiert nach Kategorie → Template) ───────────────────
    try:
        t_konfig = bot.ocr_engine.template_ocr_konfigurationen()
        grouped: dict[str, dict[str, list]] = {}
        for entry_key, cfg in t_konfig.items():
            tmpl = cfg.get("template", "?")
            try:
                s = bot.template_engine.settings
                kat = (s.get(tmpl, {}).get("kategorie")
                       or s.get(tmpl.replace("_", "-"), {}).get("kategorie")
                       or "Allgemein")
                kat = kat.capitalize()
            except Exception:
                kat = "Allgemein"
            display = entry_key[len(tmpl) + 1:] if entry_key.startswith(tmpl + "_") else entry_key
            grouped.setdefault(kat, {}).setdefault(tmpl, []).append((display, entry_key))

        data["ocr_template"] = {
            kat: {
                tmpl: sorted(entries, key=lambda e: e[0].casefold())
                for tmpl, entries in sorted(tmpl_dict.items(), key=lambda x: x[0].casefold())
            }
            for kat, tmpl_dict in sorted(grouped.items(), key=lambda x: x[0].casefold())
        }
    except Exception:
        pass

    # ── DB ───────────────────────────────────────────────────────────────────
    try:
        from core import daten_manager as dm
        listen = sorted(dm.alle_listen(), key=lambda l: l["name"].casefold())
        for l in listen:
            typ  = l.get("typ", "")
            name = l["name"]
            lid  = l["id"]

            if typ == "timer":
                zeilen = dm.zeilen_der_liste(lid)
                wert = [
                    (z["name"][4:], z["name"])
                    for z in zeilen if z["name"].startswith("[W] ")
                ]
                if wert:
                    data["db_global"][name] = sorted(wert, key=lambda e: e[0].casefold())

            elif typ == "daten":
                trans   = [t["name"] for t in dm.transformationen_der_liste(lid)]
                berechn = [b["name"] for b in dm.berechnungen_der_liste(lid)]
                vars_ = sorted(set(trans + berechn), key=str.casefold)
                if vars_:
                    data["db_standard"][name] = vars_
    except Exception:
        pass

    return data


def display_name(full_value: str, picker_data: dict | None = None) -> str:
    """
    Gibt den kurzen Anzeige-Namen für einen gespeicherten Variablen-Wert zurück.
    Beispiele:
        "state::IsRunning"                    → "IsRunning"
        "ocr::Allianz-Hilfe_Anzahl"           → "Anzahl"  (wenn picker_data übergeben)
        "db::MeineListe::[W] Wert"            → "Wert"
        "db::MeineListe::Transformation"      → "Transformation"
    """
    if not full_value or full_value in ("Bitte wählen...", "Timer wählen..."):
        return full_value or ""

    if full_value.startswith("state::"):
        return full_value[7:]

    if full_value.startswith("ocr::"):
        entry_key = full_value[5:]
        if picker_data:
            for tmpl_dict in picker_data.get("ocr_template", {}).values():
                for entries in tmpl_dict.values():
                    for disp, key in entries:
                        if key == entry_key:
                            return disp
        # Fallback: Teil nach letztem "_"
        if "_" in entry_key:
            return entry_key.rsplit("_", 1)[-1]
        return entry_key

    if full_value.startswith("db::"):
        rest = full_value[4:]
        parts = rest.split("::", 1)
        var = parts[1] if len(parts) == 2 else rest
        if var.startswith("[W] "):
            var = var[4:]
        return var

    return full_value


def build_var_menu(menu, data: dict, on_select,
                   include_state=True, include_ocr=True, include_db=True):
    """
    Füllt ein QMenu mit den strukturierten Variablen aus get_picker_data().

    on_select(full_value: str, display: str) wird bei Auswahl aufgerufen.
    """
    # ── State ────────────────────────────────────────────────────────────────
    if include_state and data.get("state"):
        s_sub = menu.addMenu("🚩 State")
        for name in data["state"]:
            s_sub.addAction(name, lambda x=name: on_select(f"state::{x}", x))
        if s_sub.isEmpty():
            s_sub.addAction("(keine)").setEnabled(False)

    # ── OCR Template ─────────────────────────────────────────────────────────
    if include_ocr:
        ocr_data = data.get("ocr_template", {})
        o_sub = menu.addMenu("🔤 OCR")
        if ocr_data:
            for kat, tmpl_dict in ocr_data.items():
                k_sub = o_sub.addMenu(f"📁 {kat}")
                for tmpl, entries in tmpl_dict.items():
                    t_sub = k_sub.addMenu(f"🖼 {tmpl}")
                    for disp, entry_key in entries:
                        t_sub.addAction(
                            disp,
                            lambda d=disp, k=entry_key: on_select(f"ocr::{k}", d)
                        )
        else:
            o_sub.addAction("(keine)").setEnabled(False)

    # ── DB Global (Timer-Listen) ──────────────────────────────────────────────
    if include_db:
        db_global = data.get("db_global", {})
        db_std    = data.get("db_standard", {})

        if db_global or db_std:
            db_menu = menu.addMenu("📊 Daten")

            g_sub = db_menu.addMenu("🌐 Global")
            if db_global:
                for liste, entries in db_global.items():
                    l_sub = g_sub.addMenu(f"⏳ {liste}")
                    for disp, stored in entries:
                        l_sub.addAction(
                            disp,
                            lambda d=disp, ln=liste, sn=stored: on_select(f"db::{ln}::{sn}", d)
                        )
            else:
                g_sub.addAction("(keine)").setEnabled(False)

            s_sub = db_menu.addMenu("📋 Standard")
            if db_std:
                for liste, vars_ in db_std.items():
                    l_sub = s_sub.addMenu(liste)
                    for v in vars_:
                        l_sub.addAction(
                            v,
                            lambda d=v, ln=liste: on_select(f"db::{ln}::{d}", d)
                        )
            else:
                s_sub.addAction("(keine)").setEnabled(False)
