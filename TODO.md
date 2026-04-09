# TODO - Roadmap TilesBot

---

## Priorität 1 (Next)

- [x] **UI Anpassung**
  - Buttons (Neuladen, Bearbeiten, Löschen, OCR, Klick) gemeinsam unterhalb beider Template-Listen
  - Zustand Manager Shortcut Button (🚩 Zustände) öffnet Zustände-Dialog direkt aus dem Panel

- **Phase F: Intelligence & Performance Evolution**
  - [x] **Multi-Template Support**: Erlaubt mehrere Bilder pro Template-Name (Varianten wie `Email.png`, `Email__2.png`) für robustere Erkennung.
  - [x] **OCR Farb-Präzision**: Farb-Picker & Pipette für gezielte Textisolierung (verhindert Geisterzahlen).
  - [ ] **OCR-Optimierung**: Scan-Frequenz-Limitierung (max. X/s) + Motion Detection (nur Scan bei Pixeländerung in Region).
  - [ ] **Action-Verifizierung**: Visuelle Rückkopplung nach Klicks (prüfen ob Klick erfolgreich war, sonst Retry).
  - [ ] **Game-State Management**: Einführung von "Screens" (z.B. Basis, Karte); Workflows laufen nur im passenden State.
  - [ ] **Auto-Tuning Engine**: Automatischer Test neuer Templates gegen Snapshots; Schwellwert-Vorschläge & Live-Anpassung.

- **Workflow Editor 2.0 (Karten-Design)**
  - [ ] **Visuelle Karten**: Schritte als Karten statt Listbox (Icons, Text, Parameter).
  - [ ] **Direktes Editieren**: Parameter (Timeout, Template, Sekunden) direkt auf der Karte ändern.
  - [ ] **Drag & Drop**: Schritte innerhalb der Kette verschieben (Reihenfolge ändern).

- **Vision Engine Evolution**
  - [ ] **Hierarchische Klassen-Erkennung**: (z.B. "Icon" -> "Email") für bessere Skalierbarkeit bei hunderten Templates.
  - [ ] **Auto-Tuning**: Bot schlägt Schwellwerte basierend auf Snapshots automatisch vor.
  - [ ] **Erweiterte Ausschnitt-Formen**: Auswahl zwischen Rechteck und Kreis beim Einlernen.

- **Visualisierungs-Overhaul**
  - [ ] **Permanente Rahmen**: Erkannte Objekte bleiben im Live-View markiert.
  - [ ] **Farbsystem**: Jede Gruppe erhält eine eigene Farbe, Kinder werden innerhalb der Gruppenfarbe differenziert.

---

## Priorität 2 (Later)

- **Scheduler / Loop-System Überarbeitung**
  - [ ] **Main-Scheduler**: Zentrales System, das basierend auf Bedingungen entscheidet.
  - [ ] **Prioritäten**: Workflows mit Prio 1, 2, 3 versehen (z.B. "Hilfe" > "Forschung").
- [ ] **Profil-System**: Erlaubt einfaches Umschalten zwischen verschiedenen Spielen/Accounts.

---

## Erledigte Features

- [x] **Modulares Architektur-Refactoring (v0.3.x)**: Komplette Trennung von UI und Logik (`core/`, `ui/`).
- [x] **Zentrales State-Management**: UI-unabhängiger Bot-Status via `BotState`.
- [x] **Bounding-Box Synchronisation**: Mathematisch exakte Koordinaten für OCR und Klicks durch BBox-Normierung.
- [x] **Hierarchisches Matching (Zwei-Phasen-Suche)**: Effiziente Erkennung von Symbolen innerhalb von Rahmen (Master/Kind-Prinzip).
- [x] **Snapshot-Management**: Speichern benannter Spielzustände und Testen gegen historische Bilder.
- [x] **ROI-Editor & Interaktiver Test**: Begrenzung der Suche auf Bildbereiche inkl. Score-Analyse.
- [x] **Integrierter Einlern-Dialog (Dual-Preview)**: Original & GPU-Mathematik synchron.
- [x] **CPU-Last-Optimierung (Multi-Threading)**: Trennung von Capture, UI und Matching (eigener Prozess).
- [x] **Gruppen-Management 2.0**: Robuste Umbenennung ganzer Gruppen und Pfad-Normalisierung.
