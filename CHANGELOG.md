# Changelog

---

## v1.5.5 (Performance-Turbo) - 01.05.2026

### ✨ Features
- **Shared Memory System**: Einführung eines 40MB Shared Memory Puffers (`SharedFrameBuffer`) für Zero-Copy Screenshots. Dies eliminiert die CPU-intensive Serialisierung (Pickle) beim Datentransfer zwischen Capture- und Matching-Prozessen.
- **Pinned Memory (DMA)**: Nutzung von Page-Locked Memory für beschleunigte PCIe-Transfers direkt zum VRAM der GPU.
- **GPU-Native Konvertierung**: Die rechenintensive Bildumwandlung (Typ-Konvertierung, Division, Kanal-Permutation) wurde von der CPU direkt auf die Grafikkarte (4080 Super optimiert) verlagert.

### ⚙️ Optimierungen
- **Präzise Performance-Logs**: Die Zeitmessung wurde in den Matching-Subprozess integriert und mit `torch.cuda.synchronize()` synchronisiert. Dies liefert exakte GPU-Latenzwerte unabhängig von asynchronen CPU-Aufrufen.
- **Subprozess-Effizienz**: Die Kommunikationslast wurde minimiert, indem nur noch Metadaten über die Queues gesendet werden; das Bildmaterial verbleibt für alle beteiligten Prozesse im Shared Memory.
- **Asynchroner Transfer**: Nutzung von `non_blocking=True` für den GPU-Upload, was die Parallelität zwischen CPU und GPU weiter steigert.

### 🛠️ Fixes
- **Matching-Timing Fix**: Behebung von Messfehlern in den Performance-Logs, die durch asynchrone Prozess-Kommunikation und GPU-Latenzen entstanden sind.

---

## v1.5.4 (Event-Bus & UX-Update) - 01.05.2026

### ✨ Features
- **Event Bus System**: Implementierung einer zentralen Pub/Sub Infrastruktur (`core/event_bus.py`) zur vollständigen Entkopplung der Engines von der Benutzeroberfläche.
- **Asynchroner Data-Worker**: Neuer Hintergrund-Dienst (`core/data_worker.py`) zur Verarbeitung von OCR-Rohdaten (Timer-Berechnungen, Einheiten-Transformationen, Formel-Auswertungen) ohne Blockierung des UI-Threads.
  - **DataWorker Heartbeat**: Kontinuierliche Berechnung von Timern und Formeln auch ohne aktive OCR-Events (1,5s Intervall).
- **Reaktive UI-Panels**: Alle Haupt-Panels (State, Workflow, Template, Variable, Daten) wurden auf ein ereignisgesteuertes Modell umgestellt und aktualisieren sich nun autonom via Event Bus.
- **Auto-Tune Engine (Alpha)**: Ein neuer interaktiver Wizard hilft beim Einlernen von Templates. Er sucht automatisch nach der besten Trennschärfe zwischen Icon und Hintergrund.
  - *Hinweis: Basis-Implementierung steht, bedarf aber noch weiterer Optimierung im realen Bot-Betrieb.*
- **Top-Down-Scan**: Intelligente Ermittlung des Schwellwerts durch schrittweises Absenken der Konfidenz.
- **Interaktives Labeling**: Im großen Vorschaufenster können korrekte Treffer per Klick markiert werden, um den Bot zu trainieren.
- **Toleranz-Sweep**: Automatische Optimierung der Hintergrund-Toleranz basierend auf den Benutzer-Markierungen.

### ⚙️ Optimierungen
- **Thread-Sicherheit (BotState)**: Einführung von Locks in `core/bot_state.py` zur Vermeidung von Race Conditions bei gleichzeitigem Zugriff von Matching- und UI-Threads auf Spielzustände.
- **UI-Performance**: Massive Entlastung des Haupt-Threads durch Entfernung von Polling-Loops; chirurgische Updates der UI-Komponenten statt vollständiger Rebuilds bei Wertänderungen.
  - **Live-Vorschau Optimierung**: Umstellung der Bildskalierung auf bilineare Interpolation (`INTER_LINEAR`) für flüssige 60-FPS-Darstellung bei geringerer CPU-Last.
