# Changelog

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
  - **Echtzeit-Timer**: Live-Countdown (⏳) direkt auf den Node-Kacheln mit 0.1s Update-Intervall.
  - Multithreaded-Ausführung sorgt für eine flüssige UI während der Simulation.

---

## v0.5.1 (Hotfix: Master-Kind ROI Sync)

### 🛠 Fixes
- **Logik-Fix: Master-Kind-Hierarchie**: Behebung eines Fehlers, bei dem Kinder-Templates innerhalb gefundener Master-Instanzen (Crops) fälschlicherweise übersprungen wurden, wenn die übergeordnete Gruppe einen statischen ROI (🎯) besaß.
- **Koordinaten-Korrektur**: Präzise Zusammenführung von Crop-Offsets und Kind-Koordinaten bei unterschiedlichen Skalierungsstufen.
- **Varianten-Support für Gruppen**: Sicherstellung, dass auch Varianten eines Masters (z.B. `Name__2`) ihre Kinder-Suche korrekt auslösen.

---

## v0.5.0 (Hierarchic ROI & OCR Power-Up)

### ✨ Features & Highlights
- **ROI-Vererbung (Scan-Bereiche)**:
  - **Hierarchische Vererbung**: Templates ohne eigenen ROI erben nun automatisch den Scan-Bereich ihrer übergeordneten Gruppen. Dies ermöglicht das Scannen ganzer Menü-Zweige in spezifischen Bildschirmbereichen.
  - **Speicher-Fix**: Passive Gruppen können nun im Editor eigene Scan-Bereiche (ROI) dauerhaft speichern.
- **OCR-Revolution & Timer-Stabilität**:
  - **Multi-Language & Umlaute**: EasyOCR erkennt nun durch Deutsch-Support auch Ä, Ö, Ü und das 'T' in 'Tagen'.
  - **Komplexe Timer**: Volle Unterstützung für Timer mit Tagen (z.B. '2T 12:44:15') inklusive automatischer Sekunden-Umrechnung.
  - **Robustes Preprocessing**: Adaptives Thresholding und morphologische Verstärkung für Timer-Regionen blenden bewegte Fortschrittsbalken und transparente Hintergründe effektiv aus.
- **Timer-Integration in Daten-Listen**:
  - Neuer Transformationstyp `timer`: OCR-Werte werden automatisch in Sekunden gewandelt und bei Wegfall intern deadline-basiert weitergezählt.
  - Formatiertes Anzeigeformat (z.B. `1t 4h 30m`) in der Daten-Tabelle.

### 🚀 Performance & UI
- **Inkrementelles Panel-Update**:
  - Daten-Liste, Variable-Panel und State-Panel wurden auf "Surgical Updates" umgestellt.
  - Nur noch geänderte Label-Texte werden aktualisiert, anstatt das gesamte Panel neu aufzubauen – eliminiert jegliches Flackern.
- **Erweiterte Header-Icons**:
  - Neues ROI-Icon (🎯) zeigt in der Liste sofort an, ob ein Scan-Bereich konfiguriert oder vererbt wurde.
  - Icons (🎯, 🚩, etc.) werden nun auch konsistent an Gruppen-Headern angezeigt.

### 🔧 Fixes & Cleanup
- **Datenbank-Konsolidierung**: Veraltete `daten.db` entfernt, alle Daten laufen nun über `daten_listen.db`.
- **Git-Workflows**: SQLite-Journal-Dateien werden nun automatisch ignoriert, was den Git-Status sauber hält.
- **Fehlerkorrektur**: Automatische Bereinigung von OCR-Fehlinterpretationen (z.B. Punkte statt Doppelpunkte bei Zeitangaben).

---

## v0.4.5 (Performance & UI Polishing)

### ✨ Features & Highlights
- **OCR-Editor Revolution** *(Commit: ca8fafb)*:
  - Verfeinerte Live-Vorschau mit intelligentem Auto-Zoom auf die markierte Region.
  - Panel-Synchronisation: Änderungen im Editor werden sofort in allen betroffenen UI-Panels gespiegelt.
  - "Best Match" Logik im OCR-Dialog für stabilere Markierungen auch bei minimalen Abweichungen.
- **Variable-Panel Stabilität** *(Commit: cad3252)*:
  - Einführung einer **2-Sekunden-Hysterese**: OCR-Werte flackern nicht mehr bei kurzen Erkennungsaussetzern.
  - **Auto-Hide Funktion**: Inaktive Variablen oder leere OCR-Ergebnisse werden optional ausgeblendet für maximale Übersicht.
  - Stabiles Layout: Verhindert den "Spalten-Reflow" (Springen der Tabelle) bei Wertänderungen.

