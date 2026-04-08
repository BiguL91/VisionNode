# Ai-Bot – Tech Stack

| Library              | Zweck                                        |
|----------------------|----------------------------------------------|
| **`windows-capture`**| Screen Capture via Windows Graphics Capture API (WGC) |
| **`torch` (PyTorch)** | **Core Engine**: GPU-beschleunigtes Template Matching (NCC) |
| **`easyocr`**        | OCR-Engine mit GPU-Support (CUDA)            |
| **`opencv-python`**  | Bildverarbeitung, Filter, I/O                |
| **`pywin32`**        | Fenster-Handling                             |
| **`Pillow`**         | Bildbearbeitung für UI & Vorschau            |
| **`numpy`**          | Matrix-Berechnungen                          |
| **`tkinter`**        | Grafische Oberfläche (GUI)                   |

---

## Capture Engine

- **WGC** (`windows-capture`): Primärer Capture-Stream (60fps), HDR-ready.
- **MSS**: Fallback für Initialisierungsphase.

## Vision Engine (GPU Powered)

- **PyTorch Matching**: Eigene Implementierung der **Maskierten Normalisierten Kreuzkorrelation (MNCC)**.
  - **Zero-Mean Normalisierung**: Gleicht Helligkeitsschwankungen dynamisch aus.
  - **Masken-Support**: Nutzt Alpha-Kanäle der Templates für präzise Formerkennung ohne Hintergrund-Noise.
  - **Box-Filter Optimierung**: Nutzt `avg_pool2d` für extrem schnelle Varianzberechnung bei unmaskierten Templates.
  - **Bbox-Autokorrektur**: Erkennt den relevanten Objektinhalt innerhalb von Templates mit viel Transparenz.
- **OCR**: EasyOCR auf GPU-Basis für Echtzeit-Texterkennung.
- **Skalierung**: Variables Matching auf 25% bis 100% der nativen Auflösung.

## Action Engine

- **ADB**: Hintergrund-Interaktion via Android Debug Bridge.
- **Koordinaten-Matrix**: Automatische Umrechnung zwischen Canvas, Window und Android-Screen (inkl. Skalierung).

## Threading- & Prozess-Modell (CPU-Optimierung)

Um die CPU-Last minimal zu halten (~5-10% bei 60fps) und den Python-GIL zu umgehen, nutzt Ai-Bot ein hybrides Modell:

| Komponente            | Typ               | Aufgabe                                      | Intervall |
|-----------------------|-------------------|----------------------------------------------|-----------|
| **UI-Thread**         | Haupt-Thread      | Event-Loop, Rendering, Display-Update        | ~16ms     |
| **Capture-Thread**    | Thread            | Empfängt WGC-Frames, Resize, Vorverarbeitung | ~16ms     |
| **Matching-Prozess**  | **OS-Prozess**    | PyTorch-Berechnungen (GPU) & NMS-Logik       | ~33-66ms  |
| **OCR-Thread**        | Thread (Worker)   | EasyOCR-Queue (GPU-gebunden)                 | nach Bedarf |
| **Scheduler-Thread**  | Thread (Worker)   | Workflow-Logik & ADB-Befehle                 | variabel  |

**Vorteile:**
- **Zero UI-Lag**: Die Oberfläche bleibt auch bei hoher Matching-Last 100% reaktiv.
- **Echte Parallelität**: Durch den separaten Matching-Prozess werden mehrere CPU-Kerne effizient genutzt.
- **GPU-Offloading**: Schwere mathematische Operationen belasten die CPU kaum, da sie direkt via CUDA auf der Grafikkarte laufen.