- **Workflow-Editor UX**:
  - **Präzises Hit-Testing**: Verbindungspunkte (Ports) nutzen nun Nearest-Neighbor-Logik; bei Überlagerungen wird immer der exakt nächste Port ausgewählt.
  - **Visuelles Feedback**: Neuer Hover-Effekt vergrößert und beleuchtet Ports beim Überfahren mit der Maus.
  - **Loop-Node Optimierung**: Erhöhter Abstand zwischen Eingang und Ausgang zur Vermeidung von Fehlklicks.
- **Robustes State-Management**: Implementierung von Heartbeat-Mechanismen im State- und Variable-Panel als Fallback für die Event-basierte Synchronisation; verbesserte Reaktivität der "Nur Aktiv" Filterung.
- **Matching-Beschleunigung**:
  - **Latenz-Minimierung**: Künstliche 50ms Verzögerung im Matching-Loop entfernt für schnellstmögliche Erkennungsergebnisse.
  - **Downsampling-Helligkeitscheck**: Beschleunigte Erkennung von Übergangsframes (Ladescreens) durch 20x20 Downsampling-Gitter.
- **OCR-Batching**: Massive Reduzierung der GPU-Last durch Bündelung aller OCR-Anfragen eines Zyklus.
- **Asynchrones Matching**: Reduzierung des PCIe-Overheads durch Queueing von GPU-Operationen im TemplateMatcher.
- **Performance-Tuning**: Standard-Upscaling für OCR von 5.0 auf 3.0 gesenkt für schnellere Verarbeitung bei identischer Erkennungsrate auf High-End-Karten.

### 🛠️ Fixes
- **State-Anzeige**: Korrektur der Initialisierung und Filter-Logik ("Nur Aktiv"), Variablen werden nun zuverlässig beim Programmstart und bei Änderungen angezeigt.
- **Varianten-Schwellenwerte**: Varianten erben nun korrekt die Einstellungen (Schwellenwert etc.) des Basis-Templates.
- **Hierarchie-Logik**: Hardcodierte Schwellenwerte (0.7) in Unter-Templates entfernt; Benutzereinstellungen greifen nun konsistent.
- **ROI-Editor Stabilität**: Testmodus korrigiert, sodass Templates trotz definierter Scan-Regionen im Editor-Test überall gefunden werden.
- **Variablen-Panel**: Korrektur des Mappings nach Umstellung auf Batch-OCR, Variablen erscheinen wieder wie gewohnt.

---

## v1.5.3 (Präzisions-Update)

### ✨ Features
- **Globales Lupe & Fadenkreuz System**: Refactoring der Lupe in `ui/widgets/magnifier.py` für projektweite Wiederverwendbarkeit.
- **Template-Editor**: Integration der Lupe und eines gestrichelten Cyan-Fadenkreuzes zur präzisen Auswahl von Regionen.
- **Haupt-UI**: Integration der Lupe und des Fadenkreuzes in die Live-Vorschau (nur im Einlern-Modus aktiv).

### ⚙️ Optimierungen
- **Lupen-Rendering**: Umstellung auf `grab()`, um Overlays und Schachbrettmuster korrekt in der Lupe darzustellen.
- **Benutzerführung**: Fadenkreuz-Farbe auf Cyan (`#00ffff`) geändert für bessere Sichtbarkeit auf dunklen/komplexen Hintergründen.

### 🛠️ Fixes
- **Lupen-Verzerrung**: Fix der Bildverzerrung an den Rändern durch Verwendung eines festen Quell-Pixmaps.
- **Ressourcen-Management**: Sichergestellt, dass das Lupen-Fenster beim Schließen der Editoren korrekt versteckt und zerstört wird.
- **Import-Fix**: Korrektur von `QRegion` (jetzt korrekt aus `PyQt6.QtGui`).

---

## v1.5.2 (Interaktion & Snapshot-Revolution)

### ✨ Features
- **Direktsteuerung (🎮)**: Klicks und Wischgesten (Swipes) können jetzt direkt über das Live-Vorschaubild an den Emulator gesendet werden.
- **Interaktions-Modus**: Automatische Umrechnung von Canvas-Koordinaten auf Emulator-Auflösung unter Berücksichtigung von Window-Chrome und Skalierung.
- **Modernisiertes Snapshot-System**:
  - **Sofort-Aufnahme**: Snapshot wird beim Klick ohne Verzögerung erstellt.
  - **Neuer Snapshot-Dialog**: Mit Live-Vorschau und direkter Benennung beim Speichern.
  - **Snapshot-Manager**: Erreichbar über Rechtsklick auf den Snapshot-Button zum Verwalten, Umbenennen und Löschen von Bildern.
