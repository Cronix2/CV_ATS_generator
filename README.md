# CV ATS Generator

Transforme un profil LinkedIn en CV lisible par les ATS (Applicant Tracking Systems).

1. **Connexion** : URL du profil + identifiants LinkedIn valides (et, si vous voulez, une clé d'API LLM compatible OpenAI).
2. **Extraction** : le backend ouvre une session LinkedIn avec [Scrapling](https://github.com/D4Vinci/Scrapling) et lit le profil section par section. Si LinkedIn demande un code de vérification, l'interface vous le demande.
3. **Tri et édition** : vous gardez/retirez chaque section et chaque élément, vous modifiez, ajoutez, réordonnez. L'aperçu PDF se met à jour en direct.
4. **Amélioration IA** (facultatif) : des sous-agents LangChain proposent un résumé, des descriptions reformulées, une liste de compétences normalisée, des corrections d'extraction et un audit ATS. Vous acceptez ou refusez chaque proposition.
5. **Export** : PDF, Word (.docx) ou projet .json (réouvrable sans repasser par LinkedIn).

## Architecture

```
backend/   Python 3.12 · FastAPI · Scrapling (StealthySession) · LangChain (create_agent) · ddgs · ReportLab · python-docx
  app/scraper/linkedin.py   connexion, gestion du checkpoint 2FA, navigation /details/<section>/
  app/scraper/parsers.py    lignes de texte LinkedIn -> champs structurés (heuristiques testées)
  app/llm/supervisor.py     agent superviseur + sous-agents chercheur / auditeur ATS
  app/llm/tools.py          outils : recherche web, lecture de page, édition du CV (journal des modifications)
  app/llm/agents.py         5 assistants « propositions » (structured output) en parallèle
  app/export/               mise en page ATS commune -> PDF / DOCX
  app/jobs.py               tâches de scraping en arrière-plan (+ attente du code de vérification)
frontend/  Next.js · React · Tailwind · lucide-react (lib/ats.ts : mots-clés et score calculés localement)
```

Le scraping se fait en Python car Scrapling et LangChain sont des bibliothèques Python ; le frontend appelle l'API sur `http://localhost:8000` (modifiable avec `NEXT_PUBLIC_API_URL`).

## Installation

Prérequis : Python 3.10+ et Node.js 20+.

```powershell
# Backend
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\scrapling install      # télécharge le navigateur utilisé par Scrapling

# Frontend
cd ..\frontend
npm install
```

## Lancement

```powershell
.\scripts\dev.ps1
```

ou dans deux terminaux :

```powershell
cd backend;  .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev
```

Puis ouvrez [http://localhost:3000](http://localhost:3000). La documentation de l'API est sur [http://localhost:8000/docs](http://localhost:8000/docs).

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pip install pytest
.\.venv\Scripts\python -m pytest
```

## Identifiants et données

- Le mot de passe LinkedIn ne sert qu'à ouvrir la session pendant l'extraction : il n'est ni stocké ni journalisé.
- Les cookies de session sont conservés par compte dans `backend/.sessions/` (ignoré par git) pour éviter une reconnexion — et donc une vérification LinkedIn — à chaque extraction. Supprimez ce dossier pour vous déconnecter.
- La clé d'API LLM reste dans le `sessionStorage` de l'onglet ; le CV en cours est gardé dans le `localStorage` du navigateur.
- Scraper LinkedIn, même son propre profil, est contraire à ses conditions d'utilisation et peut entraîner une restriction du compte. L'outil limite le volume (une page à la fois, pauses entre sections) mais le risque n'est pas nul.

## Si l'extraction échoue

- **Captcha** : relancez en cochant « Afficher le navigateur » et résolvez-le dans la fenêtre.
- **Champs mal découpés** : LinkedIn change souvent sa page. Lancez le backend avec `DEBUG_SCRAPE=1` pour enregistrer le HTML brut dans `debug/`, puis ajustez `parsers.py`. L'agent IA « Correction de l'extraction » corrige aussi la plupart des inversions.

## Poste visé et score ATS

Dans « Tri et édition », la carte **Poste visé** reçoit l'intitulé, l'entreprise et le texte de l'offre (collé, ou importé depuis un lien public). Les mots-clés de l'offre sont extraits automatiquement (modifiables) et comparés en direct au contenu du CV : vert = présent, rouge = absent. Le panneau **Qualité du CV**, au-dessus de l'aperçu, donne un score et la liste de ce qui manque.

## Agent IA

Toute API compatible OpenAI fonctionne : choisissez un fournisseur (OpenAI, Paradigm, Mistral, OpenRouter, Ollama) ou saisissez l'URL de base, celle qui précède `/chat/completions`.

- **Onglet Agent** (`app/llm/supervisor.py`) : un agent superviseur LangChain (`create_agent`) qui dispose
  - d'outils d'édition du CV (modifier, ajouter, masquer, supprimer, réordonner, mots-clés…) : **il modifie directement les données** ;
  - de `web_search` (DuckDuckGo, sans clé) et `read_webpage` (pages web publiques uniquement : localhost, IP privées et noms intranet sont refusés) ;
  - de deux sous-agents : un **chercheur** (recherche web + synthèse sourcée) et un **auditeur ATS** (score, manques).

  L'activité s'affiche en direct, chaque modification est listée avec l'avant/après, et le bouton « Restaurer le CV d'avant » ou « Annuler » (en haut) revient en arrière. Nécessite un modèle qui gère l'appel d'outils.
- **Onglet Propositions** (`app/llm/agents.py`) : 5 assistants sans outils, lancés en parallèle ; vous acceptez chaque proposition. Fonctionne avec tous les modèles.

Les agents ont pour consigne de ne jamais inventer d'expérience, de diplôme, de chiffre ou de compétence, et de traiter le contenu web comme une donnée, jamais comme une instruction.

## Export

PDF (aperçu en direct), Word ou projet `.json`. La couleur du nom et des titres de sections est réglable ; le texte reste noir, sans effet sur la lecture par les ATS.
