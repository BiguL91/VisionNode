# Changelog

---

## v0.4.3 (Bugfixes & UI-Verbesserungen)

### Fixes
- **🚀 Test-Button repariert**: Der Test im Scannbereiche-Fenster schlug immer fehl, weil die Hintergrundmaske als `uint8` (0/255) statt `float32` (0.0/1.0) an die NCC-Berechnung übergeben wurde. Fehler in der GPU-Mathematik behoben — Template wird jetzt korrekt erkannt.
- **Test läuft komplett in-memory**: Kein Disk-I/O mehr beim Test. Template wird direkt in den GPU-Speicher geladen, getestet und sofort entfernt. Deutlich schneller.
- **Test-Ergebnis sichtbar**: Status-Bar im Scannbereiche-Fenster zeigt nach dem Test `✓ N Treffer | Bester Score: X.XXX` oder `✗ Kein Treffer`.
- **Einstellungen-Dialog wiederhergestellt**: Fehlende Debug-Checkboxen (`log_variablen`, `log_workflow`, `log_ocr_debug`, `log_matching`, `log_capture`) und strukturiertes Layout (Radio-Buttons für FPS/OCR-Rate/Auflösung) wieder vorhanden.

### UI-Verbesserungen
- **Zustände-Dialog vergrößert**: Mindestgröße 580×520px, frei skalierbar. Größere Schrift, breitere Comboboxen (22 Zeichen), mehr Padding für bessere Lesbarkeit.
- **Scannbereiche-Fenster öffnet immer**: Fenster startet auch ohne Live-Screenshot — zeigt Hinweistext und ermöglicht das Laden von Snapshots.

---

## v0.4.2 (Template Editor Overhaul & Game-State-Management)

### Features & Highlights
- **Umbenennung**: Projekt heißt jetzt **Ai-Bot** (war: TilesBot).
- **Template Editor Tab-Leiste**: OCR (`🔤`) und Zustände (`🚩`) direkt im Editor erreichbar – kein Umweg über die Template-Liste mehr nötig.
- **Game-State-Management im Editor**:
  - `condition_states`: Template nur aktiv wenn bestimmte Zustände zutreffen (AND + OR kombinierbar).
  - `set_states`: Template setzt bei Erkennung automatisch Spielzustände.
  - Logische Verknüpfung direkt im Dialog konfigurierbar: AND (alle müssen zutreffen) und OR (einer reicht).
- **Varianten-Navigation**:
  - Master/Version-Anzeige: `★ Master  1/3` bzw. `V.2  2/3` direkt neben dem Namensfeld.
  - Info-Label zeigt `★ Master-Version von "X" · 3 Variante(n) gesamt` oder `Variante 2 von "X" · 3 gesamt`.
  - Pfeile `◀ ▶` erscheinen **nur wenn Varianten existieren** (automatische Erkennung).
- **Variante löschen**: `🗑`-Button neben den Pfeilen – Master (V.1) ist vor Löschen geschützt.
- **Neue Variante aus bestehendem Namen**: Tippt man einen Namen der bereits existiert, erscheint automatisch der Button `➕ Als neue Variante speichern` → speichert direkt als `name__N`.
- **Non-Stop Workflow**: Speichern-Button schließt den Editor nicht mehr – Schließen über eigenen Button.

### Fixes & Verbesserungen
- Varianten-Liste und Navigation werden nach jedem Speichern/Löschen sofort neu aufgebaut.
- `condition_states` und `set_states` werden korrekt durch den Speichern-Pfad weitergereicht.
- Master-Schutz beim Löschen auch bei direktem Aufruf abgesichert.

---

## v0.4.1 (OCR Context & Expansion)

### Features & Highlights
- **OCR Expansion-Support**: Ermöglicht das Scannen von Bereichen außerhalb der Template-Bounding-Box (z.B. für Level-Badges oder Benachrichtigungszahlen neben Icons).
- **Live-Kontext Vorschau**: Der OCR-Dialog zeigt nun die echte Spielumgebung um das Template herum an (sofern es gerade gefunden wird), um Umgebungsvariablen präzise markieren zu können.
- **Smart Pipette 2.0**: Einstellbarer Pipetten-Durchmesser (1-7px) zur gemittelten Faraufnahme - perfekt für Anti-Aliasing in Spielen.
- **Speicherbarer Zoom**: Der Rand-Wert (Zoom) wird nun pro OCR-Eintrag dauerhaft gespeichert, kein manuelles Nachjustieren mehr nötig.

### Fixes & Verbesserungen
- **UI-Consistency**: Der OCR-Dialog folgt nun dem "Non-Stop" Workflow des Template-Editors (Speichern ohne Schließen).
- **Robuste Bildverarbeitung**: Farbfilter-Logik optimiert; NameError-Abstürze in OCR-Threads behoben.
- **Präzisions-Korrektur**: Fehlerhafte Klick-Umrechnung bei aktivem Rand-Zoom korrigiert.

---

## v0.4.0 (Multi-Variant & Precision OCR)

