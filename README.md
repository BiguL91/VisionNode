# Ai-Bot – Mobile Game Automatisierung

Ein hochpräziser Bot für Mobile Games im MEMUPlayer.
Ai-Bot nutzt fortschrittliche Computer Vision und OCR, um Spielinhalte zu erkennen und Workflows autonom auszuführen.

---

## Kern-Features

- **Screen Capture (Windows Graphics Capture)**
  - Identische Technologie wie Xbox Game Bar und TeamSpeak Screen Sharing.
  - **Minimale CPU-Last (~5-10%)**: Dank Multi-Threading und GPU-Offloading bleibt das System extrem effizient.
  - Hochperformant: **60fps** stabil, auch bei komplexen Workflows.
  - Funktioniert mit DirectX, OpenGL, Vulkan und HDR-Monitoren.
- **Vision Engine (High Precision & GPU Powered)**
  - **Hierarchisches Matching (Master/Kind)**: Revolutionäres Zwei-Phasen-System. Sucht erst nach Rahmen (Master) und klassifiziert dann den Inhalt (Kind).
  - **Multi-Varianten-Support**: Beliebig viele Bild-Varianten pro Template (`name`, `name__2`, `name__3`) für robuste Erkennung.
  - **PyTorch Template Matching**: Blitzschnelle MNCC-Erkennung direkt auf der GPU.
  - **Auto-Bbox Korrektur**: Präzise Klickpunkte durch automatische Inhalts-Erkennung.
  - **EasyOCR (GPU)**: Texterkennung in Echtzeit mit Farbfilter, Pipette und **Umlaute-Support (DE)**.
  - **Maskiertes Matching**: Voller Alpha-Kanal Support für präzise Icons.
- **Hierarchische ROI-Vererbung (Scan-Bereiche)**
  - **🎯 Fadenkreuz-System**: Templates erben automatisch die Scan-Bereiche ihrer Eltern-Gruppen.
  - Maximale Performance: Nur relevante Bildschirmbereiche werden gescannt, ohne jedes Template einzeln konfigurieren zu müssen.
- **Game-State-Management**
  - Templates können Spielzustände setzen (`set_states`) und nur bei bestimmten Zuständen aktiv sein (`condition_states`).
  - Logische Verknüpfung: AND (müssen alle zutreffen) und OR (einer reicht) kombinierbar.
- **Action Engine (ADB)**
  - Hintergrund-Interaktion via Android Debug Bridge (ADB)
  - Keine Mausbewegung erforderlich – der Bot arbeitet unsichtbar im Hintergrund
  - Stabilisierte Koordinaten-Umrechnung für Portrait- und Landscape-Modus
- **Workflow & Automation**
  - Visueller Editor zum Erstellen komplexer Abläufe (suche, klick, warte, bedingung)
  - **Scheduler**: Geordnete Queue-Abarbeitung für endlose Automatisierung
- **UI & Performance (Surgical Updates)**
  - **Flackerfreie Listen**: Nur geänderte Werte werden aktualisiert, kein kompletter Widget-Rebuild pro Intervall.
  - **Daten-Panel**: Live-Update berechneter Werte (Transformationen, Formeln, Timer-Ablauf).
- **Template Editor (All-in-One)**
  - **Tab-Leiste**: Ignorieren, Klick-Zone, Scannbereiche, OCR und Zustände – alles direkt im Editor.
  - **Varianten-Navigation**: Master/Version-Anzeige mit `◀ ▶` Pfeilen, Löschen von Varianten (Master geschützt).
  - **Non-Stop Workflow**: Speichern schließt den Editor nicht – schnelles Bearbeiten mehrerer Varianten hintereinander.
- **Entwickler-Tools**
  - **ROI-Editor (Scannbereiche)**: Begrenze die Suche auf spezifische Bildschirmbereiche für maximale Performance.
  - **🚀 Interaktiver Test**: Sofortige Überprüfung der Erkennungsrate (Score) gegen Snapshots.
  - **Dual-Preview Einlern-Modus**: Live-Vorschau und GPU-Mathematik (Zero-Mean) synchron in einem Fenster.
  - **Debug-Modus**: Automatische Bildspeicherung im `/debug` Ordner für OCR-Analyse.

---

## Tech Stack

| Technologie          | Zweck                                   |
|----------------------|-----------------------------------------|
| `windows-capture`    | Screen Capture (WGC API, primär)        |
| `PyTorch` (GPU)       | Core Matching Engine (MNCC)             |
| `EasyOCR` (GPU)       | Texterkennung (OCR)                     |
| `OpenCV`             | Bildverarbeitung, I/O                   |
| `ADB`                | Hintergrund-Steuerung                   |
| `Tkinter`            | Modernes Dunkles UI                     |
| `NumPy`              | Matrix-Operationen                      |

---

## Installation & Start

1. **Voraussetzungen**: Python 3.10+, CUDA Toolkit (für GPU-OCR), MEMUPlayer
2. **Dependencies**: `pip install -r requirements.txt`
3. **Start**: `python main.py`
4. **Hinweis**: ADB (Android Debug Bridge) Der SDK Platform Tools ist Downloadbar unter https://developer.android.com/tools/releases/platform-tools?hl=de

---

## Status

v0.5.1 – **Hotfix: Master-Kind ROI Sync**.

Für Details siehe [CHANGELOG.md](CHANGELOG.md)
