# Bug Tracker

---

## Priorität: Hoch


## Priorität: Mittel


## Priorität: Niedrig


## Hinweise

- Status: 🔍 Offen | 🔧 In Arbeit | ✅ Behoben
- Bei Fix: Commit-Hash + Version angeben

---

## ✅ Behoben

- ✅ **Daten-Listen: 4 Bugs** *(Commit: 26e8b47, c56b7fa)*
  - Neu erstellte Transforms/Berechnungen/Zeilen/Spalten wurden nicht sofort gespeichert → Sofortiges Speichern in DB implementiert
  - Logikfehler im Berechnen-Tab: `elapsed_h` wurde nicht pro Variable berechnet → `zeit_h/m/s` korrekt pro Variable aus Timestamp berechnet
  - Spalten-Tab: keine Zuweisung zu Zeilen möglich → Platzhalter `{row}` in OCR-Variablen für zeilenspezifische Mappings
  - Berechnete Werte ohne Formatierung → Spalten-Formatierung `K/M/B`, `Ganzzahl`, `2 Nachkomma` implementiert

- ✅ **Daten-Listen: Tab-Wechsel erstellt neue Variable statt umzubenennen** *(Commit: c56b7fa)*
  - `_orig_transform_namen` / `_orig_berech_namen` als Referenz für alter_name beim Rename
  - Tab-Wechsel sichert Namen des aktuellen Tabs automatisch vor dem Wechsel
  - DB wird nach Tab-Wechsel neu geladen damit Formel-Builder aktuelle Namen zeigt

- ✅ **Daten-Listen: Umbenennung propagiert nicht in Berechnungs-Formeln** *(Commit: c56b7fa)*
  - `variable_umbenennen()` aktualisiert Formeln und Zuordnungen automatisch bei Rename

- ✅ **Daten-Listen: SQLite CASCADE-Deletes funktionierten nicht** *(Commit: c56b7fa)*
  - `PRAGMA foreign_keys = ON` fehlte in `_verbinden()`

- ✅ **Daten-Listen: Doppelte OCR-Cache-Einträge** *(Commit: c212fd9)*
  - `{p_name}_{entry_name}` Prefix-Key war redundant, wird nicht genutzt → entfernt

- ✅ **Daten-Listen: Mapping-Tab zeigte alle OCR-Variablen** *(Commit: c56b7fa)*
  - Nur noch Transform- und Berechnungs-Outputs werden angezeigt

- ✅ **State Template Umbenennung greift nicht an allen Stellen** *(Commit: 8abe3c5)*

- ✅ **Ignorier-Bereiche GPU-Vorschau nicht synchronisiert** *(Commit: b8ab800)*

- ✅ **Mauszeiger verlässt Vorschau-Fenster beim Markieren** *(Commit: 39a94e9)*

- ✅ **Fenstergröße beim Start** *(Commit: 97b31f8)*
  - Öffnet auf voller Bildschirmhöhe, Breite passt sich ans Bild an, Position wird gespeichert
