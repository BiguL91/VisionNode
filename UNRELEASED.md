# Unreleased Changes (Draft)

---

## v1.5.4 (TBD)
*Aktueller Stand – In Arbeit*

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