- **ROI Editor Upgrade**:
  - Neue Buttons für **Live-Vorschau** und **Snapshot laden** direkt im Scan-Regionen Editor.
  - **Visueller Snapshot-Picker**: Integration des Snapshot-Managers zur bildbasierten Auswahl (statt Datei-Explorer).
- **Proportionale Bildskalierung**: Einführung der `ScalablePreviewLabel`-Klasse für flüssige und korrekte Bilddarstellung in allen Dialogen.

### ⚙️ Optimierungen
- **Multithreaded ADB-Aktionen**: Klicks via Direktsteuerung werden in separaten Threads ausgeführt, um die UI-Reaktivität nicht zu beeinträchtigen.
- **Layout-Tuning**: Header-Höhen in Dialogen optimiert; verbesserte Bildskalierung bei Fenster-Resizing durch Dämpfungs-Timer.

### 🛠️ Fixes
- **Stabilität**: Behebung von Indentation-Fehlern und fehlenden Importen (`QSizePolicy`, `QFrame`, `QTimer`) in neu erstellten Dialogen.

---

## v1.5.1 (Persistenz & Fokus-Modus)

### ✨ Features
- **Automatisches Speichern der UI-Geometrie**: Einführung des `GeometryManager` zur dauerhaften Speicherung von Fenster- und Dialogpositionen sowie des Dock-Layouts.
- **Fokus-Modus für Docks**: Panels können in ein separates Vollformat-Fenster ausgegliedert werden, um den Fokus auf spezifische Bereiche zu legen.
- **Erweiterte Kontextmenüs**: Rechtsklick-Aktionen für OCR-Variablen und Template-Panels zur schnelleren Bedienung.

### ⚙️ Optimierungen
- **Event-basierte Persistenz**: Effiziente Speicherung der Fensterpositionen via Event-Filter (Hide-Event), um Race-Conditions beim Schließen zu vermeiden.

### 🛠️ Fixes
- **Dialog-Runtime-Errors**: Behebung von `RuntimeError: wrapped C/C++ object has been deleted` beim Schließen von Editoren durch robusteres Signal-Handling.

---

## v1.5.0 (Die UI Revolution - Dock-System)

### ✨ Features
- **Flexibles Dock-System**: Umstellung auf ein hochflexibles Dock-System (`QMainWindow`) mit hardwarebeschleunigtem Nesting- und Tab-Support.
- **Strukturierte Arbeitsbereiche**: Workflow-Panel in separate, einklappbare Docks aufgeteilt (Master, Sub, Logik) für bessere Übersicht bei komplexen Projekten.
- **Modernisiertes OCR-Variable-Panel**: Komplett-Redesign mit Live-Färbung, Match-Indikator und Smart-Template Filter.
- **Daten-Listen Pro**: Modernisierung der Daten-Listen mit `QTableWidget`, Echtzeit-Filtern und persistenter Speicherung der Spaltenkonfiguration.
- **Optimiertes Layout**: Toolbar unter das Live-Vorschaubild verschoben; Widescreen-Support durch intelligentes Nesting.

### ⚙️ Optimierungen
- **UI-Performance**: Reduzierung von Qt-Repaints durch intelligente Wertänderungs-Prüfung (`setText` Optimierung).
- **Architektur**: Strategische Code-Extraktion (`TemplateStore`, `Matcher`, `Canvas-Klassen`) zur Verbesserung der Wartbarkeit und Testbarkeit.

### 🛠️ Fixes
- **OCR-Koordinaten-Fix**: Korrektur der Drift-Problematik durch Normalisierung der Zonen auf die effektive Match-Größe (Screen-Pixel).
- **Deadlock-Prävention**: Behebung von Threading-Problemen beim on-demand Matching im Scheduler.
- **UI-Stabilität**: Fix für flackernde Rahmen, klobige SpinBox-Pfeile und fehlerhafte RadioButton-Styles.

