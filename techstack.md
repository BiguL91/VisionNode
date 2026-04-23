# Ai-Bot – Tech Stack

| Library              | Zweck                                        |
|----------------------|----------------------------------------------|
| **`PyQt6`**          | **Grafische Oberfläche (GUI)** — Hochflexibles Dock-System |
| **`windows-capture`**| Screen Capture via Windows Graphics Capture API (WGC) |
| **`torch` (PyTorch)** | **Core Engine**: GPU-beschleunigtes Template Matching (MNCC) |
| **`easyocr`**        | OCR-Engine mit GPU-Support (CUDA)            |
| **`opencv-python`**  | Bildverarbeitung, Filter, I/O                |
| **`pywin32`**        | Fenster-Handling                             |
| **`Pillow`**         | Bildbearbeitung für UI & Vorschau            |
| **`numpy`**          | Matrix-Berechnungen                          |

---

## UI Architecture (PyQt6)

- **Dock-System**: Modulares Layout via `QMainWindow` mit verschiebbaren, tabbaren und einklappbaren Panels.
- **Geometry Management**: Persistente Speicherung von Fensterpositionen und Layout-Zuständen in `app_config.json`.
- **Custom Widgets**: Hardwarebeschleunigte Vorschau-Label mit Echtzeit-Overlays für Matches und OCR.

---

## Vision Engine (GPU Powered)

- **PyTorch Matching**: Eigene Implementierung der **Maskierten Normalisierten Kreuzkorrelation (MNCC)**.
  - **Zero-Mean Normalisierung**: Gleicht Helligkeitsschwankungen dynamisch aus.
  - **Masken-Support**: Nutzt Alpha-Kanäle der Templates für präzise Formerkennung ohne Hintergrund-Noise.
  - **Box-Filter Optimierung**: Nutzt `avg_pool2d` für extrem schnelle Varianzberechnung bei unmaskierten Templates.
- **OCR**: EasyOCR auf GPU-Basis für Echtzeit-Texterkennung.

---

## Threading- & Prozess-Modell (CPU-Optimierung)

Um die CPU-Last minimal zu halten (~5-10% bei 60fps) und den Python-GIL zu umgehen, nutzt Ai-Bot ein hybrides Modell:

| Komponente            | Typ               | Aufgabe                                      | Intervall |
|-----------------------|-------------------|----------------------------------------------|-----------|
| **UI-Thread**         | Haupt-Thread      | Event-Loop, Rendering, Geometry Persistency  | ~16ms     |
| **Capture-Thread**    | Thread            | Empfängt WGC-Frames, Resize, Vorverarbeitung | ~16ms     |
| **Matching-Prozess**  | **OS-Prozess**    | PyTorch-Berechnungen (GPU) & NMS-Logik       | ~33-66ms  |
| **OCR-Thread**        | Thread (Worker)   | EasyOCR-Queue (GPU-gebunden)                 | nach Bedarf|
| **Scheduler-Thread**  | Thread (Worker)   | Workflow-Logik (Graph) & ADB-Befehle         | variabel  |

**Vorteile:**
- **Zero UI-Lag**: Die Oberfläche bleibt auch bei hoher Matching-Last 100% reaktiv.
- **Echte Parallelität**: Durch den separaten Matching-Prozess werden mehrere CPU-Kerne effizient genutzt.
- **GPU-Offloading**: Schwere mathematische Operationen belasten die CPU kaum, da sie direkt via CUDA auf der Grafikkarte laufen.
