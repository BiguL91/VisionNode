# TODO - Roadmap Ai-Bot

---

## Priorität 1 (Next)

- [X] **Timer-Integration in Daten-Liste**
  - Timer über OCR erkennen; wenn er wegfällt, intern weiterzählen.
  - Timer-Verifikation (Format `00:00:00` oder `00:00:00:00`).
  - Transformation: z.B. `00:00:44` -> `44s`.
  - Aktions-Möglichkeit: Was passiert bei Ablauf (00:00:00)? (z.B. Status-Update in DB).

- [ ] **Erweiterte Header-Icons**
  - Icons für "Scannbereich" (ROI) in den Workflow-Templates anzeigen, wenn ein separater Bereich gesetzt ist.

- [ ] **Status-Durchreichung in Passiven Gruppen**
  - Prüfung, ob Zustände tiefer als eine Ebene durchgereicht werden.
  - Scannbereiche (ROI) von passiven Gruppen an Kind-Elemente vererben.

- [ ] **Game-State Management**
  - Einführung von "Screens" (z.B. Basis, Karte); Workflows laufen nur im passenden State.

- [ ] **Auto-Tuning Engine**
  - Automatischer Test neuer Templates gegen Snapshots; Schwellwert-Vorschläge & Live-Anpassung.

- **Workflow Editor 2.0 (Karten-Design)**
  - [ ] **Visuelle Karten**: Schritte als Karten statt Listbox (Icons, Text, Parameter).
  - [ ] **Direktes Editieren**: Parameter (Timeout, Template, Sekunden) direkt auf der Karte ändern.
  - [ ] **Drag & Drop**: Schritte innerhalb der Kette verschieben (Reihenfolge ändern).

- **Vision Engine Evolution**
  - [ ] **Auto-Tuning**: Bot schlägt Schwellwerte basierend auf Snapshots automatisch vor.
  - [ ] **Erweiterte Ausschnitt-Formen**: Auswahl zwischen Rechteck und Kreis beim Einlernen.

- **Visualisierungs-Overhaul**
  - [ ] **Farbsystem**: Jede Gruppe erhält eine eigene Farbe, Kinder werden innerhalb der Gruppenfarbe differenziert.

---

## Priorität 2 (Later)

- **Scheduler / Loop-System Überarbeitung**
  - [ ] **Main-Scheduler**: Zentrales System, das basierend auf Bedingungen entscheidet.
  - [ ] **Prioritäten**: Workflows mit Prio 1, 2, 3 versehen (z.B. "Hilfe" > "Forschung").

- [ ] **Profil-System**: Erlaubt einfaches Umschalten zwischen verschiedenen Spielen/Accounts.

- [ ] **OCR-Optimierung**
  - Scan-Frequenz-Limitierung (max. X/s).
  - Motion Detection (nur Scan bei Pixeländerung in Region).
  
- [ ] **Action-Verifizierung**
  - Visuelle Rückkopplung nach Klicks (prüfen, ob Klick erfolgreich war, sonst Retry).
