import tkinter as tk
from tkinter import ttk
import threading
import json
import os
import colorsys
import cv2
import numpy as np
from PIL import Image, ImageTk
from ui.dialogs.roi_editor import ROIEditor
from ui.dialogs.template_editor import TemplateEditor
from helpers import cursor_einschraenken, cursor_freigeben

class DialogeMixin:
    def _modus_dialog(self, template_name):
        """Multi-Region OCR-Dialog mit echtem Kontext und modernem Workflow."""
        template_pfad = self.template_engine.templates.get(template_name, {}).get("pfad") or os.path.join("templates", f"{template_name}.png")
        try:
            template_pil = Image.open(template_pfad).convert("RGBA")
            bbox = self.template_engine.templates.get(template_name, {}).get("bbox")
            if bbox: bx, by, bw, bh = bbox; template_pil = template_pil.crop((bx, by, bx + bw, by + bh))
        except Exception: template_pil = None

        dialog = tk.Toplevel(self.root); dialog.title(f"OCR-Bereiche: {template_name}"); dialog.configure(bg="#2d2d2d"); dialog.resizable(True, True); dialog.grab_set()

        modus_var = tk.StringVar(value="Zahl"); VORSCHAU_GROESSE = 400; auswahl = [None]; drag_start = [None]; rect_ids = []; tk_img = [None]
        FARBEN = ["#ff5555", "#55aaff", "#55ff88", "#ffcc44", "#cc55ff", "#ff8844"]
        cv_info = {"skala": 1.0, "ox": 0, "oy": 0, "tw": 1, "th": 1}
        
        color_filter_var = tk.BooleanVar(value=False); target_color = [255, 255, 255]
        color_tol_var = tk.IntVar(value=30); pick_mode_var = tk.BooleanVar(value=False)
        pick_size_var = tk.IntVar(value=1); rand_prozent_var = tk.IntVar(value=50)

        vorschau_frame = tk.Frame(dialog, bg="#1a1a1a"); vorschau_frame.pack(padx=16, pady=(16, 0))
        canvas = tk.Canvas(vorschau_frame, width=VORSCHAU_GROESSE, height=VORSCHAU_GROESSE, bg="#1a1a1a", cursor="crosshair", highlightthickness=0); canvas.pack()

        def vorschau_aktualisieren():
            if not template_pil: return
            tw, th = template_pil.size; rand_faktor = rand_prozent_var.get() / 100.0
            match = next((m for m in self.app.state.active_matches if m[0] == template_name), None)
            bg_bild = None
            if match and self.app.current_screenshot_pil:
                _, mx, my, mw, mh, _ = match[:6]
                rx0, ry0 = int(mx - mw * rand_faktor), int(my - mh * rand_faktor)
                rx1, ry1 = int(mx + mw + mw * rand_faktor), int(my + mh + mh * rand_faktor)
                sw, sh = self.app.current_screenshot_pil.size
                rx0, ry0, rx1, ry1 = max(0, rx0), max(0, ry0), min(sw, rx1), min(sh, ry1)
                if rx1 > rx0 and ry1 > ry0:
                    bg_bild = self.app.current_screenshot_pil.crop((rx0, ry0, rx1, ry1)).convert("RGB")
                    off_x_abs, off_y_abs = mx - rx0, my - ry0; virt_w, virt_h = rx1 - rx0, ry1 - ry0
            if bg_bild is None:
                virt_w, virt_h = tw * (1 + 2*rand_faktor), th * (1 + 2*rand_faktor)
                bg_bild = Image.new("RGB", (int(virt_w), int(virt_h)), "#333333"); off_x_abs, off_y_abs = tw * rand_faktor, th * rand_faktor
                if len(template_pil.split()) > 3: bg_bild.paste(template_pil.convert("RGB"), (int(off_x_abs), int(off_y_abs)), mask=template_pil.split()[3])
                else: bg_bild.paste(template_pil.convert("RGB"), (int(off_x_abs), int(off_y_abs)))
            skala = min(VORSCHAU_GROESSE / virt_w, VORSCHAU_GROESSE / virt_h); skala = min(max(skala, 1.0), 10.0)
            final_w, final_h = int(virt_w * skala), int(virt_h * skala); canvas.config(width=final_w, height=final_h)
            tk_img[0] = ImageTk.PhotoImage(bg_bild.resize((final_w, final_h), Image.LANCZOS))
            canvas.delete("all"); canvas.create_image(0, 0, anchor=tk.NW, image=tk_img[0])
            cv_info.update({"skala": skala, "ox": int(off_x_abs * skala), "oy": int(off_y_abs * skala), "tw": tw, "th": th, "bg_ref": bg_bild})
            tabelle_aktualisieren()

        def drag_start_cb(e):
            cursor_einschraenken(e.widget)
            if pick_mode_var.get() and "bg_ref" in cv_info:
                bg = cv_info["bg_ref"]; s = cv_info["skala"]; tx, ty = int(e.x / s), int(e.y / s)
                if 0 <= tx < bg.width and 0 <= ty < bg.height:
                    r_sum = g_sum = b_sum = count = 0; rad = pick_size_var.get() // 2
                    for dx in range(-rad, rad+1):
                        for dy in range(-rad, rad+1):
                            if 0 <= tx+dx < bg.width and 0 <= ty+dy < bg.height:
                                r, g, b = bg.getpixel((tx+dx, ty+dy)); r_sum+=r; g_sum+=g; b_sum+=b; count+=1
                    if count > 0:
                        target_color[:] = [r_sum//count, g_sum//count, b_sum//count]
                        color_indicator.config(bg="#%02x%02x%02x" % tuple(target_color))
                        color_filter_var.set(True); pick_mode_var.set(False); pick_btn.config(bg="#3a3a3a"); canvas.config(cursor="crosshair"); ocr_vorschau_starten()
                return
            drag_start[0] = (e.x, e.y); auswahl[0] = None; (aktuell_rect[0] and canvas.delete(aktuell_rect[0]))
        def drag_move_cb(e):
            if not drag_start[0]: return
            if aktuell_rect[0]: canvas.delete(aktuell_rect[0])
            aktuell_rect[0] = canvas.create_rectangle(drag_start[0][0], drag_start[0][1], e.x, e.y, outline=FARBEN[len(eintraege)%len(FARBEN)], width=2, dash=(4, 2))
        def drag_end_cb(e):
            cursor_freigeben()
            if not drag_start[0]: return
            if abs(e.x - drag_start[0][0]) > 4: auswahl[0] = (min(drag_start[0][0], e.x), min(drag_start[0][1], e.y), max(drag_start[0][0], e.x), max(drag_start[0][1], e.y)); ocr_vorschau_starten()
            drag_start[0] = None
        aktuell_rect = [None]; canvas.bind("<ButtonPress-1>", drag_start_cb); canvas.bind("<B1-Motion>", drag_move_cb); canvas.bind("<ButtonRelease-1>", drag_end_cb)

        ocr_vorschau_label = tk.Label(dialog, text="—", bg="#2d2d2d", fg="#ffca28", font=("Consolas", 14, "bold")); ocr_vorschau_label.pack(pady=4)
        ki_snap_fenster = tk.Toplevel(dialog); ki_snap_fenster.withdraw(); ki_snap_canvas = tk.Canvas(ki_snap_fenster, bg="#1a1a1a", highlightthickness=0); ki_snap_canvas.pack(); ki_snap_foto = [None]

        param_frame = tk.Frame(dialog, bg="#252525", bd=1, relief=tk.FLAT); param_frame.pack(fill=tk.X, padx=16, pady=4)
        contrast_var = tk.DoubleVar(value=1.0); brightness_var = tk.IntVar(value=0); sharpness_var = tk.DoubleVar(value=1.0); upscale_var = tk.DoubleVar(value=5.0)
        def create_slider(p, l, v, f, t, r=0.1):
            fr = tk.Frame(p, bg="#252525"); fr.pack(side=tk.LEFT, expand=True, padx=2)
            tk.Label(fr, text=l, bg="#252525", fg="#888888", font=("Segoe UI", 7)).pack()
            tk.Scale(fr, from_=f, to=t, resolution=r, variable=v, orient=tk.HORIZONTAL, bg="#252525", fg="#cccccc", troughcolor="#1a1a1a", highlightthickness=0, length=70, showvalue=True, font=("Segoe UI", 7), command=lambda _: ocr_vorschau_starten()).pack()
        create_slider(param_frame, "Kontrast", contrast_var, 0.5, 3.0); create_slider(param_frame, "Helligkeit", brightness_var, -100, 100, 1); create_slider(param_frame, "Schärfe", sharpness_var, 0.0, 5.0); create_slider(param_frame, "Upscale", upscale_var, 1.0, 8.0)

        color_frame = tk.Frame(dialog, bg="#252525", bd=1, relief=tk.FLAT); color_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        tk.Checkbutton(color_frame, text="Farbfilter", variable=color_filter_var, bg="#252525", fg="#cccccc", selectcolor="#1a1a1a", font=("Segoe UI", 8), command=lambda: ocr_vorschau_starten()).pack(side=tk.LEFT, padx=4)
        color_indicator = tk.Label(color_frame, text="      ", bg="#ffffff", relief=tk.FLAT, bd=1); color_indicator.pack(side=tk.LEFT, padx=4)
        def pick_cmd(): pick_mode_var.set(not pick_mode_var.get()); pick_btn.config(bg="#e65100" if pick_mode_var.get() else "#3a3a3a"); canvas.config(cursor="tcross" if pick_mode_var.get() else "crosshair")
        pick_btn = tk.Button(color_frame, text="🎨", bg="#3a3a3a", fg="#cccccc", relief=tk.FLAT, command=pick_cmd); pick_btn.pack(side=tk.LEFT, padx=2)
        tk.OptionMenu(color_frame, pick_size_var, 1, 3, 5, 7).pack(side=tk.LEFT)
        tk.Label(color_frame, text="Tol:", bg="#252525", fg="#888888", font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=(4, 0))
        tk.Scale(color_frame, from_=5, to=150, variable=color_tol_var, orient=tk.HORIZONTAL, bg="#252525", fg="#cccccc", highlightthickness=0, length=80, showvalue=True, font=("Segoe UI", 7), command=lambda _: ocr_vorschau_starten()).pack(side=tk.LEFT)
        tk.Label(color_frame, text="Rand:", bg="#252525", fg="#00ff00", font=("Segoe UI", 7, "bold")).pack(side=tk.LEFT, padx=(8, 0))
        tk.Scale(color_frame, from_=0, to=250, variable=rand_prozent_var, orient=tk.HORIZONTAL, bg="#252525", fg="#cccccc", highlightthickness=0, length=80, showvalue=True, font=("Segoe UI", 7), command=lambda _: vorschau_aktualisieren()).pack(side=tk.LEFT)

        def ocr_vorschau_starten():
            if not auswahl[0] or not template_pil: return
            match = next((m for m in self.app.state.active_matches if m[0] == template_name), None)
            if not match: tw, th = template_pil.size; mx, my, mw, mh = 0, 0, tw, th; vorschau_basis = template_pil.convert("RGB")
            else: _, mx, my, mw, mh, _ = match[:6]; vorschau_basis = self.app.current_screenshot_pil
            if vorschau_basis is None: return
            ox, oy, s = cv_info["ox"], cv_info["oy"], cv_info["skala"]; tw_ref, th_ref = cv_info["tw"], cv_info["th"]
            cl, co = round((auswahl[0][0]-ox)/(tw_ref*s)*100, 1), round((auswahl[0][1]-oy)/(th_ref*s)*100, 1)
            cr, cu = round((ox+tw_ref*s-auswahl[0][2])/(tw_ref*s)*100, 1), round((oy+th_ref*s-auswahl[0][3])/(th_ref*s)*100, 1)
            region = {"name": f"Vorschau_{template_name}", "x": mx, "y": my, "breite": mw, "hoehe": mh, "modus": modus_var.get(), "crop_oben": co, "crop_unten": cu, "crop_links": cl, "crop_rechts": cr, "contrast": contrast_var.get(), "brightness": brightness_var.get(), "sharpness": sharpness_var.get(), "upscale": upscale_var.get(), "color_filter": color_filter_var.get(), "target_color": list(target_color), "color_tolerance": color_tol_var.get()}
            def ocr_thread():
                try:
                    res, d_info = self.ocr_engine.region_scannen(vorschau_basis, region, debug=True)
                    if d_info and d_info[4] is not None:
                        img = Image.fromarray(d_info[4]); tw, th = img.size; s = min(400/tw, 300/th) if tw > 0 else 1.0; img_res = img.resize((int(tw*s), int(th*s)), Image.NEAREST)
                        def ui_up():
                            if not dialog.winfo_exists() or not ki_snap_canvas.winfo_exists(): return
                            ocr_vorschau_label.config(text=res if res else "—", fg="#55ff88" if res else "#888888")
                            ki_snap_foto[0] = ImageTk.PhotoImage(img_res); ki_snap_canvas.config(width=ki_snap_foto[0].width(), height=ki_snap_foto[0].height()); ki_snap_canvas.delete("all"); ki_snap_canvas.create_image(0, 0, anchor="nw", image=ki_snap_foto[0])
                            if not ki_snap_fenster.winfo_ismapped(): ki_snap_fenster.deiconify()
                        dialog.after(0, ui_up)
                except Exception: pass
            threading.Thread(target=ocr_thread, daemon=True).start()

        eingabe_frame = tk.Frame(dialog, bg="#2d2d2d"); eingabe_frame.pack(fill=tk.X, padx=16); name_var = tk.StringVar(); tk.Entry(eingabe_frame, textvariable=name_var, bg="#1a1a1a", fg="#ffffff", insertbackground="white", font=("Segoe UI", 10), relief=tk.FLAT, bd=4, width=20).pack(side=tk.LEFT, padx=(0, 6))
        for m in ["Timer", "Zahl", "Text"]: tk.Radiobutton(eingabe_frame, text=m, variable=modus_var, value=m, bg="#2d2d2d", fg="#cccccc", selectcolor="#1a1a1a", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=4)

        eintraege = []; prefix = f"{template_name}_"
        for k, v in self.ocr_engine.template_ocr_konfigurationen().items():
            if v.get("template") == template_name:
                display_n = k[len(prefix):] if k.startswith(prefix) else k
                eintraege.append([display_n, v.get("modus", "Zahl"), v.get("crop_oben", 0), v.get("crop_unten", 0), v.get("crop_links", 0), v.get("crop_rechts", 0), v.get("contrast", 1.0), v.get("brightness", 0), v.get("sharpness", 1.0), v.get("upscale", 5.0), v.get("color_filter", False), v.get("target_color", [255, 255, 255]), v.get("color_tolerance", 30), v.get("dialog_rand", 50)])
                if len(eintraege) == 1: rand_prozent_var.set(v.get("dialog_rand", 50))

        tabelle_frame = tk.Frame(dialog, bg="#1a1a1a"); tabelle_frame.pack(fill=tk.X, padx=16, pady=6); zeilen_widgets = []
        def tabelle_aktualisieren():
            for w in zeilen_widgets: w.destroy()
            zeilen_widgets.clear(); ox, oy, s = cv_info["ox"], cv_info["oy"], cv_info["skala"]; tw_ref, th_ref = cv_info["tw"], cv_info["th"]
            for i, e in enumerate(eintraege):
                farbe = FARBEN[i % len(FARBEN)]; x0, y0 = int(ox + (e[4]/100)*(tw_ref*s)), int(oy + (e[2]/100)*(th_ref*s)); x1, y1 = int(ox + tw_ref*s - (e[5]/100)*(tw_ref*s)), int(oy + th_ref*s - (e[3]/100)*(th_ref*s))
                canvas.create_rectangle(x0, y0, x1, y1, outline=farbe, width=2); canvas.create_text((x0+x1)//2, y0+8, text=e[0], fill=farbe, font=("Segoe UI", 7, "bold"))
                z = tk.Frame(tabelle_frame, bg="#1a1a1a"); z.pack(fill=tk.X, pady=1); zeilen_widgets.append(z)
                def laden(idx=i):
                    val = eintraege[idx]; name_var.set(val[0]); modus_var.set(val[1]); contrast_var.set(val[6]); brightness_var.set(val[7]); sharpness_var.set(val[8]); upscale_var.set(val[9]); color_filter_var.set(val[10]); target_color[:] = val[11]; color_tol_var.set(val[12]); rand_prozent_var.set(val[13])
                    color_indicator.config(bg="#%02x%02x%02x" % tuple(target_color)); vorschau_aktualisieren()
                    x0, y0 = int(ox + (val[4]/100)*(tw_ref*s)), int(oy + (val[2]/100)*(th_ref*s)); x1, y1 = int(ox + tw_ref*s - (val[5]/100)*(tw_ref*s)), int(oy + th_ref*s - (val[3]/100)*(th_ref*s)); auswahl[0] = (x0, y0, x1, y1); ocr_vorschau_starten()
                tk.Button(z, text=e[0], bg="#1a1a1a", fg="#ffffff", font=("Segoe UI", 9), width=18, anchor="w", relief=tk.FLAT, command=laden).pack(side=tk.LEFT)
                def del_e(ix=i): eintraege.pop(ix); tabelle_aktualisieren()
                tk.Button(z, text="✕", bg="#1a1a1a", fg="#da3633", relief=tk.FLAT, command=del_e).pack(side=tk.RIGHT, padx=4)

        def hinzufuegen():
            n = name_var.get().strip()
            if not n or not auswahl[0]: return
            ox, oy, s = cv_info["ox"], cv_info["oy"], cv_info["skala"]; tw_ref, th_ref = cv_info["tw"], cv_info["th"]; sx0, sy0, sx1, sy1 = auswahl[0]
            cl, co = round((sx0 - ox) / (tw_ref * s) * 100, 1), round((sy0 - oy) / (th_ref * s) * 100, 1)
            cr, cu = round((ox + tw_ref * s - sx1) / (tw_ref * s) * 100, 1), round((oy + th_ref * s - sy1) / (th_ref * s) * 100, 1)
            neu = [n, modus_var.get(), co, cu, cl, cr, contrast_var.get(), brightness_var.get(), sharpness_var.get(), upscale_var.get(), color_filter_var.get(), list(target_color), color_tol_var.get(), rand_prozent_var.get()]
            for i, e in enumerate(eintraege):
                if e[0] == n: eintraege[i] = neu; tabelle_aktualisieren(); return
            eintraege.append(neu); tabelle_aktualisieren()

        tk.Button(eingabe_frame, text="+ Hinzufügen", bg="#2ea043", fg="white", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, command=hinzufuegen).pack(side=tk.LEFT, padx=8)
        
        ergebnis_container = [None]
        def final_speichern():
            ergebnis_container[0] = [tuple(e) for e in eintraege]
            # Speichern im Backend triggern (via Mixin/App)
            self._ocr_konfiguration_speichern(template_name, ergebnis_container[0])
            self._log(f"OCR-Bereiche für '{template_name}' permanent gespeichert.")

        btn_leiste = tk.Frame(dialog, bg="#2d2d2d"); btn_leiste.pack(fill=tk.X, padx=16, pady=12)
        tk.Button(btn_leiste, text="Speichern", bg="#2ea043", fg="white", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=4, command=final_speichern).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_leiste, text="Editor beenden", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 9), relief=tk.FLAT, padx=12, pady=4, command=dialog.destroy).pack(side=tk.RIGHT)
        
        vorschau_aktualisieren()
        dialog.update_idletasks(); dialog.geometry(f"+{self.root.winfo_x()+(self.root.winfo_width()-dialog.winfo_width())//2}+{self.root.winfo_y()+(self.root.winfo_height()-dialog.winfo_height())//2}")
        self.root.wait_window(dialog)
        return ergebnis_container[0]

    def _ocr_konfiguration_speichern(self, template_name, eintraege):
        """Hilfsmethode um OCR-Einträge permanent in der Engine zu registrieren."""
        konfig = self.ocr_engine.template_ocr_konfigurationen()
        for k, v in list(konfig.items()):
            if v.get("template") == template_name: self.ocr_engine.template_ocr_deaktivieren(k)
        
        prefix = f"{template_name}_"
        for e in eintraege:
            en, m, co, cu, cl, cr, con, br, sh, up, cf, tc, ct, dr = e
            key = en if en.startswith(prefix) else f"{prefix}{en}"
            self.ocr_engine.template_ocr_aktivieren(key, template_name, m, crop_oben=co, crop_unten=cu, crop_links=cl, crop_rechts=cr, contrast=con, brightness=br, sharpness=sh, upscale=up, color_filter=cf, target_color=tc, color_tolerance=ct, dialog_rand=dr)
        self._templates_liste_aktualisieren()
        self._timer_panel_aktualisieren()

    def _einlern_dialog_oeffnen(self):
        def on_finish():
            self._bearbeiten_name = self._einlern_dialog_fenster = self._einlern_vorschau_callback = None
            self._geplanter_typ = None
        typ = getattr(self, "_geplanter_typ", None)
        editor = TemplateEditor(self.root, self, bearbeiten_name=self._bearbeiten_name, aktueller_ausschnitt=self._aktueller_ausschnitt, einlern_modus_callback=lambda: (self._einlern_modus_umschalten() if self.einlern_modus else None, on_finish()), typ=typ)
        self._einlern_dialog_fenster = editor.window; self._einlern_vorschau_callback = editor._vorschau_setzen

    def _ocr_dialog(self):
        dialog = tk.Toplevel(self.root); dialog.title("OCR-Region"); dialog.configure(bg="#2d2d2d"); dialog.grab_set()
        tk.Label(dialog, text="Name:", bg="#2d2d2d", fg="#cccccc").pack(anchor="w", padx=16, pady=(16, 2))
        name_var = tk.StringVar(); tk.Entry(dialog, textvariable=name_var, bg="#1a1a1a", fg="#ffffff", insertbackground="white", relief=tk.FLAT, bd=4).pack(fill=tk.X, padx=16)
        tk.Label(dialog, text="Modus:", bg="#2d2d2d", fg="#cccccc").pack(anchor="w", padx=16, pady=(10, 2))
        modus_var = tk.StringVar(value="Timer")
        for m in ["Timer", "Zahl", "Text"]: tk.Radiobutton(dialog, text=m, variable=modus_var, value=m, bg="#2d2d2d", fg="#cccccc", selectcolor="#1a1a1a").pack(anchor="w", padx=24)
        ergebnis = [None]
        def bestaetigen():
            n = name_var.get().strip()
            if n: ergebnis[0] = (n, modus_var.get()); dialog.destroy()
        tk.Button(dialog, text="Speichern", bg="#2ea043", fg="white", command=bestaetigen).pack(side=tk.RIGHT, padx=16, pady=16)
        self.root.wait_window(dialog); return ergebnis[0]

    def _klickzonen_dialog(self, template_name):
        template_pfad = self.template_engine.templates.get(template_name, {}).get("pfad") or os.path.join("templates", f"{template_name}.png")
        if not os.path.exists(template_pfad): return None
        template_bild = Image.open(template_pfad).convert("RGBA")
        bbox = self.template_engine.templates.get(template_name, {}).get("bbox")
        if bbox: bx, by, bw, bh = bbox; template_bild = template_bild.crop((bx, by, bx + bw, by + bh))
        t_b, t_h = template_bild.size; skala = max(3.0, min(8.0, 300 / max(t_b, t_h)))
        anzeige_b, anzeige_h = int(t_b * skala), int(t_h * skala)
        ergebnis = [None]; dialog = tk.Toplevel(self.root); dialog.title(f"Klickzone – {template_name}"); dialog.configure(bg="#2d2d2d"); dialog.grab_set()
        canvas = tk.Canvas(dialog, width=anzeige_b, height=anzeige_h, bg="#1a1a1a", highlightbackground="#555555"); canvas.pack(padx=16, pady=4)
        foto = ImageTk.PhotoImage(template_bild.resize((anzeige_b, anzeige_h), Image.NEAREST)); canvas.create_image(0, 0, anchor="nw", image=foto); canvas.image = foto
        info_label = tk.Label(dialog, text="Punkt setzen.", bg="#2d2d2d", fg="#888888"); info_label.pack(pady=4)
        konfig = self.action_engine.klickzonen_laden()
        if template_name in konfig:
            k = konfig[template_name]; px, py = int(k["klick_rel_x"]/100*anzeige_b), int(k["klick_rel_y"]/100*anzeige_h)
            canvas.create_line(px-8, py, px+8, py, fill="#ff6600", width=2, tags="kreuz"); canvas.create_line(px, py-8, px, py+8, fill="#ff6600", width=2, tags="kreuz")
            ergebnis[0] = (k["klick_rel_x"], k["klick_rel_y"])
        def on_klick(e):
            rx, ry = round(e.x/anzeige_b*100, 1), round(e.y/anzeige_h*100, 1); ergebnis[0] = (rx, ry)
            canvas.delete("kreuz"); canvas.create_line(e.x-8, e.y, e.x+8, e.y, fill="#ff6600", width=2, tags="kreuz"); canvas.create_line(e.x, e.y-8, e.x, e.y+8, fill="#ff6600", width=2, tags="kreuz")
        canvas.bind("<Button-1>", on_klick)
        tk.Button(dialog, text="Speichern", bg="#2ea043", fg="white", command=lambda: dialog.destroy()).pack(side=tk.RIGHT, padx=16, pady=12)
        self.root.wait_window(dialog); return ergebnis[0]

    def _workflow_editor_dialog(self, name, schritte):
        ergebnis = [None]; schritte = list(schritte); dialog = tk.Toplevel(self.root); dialog.title(f"Workflow: {name}"); dialog.configure(bg="#2d2d2d"); dialog.geometry("500x600"); dialog.grab_set()
        name_var = tk.StringVar(value=name); tk.Entry(dialog, textvariable=name_var, bg="#1a1a1a", fg="#ffffff", relief=tk.FLAT, bd=4).pack(fill=tk.X, padx=16, pady=10)
        schritt_liste = tk.Listbox(dialog, bg="#1a1a1a", fg="#cccccc", font=("Segoe UI", 9), relief=tk.FLAT); schritt_liste.pack(fill=tk.BOTH, expand=True, padx=16)
        def update():
            schritt_liste.delete(0, tk.END)
            for s in schritte: schritt_liste.insert(tk.END, f"{s['typ'].upper()}: {s.get('template', s.get('sekunden', ''))}" + (f" (TO: {s['timeout']}s)" if "timeout" in s else ""))
        update()
        f = tk.Frame(dialog, bg="#2d2d2d"); f.pack(fill=tk.X, padx=16, pady=4)
        def add(t):
            if t == "warten": schritte.append({"typ": "warten", "sekunden": 2})
            else:
                a = self._get_template_auswahl()
                if a: schritte.append({"typ": t, "template": a, **({"timeout": 10} if t == "suche" else {})})
            update()
        tk.Button(f, text="+ Klick", command=lambda: add("klick")).pack(side=tk.LEFT, padx=2)
        tk.Button(f, text="+ Suche", command=lambda: add("suche")).pack(side=tk.LEFT, padx=2)
        tk.Button(f, text="+ Warten", command=lambda: add("warten")).pack(side=tk.LEFT)
        def move(d):
            s = schritt_liste.curselection()
            if s:
                i = s[0]; j = i+d
                if 0 <= j < len(schritte): schritte[i], schritte[j] = schritte[j], schritte[i]; update(); schritt_liste.selection_set(j)
        tk.Button(f, text="↑", command=lambda: move(-1)).pack(side=tk.LEFT, padx=(10, 2))
        tk.Button(f, text="↓", command=lambda: move(1)).pack(side=tk.LEFT)
        tk.Button(f, text="Del", command=lambda: (schritt_liste.curselection() and (schritte.pop(schritt_liste.curselection()[0]), update()))).pack(side=tk.LEFT, padx=10)
        tk.Button(dialog, text="Speichern", bg="#2ea043", fg="white", command=lambda: (ergebnis.__setitem__(0, (name_var.get(), schritte)), dialog.destroy())).pack(side=tk.RIGHT, padx=16, pady=12)
        self.root.wait_window(dialog); return ergebnis[0]

    def _einstellungen_dialog(self):
        dialog = tk.Toplevel(self.root); dialog.title("Einstellungen"); dialog.configure(bg="#2d2d2d"); dialog.grab_set()
        inhalt = tk.Frame(dialog, bg="#2d2d2d"); inhalt.pack(padx=20, pady=16, fill=tk.BOTH, expand=True)

        def sektion(text):
            tk.Label(inhalt, text=text, bg="#2d2d2d", fg="#888888", font=("Arial", 9, "bold")).pack(anchor="w", pady=(12, 2))

        def zeile(label_text, widget_func):
            f = tk.Frame(inhalt, bg="#2d2d2d"); f.pack(fill=tk.X, pady=1)
            tk.Label(f, text=label_text, bg="#2d2d2d", fg="#cccccc", width=22, anchor="w").pack(side=tk.LEFT)
            widget_func(f)

        # --- Capture ---
        sektion("Capture")
        fps_var = tk.IntVar(value=self.einstellungen.get("display_fps", 30))
        def fps_w(f):
            for val, lbl in [(30, "30 fps"), (60, "60 fps")]:
                tk.Radiobutton(f, text=lbl, variable=fps_var, value=val, bg="#2d2d2d", fg="#cccccc",
                               selectcolor="#444").pack(side=tk.LEFT, padx=4)
        zeile("Display-Rate:", fps_w)

        # --- OCR ---
        sektion("OCR")
        ocr_var = tk.DoubleVar(value=self.einstellungen.get("ocr_intervall", 0.5))
        def ocr_w(f):
            for val, lbl in [(0.25, "4×/s"), (0.5, "2×/s"), (1.0, "1×/s"), (2.0, "0.5×/s")]:
                tk.Radiobutton(f, text=lbl, variable=ocr_var, value=val, bg="#2d2d2d", fg="#cccccc",
                               selectcolor="#444").pack(side=tk.LEFT, padx=4)
        zeile("OCR-Rate:", ocr_w)

        # --- Matching ---
        sektion("Matching")
        skal_var = tk.DoubleVar(value=self.einstellungen.get("matching_skalierung", 0.5))
        def skal_w(f):
            for val, lbl in [(0.25, "25%"), (0.5, "50%"), (0.75, "75%"), (1.0, "100%")]:
                tk.Radiobutton(f, text=lbl, variable=skal_var, value=val, bg="#2d2d2d", fg="#cccccc",
                               selectcolor="#444").pack(side=tk.LEFT, padx=4)
        zeile("Auflösung:", skal_w)

        # --- Debug / Logging ---
        sektion("Debug & Logging")
        log_keys = [
            ("log_variablen",  "Variablen & OCR-Werte"),
            ("log_workflow",   "Workflow-Schritte"),
            ("log_ocr_debug",  "OCR Debug-Bilder speichern"),
            ("log_matching",   "Matching-Timing"),
            ("log_capture",    "Capture-Timing"),
            ("log_daten_berechnungen", "Log Daten-Berechnungen (Transform/Formeln)"),
        ]
        log_vars = {}
        for key, label in log_keys:
            var = tk.BooleanVar(value=self.einstellungen.get(key, key in ("log_variablen", "log_workflow")))
            log_vars[key] = var
            cb = tk.Checkbutton(inhalt, text=label, variable=var, bg="#2d2d2d", fg="#cccccc",
                                selectcolor="#444", activebackground="#2d2d2d", activeforeground="#ffffff")
            cb.pack(anchor="w", padx=4)

        # --- Buttons ---
        btn_f = tk.Frame(inhalt, bg="#2d2d2d"); btn_f.pack(fill=tk.X, pady=(14, 0))
        def save():
            updates = {
                "display_fps": fps_var.get(),
                "ocr_intervall": ocr_var.get(),
                "matching_skalierung": skal_var.get(),
            }
            for key, var in log_vars.items():
                updates[key] = var.get()
            self.einstellungen.update(updates)
            self.template_engine.matching_skalierung = skal_var.get()
            self.app.save_settings()
            dialog.destroy()
        tk.Button(btn_f, text="Abbrechen", bg="#444", fg="white", command=dialog.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_f, text="Speichern", bg="#2ea043", fg="white", command=save).pack(side=tk.RIGHT)

    def _einheiten_dialog(self):
        """Öffnet den Dialog zum Verwalten globaler Einheiten und Faktoren."""
        from core.daten_manager import _einheiten_laden, _einheiten_speichern
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Globale Einheiten & Faktoren")
        dialog.configure(bg="#2d2d2d")
        dialog.grab_set()
        dialog.geometry("420x500")
        dialog.resizable(False, False)

        inhalt = tk.Frame(dialog, bg="#2d2d2d")
        inhalt.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        tk.Label(inhalt, text="Zuweisung: Kürzel → Multiplikator", bg="#2d2d2d", fg="#ffca28",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(inhalt, text="Beispiel: 'Mio.' → 1.000.000 oder 'Tsd.' → 1.000",
                 bg="#2d2d2d", fg="#666666", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 10))

        # Scrollbare Liste
        list_frame = tk.Frame(inhalt, bg="#1a1a1a", bd=1, relief=tk.SOLID)
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, bg="#1a1a1a", highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview, bg="#1a1a1a")
        scrollable_frame = tk.Frame(canvas, bg="#1a1a1a")

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def zeile_bauen(k, v):
            row = tk.Frame(scrollable_frame, bg="#1a1a1a")
            row.pack(fill=tk.X, pady=2, padx=4)
            
            tk.Label(row, text=k, bg="#1a1a1a", fg="#ffffff", font=("Segoe UI", 9, "bold"),
                     width=15, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=f"× {v:,.0f}".replace(",", "."), bg="#1a1a1a", fg="#aaaaaa",
                     font=("Consolas", 9)).pack(side=tk.LEFT)
            
            def loeschen():
                if k in aktuelle_einheiten:
                    del aktuelle_einheiten[k]
                    refresh_liste()

            tk.Button(row, text="✕", bg="#1a1a1a", fg="#da3633", relief=tk.FLAT,
                      padx=6, pady=0, command=loeschen).pack(side=tk.RIGHT)

        aktuelle_einheiten = _einheiten_laden()

        def refresh_liste():
            for w in scrollable_frame.winfo_children():
                w.destroy()
            for k, v in sorted(aktuelle_einheiten.items()):
                zeile_bauen(k, v)

        refresh_liste()

        # Eingabebereich
        eingabe_f = tk.Frame(inhalt, bg="#252525", pady=10)
        eingabe_f.pack(fill=tk.X, pady=(12, 0))

        tk.Label(eingabe_f, text="Kürzel:", bg="#252525", fg="#888888", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", padx=10)
        tk.Label(eingabe_f, text="Faktor:", bg="#252525", fg="#888888", font=("Segoe UI", 8)).grid(row=0, column=1, sticky="w", padx=10)

        k_var = tk.StringVar()
        f_var = tk.StringVar()

        k_ent = tk.Entry(eingabe_f, textvariable=k_var, bg="#1a1a1a", fg="#ffffff", insertbackground="white", width=15)
        k_ent.grid(row=1, column=0, padx=10, pady=(0, 5))
        f_ent = tk.Entry(eingabe_f, textvariable=f_var, bg="#1a1a1a", fg="#ffffff", insertbackground="white", width=15)
        f_ent.grid(row=1, column=1, padx=10, pady=(0, 5))

        def hinzufuegen():
            k = k_var.get().strip().upper().rstrip(".")
            f = f_var.get().strip().replace(".", "").replace(",", "")
            if k and f.isdigit():
                aktuelle_einheiten[k] = int(f)
                k_var.set(""); f_var.set("")
                refresh_liste()

        tk.Button(eingabe_f, text="+ Hinzufügen / Update", bg="#1a3a1a", fg="#2ea043", 
                  relief=tk.FLAT, font=("Segoe UI", 9, "bold"), padx=10, command=hinzufuegen).grid(row=2, column=0, columnspan=2, pady=5)

        # Footer Buttons
        btn_f = tk.Frame(dialog, bg="#2d2d2d")
        btn_f.pack(fill=tk.X, padx=20, pady=(0, 20))

        def save():
            _einheiten_speichern(aktuelle_einheiten)
            dialog.destroy()

        tk.Button(btn_f, text="Speichern", bg="#2ea043", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=16, pady=6, command=save).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(btn_f, text="Abbrechen", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 10),
                  relief=tk.FLAT, padx=16, pady=6, command=dialog.destroy).pack(side=tk.RIGHT)

    def _zustand_manager_dialog(self, template_name):
        """Öffnet den Zustände-Dialog für ein Template direkt aus dem Haupt-Panel."""
        settings = self.template_engine.settings.get(template_name, {})
        bekannte = sorted(self.app.state.game_states.keys())

        # Condition-States migrieren (altes Format → neues Format)
        raw = settings.get("condition_states", [])
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            if "states" in raw[0] or "connector" in raw[0]:
                start_conds = raw
            else:
                start_conds = [{"connector": None if i == 0 else "OR", "states": dict(item)}
                               for i, item in enumerate(raw)]
        else:
            start_conds = []

        start_sets = dict(settings.get("set_states", {})) if isinstance(settings.get("set_states"), dict) else {}

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Zustände — {template_name}")
        dialog.configure(bg="#2d2d2d")
        dialog.grab_set()
        dialog.resizable(True, True)
        dialog.minsize(580, 520)

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
        gruppen = []

        def refresh_first_connector():
            for i, g in enumerate(gruppen):
                cf = g.get("connector_frame")
                if cf and i == 0:
                    cf.pack_forget()

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
            wrapper = tk.Frame(gruppen_container, bg="#2d2d2d")
            wrapper.pack(fill=tk.X, pady=(0, 2))
            g = {"wrapper": wrapper, "connector_frame": None, "connector_var": None, "zeilen": []}
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
            conn_frame.pack(fill=tk.X, pady=(8, 3))
            nr = len(gruppen) + 1
            box = tk.Frame(wrapper, bg="#1a1a1a", bd=1, relief=tk.SOLID,
                           highlightbackground="#3a3a3a", highlightthickness=1)
            box.pack(fill=tk.X)
            g["box"] = box
            header = tk.Frame(box, bg="#252525")
            header.pack(fill=tk.X)
            tk.Label(header, text=f"  Gruppe {nr}", bg="#252525", fg="#888888",
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, pady=5)
            tk.Button(header, text="Gruppe löschen", bg="#252525", fg="#da3633",
                      font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                      command=lambda ref=g: gruppe_loeschen(ref)).pack(side=tk.RIGHT, padx=8, pady=3)
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

        daten = start_conds if start_conds else [{"connector": None, "states": {}}]
        for gd in daten:
            gruppe_bauen(gd)

        tk.Button(gruppen_container, text="＋ Neue Gruppe hinzufügen",
                  bg="#1a3a5a", fg="#55aaff", font=("Segoe UI", 9), relief=tk.FLAT,
                  padx=10, pady=4, cursor="hand2",
                  command=lambda: gruppe_bauen({"connector": "OR", "states": {}})).pack(anchor="w", pady=(8, 0))

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

        for sk, sv in start_sets.items():
            set_zeile_bauen(sk, sv)

        tk.Button(dialog, text="+ Zustand hinzufügen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=3, cursor="hand2",
                  command=set_zeile_bauen).pack(anchor="w", padx=20, pady=(4, 10))

        # ── Speichern ──────────────────────────────────────────────────────
        btn_f = tk.Frame(dialog, bg="#2d2d2d")
        btn_f.pack(fill=tk.X, padx=20, pady=14)

        def speichern():
            condition_states = []
            for g in gruppen:
                states = {}
                for _, n_var, v_var in g["zeilen"]:
                    n = n_var.get().strip()
                    if n:
                        states[n] = v_var.get()
                if states:
                    condition_states.append({
                        "connector": g["connector_var"].get() if g["connector_var"] else None,
                        "states": states,
                    })
            if condition_states:
                condition_states[0]["connector"] = None

            set_states = {}
            for _, n_var, v_var in set_zeilen:
                n = n_var.get().strip()
                if n:
                    set_states[n] = v_var.get()

            # Direkt in Template-Settings speichern
            if template_name not in self.template_engine.settings:
                self.template_engine.settings[template_name] = {}
            self.template_engine.settings[template_name]["condition_states"] = condition_states
            self.template_engine.settings[template_name]["set_states"] = set_states
            with open("template_settings.json", "w", encoding="utf-8") as f:
                json.dump(self.template_engine.settings, f, indent=2, ensure_ascii=False)
            self._templates_liste_aktualisieren()
            self._log(f"Zustände gespeichert: {template_name}")
            dialog.destroy()

        tk.Button(btn_f, text="Übernehmen", bg="#2ea043", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=16, pady=6, command=speichern).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(btn_f, text="Abbrechen", bg="#3a3a3a", fg="#cccccc", font=("Segoe UI", 10),
                  relief=tk.FLAT, padx=16, pady=6, command=dialog.destroy).pack(side=tk.RIGHT)
        self.root.wait_window(dialog)
