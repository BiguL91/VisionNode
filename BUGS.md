# Bug Tracker

---

## Priorität: Hoch

- ✅ ** 4 Probleme Im Daten-Listen **

  - ✅ 1.  Ich habe das gefühl das manche neu erstellen Transforms/Berchnungen/Zeilen/Spalten nicht sofort bei erstellen oder änderungen gespeichert werden. (Sofortiges Speichern in DB implementiert)
  - ✅ 2. Eine Logik Fehler im "Berchen" Tab, Ich hab den Produktions wert vom spiel runtergerchnet auf die intervall vom Aktualliseren. Diesen wert Addire ich zu dem Ausgelesenen Wert Holz-Prod. Problem ist er kann die berchnung so offt ausführen wie er will, da der Holz-Prod wert sich ja nicht ändert. (Variable 'elapsed_h' wird nun korrekt pro Variable berechnet, erlaubt Simulation basierend auf Zeit seit letztem Scan)
  - ✅ 3. Im Spalten Tab müssen wir zuweißen können welche Spalte zur welcher zeile gehört (Platzhalter '{row}' in OCR-Variablen erlaubt nun zeilenspezifische Mappings)
  - ✅ 4. Die Ausgabe von den Berchnen werten kann sehr groß sein... Idee: Neuer Tab "UI Ausgabe"... (Spalten-Formatierung 'K/M/B', 'Ganzzahl', '2 Nachkomma' implementiert)


- ✅ State Template Umbennung, greift nicht an allen Stellen, (State Variablen)

- ✅ Ignorie-Bereiche im Template-Editor werden nicht korekt mit dem GPU-Vorschau Syncroniesiert, Vermutung: Da die GPU Vorschau Zugeschnitten wird fehlt dieser Factor. (Betrifft nur die Anzeige, Auschnitt Größe,Position passt)

- ✅ Alle Möglichkeite wo man was Markieren / Einrahmen kann soll der Mauszeiger das Vorschau Fenster nicht Verlassen. (Template-Editor -> Livevorschau, Templateeditor -> Ausschnittvorschau,GPUvorschau, Templateeditor -> Scannbereiche) 


## Priorität: Mittel

- ✅ Beim öffnen soll sich das Programm gleich in der größe öffnen, das 
  1. Das Programm die Max Display höche verwenden. 
  2. Der Live Bereich automatisch so Breit ist wie das gecapturte bild.  
  3. evtl. kann mann das Programm so machen, dass es sich den letzen Skallierung und Position am desktop Merkt und abspeichert. 
## Priorität: Niedrig



## Hinweise

- Status: 🔍 Offen | 🔧 In Arbeit | ✅ Behoben
- Bei Fix: Commit-Hash + Version angeben

---

## ✅ Behoben


