"""
Phase L Test — Template-Editor (Qt)
Launcher zum manuellen Testen von TemplateEditorQt.
Verwendet einen Minimal-Mock des Bots — keine GPU, kein ADB nötig.
"""
import sys
import os
from unittest.mock import MagicMock, patch

import style
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt

from ui.dialogs.template_editor_qt import TemplateEditorQt


# ── Mock-Objekte ──────────────────────────────────────────────────────────────

def _make_mock_template_engine():
    """Minimaler Mock der template_engine — lädt echte templates/ falls vorhanden."""
    te = MagicMock()

    # Echte Templates aus templates/ laden (optional)
    echte_settings = {}
    echte_templates = {}
    if os.path.exists("template_settings.json"):
        import json
        try:
            with open("template_settings.json", encoding="utf-8") as f:
                echte_settings = json.load(f)
        except Exception:
            pass

    if os.path.exists("templates"):
        try:
            from PIL import Image as _Img
        except ImportError:
            _Img = None
        for gruppe in os.listdir("templates"):
            gruppe_pfad = os.path.join("templates", gruppe)
            if not os.path.isdir(gruppe_pfad):
                continue
            for datei in os.listdir(gruppe_pfad):
                if not datei.lower().endswith(".png"):
                    continue
                name = os.path.splitext(datei)[0]
                pfad = os.path.join(gruppe_pfad, datei)
                echte_templates[name] = {
                    "pfad": pfad,
                    "gruppe": gruppe,
                    "tensor": None,
                    "maske": None,
                    "bbox": None,
                    "scan_regions": [],
                }

    te.settings = echte_settings
    te.templates = echte_templates
    te.device = "cpu"
    te._gpu_cache = {}

    # Gruppen aus echten Templates ableiten
    def get_gruppen(kategorie=None):
        gruppen = set()
        for s in echte_settings.values():
            if not isinstance(s, dict):
                continue
            g = s.get("gruppe", "")
            if g:
                gruppen.add(g)
        return sorted(gruppen)

    te.get_gruppen.side_effect = get_gruppen

    # Vorschau: gibt None zurück (kein GPU-Rendering im Mock)
    te.get_mathematik_vorschau.return_value = None

    # template_speichern: Disk-I/O überspringen, nur in-memory eintragen
    def template_speichern_mock(name, img, hg, ignore, alter_name=None, **kwargs):
        echte_settings[name] = {
            "hg_entfernen": hg,
            "hg_toleranz": kwargs.get("hintergrund_toleranz", 30),
            "match_schwellwert": kwargs.get("match_schwellwert", 0.85),
            "gruppe": kwargs.get("gruppe", name),
            "scan_regions": kwargs.get("scan_regions", []),
            "condition_states": kwargs.get("condition_states", []),
            "set_states": kwargs.get("set_states", {}),
            "ignore_regionen": ignore,
            "typ": kwargs.get("typ", "template"),
            "kategorie": kwargs.get("kategorie", "workflow"),
        }
        if alter_name and alter_name in echte_templates:
            echte_templates.pop(alter_name, None)
            echte_settings.pop(alter_name, None)
        echte_templates[name] = {
            "pfad": "", "gruppe": kwargs.get("gruppe", name),
            "tensor": None, "maske": None, "bbox": None,
            "scan_regions": kwargs.get("scan_regions", []),
        }

    te.template_speichern.side_effect = template_speichern_mock
    te.template_loeschen.side_effect = lambda n: (
        echte_templates.pop(n, None), echte_settings.pop(n, None))

    # Hintergrund-Maske: gibt leere Maske zurück
    try:
        import numpy as _np
        te._hintergrund_maske_erstellen.return_value = _np.zeros((10, 10), dtype=_np.uint8)
    except ImportError:
        te._hintergrund_maske_erstellen.return_value = None
    te._maske_bbox.return_value = None

    return te


