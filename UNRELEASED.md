# Unreleased Changes (Draft)

---

## v1.5.6 (TBD)
*Aktueller Stand – In Arbeit*

### ✨ Features
- 

### ⚙️ Optimierungen
- **Intelligentes Pruning**: Vollständige Wiederherstellung der rekursiven Filterlogik. Templates werden nur gescannt, wenn ihre Eltern-Bedingungen (z.B. offene Menüs) erfüllt sind. Dies reduziert die Anzahl der Scans pro Frame massiv.
- **Hierarchische Kaskade**: Wiederherstellung der Master-Kind-Abhängigkeit. Kinder werden nur in den Ausschnitten gescannt, in denen ihr Master tatsächlich gefunden wurde.
- **GPU-Pipeline Fast-Path**: Optimierter Durchlauf für Einzel-Templates (ROIs) zur Minimierung von Synchronisations-Overhead.
- **Batch-Caching**: Dauerhafte Speicherung von fertig gestapelten Template-Tensoren im GPU-Speicher zur Vermeidung teurer Speicher-Allokationen in jedem Frame.
- **ROI-Pool-Turbo**: Nutzung von hochoptimiertem `avg_pool2d` für Einzel-Template-Scans in definierten Regionen zur Latenz-Minimierung.

### ✨ Features
- **Visual ROI Debug**: Neue Option in den Einstellungen zur Live-Visualisierung der aktuell gescannten Bildbereiche (lila Overlays).

### 🛠️ Fixes
- **ROI-Sicherheitscheck**: Verhindert Abstürze (`RuntimeError: conv2d`), wenn Scan-Regionen durch Skalierung oder Fehlkonfiguration kleiner als das Template sind.
- **SharedMemory Windows-Fix**: Behebung von `WinError 183` durch automatisches Übernehmen existierender Puffer nach unsauberem Programmende.
- **Variablen-Panel**: Wiederherstellung der `_is_smart_recursive` Methode zur korrekten Filterung und Anzeige im UI.
---

## v1.5.5 (Performance-Turbo) - 01.05.2026

### ✨ Features
- **Shared Memory System**: Implementierung eines 40MB Shared Memory Puffers (SharedFrameBuffer) für Zero-Copy Screenshots zwischen Capture- und Matching-Prozessen. Eliminiert die teure Python-Serialisierung (Pickle) großer Arrays.
- **Pinned Memory (DMA)**: Nutzung von Page-Locked Memory für beschleunigte Datentransfers über den PCIe-Bus direkt zum VRAM der GPU.
- **GPU-Native Konvertierung**: Verlagerung der rechenintensiven Bildumwandlung (uint8 -> loat32, Skalierung, Kanal-Permutation) von der CPU direkt auf die Grafikkarte (4080 Super optimiert).

### ⚙️ Optimierungen
- **Präzise Performance-Logs**: Verlagerung der Zeitmessung in den Matching-Subprozess inklusive 	orch.cuda.synchronize(). Garantiert exakte GPU-Timings unabhängig von asynchronen CPU-Threads.
- **Subprozess-Effizienz**: Reduzierung der Datenmenge in der Matching-Queue auf reine Metadaten (Shape, Dtype), da das Bild bereits im Shared Memory liegt.
- **Asynchroner Transfer**: Nutzung von 
on_blocking=True für den GPU-Upload, was die Parallelität zwischen CPU und GPU weiter steigert.

### 🛠️ Fixes
- **Matching-Timing Fix**: Behebung von Messfehlern in den Performance-Logs, die durch asynchrone Prozess-Kommunikation und GPU-Latenzen entstanden sind.

---

## v1.5.4 (Event-Bus & UX-Update) - 01.05.2026

### ✨ Features
- **Event Bus System**: Implementierung einer zentralen Pub/Sub Infrastruktur (core/event_bus.py) zur vollständigen Entkopplung der Engines von der Benutzeroberfläche.
- **Asynchroner Data-Worker**: Neuer Hintergrund-Dienst (core/data_worker.py) zur Verarbeitung von OCR-Rohdaten (Timer-Berechnungen, Einheiten-Transformationen, Formel-Auswertungen) ohne Blockierung des UI-Threads.
  - **DataWorker Heartbeat**: Kontinuierliche Berechnung von Timern und Formeln auch ohne aktive OCR-Events (1,5s Intervall).
- **Reaktive UI-Panels**: Alle Haupt-Panels (State, Workflow, Template, Variable, Daten) wurden auf ein ereignisgesteuertes Modell umgestellt und aktualisieren sich nun autonom via Event Bus.
- **Auto-Tune Engine (Alpha)**: Ein neuer interaktiver Wizard hilft beim Einlernen von Templates. Er sucht automatisch nach der besten Trennschärfe zwischen Icon und Hintergrund.
  - *Hinweis: Basis-Implementierung steht, bedarf aber noch weiterer Optimierung im realen Bot-Betrieb.*
- **Top-Down-Scan**: Intelligente Ermittlung des Schwellwerts durch schrittweises Absenken der Konfidenz.
- **Interaktives Labeling**: Im großen Vorschaufenster können korrekte Treffer per Klick markiert werden, um den Bot zu trainieren.
- **Toleranz-Sweep**: Automatische Optimierung der Hintergrund-Toleranz basierend auf den Benutzer-Markierungen.

### ⚙️ Optimierungen
- **Thread-Sicherheit (BotState)**: Einführung von Locks in core/bot_state.py zur Vermeidung von Race Conditions bei gleichzeitigem Zugriff von Matching- und UI-Threads auf Spielzustände.
- **UI-Performance**: Massive Entlastung des Haupt-Threads durch Entfernung von Polling-Loops; chirurgische Updates der UI-Komponenten statt vollständiger Rebuilds bei Wertänderungen.
  - **Live-Vorschau Optimierung**: Umstellung der Bildskalierung auf bilineare Interpolation (INTER_LINEAR) für flüssige 60-FPS-Darstellung bei geringerer CPU-Last.
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