---

## v1.4.3 (Smart Templates & Rekursion)

### ✨ Features
- **Smart Templates**: Unterstützung für Mehrfacherkennung und indexiertes OCR.
- **Rekursive Logik**: Implementierung von rekursivem Hierarchie-Matching für verschachtelte UI-Elemente.

---

## v1.4.2 (Engine-Erweiterungen & Simulation)

### ✨ Features
- **Erweiterte Workflow-Nodes**: Neue Nodes für Schleifen, Variablen-Manipulation (`set_value`) und Suche+Klick mit voller Simulationsunterstützung.
- **Kopierfunktionen**: Duplizieren von Workflows und Logik-Netzwerke direkt im UI.
- **Variablen-Picker**: Hierarchische Auswahl mit Untergruppen im Logik-Editor.

---

## v1.4.1 (Stabilität & Logic-Fixes)

### 🛠️ Fixes
- **ADB & Klick-Präzision**: Korrektur von Klick-Versätzen durch automatische DPI-Offset-Anpassung bei MEMU-Playern.
- **Workflow-Stabilität**: Behebung von Fehlern in der Hierarchie-Bedingungsprüfung und im Simulations-Thread.

---

## v1.4.0 (Performance, Logic & Advanced OCR)

### ✨ Features
- **On-Demand Matching**: Implementierung eines `force_include` Systems, das on-demand Scans für Workflows und Editoren ermöglicht, ohne die Globalen Settings zu ändern.      
- **Search-Only Modus (💤)**: Templates und Gruppen können jetzt als "passiv" markiert werden, um Systemressourcen zu sparen, während sie für explizite Suchen (Workflows/FUP) verfügbar bleiben.
- **FUP-Logik Live-Vorschau**: Echtzeit-Visualisierung der Logik-Netzwerke direkt im Logic-Editor.
- **Doppelklick-Navigation**: Schneller Wechsel zwischen Panels und Editoren für Workflows, Logik, Templates und Zustände.
- **Optimierte Timer-Erkennung**: Unterstützung für Tage-Formate mit Punkten (z.B. "4T. 12:13:15") und 3-Segment-Zeiten (HH:MM:SS).

### ⚙️ Optimierungen
- **Editor-Fokus-System**: Ermöglicht Live-Tests von Templates im Editor, indem Bedingungen (States/ROI) temporär umgangen werden können.
- **GPU-Logging**: Detailliertes Logging der Matching-Performance direkt im UI.
- **Hierarchische Template-Auswahl**: Strukturierte Menüs (Kategorien/Gruppen) in allen Editoren.
- **[KEIN ANDERER ZUSTAND]**: Optimierung der Logik und visuellen Darstellung im State-Panel.

### 🛠️ Fixes
- **OCR-Koordinaten-Fix**: Korrektur der Drift-Problematik durch Normalisierung der Zonen auf die effektive Match-Größe (Screen-Pixel).
- **Deadlock-Prävention**: Behebung von Threading-Problemen beim on-demand Matching im Scheduler.
- **UI-Stabilität**: Fix für flackernde Rahmen, klobige SpinBox-Pfeile und fehlerhafte RadioButton-Styles.

---

## v1.3.0 (Workflow-Power & UI-Harmonisierung)

### ✨ Features
- **Modernisierter Workflow-Editor**: Hierarchische Template-Auswahl und verbesserte Übersicht.
- **Logik-Netzwerk Integration**: Direkter Zugriff auf FUP-Netzwerke aus dem Workflow-Editor heraus.
- **Daten-Listen-Upgrade**: UI-Polishing, Tab-Synchronisation und verbesserte Text-Transformationen.
- **Set-States in Gruppen**: Gruppen-Editor wurde um die Möglichkeit erweitert, Zustände direkt bei Fund zu setzen.

### 🛠️ Fixes
- **Simulation-Thread**: Behebung von Abstürzen im Simulations-Modus des Workflow-Editors.
- **ClickStepSlider**: Zuverlässige Erkennung von Klicks in den Groove-Bereich.
- **Migration target_state**: Saubere Überführung veralteter State-Konfigurationen.

---

## v1.2.0 (OCR-Editor Revolution & Auto-Save)

