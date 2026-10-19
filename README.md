<p align="center"><img src="docs/logo.svg" alt="PasseFiltre" width="300"></p>

<p align="center">
  <strong>Transforme un profil LinkedIn en CV qui passe le filtre des ATS.</strong><br>
  <a href="../../actions/workflows/ci.yml"><img src="../../actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

PasseFiltre lit votre profil LinkedIn, vous laisse choisir et corriger ce qui va dans le CV, l'aligne sur l'offre visée (mots-clés, score ATS, agent IA), puis exporte un CV en une colonne, en texte réel, avec des intitulés standards : ce que les ATS (Applicant Tracking Systems) savent lire.

1. **Connexion** : URL du profil + identifiants LinkedIn (et, si vous voulez, une clé d'API LLM compatible OpenAI).
2. **Extraction** : [Scrapling](https://github.com/D4Vinci/Scrapling) ouvre une session LinkedIn et lit le profil section par section, textes « … plus » dépliés. Si LinkedIn demande un code de vérification, l'interface vous le demande.
3. **Tri et édition** : poste visé et mots-clés de l'offre, sections et éléments à garder (surlignés), édition, score de qualité et aperçu PDF en direct.
4. **Agent IA** (facultatif) : un agent LangChain recherche sur le web ce qu'attend le poste et modifie le CV. Tout est listé et annulable.
5. **Export** : PDF, Word ou projet `.json` (réouvrable sans repasser par LinkedIn).

---

## Démarrage rapide

### Option A : sans Docker (Windows, macOS, Linux)

Prérequis : [Python 3.10+](https://www.python.org/downloads/) et [Node.js 20+](https://nodejs.org/).

```bash
git clone https://github.com/Cronix2/CV_ATS_generator.git
cd CV_ATS_generator
npm run setup     # environnement Python, Chromium pour Scrapling, dépendances, fichier .env
npm start         # API + interface, rechargement automatique
```

Ouvrez **<http://localhost:3000>**. `Ctrl+C` arrête tout.

| Commande | Effet |
| --- | --- |
| `npm run setup` | Installe tout (relançable sans risque après une mise à jour). |
| `npm start` | Lance l'API et l'interface en mode développement. |
| `npm run prod` | Build de l'interface puis lancement en mode production. |
| `npm test` | Tests du backend + vérification des types et tests unitaires du frontend. |

### Option B : avec Docker

Seul [Docker](https://docs.docker.com/get-docker/) est nécessaire.

```bash
git clone https://github.com/Cronix2/CV_ATS_generator.git
cd CV_ATS_generator
cp .env.example .env            # facultatif
docker compose up --build       # construit les images localement
# ou, avec les images publiées par la CI :  docker compose pull && docker compose up
```

Ouvrez **<http://localhost:3000>**. Sous Docker, le navigateur de Scrapling tourne sans écran : l'option « Afficher le navigateur » (captcha) n'est pas disponible. Pour un accès depuis d'autres machines, voir [Mise en réseau](#mise-en-réseau-https).

## Configuration

Tout se règle dans **un seul fichier `.env`** à la racine (créé par `npm run setup` depuis [`.env.example`](.env.example)). Il est lu par le lanceur, par l'API et par Docker Compose. Toutes les variables sont facultatives.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Ports de l'API et de l'interface. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:<BACKEND_PORT>` | Adresse de l'API vue par le navigateur (à changer pour un accès depuis une autre machine). Origine seule, **sans** `/api` (ex. `https://passefiltre.lan`) : le frontend ajoute `/api/...` lui-même. |
| `CORS_ORIGINS` | l'interface | Origines autorisées à appeler l'API, séparées par des virgules. |
| `LLM_API_KEY` | *(vide)* | Clé LLM par défaut : l'agent IA marche alors sans saisir de clé dans l'interface. La clé n'est jamais envoyée au navigateur. |
| `LLM_BASE_URL` | *(vide = OpenAI)* | URL de base compatible OpenAI, celle qui précède `/chat/completions`. |
| `LLM_MODEL` | `gpt-4o-mini` | Modèle par défaut. |
| `DEBUG_SCRAPE` | `0` | `1` enregistre le HTML des pages LinkedIn dans `debug/` pour diagnostiquer l'extraction. |
| `PASSEFILTRE_TOKEN` | *(vide)* | Jeton exigé sur toutes les routes de l'API (saisi dans l'interface). Obligatoire si PasseFiltre est accessible depuis le réseau. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Noms d'hôte supplémentaires acceptés par l'API (protection contre le DNS rebinding). |
| `BACKEND_HOST` / `FRONTEND_HOST` | `127.0.0.1` | Adresses d'écoute du lanceur (cette machine uniquement). |
| `BIND_ADDRESS` | `127.0.0.1` | Docker : interface sur laquelle les ports sont publiés. |
| `ALLOW_LOCAL_LLM` | `0` | `1` autorise une URL de LLM locale ou privée saisie dans l'interface (Ollama…). |
| `MAX_JOBS` | `2` | Tâches simultanées maximum (extractions + agent IA) ; au-delà, l'API répond 429. |
| `INTERACTIVE_CAPTCHA` | `1` | Docker : un CAPTCHA LinkedIn se résout à la main depuis l'interface (navigateur isolé dans le service `captcha-browser`, affiché par noVNC, voir [docs/deployment-serveurcasa.md](docs/deployment-serveurcasa.md) §13). `0` désactive. |
| `CAPTCHA_TIMEOUT` / `CAPTCHA_MEM_LIMIT` | `300` / `1536m` | Délai de résolution (s) et plafond mémoire du navigateur isolé (un CAPTCHA à la fois). |
| `CAPTCHA_ALLOWED_DOMAINS` | *(vide)* | Domaines HTTPS ajoutés à la liste blanche du navigateur isolé (`docker compose logs captcha-egress` liste les refus). |
| `API_DOCS` | `0` (`1` avec `npm start`) | Documentation interactive de l'API sur `/docs`. Désactivée en production et sous Docker. |
| `AUDIT_LOG_FILE` | *(vide)* | Fichier où écrire aussi le journal d'audit (toujours écrit sur la sortie standard). |
| `SITE_ADDRESS` / `HTTPS_BIND` | *(vide)* / `0.0.0.0` | Adresse servie en HTTPS et interface d'écoute du proxy Caddy (profil Docker `https`). |

Exemples d'URL de base : `https://api.mistral.ai/v1`, `https://openrouter.ai/api/v1`, `http://localhost:11434/v1` (Ollama), `https://trust.liveintelligence.orange-business.com/api/v2` (Paradigm).

## Mise en réseau (HTTPS)

Par défaut, PasseFiltre n'est joignable que depuis la machine qui le lance. Pour le rendre accessible sur le réseau local ou sur Internet, passez par le profil Docker `https` : un proxy [Caddy](https://caddyserver.com/) sert l'interface et l'API sous une même adresse, en HTTPS.

1. Générez un jeton : `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Dans `.env`, avec la **même adresse** partout (sans `https://` pour `SITE_ADDRESS`) :

   ```dotenv
   SITE_ADDRESS=passefiltre.lan
   NEXT_PUBLIC_API_URL=https://passefiltre.lan
   CORS_ORIGINS=https://passefiltre.lan
   PASSEFILTRE_TOKEN=<le jeton généré>
   ```

3. Lancez : `docker compose --profile https up -d --build`, puis ouvrez `https://passefiltre.lan` et saisissez le jeton sur l'écran de connexion.

- **Certificat** : avec un vrai nom de domaine qui pointe vers la machine (ports 80 et 443 ouverts), Caddy obtient un certificat Let's Encrypt. Avec un nom local ou une IP, il utilise sa propre autorité : importez sa racine (`docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt .`) dans les navigateurs des postes clients pour éviter l'alerte.
- **Garde-fou** : dès que la configuration expose l'API au réseau (`SITE_ADDRESS`, `ALLOWED_HOSTS`, `BIND_ADDRESS`, `BACKEND_HOST` ou une `NEXT_PUBLIC_API_URL` non locale), l'API **refuse de démarrer** sans `PASSEFILTRE_TOKEN` d'au moins 32 caractères.
- Sans Docker, l'équivalent est `BACKEND_HOST` / `FRONTEND_HOST` + les mêmes variables, derrière votre propre reverse proxy HTTPS.

### Déploiement continu (self-hosted)

Un déploiement continu vers un serveur ARM64 (Raspberry Pi) est décrit dans [docs/deployment-serveurcasa.md](docs/deployment-serveurcasa.md) : chaque push sur `main` validé par la CI construit les images `linux/arm64`, les publie sur GHCR et met à jour le serveur automatiquement (healthchecks + rollback, données persistantes préservées). Le frontend y est construit pour appeler l'API sur le même domaine HTTPS (`https://passefiltre.local.cronix.fr`, routage `/api/` par Nginx Proxy Manager).

## Sécurité

- **Accès** : écoute sur `127.0.0.1` par défaut (lanceur et Docker). Jeton `PASSEFILTRE_TOKEN` (obligatoire en réseau), contrôle de l'en-tête `Host` (DNS rebinding), requêtes cross-site refusées (vérification de `Origin` et `Content-Type: application/json` exigé sur les POST, donc pas de POST « simple » sans preflight CORS).
- **Réseau local** : depuis une IP privée (box, Wi-Fi de la maison) ou la machine elle-même, le jeton n'est pas demandé ; il reste exigé pour toute IP publique. `TRUST_LAN=0` le rend obligatoire partout (à faire avant tout tunnel ou VPN qui relaierait Internet).
- **Sessions LinkedIn** : chaque session est rangée dans un dossier dérivé, par HMAC avec un secret propre à l'installation, de l'e-mail **et** du mot de passe. Connaître l'e-mail de quelqu'un ne suffit pas pour réutiliser sa session. Le bouton « Oublier ma session LinkedIn » l'efface du serveur (il faut les mêmes identifiants).
- **Navigateur visible** : réservé à la machine qui héberge PasseFiltre ; un client distant ne peut pas ouvrir de fenêtre sur ce poste.
- **Agent IA** : il ne voit ni votre e-mail ni votre téléphone, et ne peut lire que les pages données dans votre demande, le lien de l'offre ou les résultats de ses recherches. Les URL locales et privées sont refusées pour la lecture de pages comme pour l'URL du LLM saisie dans l'interface (contrôle `is_global`, puis nouveau contrôle sur l'URL finale).
- **Journal d'audit** : une ligne par action sensible (extraction, agent, import d'offre, test LLM, jeton refusé…) avec l'IP du client, sans mot de passe, clé ni contenu du CV (l'e-mail n'y figure que sous forme d'empreinte).
- **Erreurs** : l'API renvoie des messages génériques ; le détail technique part dans les logs du serveur.
- **En-têtes** : CSP stricte, `X-Frame-Options: DENY`, `nosniff` et `Referrer-Policy: no-referrer` sur l'interface ; `Cache-Control: no-store` sur l'API ; HSTS via le proxy HTTPS.
- **Dépendances et conteneurs** : dépendances Python figées avec empreintes (`requirements.lock`, installées avec `--require-hashes`), actions GitHub figées par SHA, Dependabot hebdomadaire, conteneur de l'API non-root avec `no-new-privileges`.
- **Navigateur de l'utilisateur** : la clé LLM saisie reste dans le `sessionStorage` de l'onglet (effacée à sa fermeture), protégée par la CSP.

