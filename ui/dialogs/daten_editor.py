import tkinter as tk
from tkinter import simpledialog
from core.daten_manager import (
    spalten_der_liste, spalte_hinzufuegen, spalte_aktualisieren,
    spalte_loeschen, liste_umbenennen, liste_intervall_setzen, liste_loeschen
)


class DatenListeEditor:
    def __init__(self, parent, bot, liste, on_gespeichert=None):
        """
        parent        : Tkinter-Elternfenster
        bot           : TilesBot-Instanz (für OCR-Variablen)
        liste         : dict mit id, name, update_intervall
        on_gespeichert: Callback nach Speichern
        """
        self.parent = parent
        self.bot = bot
        self.liste = liste
        self.on_gespeichert = on_gespeichert

        # Lokale Kopie der Spalten (wird erst beim Speichern in DB geschrieben)
        self._spalten = spalten_der_liste(liste["id"])
        self._ocr_vars = self._ocr_vars_laden()

        self._setup_fenster()

    def _ocr_vars_laden(self):
        """Gibt alle verfügbaren OCR-Variablen als Liste zurück."""
        namen = list(getattr(self.bot.ocr_engine, "regionen", {}).keys())
        return sorted(namen)

    def _setup_fenster(self):
        self.fenster = tk.Toplevel(self.parent)
        self.fenster.title(f"Liste bearbeiten: {self.liste['name']}")
        self.fenster.configure(bg="#2d2d2d")
        self.fenster.resizable(True, True)
        self.fenster.transient(self.parent)
        self.fenster.grab_set()

        # Fenstergröße und Position
        self.fenster.geometry("560x480")
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 560) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 480) // 2
        self.fenster.geometry(f"+{max(0,x)}+{max(0,y)}")

        self._kopf_aufbauen()
        self._spalten_bereich_aufbauen()
        self._buttons_aufbauen()

    # ── Kopfbereich (Name + Intervall) ───────────────────────────────────────

    def _kopf_aufbauen(self):
        kopf = tk.Frame(self.fenster, bg="#252525")
        kopf.pack(fill=tk.X, padx=12, pady=(12, 8))

        # Listen-Name
        tk.Label(kopf, text="Name:", bg="#252525", fg="#888888",
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._name_var = tk.StringVar(value=self.liste["name"])
        tk.Entry(kopf, textvariable=self._name_var, bg="#1a1a1a", fg="#ffffff",
                 insertbackground="white", font=("Segoe UI", 9), relief=tk.FLAT,
                 bd=4, width=22).grid(row=0, column=1, sticky="ew", padx=(0, 16))

        # Update-Intervall
        tk.Label(kopf, text="Update alle:", bg="#252525", fg="#888888",
                 font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self._intervall_var = tk.StringVar(value=str(self.liste["update_intervall"]))
        tk.Entry(kopf, textvariable=self._intervall_var, bg="#1a1a1a", fg="#ffffff",
                 insertbackground="white", font=("Segoe UI", 9), relief=tk.FLAT,
                 bd=4, width=5).grid(row=0, column=3)
        tk.Label(kopf, text="s", bg="#252525", fg="#888888",
                 font=("Segoe UI", 9)).grid(row=0, column=4, sticky="w", padx=(2, 0))

        kopf.columnconfigure(1, weight=1)

        # Trennlinie
        tk.Frame(self.fenster, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=12, pady=(0, 8))

    # ── Spalten-Bereich ───────────────────────────────────────────────────────

    def _spalten_bereich_aufbauen(self):
        bereich = tk.Frame(self.fenster, bg="#2d2d2d")
        bereich.pack(fill=tk.BOTH, expand=True, padx=12)

        # Kopfzeile der Spalten-Tabelle
        header = tk.Frame(bereich, bg="#1e1e1e")
        header.pack(fill=tk.X, pady=(0, 2))
        for text, breite in [("Name", 14), ("Typ", 9), ("OCR-Variable", 14), ("Formel", 12), ("", 3)]:
            tk.Label(header, text=text, bg="#1e1e1e", fg="#666666",
                     font=("Segoe UI", 8, "bold"), width=breite, anchor="w",
                     padx=4, pady=3).pack(side=tk.LEFT)

        # "+ Spalte hinzufügen" Button
        tk.Button(bereich, text="+ Spalte hinzufügen", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=6, pady=2,
                  cursor="hand2", command=self._spalte_hinzufuegen).pack(anchor="w", pady=(0, 6))

        # Scrollbarer Bereich für Spalten-Zeilen
        canvas = tk.Canvas(bereich, bg="#2d2d2d", highlightthickness=0)
        scroll = tk.Scrollbar(bereich, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._spalten_container = tk.Frame(canvas, bg="#2d2d2d")
        cw = canvas.create_window((0, 0), window=self._spalten_container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._spalten_container.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._spalten_zeilen_aufbauen()

    def _spalten_zeilen_aufbauen(self):
        """Zeichnet alle Spalten-Zeilen neu."""
        for w in self._spalten_container.winfo_children():
            w.destroy()

        for sp in self._spalten:
            self._spalten_zeile_erstellen(sp)

    def _spalten_zeile_erstellen(self, sp):
        """Erstellt eine editierbare Zeile für eine Spalte."""
        zeile = tk.Frame(self._spalten_container, bg="#1a1a1a")
        zeile.pack(fill=tk.X, pady=1)

        # Name
        name_var = tk.StringVar(value=sp["name"])
        tk.Entry(zeile, textvariable=name_var, bg="#252525", fg="#cccccc",
                 insertbackground="white", font=("Segoe UI", 8), relief=tk.FLAT,
                 bd=3, width=14).pack(side=tk.LEFT, padx=(4, 2), pady=3)

        # Typ-Dropdown
        typ_var = tk.StringVar(value=sp["typ"])
        typ_menu = tk.OptionMenu(zeile, typ_var, "zahl", "text", "berechnet")
        typ_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                        relief=tk.FLAT, bd=0, width=8, highlightthickness=0,
                        activebackground="#3a3a3a", cursor="hand2")
        typ_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        typ_menu.pack(side=tk.LEFT, padx=2)

        # OCR-Variable Dropdown
        ocr_var = tk.StringVar(value=sp.get("ocr_var") or "")
        ocr_optionen = [""] + self._ocr_vars
        ocr_menu = tk.OptionMenu(zeile, ocr_var, *ocr_optionen)
        ocr_menu.config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8),
                        relief=tk.FLAT, bd=0, width=13, highlightthickness=0,
                        activebackground="#3a3a3a", cursor="hand2")
        ocr_menu["menu"].config(bg="#252525", fg="#cccccc", font=("Segoe UI", 8))
        ocr_menu.pack(side=tk.LEFT, padx=2)

        # Formel-Eingabe (nur relevant bei typ=berechnet)
        formel_var = tk.StringVar(value=sp.get("formel") or "")
        tk.Entry(zeile, textvariable=formel_var, bg="#252525", fg="#4fc3f7",
                 insertbackground="white", font=("Consolas", 8), relief=tk.FLAT,
                 bd=3, width=14).pack(side=tk.LEFT, padx=2)

        # Löschen-Button
        tk.Button(zeile, text="✕", bg="#1a1a1a", fg="#555555",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=4,
                  cursor="hand2",
                  command=lambda sid=sp["id"]: self._spalte_loeschen(sid)).pack(side=tk.LEFT, padx=(4, 2))

        # Änderungen sofort in lokaler Kopie merken
        def _on_aenderung(*_, sid=sp["id"], nv=name_var, tv=typ_var, ov=ocr_var, fv=formel_var):
            for s in self._spalten:
                if s["id"] == sid:
                    s["name"] = nv.get()
                    s["typ"] = tv.get()
                    s["ocr_var"] = ov.get() or None
                    s["formel"] = fv.get() or None
                    break

        for var in (name_var, typ_var, ocr_var, formel_var):
            var.trace_add("write", _on_aenderung)

    # ── Spalten hinzufügen / löschen ────────────────────────────────────────

    def _spalte_hinzufuegen(self):
        """Schreibt sofort eine neue leere Spalte in die DB und zeigt sie an."""
        neue_id = spalte_hinzufuegen(self.liste["id"], "Neu", typ="zahl")
        self._spalten = spalten_der_liste(self.liste["id"])
        self._spalten_zeilen_aufbauen()

    def _spalte_loeschen(self, spalte_id):
        spalte_loeschen(spalte_id)
        self._spalten = [s for s in self._spalten if s["id"] != spalte_id]
        self._spalten_zeilen_aufbauen()

    # ── Buttons (Speichern / Löschen / Abbrechen) ────────────────────────────

    def _buttons_aufbauen(self):
        tk.Frame(self.fenster, bg="#3a3a3a", height=1).pack(fill=tk.X, padx=12, pady=(8, 0))

        btn_leiste = tk.Frame(self.fenster, bg="#252525")
        btn_leiste.pack(fill=tk.X, padx=12, pady=8)

        # Liste löschen (links)
        tk.Button(btn_leiste, text="✕ Liste löschen", bg="#3a1a1a", fg="#da3633",
                  font=("Segoe UI", 8), relief=tk.FLAT, padx=8, pady=4,
                  cursor="hand2", command=self._liste_loeschen).pack(side=tk.LEFT)

        # Abbrechen + Speichern (rechts)
        tk.Button(btn_leiste, text="Abbrechen", bg="#3a3a3a", fg="#aaaaaa",
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=4,
                  cursor="hand2", command=self.fenster.destroy).pack(side=tk.RIGHT, padx=(4, 0))

        tk.Button(btn_leiste, text="✔ Speichern", bg="#2ea043", fg="white",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10, pady=4,
                  cursor="hand2", command=self._speichern).pack(side=tk.RIGHT)

    def _speichern(self):
        """Schreibt alle Änderungen in die DB."""
        # Listen-Name + Intervall
        neuer_name = self._name_var.get().strip()
        if neuer_name and neuer_name != self.liste["name"]:
            liste_umbenennen(self.liste["id"], neuer_name)

        try:
            intervall = int(self._intervall_var.get())
            if intervall > 0:
                liste_intervall_setzen(self.liste["id"], intervall)
        except ValueError:
            pass

        # Spalten-Änderungen
        for sp in self._spalten:
            spalte_aktualisieren(
                sp["id"],
                name=sp["name"],
                typ=sp["typ"],
                ocr_var=sp.get("ocr_var"),
                formel=sp.get("formel")
            )

        self.fenster.destroy()
        if self.on_gespeichert:
            self.on_gespeichert()

    def _liste_loeschen(self):
        """Löscht die gesamte Liste nach Bestätigung."""
        from tkinter import messagebox
        if messagebox.askyesno("Liste löschen",
                               f"Liste '{self.liste['name']}' wirklich löschen?\nAlle Daten gehen verloren.",
                               parent=self.fenster):
            liste_loeschen(self.liste["id"])
            self.fenster.destroy()
            if self.on_gespeichert:
                self.on_gespeichert()
