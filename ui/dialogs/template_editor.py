import tkinter as tk
from tkinter import ttk, messagebox
import os
import cv2
import numpy as np
import torch
from PIL import Image, ImageTk
from ui.dialogs.roi_editor import ROIEditor
from helpers import cursor_einschraenken, cursor_freigeben

class TemplateEditor:
    def __init__(self, root, bot, bearbeiten_name=None, aktueller_ausschnitt=None,
                 einlern_modus_callback=None, typ=None, kategorie=None):
        self.root = root
        self.bot = bot
        self.template_engine = bot.template_engine
        self.action_engine = bot.action_engine
        self.bearbeiten_name = bearbeiten_name

        # Typ und Kategorie: aus Settings ableiten (beim Bearbeiten) oder aus Parametern
        if bearbeiten_name:
            s = bot.template_engine.settings.get(bearbeiten_name, {})
            self.typ = s.get("typ") or typ or "template"
            self.kategorie = s.get("kategorie") or kategorie or "workflow"
        else:
            self.typ = typ or "template"
            self.kategorie = kategorie or "workflow"

        self.orig_bild_ref = None
        if aktueller_ausschnitt:
            self.orig_bild_ref = aktueller_ausschnitt[0]

        self.einlern_modus_callback = einlern_modus_callback

        self.window = tk.Toplevel(root)
        self.window.title("Template aktualisieren" if bearbeiten_name else "Template speichern")
        self.window.configure(bg="#2d2d2d")
        self.window.resizable(False, False)

        self.canvas_modus = tk.StringVar(value="ignore")
        self.farb_modus_aktiv = False
        self.roi_editor = None

        self.foto_ref = None
        self.foto_hg_ref = None

        self.aktuell_skala = 1.0
        self.aktuell_b = 400
        self.aktuell_h = 200

        self.drag_start = None
        self.live_rect_ids = []
        self.live_rect_ids_hg = []
        self._hg_preview_bbox = None
        self.ignore_regionen = []

        self.ignore_ids_orig = []
        self.ignore_ids_hg = []

        self.klick_zone = [None]
        self.klick_ids_orig = []
        self.klick_ids_hg = []

        self._nach_vorschau_cb = None
        self.initial_scan_regions = []
        if self.bearbeiten_name:
            self.initial_scan_regions = self.template_engine.settings.get(
                self.bearbeiten_name, {}).get("scan_regions", [])

        # Varianten
        self.varianten_liste = []
        self.aktuelle_variante_idx = 0

        # States
        self.condition_states = []  # list of dicts — dict = AND-Gruppe, list = OR zwischen Gruppen
        self.set_states = {}

        self._setup_ui()
        self._load_existing_data()

        self.window.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.window.bind("<Escape>", lambda e: self._schliessen())

        self.window.update_idletasks()
        self.window.geometry(f"+{self.root.winfo_x() + self.root.winfo_width() + 8}+{self.root.winfo_y()}")

    # ------------------------------------------------------------------ #
    #  UI Aufbau                                                           #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        PLACEHOLDER_B, PLACEHOLDER_H = 400, 200

        # --- Tab-Leiste ---
        modus_frame = tk.Frame(self.window, bg="#252525")
        modus_frame.pack(fill=tk.X, padx=16, pady=(12, 0))

        modus_btns = []
        def modus_btn(parent, text, modus_wert, farbe):
            def aktivieren():
                self.canvas_modus.set(modus_wert)
                for _, b in modus_btns:
                    b.config(bg="#3a3a3a", fg="#aaaaaa")
                btn.config(bg=farbe, fg="white")
            btn = tk.Button(parent, text=text, bg="#3a3a3a", fg="#aaaaaa", font=("Segoe UI", 8),
                            relief=tk.FLAT, padx=10, pady=3, cursor="hand2", command=aktivieren)
            return modus_wert, btn

        for txt, mv, fc in [("■ Ignorieren", "ignore", "#555555"), ("⊕ Klick-Zone", "klick", "#e65100")]:
            mv_val, btn_obj = modus_btn(modus_frame, txt, mv, fc)
            modus_btns.append((mv_val, btn_obj))
            btn_obj.pack(side=tk.LEFT, padx=(0, 4))
        modus_btns[0][1].config(bg="#555555", fg="white")

        tk.Button(modus_frame, text="🔍 Scannbereiche", bg="#3a3a3a", fg="#00ff00", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=10, pady=3, cursor="hand2",
                  command=self._roi_fenster_oeffnen).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(modus_frame, text="🔤 OCR", bg="#3a3a3a", fg="#55aaff", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=10, pady=3, cursor="hand2",
                  command=self._ocr_konfigurieren).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(modus_frame, text="🚩 Zustände", bg="#3a3a3a", fg="#ffca28", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=10, pady=3, cursor="hand2",
                  command=self._states_konfigurieren).pack(side=tk.LEFT, padx=(0, 4))

        # --- Canvases ---
        canvases_frame = tk.Frame(self.window, bg="#2d2d2d")
        canvases_frame.pack(padx=16, pady=(6, 0))

        self.canvas = tk.Canvas(canvases_frame, width=PLACEHOLDER_B, height=PLACEHOLDER_H, bg="#1a1a1a",
                                cursor="crosshair", highlightthickness=1, highlightbackground="#3a3a3a")
        self.canvas.pack(pady=(0, 4))
        self.canvas_hg = tk.Canvas(canvases_frame, width=PLACEHOLDER_B, height=PLACEHOLDER_H, bg="#1a1a1a",
                                   cursor="crosshair", highlightthickness=1, highlightbackground="#3a3a3a")
        self.canvas_hg.pack()

        for c in [self.canvas, self.canvas_hg]:
            c.create_text(PLACEHOLDER_B // 2, PLACEHOLDER_H // 2,
                          text="Live-Vorschau" if c == self.canvas else "GPU-Mathematik",
                          fill="#555555", font=("Segoe UI", 10), anchor="center")
            c.bind("<ButtonPress-1>", self._on_press)
            c.bind("<B1-Motion>", self._on_motion)
            c.bind("<ButtonRelease-1>", self._on_release)

        self.info_label = tk.Label(self.window, text="", bg="#2d2d2d", fg="#888888", font=("Segoe UI", 8))
        self.info_label.pack(pady=(3, 0))

        # Ignore/Klick
        ign_btn_f = tk.Frame(self.window, bg="#2d2d2d")
        ign_btn_f.pack(anchor="e", padx=16, pady=(2, 0))
        tk.Button(ign_btn_f, text="↩ Letzten entfernen", bg="#3a3a3a", fg="#aaaaaa", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
                  command=self._ignore_letzten_entfernen).pack(side=tk.RIGHT)

        self.klick_info = tk.Label(self.window, text="Klick-Zone: nicht gesetzt",
                                   bg="#2d2d2d", fg="#555555", font=("Segoe UI", 8))
        self.klick_info.pack(anchor="w", padx=16)
        klick_btn_f = tk.Frame(self.window, bg="#2d2d2d")
        klick_btn_f.pack(anchor="w", padx=16, pady=(0, 4))
        tk.Button(klick_btn_f, text="× Klick entfernen", bg="#3a3a3a", fg="#888888", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                  command=self._klick_entfernen).pack(side=tk.LEFT)

        tk.Frame(self.window, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=16, pady=(8, 0))

        # --- Name ---
        tk.Label(self.window, text="Name:", bg="#2d2d2d", fg="#cccccc", font=("Segoe UI", 9),
                 anchor="w").pack(fill=tk.X, padx=16, pady=(10, 2))

        name_frame = tk.Frame(self.window, bg="#2d2d2d")
        name_frame.pack(fill=tk.X, padx=16)

        self.name_var = tk.StringVar(value=self.bearbeiten_name or "")
        self.name_entry = tk.Entry(name_frame, textvariable=self.name_var, bg="#1a1a1a", fg="#ffffff",
                                   insertbackground="white", font=("Segoe UI", 10), relief=tk.FLAT, bd=4)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.name_entry.focus()

        # Varianten-Navigation (erscheint nur wenn Varianten vorhanden)
        self.varianten_nav_frame = tk.Frame(name_frame, bg="#2d2d2d")
        self.btn_var_prev = tk.Button(self.varianten_nav_frame, text="◀", bg="#3a3a3a", fg="#aaaaaa",
                                      font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                      command=self._variante_prev)
        self.btn_var_prev.pack(side=tk.LEFT)
        self.var_label = tk.Label(self.varianten_nav_frame, text="", bg="#2d2d2d", fg="#888888",
                                  font=("Segoe UI", 8), width=12, anchor="center")
        self.var_label.pack(side=tk.LEFT, padx=2)
        self.btn_var_next = tk.Button(self.varianten_nav_frame, text="▶", bg="#3a3a3a", fg="#aaaaaa",
                                      font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                      command=self._variante_next)
        self.btn_var_next.pack(side=tk.LEFT)

        self.btn_var_del = tk.Button(self.varianten_nav_frame, text="🗑", bg="#3a3a3a", fg="#da3633",
                                     font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                     command=self._variante_loeschen)
        self.btn_var_del.pack(side=tk.LEFT, padx=(4, 0))
        # initial versteckt

        # Versions-Info-Label (Master / Variante X)
        self.version_info_label = tk.Label(self.window, text="", bg="#2d2d2d", fg="#666666",
                                           font=("Segoe UI", 7, "italic"))
        self.version_info_label.pack(anchor="w", padx=16, pady=(2, 0))

        # "Als neue Variante speichern" — nur sichtbar wenn Name bereits existiert
        self.variante_btn_frame = tk.Frame(self.window, bg="#2d2d2d")
        self.btn_neue_variante = tk.Button(
            self.variante_btn_frame, text="➕ Als neue Variante speichern",
            bg="#1a3a5a", fg="#55aaff", font=("Segoe UI", 8), relief=tk.FLAT,
            padx=8, pady=2, cursor="hand2", command=self._als_neue_variante_speichern)
        self.btn_neue_variante.pack(side=tk.LEFT)
        # initial versteckt — wird eingeblendet wenn Name bereits existiert

        # Name-Trace: prüfe ob Name bereits existiert
        self.name_var.trace_add("write", self._on_name_geaendert)

        # --- Gruppe ---
        self._gruppe_frame = tk.Frame(self.window, bg="#2d2d2d")
        self._gruppe_frame.pack(fill=tk.X)

        gruppe_label_text = {
            "aktiv_gruppe": None,                          # versteckt
            "passiv_gruppe": "Übergeordnete Gruppe (optional):",
            "template": "Gruppe: *",
        }.get(self.typ, "Gruppe:")
        self._gruppe_label = tk.Label(self._gruppe_frame, text=gruppe_label_text or "Gruppe:",
                                      bg="#2d2d2d", fg="#cccccc", font=("Segoe UI", 9), anchor="w")
        self._gruppe_label.pack(fill=tk.X, padx=16, pady=(8, 2))

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground="#1a1a1a", background="#3a3a3a",
                        foreground="#ffffff", arrowcolor="#ffffff", bordercolor="#3a3a3a")
        
        # Gruppen filtern: gleiche Kategorie, und nicht man selbst
        alle_gruppen = self.template_engine.get_gruppen(kategorie=self.kategorie)
        gruppen_liste = [g for g in alle_gruppen if g != self.bearbeiten_name]
        
        self.gruppe_var = tk.StringVar(
            value=self.template_engine.settings.get(self.bearbeiten_name, {}).get("gruppe", "")
            if self.bearbeiten_name else "")
        self._gruppe_combo = ttk.Combobox(self._gruppe_frame, textvariable=self.gruppe_var,
                                          values=gruppen_liste, font=("Segoe UI", 10),
                                          style="TCombobox")
        self._gruppe_combo.pack(fill=tk.X, padx=16)

        # Gruppe-Feld initial nach Typ anpassen (wird auch später via _typ_anwenden aktualisiert)
        self._typ_anwenden()

        # --- Schwellwert ---
        self._schwellwert_frame = tk.Frame(self.window, bg="#2d2d2d")
        self._schwellwert_frame.pack(fill=tk.X)
        tk.Label(self._schwellwert_frame, text="Match-Schwellwert:", bg="#2d2d2d", fg="#cccccc",
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X, padx=16, pady=(8, 2))
        self.schwellwert_var = tk.DoubleVar(
            value=self.template_engine.settings.get(self.bearbeiten_name, {}).get("match_schwellwert", 0.85)
            if self.bearbeiten_name else 0.85)
        tk.Scale(self._schwellwert_frame, from_=0.5, to=1.0, resolution=0.01, orient=tk.HORIZONTAL,
                 variable=self.schwellwert_var, bg="#2d2d2d", fg="#cccccc", troughcolor="#1a1a1a",
                 highlightthickness=0, showvalue=True, font=("Segoe UI", 8)).pack(fill=tk.X, padx=16)

        # --- Hintergrund ---
        self.hg_var = tk.BooleanVar(value=True)
        hg_frame = tk.Frame(self.window, bg="#2d2d2d")
        hg_frame.pack(fill=tk.X, padx=16, pady=(10, 0))
        tk.Checkbutton(hg_frame, text="Hintergrund entfernen", variable=self.hg_var, bg="#2d2d2d",
                       fg="#cccccc", selectcolor="#1a1a1a", activebackground="#2d2d2d", font=("Segoe UI", 9),
                       command=self._hg_vorschau_aktualisieren).pack(side=tk.LEFT)
        self.hg_tol_var = tk.IntVar(value=30)
        self.hg_tol_slider = tk.Scale(hg_frame, from_=5, to=80, orient=tk.HORIZONTAL,
                                      variable=self.hg_tol_var, bg="#2d2d2d", fg="#cccccc",
                                      troughcolor="#1a1a1a", highlightthickness=0,
                                      length=130, showvalue=True, font=("Segoe UI", 7))
        self.hg_tol_slider.pack(side=tk.LEFT, padx=(8, 0))
        self.hg_tol_slider.bind("<ButtonRelease-1>", lambda e: self._hg_vorschau_aktualisieren())

        # --- Buttons ---
        btn_leiste = tk.Frame(self.window, bg="#2d2d2d")
        btn_leiste.pack(fill=tk.X, padx=16, pady=16)
        tk.Button(btn_leiste, text="🚀 Test", bg="#3a3a3a", fg="#4488ff", font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=14, pady=4, cursor="hand2",
                  command=self._erkennung_test).pack(side=tk.LEFT)
        tk.Button(btn_leiste, text="Schließen", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
                  command=self._schliessen).pack(side=tk.RIGHT)
        tk.Button(btn_leiste, text="Speichern", bg="#2ea043", fg="white", font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
                  command=self._speichern).pack(side=tk.RIGHT, padx=(0, 4))

    # ------------------------------------------------------------------ #
    #  Laden                                                               #
    # ------------------------------------------------------------------ #

    def _typ_anwenden(self):
        """Zeigt/versteckt UI-Elemente je nach self.typ."""
        verstecken = (self.typ == "aktiv_gruppe")
        
        # Passive Master-Gruppe? (Hat keine übergeordnete Gruppe in Settings)
        if self.typ == "passiv_gruppe" and self.bearbeiten_name:
            s = self.template_engine.settings.get(self.bearbeiten_name, {})
            # Wenn gruppe leer oder gleich Name -> es ist ein Master (kein Parent)
            if s.get("gruppe", "") in ("", self.bearbeiten_name):
                verstecken = True

        if verstecken:
            self._gruppe_frame.pack_forget()
        else:
            # Sicherstellen dass Frame sichtbar ist (nach pack_forget)
            if hasattr(self, "_schwellwert_frame"):
                self._gruppe_frame.pack(fill=tk.X, before=self._schwellwert_frame)
            else:
                self._gruppe_frame.pack(fill=tk.X)
            label_text = "Übergeordnete Gruppe (optional):" if self.typ == "passiv_gruppe" else "Gruppe: *"
            self._gruppe_label.config(text=label_text)

    def _load_existing_data(self):
        if self.bearbeiten_name:
            name = self.bearbeiten_name
            if name in self.template_engine.settings:
                s = self.template_engine.settings[name]
                self.hg_var.set(s.get("hg_entfernen", True))
                self.hg_tol_var.set(s.get("hg_toleranz", 30))
                cs = s.get("condition_states", [])
                self.condition_states = self._migrate_condition_states(cs)
                ss = s.get("set_states", {})
                self.set_states = dict(ss) if isinstance(ss, dict) else {}

            if name in self.template_engine.templates:
                pfad = self.template_engine.templates[name]["pfad"]
                if os.path.exists(pfad):
                    try:
                        tpl = Image.open(pfad).convert("RGB")
                        tw, th = tpl.size
                        self.window.after(50, lambda: self._vorschau_setzen(tpl, tw, th))
                    except Exception:
                        pass

            for r in self.template_engine.settings.get(name, {}).get("ignore_regionen", []):
                self.ignore_regionen.append(tuple(r))

            klick_konfig = self.action_engine.klickzonen_laden()
            if name in klick_konfig:
                k = klick_konfig[name]
                self.klick_zone[0] = (k["klick_rel_x"], k["klick_rel_y"])
                self.klick_info.config(
                    text=f"Klick-Zone: {k['klick_rel_x']:.0f}% / {k['klick_rel_y']:.0f}%", fg="#ff6600")

            self._varianten_erkennen(name)
            self.window.after(120, self._overlays_zeichnen)

        elif self.orig_bild_ref:
            tw, th = self.orig_bild_ref.size
            self.window.after(50, lambda: self._vorschau_setzen(self.orig_bild_ref, tw, th))

    def _varianten_erkennen(self, name):
        basis = name.split("__")[0]
        varianten = sorted(
            [n for n in self.template_engine.templates.keys()
             if n == basis or n.startswith(f"{basis}__")])
        if len(varianten) > 1:
            self.varianten_liste = varianten
            self.aktuelle_variante_idx = varianten.index(name) if name in varianten else 0
        else:
            self.varianten_liste = []
            self.aktuelle_variante_idx = 0
        self._varianten_nav_aktualisieren()

    # ------------------------------------------------------------------ #
    #  Varianten-Navigation                                               #
    # ------------------------------------------------------------------ #

    def _varianten_nav_aktualisieren(self):
        n = len(self.varianten_liste)
        idx = self.aktuelle_variante_idx

        if n > 1:
            self.varianten_nav_frame.pack(side=tk.LEFT, padx=(6, 0))
            ist_master = idx == 0
            if ist_master:
                self.var_label.config(text=f"★ Master  1/{n}", fg="#ffca28")
            else:
                self.var_label.config(text=f"V.{idx + 1}  {idx + 1}/{n}", fg="#aaaaaa")
            self.btn_var_prev.config(state=tk.NORMAL if idx > 0 else tk.DISABLED)
            self.btn_var_next.config(state=tk.NORMAL if idx < n - 1 else tk.DISABLED)
            # Löschen nur für Nicht-Master
            self.btn_var_del.config(state=tk.NORMAL if idx > 0 else tk.DISABLED,
                                    fg="#da3633" if idx > 0 else "#555555")
        else:
            self.varianten_nav_frame.pack_forget()

        self._version_info_aktualisieren()

    def _version_info_aktualisieren(self):
        name = self.bearbeiten_name
        if not name:
            self.version_info_label.config(text="")
            return
        n = len(self.varianten_liste)
        basis = name.split("__")[0]
        if n > 1:
            idx = self.aktuelle_variante_idx
            if idx == 0:
                self.version_info_label.config(
                    text=f"★ Master-Version von \"{basis}\" · {n} Variante(n) gesamt", fg="#ffca28")
            else:
                self.version_info_label.config(
                    text=f"Variante {idx + 1} von \"{basis}\" · {n} gesamt", fg="#888888")
        else:
            self.version_info_label.config(text=f"Keine weiteren Varianten", fg="#555555")

    def _variante_prev(self):
        if self.aktuelle_variante_idx > 0:
            self._variante_wechseln(self.aktuelle_variante_idx - 1)

    def _variante_next(self):
        if self.aktuelle_variante_idx < len(self.varianten_liste) - 1:
            self._variante_wechseln(self.aktuelle_variante_idx + 1)

    def _variante_loeschen(self):
        if self.aktuelle_variante_idx == 0:
            return  # Master darf nicht gelöscht werden
        name = self.varianten_liste[self.aktuelle_variante_idx]
        if not messagebox.askyesno("Variante löschen?", f"Variante \"{name}\" wirklich löschen?",
                                   parent=self.window):
            return
        self.template_engine.template_loeschen(name)
        try:
            self.bot.ocr_engine.template_ocr_alle_loeschen(name)
        except Exception:
            pass
        self.action_engine.klickzone_loeschen(name)
        self.bot._templates_liste_aktualisieren()
        self.bot.app.reload_templates()
        self.bot._timer_panel_aktualisieren()
        self.bot._log(f"Variante gelöscht: \"{name}\"")

        # Zur vorherigen Variante springen und Liste neu aufbauen
        ziel_idx = self.aktuelle_variante_idx - 1
        basis = name.split("__")[0]
        self._varianten_erkennen(basis)
        ziel_idx = min(ziel_idx, len(self.varianten_liste) - 1)
        if self.varianten_liste:
            self._variante_wechseln(ziel_idx)

    def _variante_wechseln(self, idx):
        name = self.varianten_liste[idx]
        self.aktuelle_variante_idx = idx
        self.bearbeiten_name = name
        self.name_var.set(name)

        s = self.template_engine.settings.get(name, {})
        self.hg_var.set(s.get("hg_entfernen", True))
        self.hg_tol_var.set(s.get("hg_toleranz", 30))
        self.schwellwert_var.set(s.get("match_schwellwert", 0.85))
        self.gruppe_var.set(s.get("gruppe", ""))
        cs = s.get("condition_states", [])
        self.condition_states = self._migrate_condition_states(cs)
        ss = s.get("set_states", {})
        self.set_states = dict(ss) if isinstance(ss, dict) else {}
        self.ignore_regionen = [tuple(r) for r in s.get("ignore_regionen", [])]

        klick_konfig = self.action_engine.klickzonen_laden()
        if name in klick_konfig:
            k = klick_konfig[name]
            self.klick_zone[0] = (k["klick_rel_x"], k["klick_rel_y"])
            self.klick_info.config(
                text=f"Klick-Zone: {k['klick_rel_x']:.0f}% / {k['klick_rel_y']:.0f}%", fg="#ff6600")
        else:
            self.klick_zone[0] = None
            self.klick_info.config(text="Klick-Zone: nicht gesetzt", fg="#555555")

        self.initial_scan_regions = s.get("scan_regions", [])
        if self.roi_editor and self.roi_editor.window.winfo_exists():
            self.roi_editor.window.destroy()
            self.roi_editor = None

        if name in self.template_engine.templates:
            pfad = self.template_engine.templates[name]["pfad"]
            if os.path.exists(pfad):
                try:
                    tpl = Image.open(pfad).convert("RGB")
                    tw, th = tpl.size
                    self.orig_bild_ref = tpl
                    self._vorschau_setzen(tpl, tw, th)
                except Exception:
                    pass

        self._varianten_nav_aktualisieren()

    # ------------------------------------------------------------------ #
    #  Name-Trace: existiert Name bereits?                                #
    # ------------------------------------------------------------------ #

    def _on_name_geaendert(self, *_):
        n = self.name_var.get().strip()
        # Varianten-Button anzeigen wenn Name bereits existiert und NICHT das aktuell bearbeitete Template ist
        existiert = n in self.template_engine.templates and n != self.bearbeiten_name
        if existiert:
            self.variante_btn_frame.pack(anchor="w", padx=16, pady=(2, 0))
        else:
            self.variante_btn_frame.pack_forget()

    def _als_neue_variante_speichern(self):
        """Speichert das aktuelle Bild als neue Variante des eingetippten Namens."""
        basis = self.name_var.get().strip()
        if not basis or self.orig_bild_ref is None:
            return

        # Nächste freie Varianten-Nummer finden
        n = 2
        while f"{basis}__{n}" in self.template_engine.templates:
            n += 1
        neuer_name = f"{basis}__{n}"

        entferne_hg = self.hg_var.get()
        hg_toleranz = self.hg_tol_var.get()
        match_s = self.schwellwert_var.get()
        gruppe_name = self.template_engine.settings.get(basis, {}).get("gruppe", basis)

        aktuelle_scan_regions = self.initial_scan_regions
        if self.roi_editor and self.roi_editor.window.winfo_exists():
            aktuelle_scan_regions = self.roi_editor.get_regions()

        self.template_engine.template_speichern(
            neuer_name, self.orig_bild_ref, entferne_hg, list(self.ignore_regionen),
            hintergrund_toleranz=hg_toleranz, gruppe=gruppe_name,
            match_schwellwert=match_s, scan_regions=list(aktuelle_scan_regions),
            condition_states=list(self.condition_states), set_states=dict(self.set_states))

        self.bot._log(f"Neue Variante gespeichert: \"{neuer_name}\"")
        self.bot._templates_liste_aktualisieren()
        self.bot.app.reload_templates()
        self.bot._timer_panel_aktualisieren()

        # Navigations-Update: zur neuen Variante wechseln
        self.bearbeiten_name = neuer_name
        self.name_var.set(neuer_name)
        self._varianten_erkennen(neuer_name)
        self.aktuelle_variante_idx = self.varianten_liste.index(neuer_name) if neuer_name in self.varianten_liste else 0
        self._varianten_nav_aktualisieren()

    # ------------------------------------------------------------------ #
    #  OCR                                                                 #
    # ------------------------------------------------------------------ #

    def _ocr_konfigurieren(self):
        name = self.bearbeiten_name or self.name_var.get().strip()
        if not name:
            return
        eintraege = self.bot._modus_dialog(name)
        if eintraege is None:
            return
        self.bot._ocr_konfiguration_speichern(name, eintraege)

    # ------------------------------------------------------------------ #
    #  Zustände-Dialog (AND + OR)                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _migrate_condition_states(raw):
        """Konvertiert altes Format [{name: bool}] → neues Format [{connector, states}]."""
        if not raw:
            return []
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            if "states" in raw[0] or "connector" in raw[0]:
                return raw  # bereits neues Format
            # Altes Format: jeder dict-Eintrag = eine OR-Gruppe mit einem State
            return [{"connector": None if i == 0 else "OR", "states": dict(item)}
                    for i, item in enumerate(raw)]
        return []

    def _states_konfigurieren(self):
        dialog = tk.Toplevel(self.window)
        dialog.title("Zustände konfigurieren")
        dialog.configure(bg="#2d2d2d")
        dialog.grab_set()
        dialog.resizable(True, True)
        dialog.minsize(580, 520)

        try:
            bekannte = sorted(self.bot.app.state.game_states.keys())
        except Exception:
            bekannte = []

        # ── condition_states ───────────────────────────────────────────────
        tk.Label(dialog, text="Aktiv wenn:", bg="#2d2d2d", fg="#ffca28",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(14, 2))
        tk.Label(dialog,
                 text="Bedingungen innerhalb einer Gruppe sind AND-verknüpft.\n"
                      "Gruppen untereinander können AND oder OR verknüpft werden.",
                 bg="#2d2d2d", fg="#666666", font=("Segoe UI", 8),
                 justify="left").pack(anchor="w", padx=20, pady=(0, 8))

        gruppen_container = tk.Frame(dialog, bg="#2d2d2d")
        gruppen_container.pack(fill=tk.BOTH, expand=True, padx=20)

        # gruppen = [{"wrapper": Frame, "connector_frame": Frame|None,
        #             "connector_var": StringVar|None, "box": Frame,
        #             "zeilen_frame": Frame, "zeilen": [(z, n_var, v_var)]}]
        gruppen = []

        def refresh_first_connector():
            """Versteckt den Connector der ersten Gruppe (bereits korrekt gepackt, nur hide/show)."""
            for i, g in enumerate(gruppen):
                cf = g.get("connector_frame")
                if cf:
                    if i == 0:
                        cf.pack_forget()
                    # i > 0: bereits vor der Box gepackt — nicht anfassen

        def gruppe_loeschen(g):
            gruppen.remove(g)
            g["wrapper"].destroy()
            refresh_first_connector()

        def zeile_in_gruppe_bauen(g, state_name="", state_val=True):
            zf = g["zeilen_frame"]
            z = tk.Frame(zf, bg="#1a1a1a")
            z.pack(fill=tk.X, pady=2)
            n_var = tk.StringVar(value=state_name)
            v_var = tk.BooleanVar(value=state_val)
            ttk.Combobox(z, textvariable=n_var, values=bekannte, width=22,
                         font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(6, 4), pady=4)
            tk.Checkbutton(z, text="True", variable=v_var, bg="#1a1a1a", fg="#cccccc",
                           selectcolor="#2d2d2d", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 4))
            t = (z, n_var, v_var)
            g["zeilen"].append(t)
            tk.Button(z, text="✕", bg="#1a1a1a", fg="#da3633", relief=tk.FLAT, font=("Segoe UI", 10),
                      command=lambda ref=t: (g["zeilen"].remove(ref) if ref in g["zeilen"] else None,
                                            z.destroy())).pack(side=tk.RIGHT, padx=6)

        def gruppe_bauen(gruppe_data):
            """gruppe_data: {"connector": None|"AND"|"OR", "states": {name: bool}}"""
            wrapper = tk.Frame(gruppen_container, bg="#2d2d2d")
            wrapper.pack(fill=tk.X, pady=(0, 2))

            g = {"wrapper": wrapper, "connector_frame": None,
                 "connector_var": None, "zeilen": []}

            # Connector (nur für Gruppen nach der ersten)
            conn_frame = tk.Frame(wrapper, bg="#2d2d2d")
            g["connector_frame"] = conn_frame
            cv = tk.StringVar(value=gruppe_data.get("connector") or "OR")
            g["connector_var"] = cv
            tk.Label(conn_frame, text="Verknüpfung:", bg="#2d2d2d", fg="#888888",
                     font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 8))
            for txt, clr in [("AND", "#55aaff"), ("OR", "#ffca28")]:
                tk.Radiobutton(conn_frame, text=txt, variable=cv, value=txt,
                               bg="#2d2d2d", fg=clr, selectcolor="#1a1a1a",
                               activebackground="#2d2d2d", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=4)
            # Immer VOR der Box packen — refresh_first_connector versteckt ihn für Gruppe 1
            conn_frame.pack(fill=tk.X, pady=(8, 3))

            # Gruppen-Box
            nr = len(gruppen) + 1
            box = tk.Frame(wrapper, bg="#1a1a1a", bd=1, relief=tk.SOLID,
                           highlightbackground="#3a3a3a", highlightthickness=1)
            box.pack(fill=tk.X)
            g["box"] = box

            # Header
            header = tk.Frame(box, bg="#252525")
            header.pack(fill=tk.X)
            tk.Label(header, text=f"  Gruppe {nr}", bg="#252525", fg="#888888",
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, pady=5)
            tk.Button(header, text="Gruppe löschen", bg="#252525", fg="#da3633",
                      font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                      command=lambda ref=g: gruppe_loeschen(ref)).pack(side=tk.RIGHT, padx=8, pady=3)

            # Zeilen-Bereich
            zeilen_frame = tk.Frame(box, bg="#1a1a1a")
            zeilen_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
            g["zeilen_frame"] = zeilen_frame

            for sn, sv in gruppe_data.get("states", {}).items():
                zeile_in_gruppe_bauen(g, sn, sv)

            tk.Button(box, text="+ Bedingung hinzufügen", bg="#1a1a1a", fg="#aaaaaa",
                      font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                      command=lambda ref=g: zeile_in_gruppe_bauen(ref)).pack(anchor="w", padx=8, pady=6)

            gruppen.append(g)
            refresh_first_connector()

        # Bestehende Gruppen laden
        daten = self._migrate_condition_states(self.condition_states)
        if not daten:
            daten = [{"connector": None, "states": {}}]
        for gd in daten:
            gruppe_bauen(gd)

        tk.Button(gruppen_container, text="＋ Neue Gruppe hinzufügen",
                  bg="#1a3a5a", fg="#55aaff", font=("Segoe UI", 9), relief=tk.FLAT,
                  padx=10, pady=4, cursor="hand2",
                  command=lambda: gruppe_bauen({"connector": "OR", "states": {}}
                  )).pack(anchor="w", pady=(8, 0))

        tk.Frame(dialog, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=20, pady=(14, 0))

        # ── set_states ─────────────────────────────────────────────────────
        tk.Label(dialog, text="Setzt Zustände (bei Erkennung):", bg="#2d2d2d", fg="#55ff88",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(12, 4))

        set_frame = tk.Frame(dialog, bg="#1a1a1a")
        set_frame.pack(fill=tk.X, padx=20, pady=(0, 4))
        set_zeilen = []

        def set_zeile_bauen(state_name="", state_val=True):
            z = tk.Frame(set_frame, bg="#1a1a1a")
            z.pack(fill=tk.X, pady=2)
            n_var = tk.StringVar(value=state_name)
            v_var = tk.BooleanVar(value=state_val)
            ttk.Combobox(z, textvariable=n_var, values=bekannte, width=22,
                         font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(6, 4), pady=4)
            tk.Checkbutton(z, text="True", variable=v_var, bg="#1a1a1a", fg="#cccccc",
                           selectcolor="#2d2d2d", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 4))
            t = (z, n_var, v_var)
            set_zeilen.append(t)
            tk.Button(z, text="✕", bg="#1a1a1a", fg="#da3633", relief=tk.FLAT, font=("Segoe UI", 10),
                      command=lambda ref=t: (set_zeilen.remove(ref) if ref in set_zeilen else None,
                                            z.destroy())).pack(side=tk.RIGHT, padx=6)

        for sk, sv in self.set_states.items():
            set_zeile_bauen(sk, sv)

        tk.Button(dialog, text="+ Zustand hinzufügen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=3, cursor="hand2",
                  command=set_zeile_bauen).pack(anchor="w", padx=20, pady=(4, 10))

        # ── Buttons ────────────────────────────────────────────────────────
        btn_f = tk.Frame(dialog, bg="#2d2d2d")
        btn_f.pack(fill=tk.X, padx=20, pady=14)

        def speichern():
            self.condition_states = []
            for g in gruppen:
                states = {}
                for _, n_var, v_var in g["zeilen"]:
                    n = n_var.get().strip()
                    if n:
                        states[n] = v_var.get()
                if states:
                    self.condition_states.append({
                        "connector": g["connector_var"].get() if g["connector_var"] else None,
                        "states": states,
                    })
            # Ersten Eintrag immer ohne Connector
            if self.condition_states:
                self.condition_states[0]["connector"] = None

            self.set_states = {}
            for _, n_var, v_var in set_zeilen:
                n = n_var.get().strip()
                if n:
                    self.set_states[n] = v_var.get()
            dialog.destroy()

        tk.Button(btn_f, text="Übernehmen", bg="#2ea043", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=16, pady=6, command=speichern).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(btn_f, text="Abbrechen", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 10),
                  relief=tk.FLAT, padx=16, pady=6, command=dialog.destroy).pack(side=tk.RIGHT)

        dialog.update_idletasks()
        dialog.geometry(f"+{self.window.winfo_x() + 40}+{self.window.winfo_y() + 40}")

    # ------------------------------------------------------------------ #
    #  ROI / Test                                                          #
    # ------------------------------------------------------------------ #

    def _roi_fenster_oeffnen(self):
        if self.roi_editor and self.roi_editor.window.winfo_exists():
            self.roi_editor.window.lift()
            self.roi_editor.window.focus_force()
            return
        t_name = self.bearbeiten_name or self.name_var.get().strip() or "Unbenannt"

        def get_snapshot():
            if hasattr(self.bot.app, "current_screenshot_np"):
                snap_np = self.bot.app.current_screenshot_np
                if snap_np is not None:
                    return Image.fromarray(cv2.cvtColor(snap_np, cv2.COLOR_BGR2RGB))
            return None

        self.roi_editor = ROIEditor(self.window, self.bot, t_name, self.initial_scan_regions, get_snapshot)

    def _erkennung_test(self):
        # Robuste Null-Prüfung — window kann None sein wenn kein Snapshot beim Öffnen vorhanden war
        roi_ok = (self.roi_editor is not None
                  and self.roi_editor.window is not None
                  and self.roi_editor.window.winfo_exists())
        if not roi_ok:
            self._roi_fenster_oeffnen()

        if not self.roi_editor or self.roi_editor.window is None:
            tk.messagebox.showwarning(
                "Kein Screenshot",
                "Scannbereiche-Fenster konnte nicht geöffnet werden.\n"
                "Bitte zuerst einen Live-Screenshot aufnehmen.")
            return

        # ROI-Fenster in den Vordergrund
        self.roi_editor.window.lift()
        self.roi_editor.window.focus_force()

        snap_np = self.roi_editor.get_current_snapshot_np()

        # Fallback: direkt aus dem laufenden Bot
        if snap_np is None:
            live = getattr(getattr(self.bot, "app", None), "current_screenshot_np", None)
            if live is not None:
                snap_np = live
            else:
                tk.messagebox.showwarning(
                    "Kein Screenshot",
                    "Kein Screenshot verfügbar.\n"
                    "Bitte MEMUPlayer verbinden und den Bot starten.")
                return

        if self.orig_bild_ref is None:
            tk.messagebox.showwarning("Kein Template", "Bitte zuerst ein Bild als Template laden.")
            return

        n_tmp = "test_match_preview"
        aktuelle_rois = self.roi_editor.get_regions()

        try:
            # Template direkt in-memory bauen — kein Disk-I/O, kein _templates_laden()
            bild_np = np.array(self.orig_bild_ref.convert("RGB"))
            bild_bgr = cv2.cvtColor(bild_np, cv2.COLOR_RGB2BGR)

            if self.hg_var.get():
                # _hintergrund_maske_erstellen gibt uint8 0/255 zurück.
                # _templates_laden liest die gespeicherte Alpha-Maske als float32 0.0/1.0.
                # → hier dieselbe Normalisierung wie beim Laden anwenden.
                maske_raw = self.template_engine._hintergrund_maske_erstellen(
                    bild_np, toleranz=self.hg_tol_var.get())
                for (ix0, iy0, ix1, iy1) in self.ignore_regionen:
                    maske_raw[max(0, int(iy0)):int(iy1), max(0, int(ix0)):int(ix1)] = 0
                maske_np = np.where(maske_raw > 10, 1.0, 0.0).astype(np.float32)
                bbox = self.template_engine._maske_bbox((maske_np > 0.5).astype(np.uint8))
                if bbox:
                    bx, by, bw, bh = bbox
                    bild_bgr = bild_bgr[by:by+bh, bx:bx+bw]
                    maske_np = maske_np[by:by+bh, bx:bx+bw]
            else:
                maske_np = None
                bbox = None

            dev = self.template_engine.device
            t_bild = torch.from_numpy(
                bild_bgr.transpose(2, 0, 1)).float().div(255.0).to(dev).unsqueeze(0)
            t_maske = (torch.from_numpy(maske_np).float().to(dev).unsqueeze(0).unsqueeze(0)
                       if maske_np is not None else None)

            self.template_engine.templates[n_tmp] = {
                "tensor": t_bild,
                "maske": t_maske,
                "orig_size": (self.orig_bild_ref.width, self.orig_bild_ref.height),
                "gruppe": n_tmp,
                "pfad": "",
                "match_schwellwert": self.schwellwert_var.get(),
                "scan_regions": aktuelle_rois,
                "bbox": bbox,
            }
            self.template_engine.settings[n_tmp] = {
                "match_schwellwert": self.schwellwert_var.get(),
                "scan_regions": aktuelle_rois,
                "condition_states": {},
                "set_states": {},
            }

            res = self.template_engine.matches_suchen_np(snap_np)
            my_matches = [m for m in res if m[0] == n_tmp]
            self.roi_editor.draw_test_results(my_matches, self.schwellwert_var.get())

            if my_matches:
                best = max(my_matches, key=lambda m: m[5])
                self.roi_editor.set_status(
                    f"✓ {len(my_matches)} Treffer  |  Bester Score: {best[5]:.3f}",
                    farbe="#00ff88")
            else:
                self.roi_editor.set_status(
                    f"✗ Kein Treffer  (Schwelle: {self.schwellwert_var.get():.2f})",
                    farbe="#ff6644")
        except Exception as e:
            self.roi_editor.set_status(f"Fehler: {e}", farbe="#ff4444")
        finally:
            self.template_engine.templates.pop(n_tmp, None)
            self.template_engine.settings.pop(n_tmp, None)
            # GPU-Cache für dieses Template aufräumen
            for key in [k for k in self.template_engine._gpu_cache if k[0] == n_tmp]:
                del self.template_engine._gpu_cache[key]

    # ------------------------------------------------------------------ #
    #  Vorschau                                                            #
    # ------------------------------------------------------------------ #

    def _vorschau_setzen(self, bild, breite, hoehe):
        CANVAS_MAX_B, CANVAS_MAX_H = 1100, 320
        self.orig_bild_ref = bild
        s = min(CANVAS_MAX_B / breite, CANVAS_MAX_H / hoehe)
        if s > 15.0:
            s = 15.0
        ab, ah = int(breite * s), int(hoehe * s)
        self.aktuell_skala, self.aktuell_b, self.aktuell_h = s, ab, ah
        for c in [self.canvas, self.canvas_hg]:
            c.config(width=ab, height=ah)
            c.delete("all")
        self.foto_ref = ImageTk.PhotoImage(bild.resize((ab, ah), Image.NEAREST))
        self.canvas.create_image(0, 0, anchor="nw", image=self.foto_ref)
        self.canvas.image = self.foto_ref
        self._overlays_zeichnen()
        self.info_label.config(text=f"{breite}x{hoehe}px")
        self.window.update_idletasks()
        if self._nach_vorschau_cb:
            self.window.after(30, self._nach_vorschau_cb)
        else:
            self._hg_vorschau_aktualisieren()

    def _overlays_zeichnen(self):
        ab, ah = self.aktuell_b, self.aktuell_h
        for rid in self.klick_ids_orig:
            self.canvas.delete(rid)
        for rid in self.klick_ids_hg:
            self.canvas_hg.delete(rid)
        self.klick_ids_orig.clear()
        self.klick_ids_hg.clear()
        if self.klick_zone[0]:
            px = int(self.klick_zone[0][0] / 100 * ab)
            py = int(self.klick_zone[0][1] / 100 * ah)
            self.klick_ids_orig.append(self.canvas.create_line(px-10, py, px+10, py, fill="#ff6600", width=2))
            self.klick_ids_orig.append(self.canvas.create_line(px, py-10, px, py+10, fill="#ff6600", width=2))
            self.klick_ids_hg.append(self.canvas_hg.create_line(px-10, py, px+10, py, fill="#ff6600", width=2))
            self.klick_ids_hg.append(self.canvas_hg.create_line(px, py-10, px, py+10, fill="#ff6600", width=2))
        for rid in self.ignore_ids_orig:
            self.canvas.delete(rid)
        self.ignore_ids_orig.clear()
        # canvas_hg wird in _hg_vorschau_aktualisieren mit bbox-korrekten Koordinaten gezeichnet
        for (ix0, iy0, ix1, iy1) in self.ignore_regionen:
            s = self.aktuell_skala
            rid_o = self.canvas.create_rectangle(
                int(ix0*s), int(iy0*s), int(ix1*s), int(iy1*s),
                outline="#ff4444", width=2, fill="#ff4444", stipple="gray25")
            self.ignore_ids_orig.append(rid_o)

    # ------------------------------------------------------------------ #
    #  Canvas-Events                                                       #
    # ------------------------------------------------------------------ #

    def _on_press(self, e):
        if self.farb_modus_aktiv:
            return
        if self.canvas_modus.get() == "klick":
            self._klick_setzen(e)
            return
        self.drag_start = (e.x, e.y)
        cursor_einschraenken(e.widget)

    def _canvas_zu_hg(self, x, y):
        """Wandelt canvas-Pixelkoordinaten (Original) in canvas_hg-Koordinaten um."""
        ab, ah, s = self.aktuell_b, self.aktuell_h, self.aktuell_skala
        if self._hg_preview_bbox:
            bx, by, bw, bh = self._hg_preview_bbox
            return int((x / s - bx) * (ab / bw)), int((y / s - by) * (ah / bh))
        return x, y

    def _on_motion(self, e):
        if self.farb_modus_aktiv or self.canvas_modus.get() == "klick" or not self.drag_start:
            return
        for rid in self.live_rect_ids:
            self.canvas.delete(rid)
        for rid in self.live_rect_ids_hg:
            self.canvas_hg.delete(rid)
        self.live_rect_ids.clear()
        self.live_rect_ids_hg.clear()
        x0, y0 = self.drag_start
        self.live_rect_ids.append(self.canvas.create_rectangle(
            x0, y0, e.x, e.y, outline="#ff4444", width=2, fill="#ff4444", stipple="gray25"))
        hx0, hy0 = self._canvas_zu_hg(x0, y0)
        hx1, hy1 = self._canvas_zu_hg(e.x, e.y)
        self.live_rect_ids_hg.append(self.canvas_hg.create_rectangle(
            hx0, hy0, hx1, hy1, outline="#ff4444", width=2, fill="#ff4444", stipple="gray25"))

    def _on_release(self, e):
        cursor_freigeben()
        if self.farb_modus_aktiv or self.canvas_modus.get() == "klick" or not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = e.x, e.y
        self.drag_start = None
        if abs(x1 - x0) < 4 or abs(y1 - y0) < 4:
            for rid in self.live_rect_ids:
                self.canvas.delete(rid)
            for rid in self.live_rect_ids_hg:
                self.canvas_hg.delete(rid)
            self.live_rect_ids.clear()
            self.live_rect_ids_hg.clear()
            return
        ab, ah, s = self.aktuell_b, self.aktuell_h, self.aktuell_skala
        self.ignore_regionen.append((
            int(max(0, min(x0, x1)) / s), int(max(0, min(y0, y1)) / s),
            int(min(ab, max(x0, x1)) / s), int(min(ah, max(y0, y1)) / s)))
        for rid in self.live_rect_ids:
            self.canvas.delete(rid)
        for rid in self.live_rect_ids_hg:
            self.canvas_hg.delete(rid)
        self.live_rect_ids.clear()
        self.live_rect_ids_hg.clear()
        self._overlays_zeichnen()
        self._hg_vorschau_aktualisieren()

    def _ignore_letzten_entfernen(self):
        if self.ignore_regionen:
            self.ignore_regionen.pop()
        self._overlays_zeichnen()
        self._hg_vorschau_aktualisieren()

    def _klick_setzen(self, e):
        ab, ah = self.aktuell_b, self.aktuell_h
        rel_x, rel_y = round(e.x / ab * 100, 1), round(e.y / ah * 100, 1)
        self.klick_zone[0] = (rel_x, rel_y)
        self.klick_info.config(text=f"Klick-Zone: {rel_x:.0f}% / {rel_y:.0f}%", fg="#ff6600")
        self._overlays_zeichnen()

    def _klick_entfernen(self):
        self.klick_zone[0] = None
        self.klick_info.config(text="Klick-Zone: nicht gesetzt", fg="#555555")
        self._overlays_zeichnen()

    # ------------------------------------------------------------------ #
    #  Hintergrund-Vorschau                                               #
    # ------------------------------------------------------------------ #

    def _hg_vorschau_aktualisieren(self):
        if self.orig_bild_ref is None:
            return
        n_tmp = "_tmp_preview"
        try:
            self.template_engine.template_speichern(
                n_tmp, self.orig_bild_ref, self.hg_var.get(),
                list(self.ignore_regionen), hintergrund_toleranz=self.hg_tol_var.get(),
                gruppe="temp_preview")

            # Bbox für bbox-korrekte Darstellung auf canvas_hg lesen und speichern
            bbox = self.template_engine.templates.get(n_tmp, {}).get("bbox")
            self._hg_preview_bbox = bbox

            preview = self.template_engine.get_mathematik_vorschau(n_tmp)
            if preview:
                if preview.mode == "RGBA":
                    bild_np = np.array(preview)
                    rgb, alpha = bild_np[:, :, :3], bild_np[:, :, 3] / 255.0
                    checker = self._schachbrett(bild_np.shape[1], bild_np.shape[0])
                    preview = Image.fromarray(
                        (rgb * alpha[:, :, None] + checker * (1 - alpha[:, :, None])).astype(np.uint8))
                ab, ah = self.aktuell_b, self.aktuell_h
                preview = preview.resize((ab, ah), Image.LANCZOS)
                self.foto_hg_ref = ImageTk.PhotoImage(preview)
                self.canvas_hg.delete("img_hg")
                self.canvas_hg.create_image(0, 0, anchor="nw", image=self.foto_hg_ref, tags="img_hg")
                self.canvas_hg.image = self.foto_hg_ref
                self.canvas_hg.tag_lower("img_hg")

                # Ignore-Regionen auf canvas_hg mit bbox-korrekten Koordinaten neu zeichnen
                for rid in self.ignore_ids_hg:
                    self.canvas_hg.delete(rid)
                self.ignore_ids_hg.clear()
                for (ix0, iy0, ix1, iy1) in self.ignore_regionen:
                    if bbox:
                        bx, by, bw, bh = bbox
                        sx, sy = ab / bw, ah / bh
                        rx0 = int((ix0 - bx) * sx)
                        ry0 = int((iy0 - by) * sy)
                        rx1 = int((ix1 - bx) * sx)
                        ry1 = int((iy1 - by) * sy)
                    else:
                        s = self.aktuell_skala
                        rx0, ry0 = int(ix0 * s), int(iy0 * s)
                        rx1, ry1 = int(ix1 * s), int(iy1 * s)
                    rid_h = self.canvas_hg.create_rectangle(
                        rx0, ry0, rx1, ry1,
                        outline="#ff4444", width=2, fill="#ff4444", stipple="gray25")
                    self.ignore_ids_hg.append(rid_h)
        except Exception as e:
            self.bot._log(f"Vorschau-Fehler: {e}")
        finally:
            self.template_engine.template_loeschen("_tmp_preview")

    def _schachbrett(self, w, h):
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for iy in range(h):
            for ix in range(w):
                arr[iy, ix] = (180, 180, 180) if (ix // 8 + iy // 8) % 2 == 0 else (120, 120, 120)
        return arr

    # ------------------------------------------------------------------ #
    #  Speichern / Schließen                                              #
    # ------------------------------------------------------------------ #

    def _speichern(self):
        n = self.name_var.get().strip()
        if not n:
            return

        alter_name = self.bearbeiten_name
        uebergeordnet = self.gruppe_var.get().strip() if self.typ != "aktiv_gruppe" else ""

        # Check in templates AND settings (for passive groups)
        existiert = n in self.template_engine.templates or n in self.template_engine.settings
        
        if existiert and n != alter_name:
            if not messagebox.askyesno("Überschreiben?", f"'{n}' existiert bereits. Überschreiben?"):
                return

        try:
            img_to_save = self.orig_bild_ref
            if img_to_save is None and alter_name and alter_name in self.template_engine.templates:
                pfad_alt = self.template_engine.templates[alter_name].get("pfad")
                if pfad_alt and os.path.exists(pfad_alt):
                    _arr = cv2.imdecode(np.fromfile(pfad_alt, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if _arr is not None:
                        if len(_arr.shape) == 3 and _arr.shape[2] == 4:
                            img_to_save = Image.fromarray(cv2.cvtColor(_arr[:, :, :3], cv2.COLOR_BGR2RGB))
                        else:
                            img_to_save = Image.fromarray(cv2.cvtColor(_arr, cv2.COLOR_BGR2RGB))

            if img_to_save is None or self.typ == "passiv_gruppe":
                # Passive Gruppe: kein Bild, nur Bedingungen speichern
                n = self.name_var.get().strip()
                if not n:
                    self.bot._log("Fehler beim Speichern: Kein Name angegeben.")
                    return
                
                # Check ob sich Name oder Hierarchie geändert hat
                umbenennen = alter_name and (alter_name != n)
                gruppe_geandert = False
                if alter_name:
                    alte_uebergeordnet = self.template_engine.settings.get(alter_name, {}).get("gruppe", "")
                    # Master-Gruppe zeigt 'gruppe' == Name oder leer.
                    ist_alter_master = (alte_uebergeordnet in ("", alter_name))
                    ist_neuer_master = (uebergeordnet == "")
                    
                    if ist_alter_master:
                        if not ist_neuer_master: gruppe_geandert = True
                    else:
                        if alte_uebergeordnet != uebergeordnet: gruppe_geandert = True

                if umbenennen or gruppe_geandert:
                    self.template_engine.gruppe_umbenennen(alter_name, n, neue_uebergeordnete_gruppe=uebergeordnet)

                self.template_engine.gruppe_config_speichern(
                    n, list(self.condition_states),
                    uebergeordnete_gruppe=uebergeordnet, kategorie=self.kategorie)
                
                if umbenennen: aktion = "umbenannt"
                elif alter_name: aktion = "aktualisiert"
                else: aktion = "erstellt"
                
                self.bot._log(f"Passive Gruppe {aktion}: \"{n}\"")
                self.bot.app.reload_templates()
                self.bot._templates_liste_aktualisieren()
                return

            entferne_hg = self.hg_var.get()
            hg_toleranz = self.hg_tol_var.get()
            match_s = self.schwellwert_var.get()

            # aktiv_gruppe: Gruppe = eigener Name (kein Feld im UI)
            if self.typ == "aktiv_gruppe":
                gruppe_name = n
            else:
                gruppe_name = self.gruppe_var.get().strip() or n

            aktuelle_scan_regions = self.initial_scan_regions
            if self.roi_editor and self.roi_editor.window.winfo_exists():
                aktuelle_scan_regions = self.roi_editor.get_regions()

            umbenennen = alter_name and (alter_name != n)
            gruppe_geandert = False
            if alter_name:
                alte_uebergeordnet = self.template_engine.settings.get(alter_name, {}).get("gruppe", "")
                # Master-Gruppe zeigt 'gruppe' == Name oder leer.
                ist_alter_master = (alte_uebergeordnet in ("", alter_name))
                ist_neuer_master = (gruppe_name == n) # Bei aktiven Templates bedeutet gruppe == name = Master

                if ist_alter_master:
                    if not ist_neuer_master: gruppe_geandert = True
                else:
                    if alte_uebergeordnet != gruppe_name: gruppe_geandert = True


            speichern_kwargs = dict(
                hintergrund_toleranz=hg_toleranz,
                gruppe=gruppe_name,
                match_schwellwert=match_s,
                scan_regions=list(aktuelle_scan_regions),
                condition_states=list(self.condition_states),
                set_states=dict(self.set_states),
                typ=self.typ,
                kategorie=self.kategorie,
            )

            if self.typ == "aktiv_gruppe" and (umbenennen or gruppe_geandert):
                self.template_engine.gruppe_umbenennen(alter_name, n, neue_uebergeordnete_gruppe=uebergeordnet)
                # Nach dem Umbenennen der Gruppe müssen wir alter_name aktualisieren, 
                # damit template_speichern im nächsten Schritt nicht denkt, es wäre ein neues Template.
                # Wir geben aber trotzdem den ursprünglichen alter_name für die Lösch-Logik mit.
                orig_alter_name = alter_name
                alter_name = n
                self.bearbeiten_name = n
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen), alter_name=orig_alter_name, **speichern_kwargs)
            elif umbenennen:
                self.template_engine.template_umbenennen(alter_name, n, gruppe_name)
                orig_alter_name = alter_name
                alter_name = n
                self.bearbeiten_name = n
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen), alter_name=orig_alter_name, **speichern_kwargs)
            else:
                self.template_engine.template_speichern(
                    n, img_to_save, entferne_hg, list(self.ignore_regionen), **speichern_kwargs)

            if umbenennen:
                self.action_engine.klickzone_loeschen(alter_name)
            if self.klick_zone[0]:
                self.action_engine.klickzone_speichern(n, self.klick_zone[0][0], self.klick_zone[0][1])
            elif alter_name and not umbenennen:
                self.action_engine.klickzone_loeschen(n)

            self.bot._log(f"Template {'aktualisiert' if alter_name else 'gespeichert'}: \"{n}\"")
            self.bot._templates_liste_aktualisieren()
            self.bot.app.reload_templates()
            self.bot._timer_panel_aktualisieren()

            # Nach dem Speichern: bearbeiten_name aktualisieren, Varianten neu prüfen
            self.bearbeiten_name = n
            self._varianten_erkennen(n)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.bot._log(f"Speicher-Fehler: {e}")

    def _schliessen(self):
        self.template_engine.template_loeschen("_tmp_preview")
        # test_match_preview lebt nur in-memory, kein Disk-Cleanup nötig
        self.template_engine.templates.pop("test_match_preview", None)
        self.template_engine.settings.pop("test_match_preview", None)
        self.window.destroy()
        if self.einlern_modus_callback:
            self.einlern_modus_callback()
