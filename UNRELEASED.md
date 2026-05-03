# Unreleased Changes (Draft)

---

## v1.5.6 (TBD)
*Aktueller Stand – In Arbeit*

### ✨ Features
- **Live-Matching-Monitor**: Neues permanentes UI-Panel zur Echtzeit-Visualisierung der Matching-Statistiken (ROI-Anzahl pro Template, Latenz, GPU-Last).
- **Matching.Stats Event**: Erweiterung des EventBus um detaillierte Metriken pro Matching-Zyklus.

### ⚙️ Optimierungen
- **Panel-Update-Throttle**: `MatchingMonitorPanel` und `StatePanel` werden jetzt auf max. 4fps gedrosselt. Vorher bauten beide Panels ihre Qt-Listen bei jedem Matching-Zyklus (~10–20fps) vollständig neu auf, was 5–20ms GUI-Thread-Blockage pro Update erzeugte und den 30fps-Display-Timer regelmäßig verzögerte. Der letzte State wird weiterhin sofort gespeichert; nur die Widget-Aktualisierung ist gedrosselt.
- **OCR-Subprocess auf CPU**: EasyOCR-Subprocess nutzt jetzt `gpu=False`. Ursache der 0.5–1s Matching-Unterbrechungen: Matching-Subprocess (`torch.cuda.synchronize()`) und OCR-Subprocess (EasyOCR mit GPU) liefen gleichzeitig auf derselben GPU → CUDA Context Switching verlangsamte Matching von ~50ms auf ~300–500ms → `result_q.get(timeout=0.1)` machte 3–5 Timeouts pro Frame → wirkte als "Matching unterbrochen". OCR läuft nur alle 0.5s auf wenige kleine Crops; CPU-Modus ausreichend.
- **Overlay-Rendering in Background-Thread**: Vollständige Verlagerung des Overlay-Renderings (Match-Boxen, OCR-Regionen, Scanned-Regions) aus dem GUI-Thread in den `_FrameWorker(QThread)`. `QPainter` auf `QImage` ist in Qt thread-sicher; der GUI-Thread macht nur noch 2× `QPixmap.fromImage()` + 2× `drawPixmap()`. Mit 18+ Matches: Overlay-Rendering spart ~5–20ms GUI-Thread-Blockage pro Zyklus — vollständige Eliminierung der stotterbedingten Ursache.
- **Zero-Idle Matching-Loop**: `_matching_loop` sendet den nächsten Frame **sofort nach** dem Empfang eines Ergebnisses (vor der Ergebnisverarbeitung). Subprocess erhält den neuen Frame bei T=50ms statt T=70ms → kein Idle-Fenster mehr. Bei Timeout wird ebenfalls sofort ein Frame nachgefüttert.
- **Background-Frame-Worker**: Frame-Konvertierung (BGR → QImage: cv2.resize + cvtColor) in einen `_FrameWorker(QThread)` ausgelagert. GUI-Thread schreibt Frame per Submit-Slot, Worker schreibt QImage per Result-Slot zurück. Keine Signal-Emissionen (60×/sec Signal-Flood eliminiert); `apply_pending_frame()` liest den Slot synchron ab. `QPixmap.fromImage()` und `repaint()` bleiben im GUI-Thread.
- **PreciseTimer + repaint() für Display-Loop**: `QTimer` nutzt jetzt `Qt.TimerType.PreciseTimer` (Windows-Multimedia-Timer), der auch während des modalen Windows-Fenster-Verschiebe-Loops feuert. `repaint()` (synchron, direkt `paintEvent`) statt `update()` (asynchron, blockiert im Modal-Loop).
- **Display-Cache für OCR-Konfigurationen**: `_cached_ocr_konf` und `_cached_ocr_regionen` werden einmalig gecacht und nur bei `templates.changed`-Event aktualisiert — kein teures Neuaufbauen im 60-FPS-Display-Tick.
- **Zero-Loop Tensor-Prep**: Vollständige Eliminierung von Python-Schleifen bei der Vorbereitung von Bildausschnitten (ROIs). Statt sequenziellem Padding wird nun ein einziger großer GPU-Tensor vor-allokiert, in den alle Ausschnitte per Batch-Slicing parallel hineinkopiert werden.
- **Zero-Upload Offset-Logik**: Beseitigung von Synchronisationspunkten durch Verlagerung der Koordinaten-Transformation auf die CPU. Der redundante Upload von Offsets zur GPU entfällt komplett.
- **Vektorisiertes Cascade-Batching**: Die kaskadierte Suche (Master-Kind-Beziehung) wurde vollständig vektorisiert. Alle Kinder-Templates eines Frames werden nun gesammelt in optimierten Batches verarbeitet, statt sequenziell in Schleifen.
- **Box-Filter-Precalculating**: Radikale Reduktion der Convolution-Last. Redundante Helligkeits- und Varianzberechnungen für Fullscreen-Templates werden durch einen hocheffizienten Vorberechnungsschritt (`avg_pool2d`) eliminiert.
- **Zero-Sync-Pipeline v2**: Vollständige Eliminierung von Synchronisationspunkten durch Vor-Allokation aller Schwellwerte und Metadaten als GPU-Tensoren.
- **Persistent ROI-Stacks**: Dauerhaftes Caching von gestapelten Gewichts- und Masken-Tensoren für ROI-Gruppen im VRAM. Vermeidet hunderte `torch.cat()`-Operationen pro Sekunde und schont die Speicherbandbreite.
- **Unified GPU-Transfer**: Ergebnisse verbleiben bis zum finalen Filter-Schritt als Tensoren auf der GPU. Reduktion der PCIe-Kommunikation auf einen einzigen gebündelten Transfer pro Suchvorgang.
- **Hierarchie- & Logik-Caching**: Aggressives Caching von Template-Abhängigkeiten, rekursiven Pfadprüfungen und Status-Bedingungen zur drastischen Reduktion des Python-Overheads.
- **GPU-Vektorisierung**: Koordinaten-Transformationen, Skalierungen und Offsets werden nun massiv parallel direkt auf der GPU berechnet statt seriell in Python-Schleifen.
- **ROI-Padding-Batching**: Radikale Reduktion der GPU-Kernel-Launches durch Gruppierung von ROIs gleicher Template-Größe. Bildausschnitte werden gepolstert (Padding) und in einem einzigen Batch-Scan verarbeitet.
- **No-Sync-GPU-Pipeline**: Verschiebung aller Template-Konstanten (Normen, Pixelanzahl) als fertige Tensoren in den GPU-Cache. Eliminiert teure Synchronisationspunkte (`torch.tensor()`) während des Scans.
- **Zero-Sync-Broadcasting**: Optimierte Tensor-Dimensionen im Cache ermöglichen direktes GPU-Broadcasting ohne Re-Shaping im Loop.
- **PCIe-Transfer-Optimierung**: Entfernung von `pin_memory()` zur Steigerung des Durchsatzes bei Shared-Memory-Zugriffen unter Windows.
- **Intelligentes Pruning**: Vollständige Wiederherstellung der rekursiven Filterlogik. Templates werden nur gescannt, wenn ihre Eltern-Bedingungen (z.B. offene Menüs) erfüllt sind. Dies reduziert die Anzahl der Scans pro Frame massiv.
- **Hierarchische Kaskade**: Wiederherstellung der Master-Kind-Abhängigkeit. Kinder werden nur in den Ausschnitten gescannt, in denen ihr Master tatsächlich gefunden wurde.
- **ROI-Exklusivität**: Erzwungene Priorisierung von Scan-Regionen. Sobald eine ROI definiert ist, wird der Fullscreen-Scan für dieses Template unterdrückt, was die GPU-Last halbiert.     
- **GPU-Pipeline Fast-Path**: Optimierter Durchlauf für Einzel-Templates (ROIs) zur Minimierung von Synchronisations-Overhead.
- **Batch-Caching**: Dauerhafte Speicherung von fertig gestapelten Template-Tensoren im GPU-Speicher zur Vermeidung teurer Speicher-Allokationen in jedem Frame.

