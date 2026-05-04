# TODO - Roadmap VisionNode

---

## Priorität 1 (Next)

- [ ] **Neue Workflow Node**
  - [ ] Swipe
  - [ ] Gruppe Suchen + Klick, Beispiel: Ich habe eine Gruppe Namens "Zurück" in dem Liegen verschieden Templates die ingame bewirken, Die Node soll alle Templates der Gruppe Suchen und sobalt eines von dem Aktiv ist Darauf klicken.


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