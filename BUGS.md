# Bug Tracker

---



## Priorität: Extrem Extrem -> Hoch


- **ROI** (✅ Behoben)
  - Templates die ihre ROI vom Elternteil Erben, wird im ROI-Editor teilweiße ignoriert.
  - **Fix:** Editor nutzt nun `_get_effective_regions` der TemplateEngine (hierarchische Suche), anstatt nur lokale Settings zu prüfen.
  - **Score-Explosion (3500+):**
  - **Fix:** Korrektur der Elementanzahl `N` in `template_matcher.py`. Bei unmaskierten Templates wurde `N` fälschlicherweise durch 3 geteilt, was zu negativer Varianz und Division durch fast Null führte.
  - Commit: `Fix NCC Math & ROI Inheritance` | Version: v1.5.2 (Unreleased)


## Priorität: Mittel





## Priorität: Niedrig


## Hinweise

- Status: 🔍 Offen | 🔧 In Arbeit | ✅ Behoben
- Bei Fix: Commit-Hash + Version angeben

---