### 🛠️ Fixes
- **FrameWorker Exception-Handling**: Bei einer Exception in `_render_overlay_image()` (z.B. QPainter in Non-GUI-Thread) wurde `self._result` nicht gesetzt → `apply_pending_frame()` fand kein Ergebnis und das Display fror am alten Frame ein. Fix: im `except`-Zweig wird jetzt mindestens `(frame_qimg, None, skala, ox, oy)` gespeichert, sodass das Frame immer angezeigt wird.
- **Robustes ROI-Clamping**: Suchfenster werden bei Bildschirmrand-Überschreitung nun intelligent verschoben statt verkleinert. Garantiert eine gültige Eingabegröße für GPU-Operationen und verhindert `RuntimeError`.
- **Dimension-Guard**: Sicherheitsprüfung für `max_pool2d` bei extrem kleinen oder leeren Ergebnismaps (z.B. durch Randfälle bei der Skalierung).
- **Varianten-Vererbung**: Template-Varianten (z.B. `Name__1`) erben nun korrekt die Scan-Regionen (ROI) ihres Basis-Templates.
- **Fullscreen-Diagnose**: Erweitertes Logging identifiziert nun automatisch Templates, die einen Fullscreen-Scan ohne ROI erzwingen.
- **SharedMemory Windows-Fix**: Behebung von `WinError 183` durch automatisches Übernehmen existierender Puffer nach unsauberem Programmende.
- **Variablen-Panel**: Wiederherstellung der `_is_smart_recursive` Methode zur korrekten Filterung und Anzeige im UI.
- **Crash-Isolierung durch vollständige Subprocess-Architektur**: Behebung von wiederholten `access violation` und `0xc0000374` Heap-Corruption-Abstürzen durch vollständige Prozess-Isolation aller nativen Bibliotheken:
  - *Ursache EasyOCR*: PyTorch-nativer Allokator korrumpierte den Windows-Heap des Hauptprozesses und führte zu sporadischen Access Violations in nicht verwandten Threads (z.B. WGC-Callback). Fix: EasyOCR/PyTorch läuft jetzt in `_ocr_subprocess` (eigener OS-Prozess), kommuniziert über `mp.Queue` Request/Response mit `mp.Event` Bereitschaftssignal.
  - *Ursache WGC*: Der Rust-Thread der `windows_capture`-Bibliothek gibt D3D11-Staging-Buffer ohne Python-GIL frei. Jede Kopiermethode (`bytes()`, `np.array()`, `ctypes.memmove()`) kann in diesem Zeitfenster abstürzen, da der Hauptprozess-Heap korrumpiert wird. Fix: WGC läuft in `_wgc_subprocess`, schreibt BGR-Frames per Shared Memory (`bot_wgc_frame`, 30 MB), Hauptprozess liest daraus ohne direkten Rust-Buffer-Kontakt.
  - Automatischer WGC-Subprocess-Neustart in `_capture_loop` bei Absturz; `mss` als Fallback während des Neustarts.