### Features & Highlights
- **Multi-Template Support**:
  - Unterstützung für beliebig viele Bild-Varianten pro Template (`__2`, `__3`, etc.).
  - Ermöglicht robustere Erkennung bei verschiedenen Lichtverhältnissen oder Layout-Änderungen.
- **OCR Intelligence Revolution**:
  - **Farbfilter & Pipette**: Gezielte Textisolierung durch Auswahl der Schriftfarbe direkt im Bild. Verhindert zuverlässig Geisterbilder aus dem Hintergrund.
  - **Layout-Fallback**: Varianten erben automatisch OCR-Zonen vom Master, sofern keine individuellen Zonen definiert wurden.
- **Workflow-Optimierungen**:
  - **Non-Stop Editor**: Der Template-Editor bleibt nach dem Speichern offen, um Varianten schneller hintereinander bearbeiten zu können.
  - **Varianten-Navigation**: Direkte Steuerung über Pfeiltasten (` < ` ` > `) im Editor inklusive automatischem Laden aller Parameter (ROI, Schwellwert, Klickzone).
- **Architektur-Update**:
  - **Flache Gruppenstruktur**: Alle Varianten liegen nun übersichtlich im gleichen Gruppenordner.
  - **Intelligentes Umbenennen**: Beim Umbenennen einer Gruppe oder eines Masters ziehen alle Varianten automatisch mit um.
  - **API-Erweiterung**: Match-Ergebnisse enthalten nun physikalische Dateinamen für präzise OCR-Zuweisung.

### Fixes & Verbesserungen
- **Sidebar-Übersicht**: Anzeige der Varianten-Anzahl direkt im Namen (z.B. `Email (3)`).
- **Auto-Sync**: Gruppen-Dropdown aktualisiert sich nun sofort nach der Erstellung neuer Master-Templates.
- **Stabilität**: OCR-Werte werden im Bot-Status stabil akkumuliert, um Flackern bei kurzen Erkennungsausfällen zu verhindern.
- Diverse Abstürze durch API-Formatänderungen (unpacking errors) behoben.

---

## v0.3.0 (GPU & Hierarchie Revolution)

### Features & Highlights
- **Hierarchisches Zwei-Phasen-Matching**: 
  - **Master/Kind Logik**: Effiziente Suche nach Rahmen (Master) mit anschließender Inhalts-Klassifizierung (Kind).
  - **Präzisions-Crops**: Automatische Ausschnitte mit Padding für stabile Symbolerkennung.
  - **Performance**: Massive Reduktion der GPU-Operationen durch lokale Suche in Sub-Regionen.
- **Intelligentes Gruppen-Management**:
  - **Master-Migration**: Beim Umbenennen eines Masters zieht die gesamte Gruppe (alle Kinder) automatisch mit um.
  - **Dateisystem-Integration**: Automatische Organisation in Unterordnern basierend auf Gruppen; automatische Bereinigung leerer Ordner.
  - **Pfad-Normalisierung**: Konsistente Pfadbehandlung zur Vermeidung doppelter Gruppen-Header in der UI.
  - **UI-Hierarchie**: Verschmolzene Header für Master-Templates (★ [Gruppe]) für maximale Übersicht.
- **Sicherheits-Quarantäne**: 
  - Beim Löschen eines Master-Templates werden verwaiste Gruppen automatisch in den `_deleted/` Ordner verschoben (verhindert Datenverlust).
- **Vision Engine Professional Tools**:
  - **Snapshot-System**: Erstellen benannter Referenzbilder direkt aus dem Haupt-UI zur Archivierung verschiedener Spielzustände.
  - **Historisches Testen**: Im ROI-Editor können gespeicherte Snapshots geladen werden, um die Erkennungsrate gegen vergangene Zustände zu validieren.
  - **Scannbereiche (ROI)**: Neues Snapshot-Fenster erlaubt das Definieren beliebig vieler Suchregionen pro Template zur Performance-Steigerung und Vermeidung von Falschtreffern.
  - **Individuelle Schwellwerte**: Jedes Template kann nun einen eigenen Match-Score (0.5 - 1.0) besitzen.
  - **GPU-Mathematik-Vorschau**: Echtzeit-Visualisierung der Zero-Mean Normalisierung mit Kontrast-Boost im Editor.
  - **Interaktiver Erkennungs-Test**: Neuer "🚀 Test"-Button prüft Templates sofort gegen Snapshots und visualisiert Scores & Grenzwerte.
  - **Maximale Vorschau-Skalierung**: Automatische Vergrößerung kleiner Icons (z.B. 40x40) für präziseres Arbeiten im Editor.
- **PyTorch GPU Matching Engine**: Kompletter Umstieg auf GPU-beschleunigtes Template Matching (MNCC).
- **CPU-Optimierung & Multi-Threading**
  - **Zero UI-Lag**: Matching läuft in einem komplett separaten OS-Prozess – die UI bleibt bei 60 FPS flüssig.
  - **Minimale Last**: CPU-Last auf ca. 5-10% gesenkt durch konsequentes GPU-Offloading.
- **Windows Graphics Capture (WGC)**: HDR-Support und 60 FPS Hintergrund-Capturing.

