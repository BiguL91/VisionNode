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

    # ── OCR Template (gruppiert nach Kategorie → Gruppe → Template) ──────────
    try:
        t_konfig = bot.ocr_engine.template_ocr_konfigurationen()
        # Struktur: { kategorie: { gruppe: { template: [ (display, key) ] } } }
        grouped: dict[str, dict[str, dict[str, list]]] = {}
        
        for entry_key, cfg in t_konfig.items():
            tmpl = cfg.get("template", "?")
            try:
                # Priorität 1: Die Gruppe aus dem Template-Objekt (basiert auf Dateipfad)
                t_obj = bot.template_engine.templates.get(tmpl, {})
                # Priorität 2: Die Gruppe aus den Settings (logische Gruppe)
                t_set = bot.template_engine.settings.get(tmpl, {})
                
                kat = (t_set.get("kategorie") or "Allgemein").capitalize()
                
                # Wenn im Template-Objekt eine Gruppe steht (Pfad), nehmen wir die.
                # Sonst die aus den Settings.
                grp = t_obj.get("gruppe") or t_set.get("gruppe") or "Keine Gruppe"
            except Exception:
                kat = "Allgemein"
                grp = "Keine Gruppe"
                
            display = entry_key[len(tmpl) + 1:] if entry_key.startswith(tmpl + "_") else entry_key
            
            if kat not in grouped: grouped[kat] = {}
            if grp not in grouped[kat]: grouped[kat][grp] = {}
            if tmpl not in grouped[kat][grp]: grouped[kat][grp][tmpl] = []
            
            grouped[kat][grp][tmpl].append((display, entry_key))

        # Sortieren
        sorted_data = {}
        for kat, grp_dict in sorted(grouped.items(), key=lambda x: x[0].casefold()):
            sorted_data[kat] = {}
            for grp, tmpl_dict in sorted(grp_dict.items(), key=lambda x: x[0].casefold()):
                sorted_data[kat][grp] = {}
                for tmpl, entries in sorted(tmpl_dict.items(), key=lambda x: x[0].casefold()):
                    sorted_data[kat][grp][tmpl] = sorted(entries, key=lambda e: e[0].casefold())
        
        data["ocr_template"] = sorted_data
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
                eintraege = []
                for z in zeilen:
                    fn = z["name"]
                    # Präfix entfernen für Anzeige
                    dn = fn[4:] if fn.startswith("[W] ") or fn.startswith("[T] ") else fn
                    eintraege.append((dn, fn))
                
                if eintraege:
                    data["db_global"][name] = sorted(eintraege, key=lambda e: e[0].casefold())

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
        if var.startswith("[W] ") or var.startswith("[T] "):
            var = var[4:]
        return var

    return full_value


def _get_or_create_sub_menu(parent_menu, path_parts: list[str], icon: str = "📦") -> QMenu:
    """Findet oder erstellt rekursiv ein Untermenü für eine Liste von Pfad-Teilen."""
    current = parent_menu
    for part in path_parts:
        if not part: continue
        # Suchen ob bereits ein Menü mit diesem Namen existiert
        found = False
        for action in current.actions():
            if action.menu() and action.text() == f"{icon} {part}":
                current = action.menu()
                found = True
                break
        if not found:
            current = current.addMenu(f"{icon} {part}")
    return current


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
            for kat, grp_dict in ocr_data.items():
                k_sub = o_sub.addMenu(f"📁 {kat}")
                for grp, tmpl_dict in grp_dict.items():
                    # Untergruppen-Pfad auflösen (z.B. "Kampf/PVP" -> zwei Menü-Ebenen)
                    if grp != "Keine Gruppe":
                        parts = grp.replace("\\", "/").split("/")
                        g_sub = _get_or_create_sub_menu(k_sub, parts)
                    else:
                        # Falls es andere Gruppen in dieser Kategorie gibt, "Keine Gruppe" separat zeigen
                        g_sub = k_sub.addMenu("📦 (ohne Gruppe)") if len(grp_dict) > 1 else k_sub
                        
                    for tmpl, entries in tmpl_dict.items():
                        t_sub = g_sub.addMenu(f"🖼 {tmpl}")
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