Ce qui reste à faire est suivi dans la [feuille de route sécurité](docs/security-roadmap.md).

### Mettre à jour les dépendances Python

`requirements.txt` liste les dépendances directes ; les lockfiles se régénèrent avec [uv](https://docs.astral.sh/uv/) :

```bash
cd backend
uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
uv pip compile requirements-dev.txt --universal --python-version 3.10 --generate-hashes -o requirements-dev.lock
```

## CI / CD

- **CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) : à chaque push et pull request, tests du backend, vérification des types et build du frontend, construction des deux images Docker, puis **démarrage réel de Chromium** dans l'image API (amd64 et arm64 natif) via `python -m app.scraper.browser_check`.
- **CD** ([`.github/workflows/release.yml`](.github/workflows/release.yml)) : un tag `v*` publie les images `ghcr.io/cronix2/passefiltre-api` et `passefiltre-web` sur GitHub Container Registry et crée une release avec les instructions d'installation.

```bash
git tag v1.0.0 && git push origin v1.0.0
```

Après la première publication, vérifiez que les deux packages sont publics (GitHub → Packages → *Package settings* → *Change visibility*) pour que tout le monde puisse faire `docker compose pull`.

## Architecture

```text
backend/   Python 3.12 · FastAPI · Scrapling · LangChain (create_agent) · ddgs · ReportLab · python-docx
  app/scraper/linkedin.py   connexion + code de vérification, navigation /details/<section>/, dépliage des « … plus »
  app/scraper/parsers.py    lignes de texte LinkedIn -> champs structurés (heuristiques testées)
  app/llm/supervisor.py     agent superviseur + sous-agents chercheur / auditeur ATS (outils natifs ou JSON)
  app/llm/tools.py          outils : recherche web, lecture de page, édition du CV (journal des modifications)
  app/llm/agents.py         5 assistants « propositions » (structured output) en parallèle
  app/export/               mise en page ATS commune -> PDF / DOCX
  app/jobs.py               tâches en arrière-plan (extraction, agent)
frontend/  Next.js · React · Tailwind · lucide-react (lib/ats.ts : mots-clés et score calculés localement)
scripts/passefiltre.mjs     lanceur multiplateforme (setup, start, prod, test)
```