### 🛠 Fixes
- **Daten-Liste & Stabilität**:
  - Fix: `zeit_h/m/s` Projektion basiert nun korrekt ausschließlich auf Formel-Variablen (`1f68e2d`).
  - Layout-Korrekturen in der Daten-Liste für konsistente Darstellung (`ec792aa`).
  - Massive Shutdown-Stabilitäat verbessert (keine hängenden Threads mehr beim Beenden).
- **Engine & UI Sync**:
  - Fix: Gruppen-Bedingungen werden nun ohne Verzögerung an den Subprocess weitergegeben (`e71b5c1`).
  - Template-Panel Icons: Korrekte Unterscheidung der Status-Icons (🚩 für set_states, ⚙ für condition_states).

---

## v0.4.4 (Daten-Listen System & Hierarchie-Upgrade)

### 🚀 Das neue Daten-Listen-System
- **SQLite-Integration**: Einführung der `daten_listen.db` zur dauerhaften Speicherung von Spielwerten.
- **Berechnungs-Engine**:
  - Dynamische Transformationen (z.B. `27,1k` -> `27100`).
  - Formel-Builder für komplexe Berechnungen zwischen verschiedenen OCR-Werten.
  - Zeitprojektion: Automatische Berechnung von `Stunden/Minuten/Sekunden` basierend auf Zeitstempeln.
- **Einheiten-Management**: Globales Wörterbuch (`einheiten.json`) für flexible OCR-Erkennung (Mio, Tsd, B, etc.).
- **UI: Daten-Panel**: Neues Panel mit einklappbaren Kategorien und Live-Update der berechneten Werte.

### 📂 Dateisystem & Hierarchie
- **Kategorie-System**: Explizite Trennung zwischen `State Template` und `Workflow Template`.
- **Intelligentes Umbenennen**: Beim Umbenennen eines Masters werden alle Varianten (`.png`, `__2`, etc.) physisch mit-umbenannt.
- **Hierarchisches Scannen**: Templates in passiven Gruppen werden nun zuverlässig durch die gesamte Ahnenreihe gescannt.
- **Sicherheits-Backup**: Gelöschte Templates wandern mit Zeitstempel in den `_deleted` Quarantäne-Ordner.

### 🎨 UI & Layout
- **4-Spalten-Layout**: Optimierte Platznutzung durch neue linke Workflow-Spalte und einklappbare Panels.
- **Automatisches Fenster-Scaling**: Bot-Fenster passt sich beim Start der Bildschirmhöhe und Bildbreite an.
- **Cursor-Clipping**: Mauszeiger wird beim Markieren von ROIs/OCR-Zonen auf das Canvas eingeschränkt (Präzisions-Boost).

---

## v0.4.3 (Bugfixes & UI-Verbesserungen)

### Fixes
- **🚀 Test-Button repariert**: Fehler in der GPU-Mathematik behoben — Template wird jetzt korrekt erkannt.
- **Test läuft komplett in-memory**: Kein Disk-I/O mehr beim Test. Deutlich schneller.
- **Einstellungen-Dialog wiederhergestellt**: Alle Debug-Optionen und strukturiertes Layout wieder vorhanden.

---

## v0.4.2 (Template Editor Overhaul & Game-State-Management)

### Features & Highlights
- **Game-State-Management**: `condition_states` (AND/OR Verknüpfung) und `set_states` direkt im Editor.
- **Varianten-Navigation**: Pfeiltasten und Master-Schutz für schnelles Bearbeiten von Bild-Varianten.
- **Non-Stop Workflow**: Editor bleibt nach dem Speichern offen.       

---

## v0.4.1 (OCR Context & Expansion)

### Features & Highlights
- **OCR Expansion**: Scannen außerhalb der Bounding-Box ermöglicht.  
- **Live-Kontext**: Echte Spielumgebung im OCR-Dialog sichtbar.        
- **Smart Pipette 2.0**: Einstellbarer Durchmesser für bessere Farbmittelung.

---

## v0.4.0 (Multi-Variant & Precision OCR)

### Features & Highlights
- **Multi-Template Support**: Beliebig viele Bild-Varianten pro Template.
- **OCR Farbfilter**: Pipette zur gezielten Textisolierung verhindert Geisterbilder.

---

## v0.3.0 (GPU & Hierarchie Revolution)

### Features & Highlights
- **PyTorch GPU Matching Engine**: MNCC-Suche auf der Grafikkarte.     
- **Hierarchisches Zwei-Phasen-Matching**: Master/Kind Logik für massive Performance-Steigerung.
- **Snapshot-System**: Testen gegen historische Bilder.

---

## v0.2.0 (Aktueller Stand - Refactored)

### Highlights
- **Vision Engine Upgrade** – EasyOCR Integration.
- **Action Engine via ADB** – Hintergrund-Steuerung.
- **Visueller Einlern-Dialog**.

---

## v0.1.0

### Features
- Live Vorschau MEMUPlayer
- Basis Template Matching
- Erste Workflow Engine
