# TODO - Roadmap VisionNode

---

## Priorität 1 (Next)


- [ ] **Mini-Game Engin**
  - In dem Handy game Gibt es mehrer kleine Minispiele. zb. Eine Art Candycrush, eine Art Memory.
  - Die Mini-Game Engin soll ein Neues Panel in der Gui bekommen. Mit einer Liste Der verfügbaren Games.
  - Beim Klicken auf ein Game Soll ein neuer Dialog geöffnet werden.
  - Am anfang wurde ich gerne mit dem Candycrush verschnitt anfangen da ich da bereit die Templates erstellt habe.




- [ ] **Neue Workflow Node**
  - [ ] Swipe
  - [ ] Gruppe Suchen + Klick, Beispiel: Ich habe eine Gruppe Namens "Zurück" in dem Liegen verschieden Templates die ingame bewirken, Die Node soll alle Templates der Gruppe Suchen und sobalt eines von dem Aktiv ist Darauf klicken.
  - [ ] Set Timer Benötigt zusätlich die Möglickeit Die DB Timer zu modifizeiren, genau so wie es Set Wert bereits kann
  - [ ] Smart Node. Wir haben ja Smart Template, diese sind dafür gedacht, um zb. mehrer Angriffskarte gleichzeitig zu Traken. Es werden zb mehrer Karte getrakt und für jede karte werden OCR "lvl","Envernung",etc bereit gestellt. Die neue Node soll in der lage sein Jedes OCR der Smart auszulesen und zu vergleichen
  - [ ] Node Für text eingabe. Damit der Bot zb. in den chat eine nachricht schreiben kann.
  - [ ] Starte Minigame


  - [ ] **Überarbeitung der (FUP) Logik-Liste**
    - Aktuell werden diese ja im Master Editor im Selektor angelegt. Das ist Technisch gesehen auch richtig. Aber GUI seitig nicht Intuitiv
    Vorschlag: da Jeder Master-Flow Sowieso nur einen Selektor haben kann können wir uns die configuration im Master Editor Sparen. Mann sollte direkt in der Logik-Netzwerk liste Prio/Limits und die Workflowzuweisung einstellen können. evtl durch ein Neuen Dialog.
    - Zusätzlich sollen einzelne (FUP´s) Aktiviert und Deaktiviert werden können (Bei Deaktivierten soll verständlicherweiße der Punkt Ignoriert werden)
    - Die bezeichnung zb. *Main* -> soll entfallen. In der Liste sollen nur die Netzwerke gezeigt werden vom Aktiven-Masterflow



- [ ] **Suchfunktion In Workflow/Template/Netzwerke Liste**


- [ ] **Template-Liste Kategorien einklappbar**
  - Aktive und Gruppen Templates sollen einklappbar gemacht werden für mehr Übersicht.



- [ ] **Schnellauswahl über Live Canvas**
  - Um Templates und OCR´s noch schnell zu bearbeiten soll es eine möglichkeit geben Gematchte Teile direkt am Canvas anzuklicken und über ein Kontext Menü "OCR/Template" Bearbeiten (Nur wenn Steuerung =false)






## Priorität 2 (Later)


- [ ] **Hardcodet Lang**
  - durch die Schnelle Entwicklung wurden Beschriftungen und Texte nicht sauber in de.json und en.json eingetragen.


- [ ] **Profil-System**: Erlaubt einfaches Umschalten zwischen verschiedenen Spielen/Accounts.

  
- [ ] **Action-Verifizierung**
  - Visuelle Rückkopplung nach Klicks (prüfen, ob Klick erfolgreich war, sonst Retry).

- [-] **Auto-Tuning Engine**
  - Automatischer Test neuer Templates gegen Snapshots; Schwellwert-Vorschläge & Live-Anpassung. (teilweise implementiert)

- **Vision Engine Evolution**
  - [-] **Auto-Tuning**: Bot schlägt Schwellwerte basierend auf Snapshots und Live Bilder automatisch vor. (teilweise implementiert)