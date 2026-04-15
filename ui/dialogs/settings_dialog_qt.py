"""
Einstellungen-Dialog (Qt). Ersetzt _einstellungen_dialog() aus ui_dialoge.py.

Signals:
    gespeichert(settings: dict)  — alle geänderten Einstellungen als Dict
"""
from lang import lang
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QCheckBox, QPushButton, QFrame, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal


LOG_KEYS = [
    ("log_variablen",            "Variablen & OCR-Werte"),
    ("log_workflow",             "Workflow-Schritte"),
    ("log_dateitransfers",       "Datei-Operationen (Verschieben/Rename)"),
    ("log_ocr_debug",            "OCR Debug-Bilder speichern"),
    ("log_matching",             "Matching-Timing"),
    ("log_gpu_templates",        "Gescannte Templates (GPU) loggen"),
    ("log_capture",              "Capture-Timing"),
    ("log_daten_berechnungen",   "Log Daten-Berechnungen (Transform/Formeln)"),
]

LOG_DEFAULTS = {"log_variablen", "log_workflow"}


class SettingsDialog(QDialog):
    gespeichert = pyqtSignal(dict)

    def __init__(self, einstellungen: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(lang.t("btn_settings"))
        self.setModal(True)
        self.setFixedWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._ein = einstellungen
        self._setup_ui()

    def _sektion(self, layout: QVBoxLayout, text: str):
        lbl = QLabel(text)
        lbl.setProperty("class", "lbl_header_dim")
        layout.addSpacing(8)
        layout.addWidget(lbl)

    def _radio_row(self, layout: QVBoxLayout, label: str, optionen: list[tuple], default) -> dict:
        """Erzeugt eine Zeile mit RadioButtons. Gibt {wert: QRadioButton} zurück."""
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setProperty("class", "lbl_dim")
        lbl.setFixedWidth(130)
        row.addWidget(lbl)

        grp = QButtonGroup(self)
        btns = {}
        for wert, text in optionen:
            rb = QRadioButton(text)
            rb.setChecked(wert == default)
            grp.addButton(rb)
            row.addWidget(rb)
            btns[wert] = rb

        layout.addLayout(row)
        return btns

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(2)

        # ── Capture ───────────────────────────────────────────────────────────
        self._sektion(root, "Capture")
        self._fps_btns = self._radio_row(root, "Display-Rate:",
            [(30, "30 fps"), (60, "60 fps")],
            self._ein.get("display_fps", 30))

        # ── OCR ───────────────────────────────────────────────────────────────
        self._sektion(root, "OCR")
        self._ocr_btns = self._radio_row(root, "OCR-Rate:",
            [(0.25, "4×/s"), (0.5, "2×/s"), (1.0, "1×/s"), (2.0, "0.5×/s")],
            self._ein.get("ocr_intervall", 0.5))

        # ── Matching ──────────────────────────────────────────────────────────
        self._sektion(root, "Matching")
        self._skal_btns = self._radio_row(root, "Auflösung:",
            [(0.25, "25%"), (0.5, "50%"), (0.75, "75%"), (1.0, "100%")],
            self._ein.get("matching_skalierung", 0.5))

        # ── Debug & Logging ───────────────────────────────────────────────────
        self._sektion(root, "Debug & Logging")
        self._log_checks: dict[str, QCheckBox] = {}
        for key, label in LOG_KEYS:
            default = self._ein.get(key, key in LOG_DEFAULTS)
            cb = QCheckBox(label)
            cb.setChecked(bool(default))
            root.addWidget(cb)
            self._log_checks[key] = cb

        # ── Trennlinie + Buttons ──────────────────────────────────────────────
        root.addSpacing(8)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("class", "separator")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton(lang.t("btn_cancel"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton(lang.t("btn_save"))
        btn_save.setObjectName("btn_new")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._speichern)
        btn_row.addWidget(btn_save)

        root.addLayout(btn_row)

    def _speichern(self):
        updates: dict = {}

        for wert, rb in self._fps_btns.items():
            if rb.isChecked():
                updates["display_fps"] = wert

        for wert, rb in self._ocr_btns.items():
            if rb.isChecked():
                updates["ocr_intervall"] = wert

        for wert, rb in self._skal_btns.items():
            if rb.isChecked():
                updates["matching_skalierung"] = wert

        for key, cb in self._log_checks.items():
            updates[key] = cb.isChecked()

        self.gespeichert.emit(updates)
        self.accept()

    @staticmethod
    def ausfuehren(einstellungen: dict, parent=None) -> dict | None:
        """Gibt geänderte Settings zurück oder None bei Abbruch."""
        result = {}
        dlg = SettingsDialog(einstellungen, parent)
        dlg.gespeichert.connect(lambda d: result.update(d))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result
        return None
