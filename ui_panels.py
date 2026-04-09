import tkinter as tk
import time
from ui.panels.template_panel import TemplatePanel
from ui.panels.workflow_panel import WorkflowPanel
from ui.panels.variable_panel import VariablePanel as OCRPanel
from ui.panels.state_panel import StatePanel
from ui.panels.log_panel import LogPanel

class PanelsMixin:
    def _panel_erstellen(self, parent, titel, inhalt_func, expand=False, kopf_extra=None):
        """Erstellt ein beschriftetes Panel."""
        rahmen = tk.Frame(parent, bg="#2d2d2d", relief=tk.FLAT, bd=1)
        rahmen.pack(fill=tk.BOTH, expand=expand, pady=(0, 4))

        kopf_frame = tk.Frame(rahmen, bg="#252525")
        kopf_frame.pack(fill=tk.X)
        tk.Label(kopf_frame, text=titel, bg="#252525", fg="#888888",
                 font=("Segoe UI", 8, "bold"), anchor="w", padx=8, pady=4).pack(side=tk.LEFT)
        if kopf_extra:
            kopf_extra(kopf_frame)

        inhalt = tk.Frame(rahmen, bg="#2d2d2d")
        inhalt.pack(fill=tk.BOTH, expand=expand, padx=6, pady=4)

        inhalt_func(inhalt)

    def _workflows_panel(self, parent):
        self.workflow_panel = WorkflowPanel(parent, self)

    def _templates_panel(self, parent):
        self.template_panel = TemplatePanel(parent, self, filter_modus="workflow",
                                            show_buttons=False, on_focus=self._template_panel_fokus_setzen)

    def _state_templates_panel(self, parent):
        self.state_template_panel = TemplatePanel(parent, self, filter_modus="state",
                                                  show_buttons=False, on_focus=self._template_panel_fokus_setzen)

    def _template_panel_fokus_setzen(self, panel):
        """Merkt sich welches Template-Panel zuletzt aktiv war."""
        self._aktiver_template_panel = panel

    def _template_buttons_bereich(self, parent):
        """Erstellt die gemeinsame Button-Leiste für beide Template-Listen."""
        rahmen = tk.Frame(parent, bg="#2d2d2d")
        rahmen.pack(fill=tk.X, pady=(0, 4), padx=0)

        zeile1 = tk.Frame(rahmen, bg="#2d2d2d")
        zeile1.pack(anchor="w", pady=(2, 1))

        tk.Button(zeile1, text="↺ Neu laden", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._aktive_panel_aktion("_neu_laden")).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(zeile1, text="✎ Bearbeiten", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._aktive_panel_aktion("_bearbeiten")).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(zeile1, text="✕ Löschen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._aktive_panel_aktion("_loeschen")).pack(side=tk.LEFT)

        zeile2 = tk.Frame(rahmen, bg="#2d2d2d")
        zeile2.pack(anchor="w", pady=(0, 2))

        tk.Button(zeile2, text="🔤 OCR", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._aktive_panel_aktion("_ocr_konfigurieren")).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(zeile2, text="🖱 Klick", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._aktive_panel_aktion("_klick_konfigurieren")).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(zeile2, text="🚩 Zustände", bg="#3a3a3a", fg="#ffca28",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._zustand_manager_shortcut).pack(side=tk.LEFT)

    def _aktive_panel_aktion(self, methode):
        """Gibt eine Funktion zurück die die Methode auf dem aktiven Panel aufruft."""
        def aktion():
            panel = getattr(self, "_aktiver_template_panel", None)
            if panel:
                getattr(panel, methode)()
        return aktion

    def _zustand_manager_shortcut(self):
        """Öffnet den Zustand-Manager für das ausgewählte Template."""
        panel = getattr(self, "_aktiver_template_panel", None)
        if not panel:
            return
        name = panel._get_auswahl_name()
        if not name:
            return
        self._zustand_manager_dialog(name)

    def _ocr_panel(self, parent):

        self.forschung_label = tk.Label(parent, text="(Noch nicht gescannt)", 
                                         bg="#2d2d2d", fg="#555555", font=("Segoe UI", 9))
        self.forschung_label.pack(anchor="w")

    def _variablen_kopf_extra(self, kopf_frame):
        self._aktive_toggle_btn = tk.Button(kopf_frame, text="Nur aktive", bg="#1a3a1a", fg="#2ea043", 
                                             font=("Segoe UI", 7, "bold"), relief=tk.FLAT, padx=8, pady=2, 
                                             cursor="hand2", command=self._aktive_toggle, bd=1)
        self._aktive_toggle_btn.pack(side=tk.RIGHT, padx=6, pady=2)
        self._aktive_toggle_aktualisieren()

    def _aktive_toggle_aktualisieren(self):
        if not hasattr(self, "_aktive_toggle_btn"): return
        if self._nur_aktive_variablen: 
            self._aktive_toggle_btn.config(bg="#2ea043", fg="#ffffff")
        else: 
            self._aktive_toggle_btn.config(bg="#1a1a1a", fg="#555555")

    def _aktive_toggle(self):
        self._nur_aktive_variablen = not self._nur_aktive_variablen
        self._aktive_toggle_aktualisieren()
        if hasattr(self, "ocr_panel"):
            self.ocr_panel.set_nur_aktive(self._nur_aktive_variablen)

    def _ocr_panel(self, parent):
        self.ocr_panel = OCRPanel(parent, self)
        self.ocr_panel.set_nur_aktive(self._nur_aktive_variablen)

    def _state_kopf_extra(self, kopf_frame):
        # Nur Aktive Toggle (Design angepasst an OCR-Button)
        self._nur_aktive_states = False
        self._aktive_states_btn = tk.Button(kopf_frame, text=" ● Nur Aktive ", bg="#3a3a3a", fg="#aaaaaa", 
                                          font=("Segoe UI", 8, "bold"), relief=tk.FLAT, bd=0, padx=6, 
                                          pady=2, cursor="hand2", command=self._aktive_states_toggle)
        self._aktive_states_btn.pack(side=tk.RIGHT, padx=4)

        # Hinzufügen Button
        tk.Button(kopf_frame, text=" ➕ ", bg="#1a1a1a", fg="#555555", font=("Segoe UI", 8),
                  relief=tk.FLAT, bd=0, padx=4, cursor="hand2", 
                  command=self._state_variable_hinzufuegen_dialog).pack(side=tk.RIGHT, padx=5)

    def _aktive_states_toggle(self):
        self._nur_aktive_states = not self._nur_aktive_states
        if self._nur_aktive_states:
            self._aktive_states_btn.config(bg="#1a3a1a", fg="#2ea043")
        else:
            self._aktive_states_btn.config(bg="#3a3a3a", fg="#aaaaaa")
        
        if hasattr(self, "state_panel"):
            self.state_panel.set_nur_aktive(self._nur_aktive_states)

    def _state_panel(self, parent):
        self.state_panel = StatePanel(parent, self)

    def _log_panel(self, parent):
        self.log_panel_obj = LogPanel(parent)

    # ── Delegators for backward compatibility ──
    def _log(self, message):
        if hasattr(self, "log_panel_obj"):
            self.log_panel_obj.log(message)
        else:
            print(f"LOG: {message}")

    def _status_setzen(self, text, farbe):
        if hasattr(self, "status_label"):
            self.status_label.config(text=text, fg=farbe)

    def _templates_liste_aktualisieren(self):
        if hasattr(self, "template_panel"):
            self.template_panel.aktualisieren()
        if hasattr(self, "state_template_panel"):
            self.state_template_panel.aktualisieren()

    def _workflows_liste_aktualisieren(self):
        if hasattr(self, "workflow_panel"):
            self.workflow_panel._workflows_liste_aktualisieren()

    def _schedule_liste_aktualisieren(self):
        if hasattr(self, "workflow_panel"):
            self.workflow_panel._schedule_liste_aktualisieren()

    def _timer_panel_aktualisieren(self):
        if hasattr(self, "ocr_panel"):
            self.ocr_panel.aktualisieren()

    def _state_panel_aktualisieren(self):
        if hasattr(self, "state_panel"):
            self.state_panel.aktualisieren()

    def _timer_werte_aktualisieren(self, werte):
        if hasattr(self, "ocr_panel"):
            self.ocr_panel.werte_aktualisieren(werte)

    def _template_ocr_werte_aktualisieren(self, werte):
        if hasattr(self, "ocr_panel"):
            # Template OCR values are merged into timer_eintraege in OCRPanel
            self.ocr_panel.werte_aktualisieren(werte)

    def _state_werte_aktualisieren(self, werte):
        if hasattr(self, "state_panel"):
            self.state_panel.werte_aktualisieren(werte)

    def _template_ocr_aus_panel_loeschen(self, name):
        self.ocr_engine.template_ocr_deaktivieren(name)
        self._templates_liste_aktualisieren()
        self._timer_panel_aktualisieren()

    def _ocr_region_loeschen(self, name):
        self.ocr_engine.region_loeschen(name)
        self._timer_panel_aktualisieren()