def _make_mock_bot():
    bot = MagicMock()
    bot.template_engine = _make_mock_template_engine()

    # Action-Engine
    klick_konfig = {}
    bot.action_engine.klickzonen_laden.return_value = klick_konfig
    bot.action_engine.klickzone_speichern.side_effect = (
        lambda name, x, y: klick_konfig.update({name: {"klick_rel_x": x, "klick_rel_y": y}}))
    bot.action_engine.klickzone_loeschen.side_effect = (
        lambda name: klick_konfig.pop(name, None))

    # App / State
    bot.app.state.game_states = {
        "is_kampf": False,
        "is_menu": True,
        "is_ladescreen": False,
    }
    bot.app.current_screenshot_np = None
    bot.app.reload_templates.return_value = None

    # Log
    bot._log.side_effect = lambda msg: print(f"[BOT] {msg}")
    bot._templates_liste_aktualisieren.return_value = None
    bot._timer_panel_aktualisieren.return_value = None
    bot._modus_dialog.return_value = None
    bot._ocr_konfiguration_speichern.return_value = None
    bot.ocr_engine.template_ocr_alle_loeschen.return_value = None

    return bot


# ── Test-Fenster ──────────────────────────────────────────────────────────────

class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase L Test — Template-Editor (Qt)")
        self.resize(420, 340)
        self._bot = _make_mock_bot()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        lbl = QLabel("Phase L — Template-Editor Launcher")
        lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        root.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3a3a3a;")
        root.addWidget(sep)

        self._status = QLabel("— Ergebnis erscheint hier —")
        self._status.setStyleSheet("color: #666666; font-size: 10px;")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        def btn(label, fn):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            root.addWidget(b)

        btn("1 · Neues Template erstellen",          self._test_neu)
        btn("2 · Bestehendes Template bearbeiten",   self._test_bearbeiten)
        btn("3 · Neu mit Vorschau-Bild (Testbild)",  self._test_mit_bild)

        root.addStretch()

    def _show(self, text: str):
        self._status.setText(str(text))
        print(f"[STATUS] {text}")

    def _test_neu(self):
        """Öffnet den Editor für ein komplett neues Template."""
        dlg = TemplateEditorQt(
            parent=self,
            bot=self._bot,
            bearbeiten_name=None,
            typ="template",
            kategorie="workflow",
        )
        dlg.show()
        self._show("Editor geöffnet — kein bearbeiten_name (Neu-Modus).")

    def _test_bearbeiten(self):
        """Öffnet den Editor für das erste bekannte Template (wenn vorhanden)."""
        templates = self._bot.template_engine.templates
        if not templates:
            self._show("Keine Templates in templates/ gefunden — erst via Bot anlegen.")
            return
        name = next(iter(templates))
        dlg = TemplateEditorQt(
            parent=self,
            bot=self._bot,
            bearbeiten_name=name,
            typ="template",
            kategorie="workflow",
        )
        dlg.show()
        self._show(f"Editor geöffnet für: \"{name}\"")

    def _test_mit_bild(self):
        """Öffnet den Editor mit einem synthetischen Testbild als Vorschau."""
        try:
            from PIL import Image
            import numpy as np
            # 64×48 buntes Testbild
            arr = np.zeros((48, 64, 3), dtype=np.uint8)
            arr[:24, :32] = (80, 140, 200)    # blau oben-links
            arr[24:, :32] = (200, 80,  80)    # rot unten-links
            arr[:24, 32:] = (80, 200, 80)     # grün oben-rechts
            arr[24:, 32:] = (200, 200, 80)    # gelb unten-rechts
            testbild = Image.fromarray(arr)

            dlg = TemplateEditorQt(
                parent=self,
                bot=self._bot,
                bearbeiten_name=None,
                aktueller_ausschnitt=(testbild,),
                typ="template",
                kategorie="workflow",
            )
            dlg.show()
            self._show("Editor mit 64×48 Testbild geöffnet.")
        except ImportError:
            self._show("PIL/numpy nicht verfügbar — bitte vollständige Umgebung verwenden.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(style.load())
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