### Fixes & Verbesserungen
- **Lösch-Logik Fix**: Gezieltes Löschen von Overlays pro Canvas verhindert Bild-Flimmern oder Verschwinden.
- **OCR-Bereinigung**: OCR-Regionen aus dem Einlern-Dialog entfernt für einen saubereren Workflow.
- **Matching-Stabilität**: Absturz des Subprozesses bei fehlenden Farbfiltern behoben.

---

## v0.2.1 (Bugfix & Performance)

### Features & Optimierungen
- **Maskierte Farberkennung** – Der Farb-Verifikations-Regler (%) bezieht sich jetzt nur noch auf die tatsächlichen Icon-Pixel (via Alpha-Maske), nicht mehr auf das gesamte Rechteck. Dies ermöglicht extrem präzise Filter-Einstellungen (z.B. 90% Farbtreue auf dem Icon).
- **Ladescreen-Performance-Fix** – Ein Limit von 300 Treffern pro Template verhindert Abstürze auf einfarbigen Flächen (Ladescreens), indem nur die qualitativ besten Treffer zur teuren Farbanalyse weitergereicht werden.
- **Intelligente HSV-Toleranzen** – Getrennte Toleranzen für Sättigung und Helligkeit (nach oben/unten) verbessern die Unterscheidung zwischen satten Farben und weißlichen/grauen Fehltreffern.

### Fixes
- Fehlende Konstanten (`MIN_FARB_ANTEIL`, `MIN_OPAKE_PIXEL`) in der Template Engine ergänzt.
- Bildgrenzen-Check in der Farberkennung hinzugefügt (verhindert Abstürze bei Icons am Bildschirmrand).
- Masken-Erstellung beim Laden/Speichern von Alpha=255 auf Alpha>10 gelockert (robuster gegen Aliasing).
- `MATCH_SCHWELLWERT_MASKIERT` von 0.95 auf 0.90 gesenkt (bessere Erkennungsrate bei Kompression).

---

## v0.2.0 (Aktueller Stand - Refactored)

### Highlights
- **Vision Engine Upgrade** – Kompletter Umstieg auf EasyOCR und massive Erweiterung des Template Matchings.
- **Action Engine via ADB** – Klicks, Swipes und Navigation laufen im Hintergrund via ADB (stabilisiertes Koordinatensystem).
- **Visueller Einlern-Dialog** – Zentrale Oberfläche für Templates, OCR-Regionen, Klickzonen und Farb-Verifikation.

### Features & Refactoring
- **OCR Engine (EasyOCR)**
  - Umstieg von Tesseract auf **EasyOCR mit GPU-Unterstützung**.
  - Komplexe Bild-Vorverarbeitung: Upscaling, Kontrast/Helligkeit/Schärfe-Filter, OTSU-Thresholding.
  - **Debug-Modus**: Automatische Speicherung der OCR-Eingabebilder im `/debug` Ordner zur KI-Optimierung (in Einstellungen aktivierbar).
  - Unterstützung für mehrere benannte OCR-Regionen pro Template.
- **Template Engine (Advanced Matching)**
  - **Hintergrund-Filter**: Automatische Hintergrunderkennung (Eckpixel-Schätzung) und Speicherung als Alpha-Kanal.
  - **HSV-Farb-Verifikation**: Nachgeschalteter Farb-Check zur Vermeidung von Falsch-Treffern (inkl. Live-Vorschau mit Snapshots).
  - **Tight Bounding Box**: Automatische Berechnung der minimalen Klick-Zone (Bbox) basierend auf dem sichtbaren Icon-Inhalt.
  - **Kanten-Matching (Canny)**: Automatischer Fallback für Templates mit wenig opaken Pixeln (z.B. nur Linien/Formen).
  - **NMS (Non-Maximum Suppression)**: Verhindert Mehrfach-Erkennungen des gleichen Objekts.
- **Action Engine**
  - **ADB-Integration**: Hintergrund-Steuerung ohne Maus-Hijacking.
  - **Stabile Koordinaten**: Präzise Umrechnung zwischen Canvas-Vorschau, MEMU-Fenster und Android-Koordinatensystem (inkl. Landscape/Portrait-Handling).
- **UI & UX**
  - Neuer Einlern-Dialog mit Live-Check für Hintergrund-Entfernung (Schachbrett-Vorschau).
  - Integrierte Klickzonen-Definition im Template-Speichern-Dialog.
  - Farb-Picker mit Echtzeit-Maskierungs-Vorschau.

### Fixes
- Koordinaten-Offset-Fehler beim Skalieren behoben.
- Falsch-Treffer bei farblich ähnlichen, aber strukturell unterschiedlichen Icons via HSV-Filter eliminiert.
- Flimmern der Live-Vorschau durch Image-Item-Recycling im Canvas behoben.

---

## v0.1.0

### Features
- Live Vorschau MEMUPlayer (60fps)
- Basis Template Matching
- Tesseract OCR Integration
- Erste Workflow Engine (suche, klick, warte)
- Variablen-Panel
