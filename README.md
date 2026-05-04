# VisionNode – Mobile Game Automatisierung

Ein hochpräzises Automatisierungs-Framework für Mobile Games im MEMUPlayer.
VisionNode nutzt fortschrittliche Computer Vision und OCR, um Spielinhalte zu erkennen und Workflows autonom auszuführen.

---

## Kern-Features

- **Interaktion & Steuerung**
  - **Direktsteuerung (🎮)**: Steuere den Emulator direkt über das Live-Vorschaubild im Bot – kein Task-Switching mehr nötig!
  - **Snapshot-Revolution**: Blitzschnelle Bildaufnahmen mit eigenem Manager zum Suchen, Umbenennen und Verwalten.
- **ROI-Optimierung**
  - **Scan-Regionen Live-Editor**: Definiere ROIs direkt am Live-Bild oder lade gespeicherte Snapshots in den visuellen Picker.
  - **Flüssiges Scaling**: Proportionale Bilddarstellung in allen Dialogen für maximale Präzision.
- **Flexibles Dock-System (PyQt6)**
  - Modernes, modulares UI mit verschiebbaren und einklappbaren Panels.
  - **Auto-Save & Persistenz**: Automatische Speicherung aller Fensterpositionen und Layouts.
  - **Fokus-Modus**: Ausgliederung von Panels in separate Vollformat-Fenster.
- **Vision Engine (GPU Powered)**
  - **Hierarchisches Matching**: Revolutionäres Zwei-Phasen-System.
  - **PyTorch Template Matching**: Blitzschnelle MNCC-Erkennung direkt auf der GPU.
  - **EasyOCR (GPU)**: Texterkennung in Echtzeit mit Farbfilter und Umlaute-Support.
- **Screen Capture (WGC)**
  - Minimale CPU-Last (~5-10%) dank Windows Graphics Capture API.
  - HDR-ready und stabil bei 60fps.
- **Workflow & Automation**
  - **Blueprint Editor**: Visueller Graphen-Editor für komplexe Logik (FUP).
  - **Live-Simulation**: Teste Workflows sicher ohne ADB-Eingriff.

---

## Tech Stack

| Technologie          | Zweck                                   |
|----------------------|-----------------------------------------|
| `PyQt6`              | Modernes hardwarebeschleunigtes UI      |
| `PyTorch` (CUDA)     | Core Matching Engine (MNCC)             |
| `EasyOCR`            | Texterkennung (GPU)                     |
| `windows-capture`    | High-Speed Screen Capture (WGC)         |
| `ADB`                | Hintergrund-Steuerung                   |

---

## Installation & Start

1. **Voraussetzungen**: Python 3.10+, NVIDIA GPU (für CUDA-Support empfohlen), MEMUPlayer.
2. **Dependencies**:
   - **NVIDIA GPU**: `pip install -r requirements-cuda.txt`
   - **Standard (CPU)**: `pip install -r requirements.txt`
3. **Start**: `python main.py`

---

## Status

VisionNode v1.5.7 – **Stabilität & UI-Architektur**.


Für Details siehe [CHANGELOG.md](CHANGELOG.md)
