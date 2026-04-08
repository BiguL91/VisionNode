import tkinter as tk
from PIL import ImageTk, ImageDraw, Image

class EinlernMixin:
    def _canvas_maus_binden(self):
        """Bindet Maus-Events für den Einlern-Modus."""
        self.vorschau_canvas.bind("<ButtonPress-1>", self._auswahl_start)
        self.vorschau_canvas.bind("<B1-Motion>", self._auswahl_ziehen)
        self.vorschau_canvas.bind("<ButtonRelease-1>", self._auswahl_ende)
        self.vorschau_canvas.bind("<Motion>", self._lupe_aktualisieren)
        self.vorschau_canvas.bind("<Leave>", self._lupe_verstecken)

    def _einlern_modus_umschalten(self):
        """Aktiviert/deaktiviert den Template-Einlern-Modus."""
        if self.ocr_modus:
            self._ocr_modus_umschalten()
        
        self.einlern_modus = not self.einlern_modus
        if self.einlern_modus:
            self.einlern_btn.config(bg="#1565c0", fg="white", text="✕ Abbrechen")
            self.vorschau_canvas.config(cursor="crosshair")
            self._log("Einlern-Modus aktiv – Region auf der Vorschau auswählen.")
            self._einlern_dialog_oeffnen()
        else:
            self._bearbeiten_name = None
            self._aktueller_ausschnitt = None
            self._einlern_vorschau_callback = None
            if self._einlern_dialog_fenster and self._einlern_dialog_fenster.winfo_exists():
                self._einlern_dialog_fenster.destroy()
            self._einlern_dialog_fenster = None
            self.einlern_btn.config(bg="#3a3a3a", fg="#cccccc", text="+ Template")
            self.vorschau_canvas.config(cursor="")
            self._auswahl_entfernen()

    def _ocr_modus_umschalten(self):
        """Aktiviert/deaktiviert den OCR-Region Einlern-Modus."""
        if self.einlern_modus:
            self._einlern_modus_umschalten()
        self.ocr_modus = not self.ocr_modus
        if self.ocr_modus:
            self.ocr_btn.config(bg="#6a1b9a", fg="white", text="✕ Abbrechen")
            self.vorschau_canvas.config(cursor="crosshair")
            self._log("OCR-Modus aktiv – Region auf der Vorschau auswählen.")
        else:
            self.ocr_btn.config(bg="#3a3a3a", fg="#cccccc", text="+ OCR-Region")
            self.vorschau_canvas.config(cursor="")
            self._auswahl_entfernen()

    def _auswahl_start(self, event):
        """Merkt sich den Startpunkt der Auswahl."""
        if not self.einlern_modus and not self.ocr_modus:
            return
        self.auswahl_start = (event.x, event.y)
        self._auswahl_entfernen()

    def _lupe_aktualisieren(self, event):
        """Zeichnet eine vergrößerte Ansicht (Lupe) um den Mauszeiger."""
        screenshot = self.app.current_screenshot_pil
        if (not self.einlern_modus and not self.ocr_modus) or screenshot is None:
            self._lupe_verstecken()
            return

        # Canvas-Koordinaten → Original-Screenshot-Koordinaten
        mx = int((event.x - self.bild_offset_x) / self.bild_skalierung_x)
        my = int((event.y - self.bild_offset_y) / self.bild_skalierung_y)

        r = 20
        box = (mx - r, my - r, mx + r, my + r)
        
        sw, sh = screenshot.size
        if box[0] < 0 or box[1] < 0 or box[2] > sw or box[3] > sh:
            self._lupe_verstecken()
            return

        # Ausschnitt holen und vergrößern (4x)
        ausschnitt = screenshot.crop(box)
        lupe_img = ausschnitt.resize((160, 160), Image.NEAREST)
        
        draw = ImageDraw.Draw(lupe_img)
        draw.line((80, 0, 80, 160), fill="red", width=1)
        draw.line((0, 80, 160, 80), fill="red", width=1)
        draw.rectangle((0, 0, 159, 159), outline="#cccccc", width=1)

        self._lupe_foto = ImageTk.PhotoImage(lupe_img)
        
        lx, ly = event.x + 30, event.y + 30
        if lx + 160 > self.vorschau_canvas.winfo_width(): lx = event.x - 190
        if ly + 160 > self.vorschau_canvas.winfo_height(): ly = event.y - 190

        if not hasattr(self, "_lupe_id") or self._lupe_id is None:
            self._lupe_id = self.vorschau_canvas.create_image(lx, ly, image=self._lupe_foto, anchor="nw", tags="lupe")
        else:
            self.vorschau_canvas.coords(self._lupe_id, lx, ly)
            self.vorschau_canvas.itemconfig(self._lupe_id, image=self._lupe_foto)
        
        self.vorschau_canvas.tag_raise(self._lupe_id)

    def _lupe_verstecken(self, event=None):
        """Entfernt die Lupe vom Canvas."""
        if hasattr(self, "_lupe_id") and self._lupe_id:
            self.vorschau_canvas.delete(self._lupe_id)
            self._lupe_id = None
        self._lupe_foto = None

    def _auswahl_ziehen(self, event):
        """Zeichnet das Auswahlrechteck während des Ziehens."""
        if (not self.einlern_modus and not self.ocr_modus) or not self.auswahl_start:
            return
        self._auswahl_entfernen()
        x0, y0 = self.auswahl_start
        self.auswahl_rect_id = self.vorschau_canvas.create_rectangle(
            x0, y0, event.x, event.y,
            outline="#1e88e5", width=2, dash=(4, 2)
        )
        self._lupe_aktualisieren(event)

    def _auswahl_ende(self, event):
        """Beendet die Auswahl."""
        if not self.einlern_modus and not self.ocr_modus: return
        if not self.auswahl_start: return
        
        if self.ocr_modus:
            self._ocr_region_speichern(event)
            return
            
        screenshot = self.app.current_screenshot_pil
        if screenshot is None:
            self._log("Kein Screenshot verfügbar.")
            return

        x0, y0 = self.auswahl_start
        x1, y1 = event.x, event.y

        if abs(x1 - x0) < 5 or abs(y1 - y0) < 5:
            self._auswahl_entfernen()
            return

        mx0 = int((min(x0, x1) - self.bild_offset_x) / self.bild_skalierung_x)
        my0 = int((min(y0, y1) - self.bild_offset_y) / self.bild_skalierung_y)
        mx1 = int((max(x0, x1) - self.bild_offset_x) / self.bild_skalierung_x)
        my1 = int((max(y0, y1) - self.bild_offset_y) / self.bild_skalierung_y)

        memu_b, memu_h = screenshot.size
        mx0 = max(0, min(mx0, memu_b))
        my0 = max(0, min(my0, memu_h))
        mx1 = max(0, min(mx1, memu_b))
        my1 = max(0, min(my1, memu_h))

        if mx1 - mx0 < 2 or my1 - my0 < 2:
            self._auswahl_entfernen()
            return

        ausschnitt = screenshot.crop((mx0, my0, mx1, my1))
        self._auswahl_entfernen()

        self._aktueller_ausschnitt = (ausschnitt, mx1 - mx0, my1 - my0)
        if self._einlern_vorschau_callback:
            self._einlern_vorschau_callback(ausschnitt, mx1 - mx0, my1 - my0)

    def _auswahl_entfernen(self):
        """Entfernt das Auswahlrechteck vom Canvas."""
        if self.auswahl_rect_id:
            self.vorschau_canvas.delete(self.auswahl_rect_id)
            self.auswahl_rect_id = None

    def _ocr_region_speichern(self, event):
        """Speichert eine neue OCR-Region nach der Auswahl."""
        screenshot = self.app.current_screenshot_pil
        if screenshot is None:
            self._log("Kein Screenshot verfügbar.")
            self._auswahl_entfernen()
            return

        x0, y0 = self.auswahl_start
        x1, y1 = event.x, event.y

        if abs(x1 - x0) < 5 or abs(y1 - y0) < 5:
            self._auswahl_entfernen()
            return

        mx0 = int((min(x0, x1) - self.bild_offset_x) / self.bild_skalierung_x)
        my0 = int((min(y0, y1) - self.bild_offset_y) / self.bild_skalierung_y)
        mx1 = int((max(x0, x1) - self.bild_offset_x) / self.bild_skalierung_x)
        my1 = int((max(y0, y1) - self.bild_offset_y) / self.bild_skalierung_y)

        memu_b, memu_h = screenshot.size
        mx0 = max(0, min(mx0, memu_b)); my0 = max(0, min(my0, memu_h))
        mx1 = max(0, min(mx1, memu_b)); my1 = max(0, min(my1, memu_h))

        self._auswahl_entfernen()

        ergebnis = self._ocr_dialog()
        if not ergebnis: return

        name, modus = ergebnis
        self.ocr_engine.region_hinzufuegen(name, mx0, my0, mx1 - mx0, my1 - my0, modus)
        self._timer_panel_aktualisieren()
        self._log(f"OCR-Region gespeichert: \"{name}\" ({modus}, {mx1-mx0}×{my1-my0}px)")
        self._ocr_modus_umschalten()
