"""
Auto-Tune Dialog (Qt) — Interaktiver Top-Down Assistent.
Optimiert Schwellwert UND Hintergrund-Toleranz basierend auf User-Markierungen.
"""
import os
import torch
import time
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QProgressBar, QListWidget, QMessageBox, QFrame, QScrollArea, QWidget,
    QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont, QCursor, QPainter, QPen
from lang import lang
import cv2
import numpy as np
from PIL import Image

class AutoTunePreviewWindow(QDialog):
    """Separates Fenster für die interaktive Treffer-Markierung. Stabil skaliert."""
    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Tune: Korrekte Icons markieren")
        
        # Initiale Mindestgröße
        self.setMinimumSize(400, 300)
        
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        
        self.label = QLabel("Warte auf Scan...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background-color: #000; border: 1px solid #444;")
        
        # WICHTIG: Verhindert Feedback-Loops
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.main_layout.addWidget(self.label)
        
        self.pixmap_raw = None
        self.scan_regions = []
        self.matches = [] 
        self.skala = 1.0
        self._ratio_set = False

    def update_preview(self, pil_img, regions, matches_raw):
        if pil_img:
            img_np = np.array(pil_img.convert("RGB"))
            h, w, _ = img_np.shape
            qimg = QImage(img_np.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self.pixmap_raw = QPixmap.fromImage(qimg)
            
            # Einmalige Anpassung der Fensterform an das Bildformat
            if not self._ratio_set:
                screen = QApplication.primaryScreen().availableGeometry()
                # Wir zielen auf 75% der Bildschirmhöhe ab
                target_h = int(screen.height() * 0.75)
                ratio = w / h
                target_w = int(target_h * ratio)
                
                # Falls das Fenster zu breit für den Monitor würde (z.B. bei Widescreen)
                if target_w > screen.width() * 0.8:
                    target_w = int(screen.width() * 0.8)
                    target_h = int(target_w / ratio)
                
                self.resize(target_w, target_h)
                self._ratio_set = True
        
        self.scan_regions = regions
        old_selected = { (m["rect"].x(), m["rect"].y()) for m in self.matches if m["selected"] }
        
        self.matches = []
        for m in matches_raw:
            rx, ry = int(m[1]), int(m[2])
            is_selected = (rx, ry) in old_selected
            self.matches.append({
                "rect": QRect(rx, ry, int(m[3]), int(m[4])),
                "score": m[5],
                "selected": is_selected
            })
        
        self._redraw()

    def mousePressEvent(self, event):
        if not self.pixmap_raw or not self.matches: return
        
        # Klick-Position relativ zum Label finden
        lbl_pos = self.label.mapFrom(self, event.pos())
        
        # Versatz durch Zentrierung (Alignment) im Label berücksichtigen
        curr_pix = self.label.pixmap()
        if not curr_pix: return
        
        offset_x = (self.label.width() - curr_pix.width()) // 2
        offset_y = (self.label.height() - curr_pix.height()) // 2
        
        # Auf Bild-Koordinaten umrechnen (Nur wenn Klick innerhalb des Bildareals)
        img_x = int((lbl_pos.x() - offset_x) / self.skala)
        img_y = int((lbl_pos.y() - offset_y) / self.skala)
        
        hit = False
        for m in self.matches:
            if m["rect"].contains(img_x, img_y):
                m["selected"] = not m["selected"]
                hit = True
                break
        
        if hit:
            self._redraw()
            self.selection_changed.emit()

    def _redraw(self):
        if not self.pixmap_raw: return
        
        # Aktuelle Größe des Containers (Label) nutzen
        w, h = self.label.width(), self.label.height()
        if w < 10 or h < 10: return # Zu klein zum Zeichnen
        
        # Bild proportional skalieren
        scaled = self.pixmap_raw.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.skala = scaled.width() / self.pixmap_raw.width()
        
        # Canvas für Overlays erstellen
        canvas = scaled.copy()
        p = QPainter(canvas)
        
        # 1. ROI (Blau)
        p.setPen(QPen(QColor(0, 150, 255, 100), 1, Qt.PenStyle.DashLine))
        for r in self.scan_regions:
            x0, y0, x1, y1 = [int(v * self.skala) for v in r[:4]]
            p.drawRect(x0, y0, x1 - x0, y1 - y0)
            
        # 2. Treffer (Grün/Gelb)
        for m in self.matches:
            rx = int(m["rect"].x() * self.skala)
            ry = int(m["rect"].y() * self.skala)
            rw = int(m["rect"].width() * self.skala)
            rh = int(m["rect"].height() * self.skala)
            
            if m["selected"]:
                p.setPen(QPen(QColor(0, 255, 100), 3))
                p.drawRect(rx, ry, rw, rh)
                p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                p.drawText(rx, ry - 5, f"OK ({m['score']:.2f})")
            else:
                p.setPen(QPen(QColor(255, 200, 0, 150), 1))
                p.drawRect(rx, ry, rw, rh)
        
        p.end()
        self.label.setPixmap(canvas)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw()

class AutoTuneDialog(QDialog):
    finished_tuning = pyqtSignal(float, int)

    def __init__(self, parent, bot, template_name, current_variants, scan_regions):
        super().__init__(parent)
        self.bot = bot
        self.template_name = template_name
        self.variants = current_variants 
        self.scan_regions = scan_regions
        
        self.setWindowTitle(f"Auto-Tune Assistent: {template_name}")
        self.setMinimumSize(480, 580)
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        self.current_sw = 0.95
        self.best_tol = 30
        self.step = 1 # 1: Positiv Scan, 2: Negativ-Test, 3: Ergebnis
        self.preview_window = None
        
        self.negativ_scores = []

        self._setup_ui()
        self._update_ui()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.lbl_title = QLabel("Schritt 1: Icons identifizieren")
        self.lbl_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.main_layout.addWidget(self.lbl_title)

        self.lbl_desc = QLabel("...")
        self.lbl_desc.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_desc)

        self.progress = QProgressBar()
        self.progress.setRange(0, 3); self.progress.setValue(1); self.progress.setFixedHeight(6)
        self.main_layout.addWidget(self.progress)

        self.tune_controls = QFrame()
        self.tune_controls.setStyleSheet("background: #252525; border-radius: 8px;")
        tc_lay = QVBoxLayout(self.tune_controls)
        
        sw_row = QHBoxLayout()
        self.lbl_sw_display = QLabel("Scan-Schwellwert:")
        self.lbl_sw_val = QLabel("0.95")
        self.lbl_sw_val.setStyleSheet("color: #00ffff; font-weight: bold; font-size: 16px;")
        sw_row.addWidget(self.lbl_sw_display); sw_row.addStretch(); sw_row.addWidget(self.lbl_sw_val)
        tc_lay.addLayout(sw_row)

        btn_row = QHBoxLayout()
        self.btn_more = QPushButton("➕ Mehr Treffer"); self.btn_more.clicked.connect(self._lower_sw)
        self.btn_less = QPushButton("➖ Weniger"); self.btn_less.clicked.connect(self._higher_sw)
        btn_row.addWidget(self.btn_less); btn_row.addWidget(self.btn_more)
        tc_lay.addLayout(btn_row)

        self.btn_optimize_tol = QPushButton("🎯 Toleranz optimieren (nach Markierung)")
        self.btn_optimize_tol.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_optimize_tol.setEnabled(False)
        self.btn_optimize_tol.clicked.connect(self._run_tolerance_optimization)
        tc_lay.addWidget(self.btn_optimize_tol)
        
        self.lbl_tol_info = QLabel("Aktuelle Toleranz: 30")
        self.lbl_tol_info.setStyleSheet("color: #ff9800; font-size: 11px;")
        self.lbl_tol_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tc_lay.addWidget(self.lbl_tol_info)
        
        self.main_layout.addWidget(self.tune_controls)

        self.list_data = QListWidget()
        self.list_data.setMaximumHeight(100)
        self.main_layout.addWidget(self.list_data)

        btn_box = QHBoxLayout()
        self.btn_action = QPushButton("🔍 Bild analysieren"); self.btn_action.setObjectName("btn_highlight")
        self.btn_action.setMinimumHeight(45); self.btn_action.clicked.connect(self._perform_action)
        
        self.btn_next_step = QPushButton("Weiter ➔")
        self.btn_next_step.setMinimumHeight(45)
        self.btn_next_step.clicked.connect(self._next_step)
        self.btn_next_step.setEnabled(False)

        btn_box.addWidget(self.btn_action); btn_box.addWidget(self.btn_next_step)
        self.main_layout.addLayout(btn_box)

    def _update_ui(self):
        if self.step == 1:
            self.lbl_title.setText("🎯 Schritt 1: Icons identifizieren")
            self.lbl_desc.setText("Navigiere zum Icon. Nutze +/- bis alle Icons gelb umrandet sind. Klicke dann im Vorschaufenster die richtigen Treffer an (Grün).")
            self.tune_controls.show()
            self.progress.setValue(1)
        elif self.step == 2:
            self.lbl_title.setText("🚫 Schritt 2: Negativ-Test")
            self.lbl_desc.setText("Navigiere zu einem Screen OHNE das Icon, um das Hintergrundrauschen zu messen.")
            self.btn_action.setText("📸 Negativ messen")
            self.tune_controls.hide()
            self.progress.setValue(2)
        elif self.step == 3:
            self.lbl_title.setText("📊 Ergebnis & Finale")
            self.btn_action.hide(); self.tune_controls.hide()
            self.progress.setValue(3)
            self._berechne_ergebnis()

    def _perform_action(self):
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            if self.step == 1: self._do_top_down_scan()
            elif self.step == 2: self._measure_negativ()
        finally: self.setCursor(Qt.CursorShape.ArrowCursor)

    def _lower_sw(self):
        self.current_sw = max(0.01, self.current_sw - 0.05)
        self.lbl_sw_val.setText(f"{self.current_sw:.2f}")
        self._do_top_down_scan()

    def _higher_sw(self):
        self.current_sw = min(1.0, self.current_sw + 0.05)
        self.lbl_sw_val.setText(f"{self.current_sw:.2f}")
        self._do_top_down_scan()

    def _do_top_down_scan(self):
        if not self.bot or not hasattr(self.bot, "app") or self.bot.app.current_screenshot_np is None: return
        bgr = self.bot.app.current_screenshot_np
        self.last_img_pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        
        if not self.preview_window:
            self.preview_window = AutoTunePreviewWindow(self)
            self.preview_window.selection_changed.connect(self._on_selection_changed)
        
        matches = self._scan_with_params(bgr, self.current_sw, self.best_tol)
        if not matches and self.current_sw > 0.5:
            while not matches and self.current_sw > 0.1:
                self.current_sw -= 0.05
                matches = self._scan_with_params(bgr, self.current_sw, self.best_tol)
            self.lbl_sw_val.setText(f"{self.current_sw:.2f}")

        self.preview_window.update_preview(self.last_img_pil, self.scan_regions, matches)
        self.preview_window.show()
        self.preview_window.raise_()

    def _on_selection_changed(self):
        num_selected = len([m for m in self.preview_window.matches if m["selected"]])
        self.btn_optimize_tol.setEnabled(num_selected > 0)
        self.btn_next_step.setEnabled(num_selected > 0)

    def _run_tolerance_optimization(self):
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.btn_optimize_tol.setText("⌛ Optimiere...")
        QApplication.processEvents()
        bgr = self.bot.app.current_screenshot_np
        best_overall_delta = -1.0
        best_found_tol = 30
        toleranz_stufen = [10, 20, 30, 40, 50, 60]
        marked_rects = [m["rect"] for m in self.preview_window.matches if m["selected"]]
        for tol in toleranz_stufen:
            matches = self._scan_with_params(bgr, 0.01, tol)
            signals, noises = [], []
            for m in matches:
                m_rect = QRect(int(m[1]), int(m[2]), int(m[3]), int(m[4]))
                if any(m_rect.intersects(r) for r in marked_rects): signals.append(m[5])
                else: noises.append(m[5])
            if signals:
                delta = min(signals) - (max(noises) if noises else 0)
                if delta > best_overall_delta: best_overall_delta = delta; best_found_tol = tol
        self.best_tol = best_found_tol
        self.lbl_tol_info.setText(f"Optimale Toleranz gefunden: ⭐ {self.best_tol}")
        self.btn_optimize_tol.setText("✅ Erneut optimieren")
        self.setCursor(Qt.CursorShape.ArrowCursor); self._do_top_down_scan()

    def _measure_negativ(self):
        if self.bot.app.current_screenshot_np is not None:
            bgr = self.bot.app.current_screenshot_np
            matches = self._scan_with_params(bgr, 0.1, self.best_tol)
            if matches:
                max_noise = max(m[5] for m in matches)
                self.negativ_scores.append(max_noise)
                self.list_data.addItem(f"🚫 Max. Rauschen (Tol {self.best_tol}): {max_noise:.3f}")
            else:
                self.negativ_scores.append(0.1)
                self.list_data.addItem(f"🚫 Kein Rauschen über 0.10 gefunden.")
            self.btn_next_step.setEnabled(True)

    def _scan_with_params(self, bgr, sw, tol):
        te = self.bot.template_engine; n_tmp = "autotune_temp"; all_matches = []
        for var_img in self.variants:
            var_np = np.array(var_img.convert("RGB"))
            maske_raw = te._hintergrund_maske_erstellen(var_np, toleranz=tol)
            maske_np = np.where(maske_raw > 10, 1.0, 0.0).astype(np.float32)
            bbox = te._maske_bbox((maske_np > 0.5).astype(np.uint8))
            var_bgr = cv2.cvtColor(var_np, cv2.COLOR_RGB2BGR)
            v_bgr, m_np = (var_bgr[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]], maske_np[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]) if bbox else (var_bgr, maske_np)
            dev = te.device
            te.templates[n_tmp] = {"tensor": torch.from_numpy(v_bgr.transpose(2,0,1)).float().div(255).to(dev).unsqueeze(0), 
                                   "maske": torch.from_numpy(m_np).float().to(dev).unsqueeze(0).unsqueeze(0), 
                                   "orig_size": var_img.size, "gruppe": n_tmp, "pfad": "", "match_schwellwert": sw, "scan_regions": self.scan_regions, "bbox": bbox}
            te.settings[n_tmp] = {"match_schwellwert": sw, "scan_regions": self.scan_regions}
            res, _ = te.matches_suchen_np(bgr, force_include=[n_tmp])
            all_matches.extend([m for m in res if m[0] == n_tmp])
            te.templates.pop(n_tmp, None); te.settings.pop(n_tmp, None)
            if hasattr(te, "_matcher"): te._matcher.cache_leeren()
        return all_matches

    def _berechne_ergebnis(self):
        signals = [m["score"] for m in self.preview_window.matches if m["selected"]]
        noises = [m["score"] for m in self.preview_window.matches if not m["selected"]] + self.negativ_scores
        min_sig, max_noise = min(signals) if signals else 0.90, max(noises) if noises else 0.30
        self.best_sw = max(0.4, min(0.98, (min_sig + max_noise) / 2))
        res_w = QWidget(); lay = QVBoxLayout(res_w)
        sw_lbl = QLabel(f"{self.best_sw:.2f}"); sw_lbl.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold)); sw_lbl.setStyleSheet("color:#00ffff;"); sw_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tol_lbl = QLabel(f"Toleranz: {self.best_tol}"); tol_lbl.setFont(QFont("Segoe UI", 18)); tol_lbl.setStyleSheet("color:#ff9800;"); tol_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(QLabel("Optimierte Einstellungen:")); lay.addWidget(sw_lbl); lay.addWidget(tol_lbl)
        ld = QLabel(f"Sicherster Treffer: {min_sig:.2f}\nHöchstes Rauschen: {max_noise:.2f}\nTrennschärfe: {min_sig - max_noise:.2f}"); ld.setStyleSheet("background:#222; padding:10px;"); lay.addWidget(ld)
        self.main_layout.insertWidget(4, res_w); self.btn_next_step.setEnabled(True); self.btn_next_step.setText("Werte übernehmen & Schließen")

    def _next_step(self):
        if self.step < 3: self.step += 1; self.btn_next_step.setEnabled(False); self._update_ui()
        else:
            if self.preview_window: self.preview_window.close()
            self.finished_tuning.emit(self.best_sw, self.best_tol); self.accept()

    def closeEvent(self, event):
        if self.preview_window: self.preview_window.close()
        super().closeEvent(event)
