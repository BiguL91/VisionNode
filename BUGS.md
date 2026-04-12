# Bug Tracker

---



## Priorität: Hoch


## Priorität: Mittel


## Priorität: Niedrig


## Hinweise

- Status: 🔍 Offen | 🔧 In Arbeit | ✅ Behoben
- Bei Fix: Commit-Hash + Version angeben

---

## ✅ Behoben

- ✅ **PyQt6 Revolution & UI Polish (Aktuell)**
  - **Crashes:** Veraltete Methodenaufrufe (`_templates_liste_aktualisieren`) und Parameter-Fehler (`TypeError` in `aktualisieren()`) behoben.
  - **Layout:** Globale Mindestgröße (1000x600) und feste Panel-Mindestbreiten via `QSplitter` eingeführt.
  - **Collapsible Panels:** "Springen" beim Ein-/Ausklappen behoben, automatisches Nachskalieren implementiert.
  - **Cleanup:** Obsolete Toolbar-Buttons (`+ OCR-Region`, `+ Template`) und ROI-Editor-Buttons (`Live wählen`) entfernt.
  - **OCR-Dialog:** Pfeile durch intuitive `QSlider` (mit Wertanzeige) ersetzt; Color Picker für Filterfarbe integriert.
  - **Template-Editor:** Skalierung im ROI-Editor auf 1:1 (Originalgröße) fixiert für pixelgenaue Auswahl.
  - **Usability:** Checkbox-Styling (Checked-Status) verbessert, Button-Kontraste in Toolbar und Editoren optimiert.
  - **Daten-Listen:** Lösch-Funktion im `DatenPanelQt` implementiert inkl. UI-Refresh; Layout im Berechnungs-Tab entzerrt.

- ✅ **OCR-Optimierung: Timer & Umlaute** *(Commit: tbd)*
...
  - Adaptives Thresholding für Timer gegen transparente Hintergründe implementiert
  - Unterstützung für Timer mit Tagen (z.B. '2T 12:44:15') inkl. Sekunden-Umrechnung
  - Deutsch-Support für EasyOCR hinzugefügt (Ä, Ö, Ü Erkennung)
  - Morphologische Verstärkung dünner Ziffern bei Timern

- ✅ **Daten-Listen: 4 Bugs** *(Commit: 26e8b47, c56b7fa)*
  - Neu erstellte Transforms/Berechnungen/Zeilen/Spalten wurden nicht sofort gespeichert → Sofortiges Speichern in DB implementiert
  - Logikfehler im Berechnen-Tab: `elapsed_h` wurde nicht pro Variable berechnet → `zeit_h/m/s` korrekt pro Variable aus Timestamp berechnet
  - Spalten-Tab: keine Zuweisung zu Zeilen möglich → Platzhalter `{row}` in OCR-Variablen für zeilenspezifische Mappings
  - Berechnete Werte ohne Formatierung → Spalten-Formatierung `K/M/B`, `Ganzzahl`, `2 Nachkomma` implementiert

- ✅ **Daten-Listen: Tab-Wechsel erstellt neue Variable statt umzubenennen** *(Commit: c56b7fa)*
  - `_orig_transform_namen` / `_orig_berech_namen` als Referenz für alter_name beim Rename
  - Tab-Wechsel sichert Namen des aktuellen Tabs automatisch vor dem Wechsel
  - DB wird nach Tab-Wechsel neu geladen damit Formel-Builder aktuelle Namen zeigt

- ✅ **Daten-Listen: Umbenennung propagiert nicht in Berechnungs-Formeln** *(Commit: c56b7fa)*
  - `variable_umbenennen()` aktualisiert Formeln und Zuordnungen automatisch bei Rename

- ✅ **Daten-Listen: SQLite CASCADE-Deletes funktionierten nicht** *(Commit: c56b7fa)*
  - `PRAGMA foreign_keys = ON` fehlte in `_verbinden()`

- ✅ **Daten-Listen: Doppelte OCR-Cache-Einträge** *(Commit: c212fd9)*
  - `{p_name}_{entry_name}` Prefix-Key war redundant, wird nicht genutzt → entfernt

- ✅ **Daten-Listen: Mapping-Tab zeigte alle OCR-Variablen** *(Commit: c56b7fa)*
  - Nur noch Transform- und Berechnungs-Outputs werden angezeigt

- ✅ **State Template Umbenennung greift nicht an allen Stellen** *(Commit: 8abe3c5)*

- ✅ **Ignorier-Bereiche GPU-Vorschau nicht synchronisiert** *(Commit: b8ab800)*

- ✅ **Mauszeiger verlässt Vorschau-Fenster beim Markieren** *(Commit: 39a94e9)*

- ✅ **Fenstergröße beim Start** *(Commit: 97b31f8)*
  - Öffnet auf voller Bildschirmhöhe, Breite passt sich ans Bild an, Position wird gespeichert


 -  ✅ "_migrated_v2": true erkennung kann weg. es gibt nur noch das neue. (alles einmal gelöscht und neu)

  - ✅ Klick bereiche Beim "Neues Element Erstellen" passen nicht beim Klicken auf Text wird nicht die funktion ausgewählt

  - ✅ Erstellen Einer Passiven Gruppe ist das Dialog fenster "Zustände" Irrefürend. Sollte eher ein Dialog kommen Neue Gruppe -> Gruppe zuweißen

  - ✅ Beim Zuweißen Einer Passiven Gruppe zur State Templates, bleibt die passive trotzdem Im Workflow Template / Hintergrund: State Templates sollen Auch verschachtelt werden können. Einfacher Fix: User gibt beim erstellen einfach selber den Tag an wo er die gruppe einsotiert haben möchte "State Template oder Workflow Template"
  Vorteil: Alles Funktiniert genau gleich. 
  Umsetzung: Bei Klick Auf + Neu -> Erstelle Workflow Template oder State-Template -> Aktive Gruppe / Passive / Template 
  
  - ✅ Ordnerstrucktur anpassen: "State Template / Workflow Template " -> Aktive/Passive Gruppe -> Passive Gruppe / Template -> Template
  Dadurch ist es möglich sauber verschiedene Gruppen und Templates umzuweißen


  - ✅ Master Container: Darf Keine "Gruppe" Dialog haben im Template Editor, (Verwirung)
  Umsetzung: Prüfung ist Template Egal ob Aktiv/passiv Überlagert? ja nein

  - ✅ "+ Template" Button im Haupt UI kann weg. führt nur noch zu verwirrung

  - ✅  "Zustände" haben keinen einfluss mehr auf die zuordnung "State Template / Workflow Template"