- **TemplateEngine CPU-Isolation im Hauptprozess**: `TemplateEngine` im Hauptprozess lädt Templates jetzt ausschließlich auf CPU (`force_cpu=True`). Ursache: `_templates_laden()` rief `.to(cuda)` beim Start und bei jedem Reload auf, wodurch PyTorchs CUDA-Allocator im Hauptprozess aktiv war und sporadisch den Windows-Heap korrumpierte (Access Violation in `mp.Queue._feed`). Der Matching-Subprocess verwendet weiterhin CUDA und ist davon nicht betroffen.
- **ROI-Editor Matches**: `matches_suchen_np` gibt seit den Performance-Optimierungen 4 Werte zurück (`matches, master_namen, scanned_regions, search_stats`). Der ROI-Editor-Test hat nur 2 entpackt → `too many values to unpack`. Korrigiert auf `res, master_namen, _, _ = ...`.
- **VorschauLabel AttributeError beim Start**: `set_frame()` verglich `scanned_regions != self._scanned_regions` bevor `_scanned_regions` in `__init__` initialisiert war → `AttributeError`. Fix: `self._scanned_regions: list = []` und `self._show_roi: bool = False` in `__init__` ergänzt.
- **EventBus Thread-Safety / Access Violation im Qt-Event-Loop**: Der EventBus rief alle Callbacks synchron im Publisher-Thread auf. Da `_matching_loop`, `_ocr_loop` und `_capture_loop` aus Background-Threads publishten, wurden Qt-Panel-Updates (`matching_monitor`, `variable_panel`, `state_panel`, `daten_panel`) direkt aus fremden Threads ausgeführt — ein fataler Qt-Threading-Verstoß der sporadische Access Violations in `app.exec()` verursachte. Fix: `EventBus.publish()` erkennt jetzt ob es aus einem Background-Thread aufgerufen wird. Falls ja, wird ein `QObject`-basierter Dispatcher (`pyqtSignal` mit `AutoConnection`) verwendet, der Qt's eigenen Queued-Connection-Mechanismus nutzt und die Callbacks sicher in den GUI-Thread einreiht. Der Dispatcher wird lazy beim ersten publish aus dem Haupt-Thread initialisiert; in Subprocessen (kein `QApplication`) bleibt das bisherige Direktaufruf-Verhalten erhalten.

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
