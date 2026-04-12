"""
test_phase_l.py — Phase L: Template-Editor (Qt)
Testet TemplateCanvas isoliert (kein Bot nötig).
TemplateEditorQt selbst erfordert eine laufende Bot-Instanz (cv2, torch, etc.)
"""
import sys
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer

app = QApplication.instance() or QApplication(sys.argv)

from style import load as load_style
app.setStyleSheet(load_style())

from ui.dialogs.template_editor_qt import TemplateCanvas

print("OK: TemplateCanvas importiert")

# ── Demo-Fenster ──────────────────────────────────────────────────────────────
win = QWidget()
win.setWindowTitle("Phase L — TemplateCanvas Demo")
win.setStyleSheet("background: #2d2d2d;")
lay = QVBoxLayout(win)
lay.setSpacing(8)
lay.setContentsMargins(16, 16, 16, 16)

lbl = QLabel("Zwei TemplateCanvas-Widgets (Original + HG-Mathematik):")
lbl.setStyleSheet("color: #cccccc;")
lay.addWidget(lbl)

canvas_orig = TemplateCanvas("Live-Vorschau")
canvas_hg   = TemplateCanvas("GPU-Mathematik")
canvas_hg.setEnabled(False)

lay.addWidget(canvas_orig)
lay.addWidget(canvas_hg)

lbl_status = QLabel("Modus: Ignorieren  |  Ziehe ein Rechteck auf Canvas-Orig")
lbl_status.setStyleSheet("color: #888888; font-size: 8pt;")
lay.addWidget(lbl_status)

# Fake-Daten: Ignore-Regionen direkt setzen
fake_regionen = [(10, 10, 80, 60), (120, 30, 200, 100)]
canvas_orig.set_ignore_regionen(fake_regionen)

# Klick-Zone setzen (50% / 50%)
canvas_orig.set_klick_zone(50.0, 50.0)
canvas_hg.set_klick_zone(50.0, 50.0)

# Fake HG-Regionen (bbox-korrigiert)
canvas_hg.set_ignore_pixel([(5, 5, 60, 45), (90, 20, 160, 80)])

def on_region_drawn(reg):
    lbl_status.setText(f"Region gezeichnet: {reg}")
    fake_regionen.append(reg)
    canvas_orig.set_ignore_regionen(fake_regionen)

def on_klick_gesetzt(rx, ry):
    lbl_status.setText(f"Klick-Zone: {rx:.0f}% / {ry:.0f}%")
    canvas_orig.set_klick_zone(rx, ry)

canvas_orig.region_drawn.connect(on_region_drawn)
canvas_orig.klick_gesetzt.connect(on_klick_gesetzt)

# Modus-Wechsel nach 3s testen
def switch_to_klick():
    canvas_orig._modus = "klick"
    lbl_status.setText("Modus: Klick-Zone  |  Klick auf Canvas setzt Kreuz")

QTimer.singleShot(3000, switch_to_klick)

win.show()
print("OK: Demo-Fenster offen")
print()
print("Phase L — TemplateCanvas OK.")
print("TemplateEditorQt: manuell mit vollem Bot testen.")

sys.exit(app.exec())
