# debug/

Quand le backend est lancé avec `DEBUG_SCRAPE=1`, le scraper
(`backend/app/scraper/linkedin.py`) écrit ici le HTML brut de chaque page
LinkedIn visitée (`profile.html`, `contact.html`, `experience.html`, …).
Utile pour ajuster les heuristiques de `parsers.py` si LinkedIn change sa page.

## ⚠️ Contenu sensible

Ces fichiers contiennent des **données personnelles**. Le `.gitignore` exclut
tout le contenu de `/debug/` sauf ce `README.md` et le `.gitkeep`.

Nettoyage :

```powershell
Get-ChildItem debug -Exclude .gitkeep,README.md | Remove-Item -Recurse -Force
```