### ✨ Features
- **OCR-Editor Overhaul**: Integration von Lupe, Live-Kontext (Spielhintergrund) und persistenter Hintergrund-Referenzen.
- **Auto-Save & Persistenz**: OCR-Zonen und Hintergründe werden nun sofort und robust gespeichert.
- **Kaskadierendes Löschen**: Beim Löschen von Gruppen werden nun auch alle zugehörigen Metadaten und Referenzen bereinigt.

### 🛠️ Fixes
- **Koordinaten-Sync**: Korrekte Synchronisation zwischen Markierung und tatsächlicher OCR-Region.
- **Fenster-Management**: Fix für hängende Debug-Fenster beim Schließen des Editors.
- **Bereinigung**: Automatisches Entfernen von Dateileichen im Dateisystem.

---

## v1.1.0 (Hierarchische Gruppen & Maskierung)

### ✨ Features
- **Echte Gruppen-Hierarchie**: Volle Unterstützung für verschachtelte Gruppen mit visueller Vererbung von ROI und Bedingungen.
- **Kreisförmige Masken**: Unterstützung für kreisförmige OCR-Ausschnitte und Maskierungen für komplexe UI-Elemente.
- **Einheitliches Button-System**: Umstellung auf QSS-basiertes Styling für konsistente Optik (Python setzt nur noch den ObjectName).
- **Dynamische Fenstertitel**: Editoren zeigen nun immer das aktuell bearbeitete Template/Element im Titel an.

### 🛠️ Fixes
- **ROI/Condition Vererbung**: Fehler bei der Weitergabe von Attributen durch die Hierarchie behoben.
- **Template-Erstellung**: Bugs beim initialen Anlegen von Templates im Panel beseitigt.
- **Style-Konsistenz**: Einheitliches Padding, Margins und Hover-Effekte über alle Panels hinweg.

---

## v1.0.0 (The PyQt6 Revolution)

### ✨ Highlights
- **Komplette UI-Ablösung**: Radikaler Umstieg von tkinter auf **PyQt6 (Qt 6.11.0)** für eine moderne, flüssige und hardwarebeschleunigte Benutzeroberfläche.
- **Architektur-Refactoring**:
  - Sämtliche Engines in den `engines/` Unterordner modularisiert.
  - Core-Logik, Helpers und State-Management in `core/` konsolidiert.
  - Blitzsauberes Root-Verzeichnis: Nur noch `main.py` und Dokumentation.
- **Zentralisiertes Daten-Management**:
  - Alle Konfigurationen, Templates und Datenbanken werden jetzt strukturiert unter `templates/settings/` und `templates/settings/data/` verwaltet.
  - Verwaiste Pfade und redundante JSON-Dateien im Root wurden eliminiert.
- **Hardware-Fokus**:
  - Getrennte Requirements für CPU (`requirements.txt`) und NVIDIA GPU (`requirements-cuda.txt`).
  - Native Unterstützung für CUDA 12.4 für blitzschnelles Template-Matching und OCR.

---

## v0.6.0 (Workflow-Power & Live-Simulation)

### ✨ Features & Highlights
- **Workflow Editor 2.0 (Blueprint-Stil)**:
  - Neuer visueller Canvas-Editor im Node-RED / Blueprint-Stil mit Bézier-Kurven.
  - Nodes als farbige Kacheln (Start, Suche, Klick, Warten, Bedingung, etc.).
  - Zoom (25% – 400%) und Pan-Funktion für große Graphen.
  - Gruppierte Template- und Variablen-Picker (Workflow/State/DB).
- **Graph-Modell & Engine**:
  - `workflow_engine.py` komplett auf Graph-Modell umgestellt.
  - Echtes Branching für Bedingungen (`true`/`false`) und Template-Suchen (`success`/`failure`).
- **Live-Simulation & Interaktiver Debugger**:
  - Simulation nutzt reale Bot-Daten (Matches, OCR, Game-States).
  - **Interaktiver Debugger**: Bei Aktionen (Klick, Zurück, Home) erscheint ein Abfrage-Dialog (Simulieren vs. ADB Ausführen).
  - **Echtzeit-Timer**: Live-Countdown (⌛) direkt auf den Node-Kacheln mit 0.1s Update-Intervall.
  - Multithreaded-Ausführung sorgt für eine flüssige UI während der Simulation.

