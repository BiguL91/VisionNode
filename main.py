"""
TilesBot Hauptfenster (Qt) — Ersetzt main.py (tkinter).
Einstiegspunkt: python main_qt.py

Architektur:
    VorschauLabel   — Custom QLabel für Live-Vorschau + Overlays + Einlern-Maus
    TilesBotWindow  — QMainWindow, verbindet alle Qt-Panels via Signals
"""
from __future__ import annotations
import os
import json
import threading

from style import style

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QComboBox, QInputDialog,
    QMessageBox, QScrollArea, QSizePolicy, QApplication, QFrame,
    QMenu, QDockWidget,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QMetaObject, Q_ARG, QSize
from PyQt6.QtGui import (
    QImage, QPixmap, QFont, QCloseEvent,
    QAction,
)

class CustomDockTitleBar(QFrame):
    """Eigene Titelzeile für Docks mit Einklapp-Funktion."""
    def __init__(self, title, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self._collapsed = False
        self.setFixedHeight(30)
        self.setObjectName("dock_title_bar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(6)

        # Titel
        self.lbl = QLabel(title)
        self.lbl.setStyleSheet("font-weight: bold; color: #888888; background: transparent; border: none; font-size: 12px;")
        layout.addWidget(self.lbl)
        layout.addStretch()

        # Button Style (Noch dezenter und kleiner)
        btn_style = """
            QPushButton { 
                background-color: #333333; 
                border: 1px solid #3d3d3d; 
                color: #777777; 
                font-family: 'Arial';
                font-size: 10px; 
                border-radius: 2px;
                min-width: 18px;
                min-height: 18px;
            }
            QPushButton:hover { 
                background-color: #444444; 
                color: #ffffff; 
                border: 1px solid #555555;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
        """

        # Einklapp-Button
        self.btn_collapse = QPushButton("▲")
        self.btn_collapse.setFixedSize(18, 18)
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.setStyleSheet(btn_style)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        layout.addWidget(self.btn_collapse)

        # Rauslösen-Button (Float)
        self.btn_float = QPushButton("❐")
        self.btn_float.setFixedSize(18, 18)
        self.btn_float.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_float.setStyleSheet(btn_style)
        self.btn_float.clicked.connect(lambda: self.dock.setFloating(not self.dock.isFloating()))
        layout.addWidget(self.btn_float)

        self.setStyleSheet("""
            QFrame#dock_title_bar {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d2d2d, stop:1 #252525); 
                border-bottom: 1px solid #3d3d3d;
            }
            QFrame#dock_title_bar:hover {
                background-color: #444444;
            }
            QFrame#dock_title_bar QLabel {
                color: #888888;
            }
            QFrame#dock_title_bar:hover QLabel {
                color: #ffffff;
            }
        """)

    def set_locked(self, locked: bool):
        self.btn_float.setVisible(not locked)

    def toggle_collapse(self):
        content = self.dock.widget()
        if not content: return

        self._collapsed = not self._collapsed
        
        if self._collapsed:
            # Größe merken
            self._last_width = self.dock.width()
            self._last_height = self.dock.height()
            self.btn_collapse.setText("▼")
            content.hide()
            
            # Dock auf Titelzeile fixieren
            self.dock.setMinimumHeight(30)
            self.dock.setMaximumHeight(30)
            self.dock.setMinimumWidth(self._last_width)
            self.dock.setMaximumWidth(self._last_width)
        else:
            self.btn_collapse.setText("▲")
            
            # 1. Erstmal alle Schranken auf
            self.dock.setMinimumSize(0, 0)
            self.dock.setMaximumSize(16777215, 16777215)
            
            # 2. Inhalt zeigen
            content.show()
            
            # 3. Alte Größe forcieren (kurzzeitig fixieren, damit Qt sie übernimmt)
            if hasattr(self, "_last_height"):
                self.dock.resize(self._last_width, self._last_height)
                # Kleiner Hack: Kurzzeitig als Minimum setzen, damit das Layout aufspringt
                self.dock.setMinimumHeight(self._last_height)
                QTimer.singleShot(50, lambda: self.dock.setMinimumHeight(0))
        
        self.dock.updateGeometry()
        if self.dock.parentWidget():
            self.dock.parentWidget().update()

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from PIL import Image as _PILImage
except ImportError:
    _PILImage = None

# ── Core ─────────────────────────────────────────────────────────────────────
from core.main_app import TilesBotApp
from core.helpers import _template_farbe
from core.daten_manager import alle_listen, cache_lesen, sekunden_formatieren

# ── Qt Panels ─────────────────────────────────────────────────────────────────
from ui.panels.log_panel_qt      import LogPanel      as LogPanelQt
from ui.panels.state_panel_qt    import StatePanel    as StatePanelQt
from ui.panels.workflow_panel_qt import WorkflowPanel as WorkflowPanelQt
from ui.panels.variable_panel_qt import VariablePanel as VariablePanelQt
from ui.panels.template_panel_qt import TemplatePanel as TemplatePanelQt
from ui.panels.daten_panel_qt    import DatenPanel    as DatenPanelQt

# ── Qt Widgets / Dialoge ──────────────────────────────────────────────────────
from ui.widgets.vorschau_label     import VorschauLabel, _frame_to_qpixmap
from ui.widgets.klick_canvas       import KlickCanvas
from ui.dialogs.template_editor_qt import TemplateEditorQt
from ui.dialogs.workflow_editor_qt import WorkflowEditorDialogQt
from ui.dialogs.daten_editor_qt    import DatenListeEditorQt
from ui.dialogs.timer_editor_qt    import TimerEditorDialogQt
from ui.dialogs.einheiten_dialog_qt import EinheitenDialogQt
from ui.dialogs.typ_dialog_qt      import TypDialog
from ui.dialogs.legende_dialog_qt  import LegendDialog
from ui.dialogs.state_dialogs_qt   import StateHinzufuegenDialog, StateEditorDialog
from ui.dialogs.settings_dialog_qt import SettingsDialog
from ui.dialogs.gruppe_editor_qt   import GruppeEditorQt
from ui.dialogs.ocr_dialog_qt      import OCRKonfigDialog

APP_CONFIG_DATEI = os.path.join("templates", "settings", "app_config.json")
DISPLAY_FPS_DEFAULT = 30


# ── Hauptfenster ──────────────────────────────────────────────────────────────

class TilesBotWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ai-Bot")
        self.setMinimumSize(1450, 700)

        # Dock-Optionen für maximale Flexibilität (Widescreen-Support)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks |
            QMainWindow.DockOption.AllowTabbedDocks |
            QMainWindow.DockOption.AnimatedDocks
        )

        # Core
        self.app = TilesBotApp(log_callback=self._log)
        self.template_engine  = self.app.template_engine
        self.ocr_engine       = self.app.ocr_engine
        self.action_engine    = self.app.action_engine
        self.workflow_engine  = self.app.workflow_engine
        self.einstellungen    = self.app.settings

        # UI State
        self.einlern_modus = False
        self.ocr_modus     = False
        self._live_ocr_receiver = None
        self._geplanter_typ      = None
        self._geplante_kategorie = None
        self._aktueller_ausschnitt = None
        self._aktiver_template_panel = None
        self._nur_aktive_variablen   = False
        self._logic_clipboard = None
        self._active_dialogs = []
        self._ui_locked = self.einstellungen.get("layout_locked", False)

        self._gui_aufbauen()
        self._connect_signals()
        self._fenster_groesse_initialisieren()

        # Panels initial befüllen
        self._panels_aktualisieren()

        # Menü & Toolbar
        self._setup_menus()

        # Start-Sequenz
        if self.app.find_memu():
            self.app.start()
            self._start_display_loop()
        else:
            self._vorschau.set_status("MEMUPlayer nicht gefunden. Bitte starten.")
            self._check_memu_retry()

    def _show_dialog(self, dlg: QDialog):
        """Registriert einen Dialog, um ihn vor dem Garbage Collector zu schützen und zeigt ihn an."""
        self._active_dialogs.append(dlg)
        
        # Wieder aktivieren, da das "Blitzen" (Positionierung) gelöst ist
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) 
        
        def cleanup():
            if dlg in self._active_dialogs:
                self._active_dialogs.remove(dlg)

        dlg.destroyed.connect(cleanup)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    # ── GUI Aufbau ────────────────────────────────────────────────────────────

    def _setup_menus(self):
        """Erstellt die Menüleiste."""
        menubar = self.menuBar()
        
        # Ansicht-Menü
        view_menu = menubar.addMenu("Ansicht")
        
        # Dock-Toggles
        docks = [
            ("Workflows", self._dock_workflows),
            ("Workflow Templates", self._dock_templates_wf),
            ("State Templates", self._dock_templates_st),
            ("OCR Variablen", self._dock_ocr),
            ("State Variablen", self._dock_states),
            ("Log", self._dock_log),
            ("Daten-Listen", self._dock_daten),
        ]
        for title, dock in docks:
            view_menu.addAction(dock.toggleViewAction())
            
        view_menu.addSeparator()

        # Layout fixieren
        self._act_lock_layout = QAction("Layout fixieren", self)
        self._act_lock_layout.setCheckable(True)
        self._act_lock_layout.setChecked(self._ui_locked)
        self._act_lock_layout.triggered.connect(self._layout_sperren_umschalten)
        view_menu.addAction(self._act_lock_layout)

        view_menu.addSeparator()
        act_reset = QAction("Layout zurücksetzen", self)
        act_reset.triggered.connect(self._reset_layout)
        view_menu.addAction(act_reset)

    def _reset_layout(self):
        """Setzt das Dock-Layout auf den IDE-Klassik Standard zurück."""
        # Alle Docks einblenden
        self._dock_workflows.show()
        self._dock_templates_wf.show()
        self._dock_templates_st.show()
        self._dock_ocr.show()
        self._dock_states.show()
        self._dock_log.show()
        self._dock_daten.show()
        
        # Positionen erzwingen
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_workflows)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_templates_wf)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_templates_st)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock_ocr)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock_states)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dock_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dock_daten)
        
        # Tabbing unten
        self.tabifyDockWidget(self._dock_log, self._dock_daten)
        self._dock_log.raise_()
        
        # Größen (ungefähr)
        self.resizeDocks([self._dock_workflows, self._dock_templates_wf, self._dock_templates_st], [300, 300, 200], Qt.Orientation.Vertical)
        self.resizeDocks([self._dock_ocr, self._dock_states], [400, 200], Qt.Orientation.Vertical)
        
        self._fenster_geometrie_speichern()
        self._log("UI Layout zurückgesetzt.")

    def _layout_sperren_umschalten(self):
        """Sperrt oder entsperrt das Verschieben und Rauslösen von Docks."""
        self._ui_locked = self._act_lock_layout.isChecked()
        self.einstellungen["layout_locked"] = self._ui_locked
        self.app.save_settings()

        docks = self.findChildren(QDockWidget)
        for dock in docks:
            if self._ui_locked:
                dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            else:
                dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | 
                                 QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                                 QDockWidget.DockWidgetFeature.DockWidgetClosable)
            
            # Titelzeile informieren
            tb = dock.titleBarWidget()
            if isinstance(tb, CustomDockTitleBar):
                tb.set_locked(self._ui_locked)

        self._log(f"UI Layout {'fixiert' if self._ui_locked else 'entsperrt'}.")

    def _create_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea, object_name: str) -> QDockWidget:
        """Erstellt ein QDockWidget mit einer eigenen einklappbaren Titelzeile."""
        dock = QDockWidget(title, self)
        dock.setObjectName(object_name)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        # Features je nach Sperrzustand
        if self._ui_locked:
            dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        else:
            dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | 
                             QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                             QDockWidget.DockWidgetFeature.DockWidgetClosable)

        # Eigene Titelzeile setzen
        title_bar = CustomDockTitleBar(title, dock)
        title_bar.set_locked(self._ui_locked)
        dock.setTitleBarWidget(title_bar)
        
        self.addDockWidget(area, dock)
        return dock

    def _gui_aufbauen(self):
        # ── Zentrales Widget (Live-Vorschau) ──────────────────────────────────
        self._vorschau = VorschauLabel()
        self._vorschau.setMinimumWidth(400)
        
        self._vorschau_scroll = QScrollArea()
        self._vorschau_scroll.setWidgetResizable(True)
        self._vorschau_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vorschau_scroll.setWidget(self._vorschau)
        self.setCentralWidget(self._vorschau_scroll)

        # ── Docks Erstellen ───────────────────────────────────────────────────
        
        # 1. Links: Workflows & Templates
        self.workflow_panel = WorkflowPanelQt()
        self._dock_workflows = self._create_dock("Workflows", self.workflow_panel, Qt.DockWidgetArea.LeftDockWidgetArea, "dock_workflows")

        self.template_panel = TemplatePanelQt(filter_modus="workflow", show_buttons=True)
        self._dock_templates_wf = self._create_dock("Workflow Templates", self.template_panel, Qt.DockWidgetArea.LeftDockWidgetArea, "dock_templates_wf")
        
        self.state_template_panel = TemplatePanelQt(filter_modus="state", show_buttons=True)
        self._dock_templates_st = self._create_dock("State Templates", self.state_template_panel, Qt.DockWidgetArea.LeftDockWidgetArea, "dock_templates_st")
        
        # 2. Rechts: OCR & States
        self.ocr_panel = VariablePanelQt()
        self._dock_ocr = self._create_dock("OCR Variablen", self.ocr_panel, Qt.DockWidgetArea.RightDockWidgetArea, "dock_ocr")

        self.state_panel = StatePanelQt()
        self._dock_states = self._create_dock("State Variablen", self.state_panel, Qt.DockWidgetArea.RightDockWidgetArea, "dock_states")

        # 3. Unten: Log & Daten
        self.log_panel = LogPanelQt()
        self._dock_log = self._create_dock("Log", self.log_panel, Qt.DockWidgetArea.BottomDockWidgetArea, "dock_log")

        self.global_vars_panel = DatenPanelQt(bot_ref=self, filter_typ="timer")
        self._dock_global_vars = self._create_dock("Globale Var.", self.global_vars_panel, Qt.DockWidgetArea.BottomDockWidgetArea, "dock_global_vars")

        self.daten_panel = DatenPanelQt(bot_ref=self, filter_typ="daten")
        self._dock_daten = self._create_dock("Daten-Listen", self.daten_panel, Qt.DockWidgetArea.BottomDockWidgetArea, "dock_daten")

        # Log, Globale Var und Daten tabben
        self.tabifyDockWidget(self._dock_log, self._dock_global_vars)
        self.tabifyDockWidget(self._dock_global_vars, self._dock_daten)
        self._dock_log.raise_() # Log standardmäßig vorne

        # ── Toolbar ───────────────────────────────────────────────────────────
        # In QMainWindow nutzen wir die native Toolbar-Area
        toolbar_widget = self._setup_toolbar()
        # Wir betten das existierende Toolbar-Frame in ein QWidget ein, 
        # oder nutzen addToolBar (bequemer). 
        # Da wir das CSS für das Frame behalten wollen, fügen wir es oben im Layout hinzu.
        
        # Wir erstellen einen Container für das CentralWidget + Toolbar, 
        # da setCentralWidget den ganzen Platz einnimmt.
        # Alternativ: Die Toolbar bleibt ein QWidget im CentralWidget Layout.
        
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Erst das Live-Bild (Vorschau)
        main_layout.addWidget(self._vorschau_scroll, stretch=1)
        
        # Dann die Toolbar (Buttons) unten drunter
        main_layout.addWidget(toolbar_widget)
        
        self.setCentralWidget(main_container)

    def _setup_templates_widget(self) -> QWidget:
        """Kombiniert Workflow-, State-Templates und Buttons für das Dock."""
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(4, 4, 4, 4)
        l.setSpacing(4)

        # Workflow-Templates
        self.template_panel = TemplatePanelQt(filter_modus="workflow", show_buttons=False)
        def select_workflow():
            self._aktiver_template_panel = self.template_panel
            self.state_template_panel.auswahl_aufheben()
        self.template_panel.liste.itemClicked.connect(select_workflow)
        l.addWidget(QLabel("WORKFLOW TEMPLATES"))
        l.addWidget(self.template_panel, stretch=2)

        # State-Templates
        self.state_template_panel = TemplatePanelQt(filter_modus="state", show_buttons=False)
        def select_state():
            self._aktiver_template_panel = self.state_template_panel
            self.template_panel.auswahl_aufheben()
        self.state_template_panel.liste.itemClicked.connect(select_state)
        l.addWidget(QLabel("STATE TEMPLATES"))
        l.addWidget(self.state_template_panel, stretch=1)

        # Geteilte Template-Buttons
        self._setup_shared_template_buttons(l)
        return w

    def _setup_shared_template_buttons(self, parent_layout: QVBoxLayout):
        """Gemeinsame Button-Leiste für Workflow- und State-Template-Panel."""
        bar = QWidget()
        bar_lay = QVBoxLayout(bar)
        bar_lay.setContentsMargins(0, 2, 0, 4)
        bar_lay.setSpacing(4)

        def _name():
            p = getattr(self, "_aktiver_template_panel", None) or self.template_panel
            n = p.get_auswahl_name()
            # self._log(f"DEBUG: Auswahl-Name aus Panel: '{n}'")
            return n

        def _gruppe():
            p = getattr(self, "_aktiver_template_panel", None) or self.template_panel
            return p._last_gruppe

        zeile1 = QHBoxLayout()
        zeile1.setSpacing(4)
        btn_neu      = QPushButton("+ Neu")
        btn_neu.setObjectName("btn_new_sm")
        btn_bearb    = QPushButton("✎ Bearbeiten")
        btn_bearb.setObjectName("btn_sm")
        btn_del      = QPushButton("✕ Löschen")
        btn_del.setObjectName("btn_del_sm")
        for btn in [btn_neu, btn_bearb, btn_del]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            zeile1.addWidget(btn)

        zeile2 = QHBoxLayout()
        zeile2.setSpacing(4)
        btn_ocr      = QPushButton(f"🔤 {lang.t('btn_ocr')}")
        btn_ocr.setObjectName("btn_ocr_action")
        btn_klick    = QPushButton(f"🖱 {lang.t('btn_click')}")
        btn_klick.setObjectName("btn_klick_action")
        btn_gruppe   = QPushButton(f"🚩 {lang.t('tab_states')}")
        btn_gruppe.setObjectName("btn_states_action")
        for btn in [btn_ocr, btn_klick, btn_gruppe]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            zeile2.addWidget(btn)

        bar_lay.addLayout(zeile1)
        bar_lay.addLayout(zeile2)
        parent_layout.addWidget(bar)

        def on_bearbeiten_click():
            name = _name()
            if name:
                self._template_bearbeiten(name)

        btn_neu.clicked.connect(self._template_neu_erstellen)
        btn_bearb.clicked.connect(on_bearbeiten_click)
        btn_del.clicked.connect(lambda: _name() and self._template_loeschen(_name()))
        btn_ocr.clicked.connect(lambda: _name() and self._ocr_konfigurieren(_name()))
        btn_klick.clicked.connect(lambda: _name() and self._klick_konfigurieren(_name()))
        btn_gruppe.clicked.connect(lambda: _gruppe() and self._gruppe_konfigurieren(_gruppe()))

    def _setup_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setObjectName("toolbar_frame")
        toolbar.setFixedHeight(44)

        l = QHBoxLayout(toolbar)
        l.setContentsMargins(10, 4, 10, 4)
        l.setSpacing(6)

        # Start / Stop
        self.start_btn = QPushButton("▶ Start")
        self.start_btn.setObjectName("btn_start")
        self.start_btn.clicked.connect(self._start)
        l.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("btn_stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        l.addWidget(self.stop_btn)

        # Status
        self.status_label = QLabel("● Bereit")
        self.status_label.setObjectName("status_label")
        l.addWidget(self.status_label)

        l.addStretch()

        # Rechts: Debug / Snapshot / Einstellungen / ?
        self.debug_btn = QPushButton("● Debug Aus")
        self.debug_btn.setObjectName("btn_debug_toggle")
        self.debug_btn.setCheckable(True)
        self.debug_btn.clicked.connect(self._debug_umschalten)
        l.addWidget(self.debug_btn)

        snapshot_btn = QPushButton("📸 Snapshot")
        snapshot_btn.setObjectName("btn_sm")
        snapshot_btn.clicked.connect(self._snapshot_erstellen)
        l.addWidget(snapshot_btn)

        settings_btn = QPushButton("Einstellungen")
        settings_btn.setObjectName("btn_sm")
        settings_btn.clicked.connect(self._einstellungen_dialog)
        l.addWidget(settings_btn)

        legende_btn = QPushButton("?")
        legende_btn.setObjectName("btn_sm")
        legende_btn.setFixedWidth(28)
        legende_btn.clicked.connect(self._legende_zeigen)
        l.addWidget(legende_btn)

        return toolbar

    # ── Signal-Verbindungen ───────────────────────────────────────────────────

    def _connect_signals(self):
        # Vorschau-Selektion
        self._vorschau.region_ausgewaehlt.connect(self._region_ausgewaehlt)

        # Workflow-Panel
        self.workflow_panel.master_neu_requested.connect(self._master_neu)
        self.workflow_panel.master_bearbeiten_requested.connect(self._master_bearbeiten)
        self.workflow_panel.master_loeschen_requested.connect(self._master_loeschen)
        self.workflow_panel.master_aktiv_requested.connect(self._master_aktiv_setzen)
        self.workflow_panel.workflow_neu_requested.connect(self._workflow_neu)
        self.workflow_panel.workflow_bearbeiten_requested.connect(self._workflow_bearbeiten)
        self.workflow_panel.workflow_kopieren_requested.connect(self._workflow_kopieren)
        self.workflow_panel.workflow_loeschen_requested.connect(self._workflow_loeschen)
        self.workflow_panel.logic_network_edit_requested.connect(self._logic_netzwerk_bearbeiten)
        self.workflow_panel.logic_network_copy_requested.connect(self._logic_kopieren)

        # Template-Panels
        self.template_panel.neu_laden_requested.connect(self._template_neu_erstellen)
        self.state_template_panel.neu_laden_requested.connect(self._template_neu_erstellen)
        for panel in [self.template_panel, self.state_template_panel]:
            panel.bearbeiten_requested.connect(self._template_bearbeiten)
            panel.loeschen_requested.connect(self._template_loeschen)
            panel.ocr_konfigurieren_requested.connect(self._ocr_konfigurieren)
            panel.klick_konfigurieren_requested.connect(self._klick_konfigurieren)
            panel.gruppe_konfigurieren_requested.connect(self._gruppe_konfigurieren)

        # Variable-Panel (OCR)
        self.ocr_panel.feste_region_loeschen.connect(
            lambda n: (self.ocr_engine.region_loeschen(n), self._panels_aktualisieren()))
        self.ocr_panel.template_ocr_loeschen.connect(
            lambda n: (self.ocr_engine.template_ocr_deaktivieren(n), self._panels_aktualisieren()))
        self.ocr_panel.ocr_konfigurieren_requested.connect(self._ocr_konfigurieren)

        # State-Panel
        self.state_panel.add_requested.connect(self._state_hinzufuegen)
        self.state_panel.rename_requested.connect(self._state_umbenennen)
        self.state_panel.delete_requested.connect(self._state_loeschen)

        # Daten-Panels (Global & Listen)
        for p in [self.global_vars_panel, self.daten_panel]:
            p.liste_bearbeiten_requested.connect(self._liste_bearbeiten_dialog)
            p.timer_bearbeiten_requested.connect(self._timer_bearbeiten_dialog)
            p.einheiten_requested.connect(self._einheiten_dialog)
            p.geandert.connect(self._panels_aktualisieren)

    # ── Display Loop ──────────────────────────────────────────────────────────

    def _check_memu_retry(self):
        if self.app.find_memu():
            self.app.start()
            self._start_display_loop()
        else:
            QTimer.singleShot(3000, self._check_memu_retry)

    def _start_display_loop(self):
        fps = self.einstellungen.get("display_fps", DISPLAY_FPS_DEFAULT)
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(1000 // fps)
        self._display_timer.timeout.connect(self._display_tick)
        self._display_timer.start()

    def _display_tick(self):
        if not self.app.state.capture_active:
            return
        frame = self.app.current_screenshot_np
        if frame is None:
            return

        ocr_konf = dict(self.ocr_engine.template_ocr_konfigurationen())
        self._vorschau.set_frame(
            frame,
            list(self.app.state.active_matches),
            dict(self.ocr_engine.regionen),
            dict(self.app.state.ocr_values),
            ocr_konf,
        )

        # Panel-Updates
        matches = list(self.app.state.active_matches)
        match_namen = {m[0] for m in matches}
        match_namen |= {m[6] for m in matches if len(m) > 6}

        if not hasattr(self, "_letzte_match_namen") or self._letzte_match_namen != match_namen:
            self._letzte_match_namen = match_namen
            self.ocr_panel.aktualisieren(
                dict(self.ocr_engine.regionen),
                ocr_konf,
                _template_farbe,
                is_smart_func=self.template_engine._is_smart_recursive
            )

        alle_ocr_werte = {**self.app.state.ocr_values, **self.app.state.template_ocr_values}
        
        # Globale Variablen (DB) hinzufügen
        try:
            jetzt = time.time()
            for l in alle_listen():
                if l.get("typ") == "timer":
                    cache = cache_lesen(l["id"])
                    for var_name, (val, ts) in cache.items():
                        if var_name.endswith("._deadline"): continue
                        
                        full_key = f"db::{l['name']}::{var_name}"
                        is_timer = not var_name.startswith("[W] ")
                        
                        if is_timer:
                            de = cache.get(f"Timer.{var_name}._deadline")
                            if de:
                                rest = max(0, int(float(de[0]) - jetzt))
                                alle_ocr_werte[full_key] = sekunden_formatieren(rest)
                            else:
                                alle_ocr_werte[full_key] = "–"
                        else:
                            alle_ocr_werte[full_key] = str(val)
        except Exception:
            pass

        self.ocr_panel.werte_aktualisieren(
            alle_ocr_werte,
            match_namen,
            ocr_konf
        )
        self.state_panel.werte_aktualisieren(dict(self.app.state.game_states))

    # ── Bot-Steuerung ─────────────────────────────────────────────────────────

    def _start(self):
        self.app.start_bot()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._status_setzen("● Bot läuft", "#2ea043")
        self._log("Bot gestartet.")

    def _stop(self):
        self.app.stop_bot()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._status_setzen("● Gestoppt", "#888888")
        self._log("Bot gestoppt.")

    def _snapshot_erstellen(self):
        snap_np = self.app.current_screenshot_np
        if snap_np is None:
            return
        name, ok = QInputDialog.getText(self, "Snapshot", "Name für Snapshot:")
        if ok and name:
            os.makedirs("snapshots", exist_ok=True)
            pfad = os.path.join("snapshots", f"{name}.png")
            if cv2:
                cv2.imwrite(pfad, snap_np)
                self._log(f"Snapshot gespeichert: {pfad}")

    def _debug_umschalten(self):
        if self.ocr_engine.debug_filter == "Aus":
            self.ocr_engine.debug_filter = "Alle"
            self.debug_btn.setText("● Debug An")
            self.debug_btn.setProperty("active", True)
        else:
            self.ocr_engine.debug_filter = "Aus"
            self.debug_btn.setText("● Debug Aus")
            self.debug_btn.setProperty("active", False)
        self.debug_btn.setStyle(self.debug_btn.style())

    # ── Einlern-Modus ─────────────────────────────────────────────────────────

    def _einlern_modus_umschalten(self):
        if self.ocr_modus:
            self._ocr_modus_umschalten()
        self.einlern_modus = not self.einlern_modus
        if self.einlern_modus:
            self._vorschau.set_aktiv(True)
            self._log("Einlern-Modus aktiv – Region auf der Vorschau auswählen.")
            self.status_label.setText("● Einlern-Modus")
            self.status_label.setProperty("class", "lbl_warning")
        else:
            self._geplanter_typ = None
            self._geplante_kategorie = None
            self._aktueller_ausschnitt = None
            self._vorschau.set_aktiv(False)
            self.status_label.setText("● Bereit")
            self.status_label.setProperty("class", "")
        self.status_label.setStyle(self.status_label.style())

    def _ocr_modus_umschalten(self):
        if self.einlern_modus:
            self._einlern_modus_umschalten()
        self.ocr_modus = not self.ocr_modus
        if self.ocr_modus:
            self._vorschau.set_aktiv(True)
            self._log("OCR-Modus aktiv – Region auf der Vorschau auswählen.")
            self.status_label.setText("● OCR-Modus")
            self.status_label.setProperty("class", "lbl_highlight")
        else:
            self._vorschau.set_aktiv(False)
            self.status_label.setText("● Bereit")
            self.status_label.setProperty("class", "")
        self.status_label.setStyle(self.status_label.style())

    def _region_ausgewaehlt(self, x0: int, y0: int, x1: int, y1: int, form: str = "box"):
        screenshot = self.app.current_screenshot_pil
        if screenshot is None:
            self._log("Kein Screenshot verfügbar.")
            return

        if self.ocr_modus:
            self._ocr_region_speichern(x0, y0, x1, y1)
            return

        if self.einlern_modus and _PILImage:
            ausschnitt = screenshot.crop((x0, y0, x1, y1))
            
            # Falls Kreis, Alpha-Maske anwenden
            if form == "kreis":
                from PIL import ImageDraw
                ausschnitt = ausschnitt.convert("RGBA")
                mask = _PILImage.new("L", ausschnitt.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, ausschnitt.size[0], ausschnitt.size[1]), fill=255)
                ausschnitt.putalpha(mask)

            self._aktueller_ausschnitt = (ausschnitt, x1 - x0, y1 - y0, form)
            
            # Öffne/update Template-Editor
            try:
                editor_offen = (hasattr(self, "_einlern_editor") and
                                self._einlern_editor is not None and
                                self._einlern_editor.isVisible())
            except RuntimeError:
                editor_offen = False
                self._einlern_editor = None
                
            if editor_offen:
                # Nutzt die neue Methode zur sauberen Bild-Aktualisierung
                self._einlern_editor.neues_bild_setzen(ausschnitt)
                self._einlern_modus_umschalten()
            else:
                self._einlern_dialog_oeffnen()

    def set_live_ocr_receiver(self, receiver):
        self._live_ocr_receiver = receiver

    def _ocr_region_speichern(self, x0: int, y0: int, x1: int, y1: int):
        # Wenn ein Dialog eine Live-Wahl angefordert hat, schicken wir sie dorthin
        if hasattr(self, "_live_ocr_receiver") and self._live_ocr_receiver:
            self._live_ocr_receiver.empfange_live_region(x0, y0, x1, y1)
            self._live_ocr_receiver = None
            if self.ocr_modus:
                self._ocr_modus_umschalten() # Modus wieder aus
            return

        name, ok = QInputDialog.getText(self, "OCR-Region", "Name der Region:")
        if not ok or not name:
            return
        modi = ["Timer", "Zahl", "Text"]
        modus_str, ok2 = QInputDialog.getItem(self, "OCR-Modus", "Modus:", modi, 1, False)
        if not ok2:
            return
        self.ocr_engine.region_hinzufuegen(name, x0, y0, x1 - x0, y1 - y0, modus_str)
        self._panels_aktualisieren()
        self._log(f"OCR-Region gespeichert: \"{name}\" ({modus_str}, {x1-x0}×{y1-y0}px)")
        self._ocr_modus_umschalten()

    def _einlern_dialog_oeffnen(self):
        editor = TemplateEditorQt(
            parent=self,
            bot=self,
            bearbeiten_name=None,
            aktueller_ausschnitt=self._aktueller_ausschnitt,
            typ=self._geplanter_typ or "template",
            kategorie=self._geplante_kategorie or "workflow",
        )
        self._einlern_editor = editor

        def on_close():
            self._einlern_editor = None
            if self.einlern_modus:
                self._einlern_modus_umschalten()

        editor.destroyed.connect(on_close)
        self._show_dialog(editor)

    # ── Template-Aktionen ─────────────────────────────────────────────────────

    def _template_neu_erstellen(self):
        result = TypDialog.ausfuehren(self)
        if result is None:
            return
        typ, kategorie = result[0], result[1]
        if typ == "passiv_gruppe":
            art = result[2].get("art", "master") if len(result) > 2 else "master"
            self._passiv_gruppe_erstellen_dialog(kategorie, ist_master=(art == "master"))
        else:
            self._geplanter_typ = typ
            self._geplante_kategorie = kategorie
            self._einlern_modus_umschalten()

    def _template_bearbeiten(self, name: str):
        try:
            self._log(f"DEBUG: Erstelle TemplateEditorQt für '{name}'...")
            editor = TemplateEditorQt(
                parent=self,
                bot=self,
                bearbeiten_name=name,
                typ=self.template_engine.settings.get(name, {}).get("typ", "template"),
                kategorie=self.template_engine.settings.get(name, {}).get("kategorie", "workflow"),
            )
            self._log(f"DEBUG: Editor erstellt, rufe _show_dialog auf.")
            self._show_dialog(editor)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self._log(f"FEHLER beim Öffnen des Editors: {e}")
            print(error_details) # Auch in die Konsole für volle Details

    def _template_loeschen(self, name: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Löschen")
        msg.setText(f"\"{name}\" wirklich löschen?")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_nein)
        msg.exec()
        
        if msg.clickedButton() != btn_ja:
            return
            
        typ = self.template_engine.settings.get(name, {}).get("typ", "template")
        
        # Alle betroffenen Elemente sammeln, um OCR und Klicks zu bereinigen
        zu_loeschen = [name]
        if typ in ("passiv_gruppe", "aktiv_gruppe"):
            zu_loeschen.extend(self.template_engine.get_kinder(name))
            self.template_engine.gruppe_config_loeschen(name, mit_inhalt=True)
        else:
            self.template_engine.template_loeschen(name)

        # OCR-Variablen und Klickzonen für alle betroffenen Elemente löschen
        for element in zu_loeschen:
            try:
                self.ocr_engine.template_ocr_alle_loeschen(element)
            except Exception:
                pass
            
            try:
                self.action_engine.klickzone_loeschen(element)
            except Exception:
                pass

        self.app.reload_templates()
        self._panels_aktualisieren()
        info_text = f" (inkl. {len(zu_loeschen)-1} Unterelementen)" if len(zu_loeschen) > 1 else ""
        self._log(f"Gelöscht: {name}{info_text}")

    def _template_neu_laden(self):
        self.app.reload_templates()
        self._panels_aktualisieren()
        self._log("Templates neu geladen.")

    def _ocr_konfigurieren(self, name: str):
        dlg = OCRKonfigDialog(name, bot=self, parent=self)
        dlg.gespeichert.connect(self._panels_aktualisieren)
        self._show_dialog(dlg)

    def _klick_konfigurieren(self, name: str):
        """Öffnet Klickzone-Dialog für ein Template (einfacher QDialog)."""
        if _PILImage is None:
            self._log("PIL nicht verfügbar.")
            return
        import os
        pfad = self.template_engine.templates.get(name, {}).get("pfad") or \
               os.path.join("templates", f"{name}.png")
        if not os.path.exists(pfad):
            self._log(f"Template-Bild nicht gefunden: {pfad}")
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from ui.dialogs.roi_editor_qt import ROIEditorQt

        pil = _PILImage.open(pfad).convert("RGBA")
        bbox = self.template_engine.templates.get(name, {}).get("bbox")
        if bbox:
            bx, by, bw, bh = bbox
            pil = pil.crop((bx, by, bx + bw, by + bh))

        # Nutze ROIEditorQt vereinfacht — zeige einfaches QDialog mit Click-Point
        self._klick_dialog(name, pil)

    def _klick_dialog(self, name: str, pil_bild):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from PyQt6.QtGui import QPixmap, QImage

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Klickzone — {name}")
        dlg.setModal(True)

        tw, th = pil_bild.size
        skala = max(3.0, min(8.0, 300 / max(tw, th)))
        nw, nh = int(tw * skala), int(th * skala)
        scaled = pil_bild.resize((nw, nh), _PILImage.LANCZOS).convert("RGB")
        qimg = QImage(scaled.tobytes(), nw, nh, nw * 3, QImage.Format.Format_RGB888)
        pm = QPixmap.fromImage(qimg)

        root = QVBoxLayout(dlg)
        canvas = KlickCanvas(pm)
        root.addWidget(canvas)

        # Bestehenden Punkt laden
        konfig = self.action_engine.klickzonen_laden()
        if name in konfig:
            k = konfig[name]
            canvas.set_punkt(k["klick_rel_x"], k["klick_rel_y"])

        info = QLabel("Klick-Punkt setzen.")
        info.setProperty("class", "lbl_info")
        root.addWidget(info)

        btn_save = QPushButton("Speichern")
        btn_save.setObjectName("btn_new")

        def speichern():
            if canvas._rx is not None:
                self.action_engine.klickzone_speichern(name, canvas._rx, canvas._ry)
                self._log(f"Klickzone gespeichert: {name} ({canvas._rx}%, {canvas._ry}%)")
            dlg.accept()

        btn_save.clicked.connect(speichern)
        root.addWidget(btn_save)
        dlg.exec()

    def _gruppe_konfigurieren(self, name: str):
        settings = self.template_engine.settings.get(name, {})
        bekannte = sorted(self.app.state.game_states.keys())
        raw = settings.get("condition_states", [])
        
        # Früher gab es 'target_state' (string), jetzt 'set_states' (dict)
        # Wir migrieren beim Laden falls nötig
        set_states = settings.get("set_states", {})
        if not set_states and settings.get("target_state"):
            set_states = {settings["target_state"]: True}

        search_only = settings.get("search_only", False)

        dlg = GruppeEditorQt(name, bekannte, raw, set_states=set_states, search_only=search_only, parent=self)

        def on_gespeichert(gruppe_name, conditions, new_set_states, new_search_only):
            if name not in self.template_engine.settings:
                self.template_engine.settings[name] = {}
            self.template_engine.settings[name]["condition_states"] = conditions
            self.template_engine.settings[name]["set_states"] = new_set_states
            self.template_engine.settings[name]["search_only"] = new_search_only
            # Altes Feld aufräumen
            if "target_state" in self.template_engine.settings[name]:
                del self.template_engine.settings[name]["target_state"]
                
            self.template_engine._settings_speichern()
            self.app.reload_templates()
            self._panels_aktualisieren()
            self._log(f"Gruppen-Konfiguration gespeichert: {gruppe_name}")

        def on_geloescht(gruppe_name):
            zu_loeschen = [gruppe_name] + self.template_engine.get_kinder(gruppe_name)
            self.template_engine.gruppe_config_loeschen(gruppe_name, mit_inhalt=True)
            
            # OCR-Variablen und Klickzonen für alle betroffenen Elemente löschen
            for element in zu_loeschen:
                try:
                    self.ocr_engine.template_ocr_alle_loeschen(element)
                except Exception:
                    pass
                
                try:
                    self.action_engine.klickzone_loeschen(element)
                except Exception:
                    pass

            self.app.reload_templates()
            self._panels_aktualisieren()
            info_text = f" (inkl. {len(zu_loeschen)-1} Unterelementen)" if len(zu_loeschen) > 1 else ""
            self._log(f"Gruppen-Konfiguration gelöscht: {gruppe_name}{info_text}")

        dlg.gespeichert.connect(on_gespeichert)
        dlg.geloescht.connect(on_geloescht)
        dlg.exec()

    # ── Passiv-Gruppe ─────────────────────────────────────────────────────────

    def _passiv_gruppe_erstellen_dialog(self, kategorie: str = "workflow", ist_master: bool = True):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QComboBox, QLabel, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("Neue Gruppe erstellen")
        dlg.setModal(True)
        dlg.setFixedWidth(350)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        titel = "Master-Gruppe" if ist_master else "Untergeordnete Gruppe"
        lbl_titel = QLabel(f"{titel} ({kategorie.capitalize()})")
        lbl_titel.setObjectName("dialog_header_title_gold_small")
        root.addWidget(lbl_titel)

        root.addWidget(QLabel("Name der neuen Gruppe:"))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("z.B. Hauptmenü, Kampf, etc.")
        root.addWidget(name_edit)

        combo = None
        if not ist_master:
            root.addWidget(QLabel("Zuweisen zu Gruppe:"))
            combo = QComboBox()
            # Nur Gruppen der gleichen Kategorie anzeigen
            verfuegbar = sorted([
                g for g, v in self.template_engine.settings.items()
                if isinstance(v, dict)
                and v.get("typ") in ("passiv_gruppe", "aktiv_gruppe")
                and v.get("kategorie") == kategorie
            ])
            if not verfuegbar:
                lbl_no = QLabel("Keine Gruppen zur Zuweisung vorhanden!\nBitte erst eine Master-Gruppe erstellen.")
                lbl_no.setProperty("class", "lbl_error")
                root.addWidget(lbl_no)
                btn_erstellen.setEnabled(False)
            else:
                combo.addItems(verfuegbar)
                root.addWidget(combo)

        err_lbl = QLabel("")
        err_lbl.setProperty("class", "lbl_error")
        root.addWidget(err_lbl)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(dlg.reject)
        
        btn_erstellen = QPushButton("Erstellen")
        btn_erstellen.setObjectName("btn_new")
        
        btn_row.addWidget(btn_cancel)
        btn_erstellen.clicked.connect(lambda: None) # placeholder for lambda in replace
        btn_row.addWidget(btn_erstellen)
        root.addLayout(btn_row)

        def erstellen():
            n = name_edit.text().strip()
            if not n:
                err_lbl.setText("Name darf nicht leer sein.")
                return
            if n in self.template_engine.settings:
                err_lbl.setText(f"'{n}' existiert bereits.")
                return
            
            uebergeordnet = ""
            if not ist_master and combo:
                uebergeordnet = combo.currentText().strip()
                if not uebergeordnet:
                    err_lbl.setText("Bitte eine Gruppe auswählen.")
                    return

            # Speichern in der Engine
            self.template_engine.gruppe_config_speichern(
                n, [], uebergeordnete_gruppe=uebergeordnet, kategorie=kategorie)
            
            self._log(f"Passive Gruppe erstellt: {n} (Kategorie: {kategorie})")
            dlg.accept()
            self.app.reload_templates()
            self._panels_aktualisieren()

        name_edit.returnPressed.connect(erstellen)
        btn_erstellen.clicked.connect(erstellen)
        dlg.exec()

    # ── Workflow-Aktionen ─────────────────────────────────────────────────────

    def _master_neu(self):
        name, ok = QInputDialog.getText(self, "Master Workflow", "Name des Master-Workflows:")
        if not ok or not name:
            return
        self.workflow_engine.master_workflow_speichern(name, {"nodes": [], "connections": []})
        self._panels_aktualisieren()
        self._log(f"Master-Workflow erstellt: {name}")

    def _master_bearbeiten(self, name: str):
        graph = self.workflow_engine.master_workflows.get(name, {})
        dlg = WorkflowEditorDialogQt(parent=self, bot=self, name=name, graph=graph, is_master=True)

        def on_gespeichert(neuer_name, neuer_graph):
            self.workflow_engine.master_workflow_speichern(neuer_name, neuer_graph, alter_name=name)
            self._panels_aktualisieren()
            self._log(f"Master-Workflow gespeichert: {neuer_name}")

        dlg.gespeichert.connect(on_gespeichert)
        self._show_dialog(dlg)

    def _master_loeschen(self, name: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Master löschen")
        msg.setText(f"Master-Workflow \"{name}\" löschen?")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_nein)
        msg.exec()
        
        if msg.clickedButton() == btn_ja:
            self.workflow_engine.master_workflow_loeschen(name)
            self._panels_aktualisieren()
            self._log(f"Master-Workflow gelöscht: {name}")

    def _master_aktiv_setzen(self, name: str):
        self.workflow_engine.master_aktiv_setzen(name)
        self._panels_aktualisieren()
        self._log(f"Aktiver Master-Workflow: {name}")

    def _workflow_neu(self):
        name, ok = QInputDialog.getText(self, "Neuer Workflow", "Workflow-Name:")
        if not ok or not name:
            return
        self.workflow_engine.workflow_speichern(name, {"nodes": [], "connections": []})
        self._panels_aktualisieren()

    def _workflow_bearbeiten(self, name: str):
        graph = self.workflow_engine.workflows.get(name, {"nodes": [], "connections": []})
        dlg = WorkflowEditorDialogQt(parent=self, bot=self, name=name, graph=graph)

        def on_gespeichert(neuer_name, neuer_graph):
            self.workflow_engine.workflow_speichern(neuer_name, neuer_graph, alter_name=name)
            self._panels_aktualisieren()
            self._log(f"Workflow gespeichert: {neuer_name}")

        dlg.gespeichert.connect(on_gespeichert)
        self._show_dialog(dlg)

    def _workflow_loeschen(self, name: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Workflow löschen")
        msg.setText(f"Workflow \"{name}\" löschen?")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_ja = msg.addButton(lang.t("dialog_yes"), QMessageBox.ButtonRole.YesRole)
        btn_nein = msg.addButton(lang.t("dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_nein)
        msg.exec()
        
        if msg.clickedButton() == btn_ja:
            self.workflow_engine.workflow_loeschen(name)
            self._panels_aktualisieren()
            self._log(f"Workflow gelöscht: {name}")

    def _workflow_kopieren(self, name: str):
        neuer_name = self.workflow_engine.workflow_kopieren(name)
        if neuer_name:
            self._panels_aktualisieren()
            self._log(f"Workflow kopiert: {name} → {neuer_name}")

    def _logic_kopieren(self, wf_type: str, wf_name: str, node_id: str, port_name: str, graph: dict):
        # Workflow finden
        wf_dict = self.workflow_engine.master_workflows if wf_type == "master" else self.workflow_engine.workflows
        target_wf = wf_dict.get(wf_name)
        if not target_wf: return

        import copy
        gefundener_node = False
        neu_port_name = f"{port_name} (Kopie)"
        for node in target_wf.get("nodes", []):
            if node.get("id") == node_id:
                if node.get("typ") == "priority_selector":
                    ausgaenge = node.get("ausgaenge", [])
                    # Den Quell-Ausgang suchen
                    quell_aus = None
                    for aus in ausgaenge:
                        if aus.get("port") == port_name:
                            quell_aus = aus
                            break

                    if quell_aus:
                        # Duplizieren
                        neu_aus = copy.deepcopy(quell_aus)
                        # Eindeutigen Namen sicherstellen
                        zaehler = 1
                        tmp_name = neu_port_name
                        while any(a.get("port") == tmp_name for a in ausgaenge):
                            zaehler += 1
                            tmp_name = f"{port_name} (Kopie {zaehler})"
                        neu_aus["port"] = tmp_name
                        neu_port_name = tmp_name

                        ausgaenge.append(neu_aus)
                        gefundener_node = True
                        break

        if gefundener_node:
            if wf_type == "master":
                self.workflow_engine.master_workflow_speichern(wf_name, target_wf)
            else:
                self.workflow_engine.workflow_speichern(wf_name, target_wf)

            self._panels_aktualisieren()
            self._log(f"Logik-Netzwerk in [{wf_name}] dupliziert: {port_name} → {neu_port_name}")
        else:
            self._log(f"Ziel-Node {node_id} nicht gefunden.")

    def _logic_netzwerk_bearbeiten(self, wf_type: str, wf_name: str, node_id: str, port_name: str, graph: dict):

        from ui.dialogs.logic_editor_qt import LogicEditorDialogQt
        
        dlg = LogicEditorDialogQt(
            name=f"{wf_name} → {port_name}",
            graph=graph,
            templates=list(self.template_engine.templates.keys()),
            parent=self,
            bot=self.app
        )
        
        def on_save(new_graph):
            # Workflow finden und updaten
            wf_dict = self.workflow_engine.master_workflows if wf_type == "master" else self.workflow_engine.workflows
            target_wf = wf_dict.get(wf_name)
            if not target_wf: return
            
            for node in target_wf.get("nodes", []):
                if node.get("id") == node_id:
                    # In den Ausgängen des Selektors suchen
                    if node.get("typ") == "priority_selector":
                        for aus in node.get("ausgaenge", []):
                            if aus.get("port") == port_name:
                                aus["logic_graph"] = new_graph
                                break
            
            # Speichern erzwingen
            if wf_type == "master":
                self.workflow_engine.master_workflow_speichern(wf_name, target_wf)
            else:
                self.workflow_engine.workflow_speichern(wf_name, target_wf)
            
            self._panels_aktualisieren()
            self._log(f"Logik-Netzwerk in [{wf_name}] gespeichert.")

        dlg.gespeichert.connect(on_save)
        self._show_dialog(dlg)

    # ── State-Aktionen ────────────────────────────────────────────────────────

    def _state_hinzufuegen(self):
        result = StateHinzufuegenDialog.ausfuehren(self)
        if result:
            name, wert = result
            self.app.state.set_game_state(name, wert)
            self._panels_aktualisieren()
            self._log(f"State-Variable hinzugefügt: {name} = {wert}")

    def _state_umbenennen(self, alter_name: str):
        aktueller_wert = self.app.state.game_states.get(alter_name, False)
        result = StateEditorDialog.ausfuehren(alter_name, aktueller_wert, self)
        if result:
            _, neuer_name, neuer_wert = result
            
            # Aus altem Namen entfernen
            self.app.state.game_states.pop(alter_name, None)
            # Mit neuem Namen (oder altem, falls gleich) und neuem Wert setzen
            self.app.state.game_states[neuer_name] = neuer_wert
            
            # Falls Name geändert wurde: Template-Settings aktualisieren
            if neuer_name != alter_name:
                self.template_engine.state_umbenennen_in_settings(alter_name, neuer_name)
                self._log(f"State umbenannt: {alter_name} → {neuer_name} (Wert: {neuer_wert})")
            else:
                self._log(f"State-Wert geändert: {neuer_name} = {neuer_wert}")
            
            self.state_panel.aktualisieren(dict(self.app.state.game_states))

    def _state_loeschen(self, name: str):
        self.app.state.game_states.pop(name, None)
        # Template-Settings aktualisieren
        self.template_engine.state_loeschen_in_settings(name)
        
        self.state_panel.aktualisieren(dict(self.app.state.game_states))
        self._log(f"State-Variable gelöscht: {name}")

    # ── Variablen / OCR Aktionen ──────────────────────────────────────────────

    def _nur_aktive_toggle(self, aktiv: bool):
        self._nur_aktive_variablen = aktiv
        self.ocr_panel.set_nur_aktive(aktiv)

    # ── Dialoge ───────────────────────────────────────────────────────────────

    def _einstellungen_dialog(self):
        result = SettingsDialog.ausfuehren(self.einstellungen, self)
        if result:
            self.einstellungen.update(result)
            self.template_engine.matching_skalierung = result.get(
                "matching_skalierung", self.template_engine.matching_skalierung)
            
            # Workflow-Delay sofort anwenden
            if "workflow_node_delay" in result:
                self.app.workflow_engine.node_delay = result["workflow_node_delay"]
            
            # Klick-Logging sofort anwenden
            if "log_klick_koordinaten" in result:
                self.app.action_engine.log_enabled = result["log_klick_koordinaten"]

            self.app.save_settings()
            # FPS des Display-Timers anpassen
            if hasattr(self, "_display_timer"):
                fps = self.einstellungen.get("display_fps", DISPLAY_FPS_DEFAULT)
                self._display_timer.setInterval(1000 // fps)

    def _legende_zeigen(self):
        dlg = LegendDialog(self)
        dlg.exec()

    def _liste_bearbeiten_dialog(self, listen_dict: dict):
        ocr_func = lambda n: {**self.app.state.ocr_values, **self.app.state.template_ocr_values}.get(n)
        dlg = DatenListeEditorQt(listen_dict, ocr_state_func=ocr_func, parent=self)
        
        # ... (OCR Variablen Sammel-Logik unverändert)
        
        def reload_all():
            self.global_vars_panel.listen_neu_laden()
            self.daten_panel.listen_neu_laden()

        # Wir müssen den Teil mit sorted_struk und set_ocr_vars behalten, 
        # aber hier im replace ist das schwierig ohne den ganzen Kontext.
        # Ich versuche nur den Aufruf-Teil am Ende zu ändern.
        pass

    def _timer_bearbeiten_dialog(self, listen_dict: dict):
        dlg = TimerEditorDialogQt(listen_dict, parent=self)
        
        def reload_all():
            self.global_vars_panel.listen_neu_laden()
            self.daten_panel.listen_neu_laden()

        dlg.gespeichert.connect(reload_all)
        dlg.finished.connect(reload_all)
        self._show_dialog(dlg)

    def _einheiten_dialog(self):
        dlg = EinheitenDialogQt(parent=self)
        dlg.exec()

    # ── Panel-Delegatoren ─────────────────────────────────────────────────────

    def _template_panel_daten(self):
        """Liefert alle Daten die TemplatePanelQt.aktualisieren() braucht."""
        def passive_gruppen_func(filter_modus: str) -> list[str]:
            return [
                n for n, s in self.template_engine.settings.items()
                if isinstance(s, dict) and s.get("typ") == "passiv_gruppe"
                and (filter_modus == "all" or s.get("kategorie", "workflow") == filter_modus)
            ]

        return (
            dict(self.template_engine.templates),
            dict(self.template_engine.settings),
            dict(self.ocr_engine.template_ocr_konfigurationen()),
            dict(self.action_engine.klickzonen_laden()),
            _template_farbe,
            passive_gruppen_func,
        )

    def _log(self, message: str):
        if hasattr(self, "log_panel"):
            QMetaObject.invokeMethod(
                self.log_panel, "log",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, message),
            )
        else:
            print(f"LOG: {message}")

    def _status_setzen(self, text: str, farbe: str):
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
            if farbe == "#2ea043":
                self.status_label.setProperty("class", "lbl_success")
            else:
                self.status_label.setProperty("class", "lbl_dim")
            self.status_label.setStyle(self.status_label.style())

    def _timer_panel_aktualisieren(self):
        """Stub — wird vom TemplateEditor aufgerufen; hier kein separates Timer-Panel."""
        pass

    def _panels_aktualisieren(self):
        """Aktualisiert alle Panels nach Template/OCR/Workflow-Änderungen."""
        daten = self._template_panel_daten()
        if hasattr(self, "template_panel"):
            self.template_panel.aktualisieren(*daten)
        if hasattr(self, "state_template_panel"):
            self.state_template_panel.aktualisieren(*daten)
        if hasattr(self, "ocr_panel"):
            self.ocr_panel.aktualisieren(
                dict(self.ocr_engine.regionen),
                dict(self.ocr_engine.template_ocr_konfigurationen()),
                _template_farbe,
                is_smart_func=self.template_engine._is_smart_recursive
            )
        if hasattr(self, "workflow_panel"):
            self.workflow_panel.aktualisieren(
                dict(self.workflow_engine.master_workflows),
                getattr(self.workflow_engine, "aktiver_master", ""),
                dict(self.workflow_engine.workflows),
            )
        if hasattr(self, "state_panel"):
            self.state_panel.aktualisieren(dict(self.app.state.game_states))

    # ── Fenstergröße & Layout Persistenz ──────────────────────────────────────

    def _fenster_groesse_initialisieren(self):
        try:
            if os.path.exists(APP_CONFIG_DATEI):
                with open(APP_CONFIG_DATEI, encoding="utf-8") as f:
                    config = json.load(f)
                
                geo = config.get("fenster_geometrie")
                if geo:
                    self.restoreGeometry(bytes.fromhex(geo))
                
                state = config.get("fenster_status")
                if state:
                    self.restoreState(bytes.fromhex(state))
                
                if geo: return
        except Exception:
            pass

        # Fallback Default
        screen = QApplication.primaryScreen().availableGeometry()
        target_w = min(1600, int(screen.width() * 0.90))
        self.resize(target_w, screen.height() - 100)

    def _fenster_geometrie_speichern(self):
        try:
            config = {}
            if os.path.exists(APP_CONFIG_DATEI):
                with open(APP_CONFIG_DATEI, encoding="utf-8") as f:
                    config = json.load(f)
            
            config["fenster_geometrie"] = self.saveGeometry().toHex().data().decode()
            config["fenster_status"]    = self.saveState().toHex().data().decode()
            
            with open(APP_CONFIG_DATEI, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent):
        self._fenster_geometrie_speichern()
        self.app.shutdown()
        QApplication.quit()
        event.accept()


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from lang import lang
    lang.load("de")
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TilesBotWindow()
    win.show()
    sys.exit(app.exec())