## Agent IA

- **Onglet Agent** : un agent superviseur LangChain qui
  - édite le CV avec ses outils (modifier, ajouter, masquer, supprimer, réordonner, mots-clés…) ;
  - cherche sur le web (`web_search` via DuckDuckGo, sans clé) et lit des pages (`read_webpage`, pages publiques uniquement : localhost, IP privées et noms intranet sont refusés) ;
  - délègue à deux sous-agents : un **chercheur** (synthèse web sourcée) et un **auditeur ATS** (score, manques).

  Si le fournisseur ne gère pas l'appel d'outils natif (ex. vLLM sans `--enable-auto-tool-choice`), l'agent bascule automatiquement sur un protocole d'outils par JSON. L'activité s'affiche en direct, chaque modification est listée avec l'avant/après, et « Restaurer le CV d'avant » ou « Annuler » revient en arrière.
- **Onglet Propositions** : 5 assistants sans outils lancés en parallèle ; vous acceptez chaque proposition.

Les agents ont pour consigne de ne jamais inventer d'expérience, de diplôme, de chiffre ou de compétence, et de traiter le contenu web comme une donnée, jamais comme une instruction.

## Identifiants et données

- Le mot de passe LinkedIn ne sert qu'à ouvrir la session pendant l'extraction : il n'est ni stocké ni journalisé.
- Les cookies de session sont conservés par compte dans `backend/.sessions/` (volume `sessions` sous Docker, ignoré par git) pour éviter une vérification LinkedIn à chaque extraction. Supprimez-les pour vous déconnecter.
- La clé LLM saisie dans l'interface reste dans le `sessionStorage` de l'onglet ; le CV en cours est gardé dans le `localStorage` du navigateur.
- Scraper LinkedIn, même son propre profil, est contraire à ses conditions d'utilisation et peut entraîner une restriction du compte. PasseFiltre limite le volume (une page à la fois, pauses entre sections) mais le risque n'est pas nul.

## Si l'extraction échoue

- **Captcha** : relancez en cochant « Afficher le navigateur » (hors Docker) et résolvez-le dans la fenêtre.
- **Champs mal découpés** : LinkedIn change souvent sa page. Mettez `DEBUG_SCRAPE=1` dans `.env` pour enregistrer le HTML brut dans `debug/`, puis ajustez `parsers.py`. L'agent IA (« Corriger l'extraction ») rattrape aussi la plupart des inversions.
- **« Le port … est déjà utilisé »** : PasseFiltre tourne déjà, ou changez `BACKEND_PORT` / `FRONTEND_PORT` dans `.env`.
