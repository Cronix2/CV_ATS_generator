# debug/

Ce dossier est utilisé en **runtime** par le scraper LinkedIn
(`lib/linkedin-scraper.ts`) pour écrire des artefacts de diagnostic :

- captures d'écran de la page de login et du profil (`*.png`)
- HTML brut du profil et des sections (`02-profile-FULL.html`, `_sec_*.html`)
- JSON intermédiaires pour chaque étape (`03-personal-info.json`,
  `04-experience-raw.json`, …, `11-final-result.json`)
- logs du serveur Next en mode déploiement local
  (`next-server.out.log`, `next-server.err.log`)

## ⚠️ Contenu sensible

**Tous les fichiers générés ici contiennent des données personnelles**
(nom, prénom, email, téléphone, adresse, expériences, etc.) scrapées depuis
un profil LinkedIn réel.

Pour cette raison, le `.gitignore` à la racine exclut **tout** le contenu de
`/debug/` sauf ce `README.md` et le `.gitkeep`. Ne jamais committer les
fichiers produits par le scraper.

## Nettoyage

Pour supprimer tous les artefacts avant un commit :

```powershell
Get-ChildItem debug -Exclude .gitkeep,README.md | Remove-Item -Recurse -Force
```
