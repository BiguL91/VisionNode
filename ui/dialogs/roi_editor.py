import tkinter as tk
from tkinter import ttk
import os
import cv2
import numpy as np
from PIL import Image, ImageTk
from helpers import cursor_einschraenken, cursor_freigeben

class ROIEditor:
    def __init__(self, parent, bot, t_name, initial_regions, get_live_snap_func):
        self.parent = parent
        self.bot = bot
        self.t_name = t_name
        self.scan_regions = list(initial_regions)
        self.get_live_snap_func = get_live_snap_func
        
        self.window = None
        self.canvas = None
        self.scaling = 1.0
        self.snapshot_np = None
        self.snapshot_pil = None
        self.img_ref = None
        
        self.rect_ids = []
        self.test_result_ids = []
        self.drag_start = None
        self.live_rect_id = None
        
        self._setup_window()

    def _setup_window(self):
        # Initialen Snapshot holen
        self.snapshot_pil = self.get_live_snap_func()

        # Fenster-Größe: entweder vom Snapshot oder Fallback-Größe
        if self.snapshot_pil is not None:
            sw, sh = self.snapshot_pil.size
            max_h = int(self.parent.winfo_screenheight() * 0.85)
            self.scaling = max_h / sh if sh > max_h else 1.0
            rw, rh = int(sw * self.scaling), int(sh * self.scaling)
        else:
            rw, rh = 800, 500
            self.scaling = 1.0
        
        self.window = tk.Toplevel(self.parent)
        self.window.title(f"Scannbereiche - {self.t_name}")
        self.window.configure(bg="#1a1a1a")
        self.window.resizable(False, False)
        
        # Positionierung rechts vom Parent
        self.parent.update_idletasks()
        pos_x = self.parent.winfo_x() + self.parent.winfo_width() + 10
        pos_y = self.parent.winfo_y()
        self.window.geometry(f"{rw}x{rh+80}+{pos_x}+{pos_y}")
        
        # --- Snapshot Auswahl ---
        top_f = tk.Frame(self.window, bg="#2d2d2d")
        top_f.pack(fill=tk.X)
        
        tk.Label(top_f, text="Quelle:", bg="#2d2d2d", fg="#888888", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(10, 2))
        
        self.snap_var = tk.StringVar(value="Live Snapshot")
        snap_cb = ttk.Combobox(top_f, textvariable=self.snap_var, values=self._get_snap_files(), 
                               font=("Segoe UI", 9), state="readonly", width=25)
        snap_cb.pack(side=tk.LEFT, padx=5, pady=5)
        self.snap_var.trace_add("write", self._on_snap_change)
        
        tk.Button(top_f, text="🔄 Aktualisieren", bg="#3a3a3a", fg="#4488ff", font=("Segoe UI", 8), 
                  relief=tk.FLAT, padx=8, pady=2, command=self.refresh_live_snap).pack(side=tk.LEFT, padx=5)
        
        self.live_mode_btn = tk.Button(top_f, text="📍 Live wählen", bg="#3a3a3a", fg="#ffca28", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=2, command=self._toggle_live_mode)
        self.live_mode_btn.pack(side=tk.LEFT, padx=5)

        # --- Canvas ---
        self.canvas = tk.Canvas(self.window, width=rw, height=rh, bg="#000000", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        
        # --- Steuerung ---
        ctrl_f = tk.Frame(self.window, bg="#2d2d2d")
        ctrl_f.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Button(ctrl_f, text="× Alle weg", bg="#3a3a3a", fg="#da3633", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=3, command=self.clear_regions).pack(side=tk.LEFT, padx=10, pady=5)
        tk.Button(ctrl_f, text="↩ Rückgängig", bg="#3a3a3a", fg="#aaaaaa", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=3, command=self.undo_last).pack(side=tk.LEFT, pady=5)

        self.status_label = tk.Label(ctrl_f, text="Suchbereiche (ROI) festlegen",
                                     bg="#2d2d2d", fg="#888888", font=("Segoe UI", 8))
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        self.window.protocol("WM_DELETE_WINDOW", self._schliessen)
        self._update_display()

    def _schliessen(self):
        if self.bot and self.bot._ocr_konfig_callback == self._on_live_selection:
            self.bot._ocr_konfig_callback = None
            self.bot.vorschau_canvas.config(cursor="")
        self.window.destroy()

    def _toggle_live_mode(self):
        if not self.bot: return
        
        # Callback am Bot setzen
        if self.bot._ocr_konfig_callback == self._on_live_selection:
            # Ausschalten
            self.bot._ocr_konfig_callback = None
            self.bot.vorschau_canvas.config(cursor="")
            self.live_mode_btn.config(bg="#3a3a3a", fg="#ffca28")
            self.bot._log("Live-Auswahl für Scannbereiche deaktiviert.")
            # Grab wiederherstellen falls parent ihn hatte (meistens TemplateEditor)
            try: self.parent.grab_set()
            except: pass
        else:
            # Einschalten
            # WICHTIG: Grabs lösen damit Hauptfenster Events kriegt
            try: self.window.grab_release()
            except: pass
            try: self.parent.grab_release()
            except: pass
            
            self.bot._ocr_konfig_callback = self._on_live_selection
            self.bot.vorschau_canvas.config(cursor="crosshair")
            self.live_mode_btn.config(bg="#1a3a5a", fg="#ffffff")
            self.bot._log("Live-Auswahl für Scannbereiche aktiv – Region auf Live-Vorschau ziehen.")

    def _on_live_selection(self, x0, y0, x1, y1):
        # Koordinaten kommen bereits in Original-Pixeln an
        self.scan_regions.append((x0, y0, x1, y1))
        self.draw_regions()
        self.set_status(f"Region via Live-View hinzugefügt: {x1-x0}x{y1-y0}px", "#55ff88")

    def _get_snap_files(self):
        files = ["Live Snapshot"]
        if os.path.exists("snapshots"):
            f_list = [f[:-4] for f in os.listdir("snapshots") if f.endswith(".png")]
            files.extend(sorted(f_list))
        return files

    def _on_snap_change(self, *args):
        val = self.snap_var.get()
        if val == "Live Snapshot":
            self.snapshot_pil = self.get_live_snap_func()
        else:
            pfad = os.path.join("snapshots", f"{val}.png")
            if os.path.exists(pfad):
                arr = cv2.imdecode(np.fromfile(pfad, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if arr is not None:
                    self.snapshot_np = arr.copy()
                    self.snapshot_pil = Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
        self._update_display()

    def refresh_live_snap(self):
        if self.snap_var.get() == "Live Snapshot":
            self._on_snap_change()
        else:
            self.snap_var.set("Live Snapshot")

    def _update_display(self):
        self.canvas.delete("all")
        if self.snapshot_pil is None:
            self.canvas.create_text(
                self.canvas.winfo_reqwidth() // 2, self.canvas.winfo_reqheight() // 2,
                text="Kein Screenshot verfügbar\n🔄 Aktualisieren klicken",
                fill="#555555", font=("Segoe UI", 12), justify="center")
            return

        sw, sh = self.snapshot_pil.size
        rw, rh = int(sw * self.scaling), int(sh * self.scaling)

        disp_pil = self.snapshot_pil.resize((rw, rh), Image.LANCZOS) if self.scaling != 1.0 else self.snapshot_pil
        self.img_ref = ImageTk.PhotoImage(disp_pil)

        self.canvas.create_image(0, 0, anchor="nw", image=self.img_ref)
        self.draw_regions()

    def draw_regions(self):
        for rid in self.rect_ids: self.canvas.delete(rid)
        self.rect_ids.clear()
        for i, (rx0, ry0, rx1, ry1) in enumerate(self.scan_regions):
            s = self.scaling
            rid = self.canvas.create_rectangle(int(rx0*s), int(ry0*s), int(rx1*s), int(ry1*s), outline="#00ff00", width=3)
            tid = self.canvas.create_text(int(rx0*s)+5, int(ry0*s)+5, text=str(i+1), fill="#00ff00", anchor="nw", font=("Segoe UI", 10, "bold"))
            self.rect_ids.extend([rid, tid])

    def set_status(self, text, farbe="#4488ff"):
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.config(text=text, fg=farbe)

    def draw_test_results(self, matches, limit):
        for rid in self.test_result_ids: self.canvas.delete(rid)
        self.test_result_ids.clear()
        for m in matches:
            name, rx, ry, rw, rh, score = m[:6]
            farbe = "#00ff00" if score >= limit else "#ffcc00"
            s = self.scaling
            rid = self.canvas.create_rectangle(int(rx*s), int(ry*s), int((rx+rw)*s), int((ry+rh)*s), outline=farbe, width=2, dash=(4,4))
            tid = self.canvas.create_text(int(rx*s), int(ry*s)-2, text=f"{score:.2f}", fill=farbe, anchor="sw", font=("Segoe UI", 8, "bold"))
            self.test_result_ids.extend([rid, tid])

    def clear_regions(self):
        self.scan_regions.clear()
        self.draw_regions()

    def undo_last(self):
        if self.scan_regions: self.scan_regions.pop()
        self.draw_regions()

    def _on_press(self, e):
        self.drag_start = (e.x, e.y)
        cursor_einschraenken(e.widget)

    def _on_motion(self, e):
        if not self.drag_start: return
        if self.live_rect_id: self.canvas.delete(self.live_rect_id)
        x0, y0 = self.drag_start
        self.live_rect_id = self.canvas.create_rectangle(x0, y0, e.x, e.y, outline="#ffff00", width=2)

    def _on_release(self, e):
        cursor_freigeben()
        if not self.drag_start: return
        x0, y0 = self.drag_start
        x1, y1 = e.x, e.y
        self.drag_start = None
        if self.live_rect_id:
            self.canvas.delete(self.live_rect_id)
            self.live_rect_id = None
        if abs(x1-x0) > 5 and abs(y1-y0) > 5:
            s = self.scaling
            orig_x0, orig_y0 = int(min(x0,x1)/s), int(min(y0,y1)/s)
            orig_x1, orig_y1 = int(max(x0,x1)/s), int(max(y0,y1)/s)
            self.scan_regions.append((orig_x0, orig_y0, orig_x1, orig_y1))
            self.draw_regions()

    def set_regions(self, regions):
        """Aktualisiert die Regionen-Liste von außen (z.B. beim Blättern durch Varianten)."""
        self.scan_regions = [list(r) for r in regions]
        self.draw_regions()

    def get_regions(self):
        return self.scan_regions

    def get_current_snapshot_np(self):
        """Gibt den aktuell im ROI-Fenster angezeigten Snapshot als Numpy-Array (BGR) zurück."""
        if self.snapshot_np is not None:
            return self.snapshot_np
        # Falls nur PIL existiert (Live Snapshot), umwandeln
        if self.snapshot_pil:
            arr = np.array(self.snapshot_pil.convert("RGB"))
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return None