---

## v0.5.1 (Hotfix: Master-Kind ROI Sync)

### 🛠️ Fixes
- **Logik-Fix: Master-Kind-Hierarchie**: Behebung eines Fehlers, bei dem Kinder-Templates innerhalb gefundener Master-Instanzen (Crops) fälschlicherweise übersprungen wurden, wenn die übergeordnete Gruppe einen statischen ROI (🎯) besaß.
- **Koordinaten-Korrektur**: Präzise Zusammenführung von Crop-Offsets und Kind-Koordinaten bei unterschiedlichen Skalierungsstufen.
- **Varianten-Support für Gruppen**: Sicherstellung, dass auch Varianten eines Masters (z.B. `Name__2`) ihre Kinder-Suche korrekt auslösen.

---

## v0.5.0 (Hierarchic ROI & OCR Power-Up)

### ✨ Features & Highlights
- **ROI-Vererbung (Scan-Bereiche)**:
  - **Hierarchische Vererbung**: Templates ohne eigenen ROI erben nun automatisch den Scan-Bereich ihrer übergeordneten Gruppen.
  - **Speicher-Fix**: Passive Gruppen können nun im Editor eigene Scan-Bereiche (ROI) dauerhaft speichern.
- **OCR-Revolution & Timer-Stabilität**:
  - **Multi-Language & Umlaute**: EasyOCR erkennt nun auch Ä, Ö, Ü und das 'T' in 'Tagen'.
  - **Komplexe Timer**: Volle Unterstützung für Timer mit Tagen inklusive automatischer Sekunden-Umrechnung.
  - **Robustes Preprocessing**: Adaptives Thresholding für stabilere Timer-Erkennung.
- **Timer-Integration in Daten-Listen**:
  - Neuer Transformationstyp `timer`: OCR-Werte werden automatisch in Sekunden gewandelt.

---

## v0.4.5 (Performance & UI Polishing)

### ✨ Features & Highlights
- **OCR-Editor Revolution**: Verfeinerte Live-Vorschau mit intelligentem Auto-Zoom.
- **Variable-Panel Stabilität**: Einführung einer 2-Sekunden-Hysterese gegen Flackern.

---

## v0.4.4 (Daten-Listen System & Hierarchie-Upgrade)

### 🚀 Das neue Daten-Listen-System
- **SQLite-Integration**: Einführung der `daten_listen.db`.
- **Berechnungs-Engine**: Dynamische Transformationen und Formel-Builder.
- **Einheiten-Management**: Globales Wörterbuch (`einheiten.json`).

---

## v0.4.3 (Bugfixes & UI-Verbesserungen)

### 🛠️ Fixes
- **🚀 Test-Button repariert**: Fehler in der GPU-Mathematik behoben.
- **In-Memory Tests**: Kein Disk-I/O mehr beim Testen von Templates.

---

## v0.4.2 (Template Editor Overhaul)

### ✨ Features
- **Game-State-Management**: `condition_states` und `set_states` direkt im Editor.
- **Varianten-Navigation**: Schnelles Bearbeiten von Bild-Varianten.

---

## v0.4.1 (OCR Context)

### ✨ Features
- **OCR Expansion**: Scannen außerhalb der Bounding-Box ermöglicht.
- **Live-Kontext**: Echte Spielumgebung im OCR-Dialog sichtbar.

---

## v0.4.0 (Multi-Variant OCR)

### ✨ Features
- **Multi-Template Support**: Beliebig viele Bild-Varianten pro Template.
- **OCR Farbfilter**: Pipette zur gezielten Textisolierung.

---

## v0.3.0 (GPU Matching Revolution)

### ✨ Features
- **PyTorch GPU Matching Engine**: MNCC-Suche auf der Grafikkarte.
- **Zwei-Phasen-Matching**: Master/Kind Logik für Performance-Boost.

---

## v0.2.0 (Action Engine & ADB)

### ✨ Features
- **EasyOCR Integration**.
- **ADB Hintergrund-Steuerung**.

---

## v0.1.0 (Initial Release)

### ✨ Features
- Live Vorschau MEMUPlayer
- Basis Template Matching
- Erste Workflow Engine
