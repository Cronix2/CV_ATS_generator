# Déploiement continu sur ServeurCasa (Raspberry Pi 5, arm64)

Ce document décrit le déploiement continu de **PasseFiltre** sur le serveur
`serveurcasa` (Raspberry Pi 5, `linux/arm64`, IP locale `192.168.1.63`).

## 1. Architecture CI/CD

```
push sur main
      │
      ▼
┌──────────────┐   succès    ┌──────────────────────────────────────────────┐
│   CI (ci.yml)│────────────▶│  Deploy to ServeurCasa (deploy-serveurcasa.yml)│
│  tests + build│            │                                                │
└──────────────┘             │  job build  (GitHub-hosted, ubuntu-latest)     │
                             │    buildx + QEMU → images linux/arm64          │
                             │    push GHCR : passefiltre-api / -web          │
                             │    tag immuable  sha-<commit>  (+ main)        │
                             │                                                │
                             │  job deploy (self-hosted, arm64, serveurcasa)  │
                             │    pull des images + up -d + healthcheck       │
                             │    rollback automatique si échec               │
                             └──────────────────────────────────────────────┘
```

- Le déploiement est déclenché par `workflow_run` **après** la CI, et **seulement
  si la CI a réussi**. Une Pull Request ne déclenche jamais de déploiement
  (garde `event == 'push'` et `head_branch == 'main'`).
- La compilation des images se fait **sur GitHub**, jamais sur le Raspberry Pi.
- Le Pi ne fait que *télécharger* des images `arm64` déjà construites et
  redémarrer les conteneurs du projet `passefiltre`.
- Avant le déploiement, Chromium est **réellement démarré** dans l'image API
  sur un runner GitHub ARM64 natif (job `smoke`), puis sur le Pi avant
  `compose up` (voir §12).

### Fichiers concernés

| Fichier | Rôle |
| --- | --- |
| `.github/workflows/ci.yml` | CI existante (inchangée) : tests + build. |
| `.github/workflows/release.yml` | Release GHCR sur tag `v*` (inchangée). |
| `.github/workflows/deploy-serveurcasa.yml` | **Nouveau** : build arm64 + déploiement. |
| `docker-compose.yml` | Base (inchangé) : ports, volumes, sécurité, env_file. |
| `docker-compose.server.yml` | **Nouveau** : images GHCR épinglées, pas de build, projet `passefiltre`. |

## 2. Prérequis

### Sur ServeurCasa (déjà en place)

- Runner self-hosted dédié au dépôt, labels `self-hosted`, `Linux`, `ARM64`,
  service `actions.runner.Cronix2-CV_ATS_generator.serveurcasa.service`, accès
  Docker via le groupe `docker`.
- **Label dédié `passefiltre`** à ajouter au runner. Le job de déploiement cible
  `runs-on: [self-hosted, Linux, ARM64, passefiltre]` pour ne jamais être
  exécuté par un autre runner ARM64 (autre projet). Ajout du label (à faire une
  fois sur le serveur, dans le dossier du runner) :

  ```bash
  # runner en service : reconfigurer les labels
  sudo ./svc.sh stop
  ./config.sh --labels passefiltre          # ajoute le label au runner existant
  sudo ./svc.sh start
  # vérifier ensuite dans Settings → Actions → Runners que « passefiltre » est présent
  ```

- Docker Engine + plugin `docker compose` **≥ 2.24.4** (nécessaire pour le tag
  YAML `!reset` utilisé par `docker-compose.server.yml`).
- `flock` (paquet `util-linux`, présent par défaut) : sérialise les
  déploiements concurrents côté serveur.
- Répertoire `/opt/passefiltre/` appartenant à `cronix`.
- `/opt/passefiltre/.env` (permissions `600`, appartenant à `cronix`) contenant
  au minimum :

  ```dotenv
  BACKEND_PORT=8100
  FRONTEND_PORT=3101
  BIND_ADDRESS=192.168.1.63
  NEXT_PUBLIC_API_URL=https://passefiltre.local.cronix.fr
  CORS_ORIGINS=https://passefiltre.local.cronix.fr,http://192.168.1.63:3101
  ALLOWED_HOSTS=passefiltre.local.cronix.fr,192.168.1.63
  PASSEFILTRE_TOKEN=<jeton secret ≥ 32 caractères>
  ```

  `CORS_ORIGINS` et `ALLOWED_HOSTS` doivent contenir le domaine HTTPS (voir
  §2bis). `http://192.168.1.63:3101` et `192.168.1.63` ne servent qu'à garder
  l'accès direct par IP (healthchecks du workflow, dépannage) : les retirer si
  cet accès n'est plus voulu — le healthcheck du workflow, qui appelle
  `http://192.168.1.63:8100/api/health`, a besoin de `192.168.1.63` dans
  `ALLOWED_HOSTS`. Côté serveur, `NEXT_PUBLIC_API_URL` ne sert qu'à la liste
  des hôtes autorisés : l'URL réellement utilisée par le navigateur est celle
  figée dans l'image `web` par le workflow.

  Ce fichier **n'est jamais** modifié, affiché ni copié par le workflow : il est
  seulement vérifié présent (`test -f`).

### Sur GitHub (à configurer une fois)

- Rien d'obligatoire : le workflow utilise `GITHUB_TOKEN` (aucun secret à créer).
- Variable de dépôt **facultative** `SERVEURCASA_API_URL` pour surcharger
  l'URL de l'API intégrée au build du frontend (défaut :
  `https://passefiltre.local.cronix.fr`). Elle doit être une **origine HTTPS
  seule** (`https://hôte[:port]`, sans chemin, sans `/api`, sans `/` final) :
  le job `build` échoue sinon (étape *Validate frontend API URL*).

> **Important — construction du frontend.** `NEXT_PUBLIC_API_URL` est **figé au
> moment du build** Next.js (voir `frontend/Dockerfile`). Le job `build`
> construit donc l'image `web` avec
> `NEXT_PUBLIC_API_URL=https://passefiltre.local.cronix.fr` pour que le
> navigateur appelle l'API **sur le même domaine HTTPS** que l'interface
> (§2bis). Changer de domaine impose de **reconstruire** l'image `web` (un
> nouveau push sur `main` suffit).

## 2bis. Accès HTTPS via Nginx Proxy Manager (même origine)

L'interface est servie sur <https://passefiltre.local.cronix.fr> par Nginx Proxy
Manager (NPM, existant, hors de ce dépôt), qui route :

| Chemin | Cible | Service |
| --- | --- | --- |
| `/` | `http://192.168.1.63:3101` | `web` (Next.js) |
| `/api/` | `http://192.168.1.63:8100` | `api` (FastAPI) |

Le frontend appelle l'API à `NEXT_PUBLIC_API_URL` + `/api/...` (toutes les
routes de `frontend/lib/api.ts` commencent déjà par `/api/`). Avec
`NEXT_PUBLIC_API_URL=https://passefiltre.local.cronix.fr`, le navigateur appelle
donc `https://passefiltre.local.cronix.fr/api/...` : **même origine**, pas de
contenu mixte HTTP/HTTPS, CSP `connect-src` satisfaite.

**Éviter `/api/api/`** :

- `NEXT_PUBLIC_API_URL` est une **origine**, jamais `…/api`. Par sécurité,
  `frontend/lib/apiBase.ts` retire un `/api` ou un `/` final, et le workflow
  refuse toute valeur avec un chemin.
- Dans NPM, la *Custom location* `/api/` doit transmettre le chemin **tel
  quel** à `http://192.168.1.63:8100` (aucune réécriture, pas de chemin
  ajouté après le port) : l'API attend `/api/health`, `/api/scrape`, etc.

**CORS et hôtes autorisés** (à régler dans `/opt/passefiltre/.env`, voir §2) :

- Même en même origine, le navigateur envoie `Origin:
  https://passefiltre.local.cronix.fr` sur les `POST`. L'API refuse (`403`)
  toute origine absente de `CORS_ORIGINS` : le domaine HTTPS **doit** y figurer,
  sinon le scraping, l'IA et l'export échouent alors que `/api/health` (GET)
  répond.
- NPM transmet l'en-tête `Host: passefiltre.local.cronix.fr` : il doit être
  dans `ALLOWED_HOSTS` (ou déduit de `NEXT_PUBLIC_API_URL`), sinon `400`.
- Après modification du `.env`, recréer le conteneur API (l'environnement est
  lu au démarrage) : `pf up -d api` (voir §6), ou attendre le prochain
  déploiement.

**Autres environnements** : inchangés. En développement (`npm start`,
`npm run dev`) et avec `docker-compose.yml` seul, l'URL par défaut reste
`http://localhost:<BACKEND_PORT>` (origines différentes : `localhost:3000`
est dans `CORS_ORIGINS` par défaut). Les images de release (`release.yml`)
ne sont pas concernées.

Vérification après déploiement :

```bash
curl -fsS https://passefiltre.local.cronix.fr/api/health
# Dans le navigateur (outils de développement → Réseau) : les requêtes partent vers
# https://passefiltre.local.cronix.fr/api/... (jamais 192.168.1.63:8100 ni /api/api/).
```

## 3. Déclenchement automatique

Après la **fusion de la Pull Request**, chaque `push` sur `main` qui fait passer
la CI déclenche automatiquement :

1. le build des images `arm64` et leur publication sur GHCR sous le tag
   `sha-<commit>` ;
2. le déploiement sur ServeurCasa (pull + `up -d` + healthchecks).

> `workflow_run` n'est actif qu'une fois le fichier de workflow présent **sur la
> branche par défaut**. Le tout premier déploiement automatique a donc lieu au
> premier push sur `main` *après* la fusion de cette PR.

## 4. Premier déploiement

1. Fusionner la PR `feat/cd-serveurcasa-arm64` dans `main`.
2. Vérifier `/opt/passefiltre/.env` (voir §2).
3. Faire un petit commit sur `main` (ou relancer la CI) pour déclencher le
   workflow.
4. Suivre l'exécution dans **Actions → Deploy to ServeurCasa**.
5. Au succès : <https://passefiltre.local.cronix.fr> (frontend) et
   <https://passefiltre.local.cronix.fr/api/health> (API). Les healthchecks
   du workflow, eux, interrogent directement `192.168.1.63:8100` / `:3101`.

Le premier build `arm64` sous QEMU est lent (installation de Chromium /
Playwright émulée). Les builds suivants réutilisent le cache GitHub Actions.

## 5. Mise à jour automatique

Rien à faire : un `push` sur `main` qui passe la CI met à jour PasseFiltre.
Le workflow :

- vérifie **deux fois** que le commit est toujours la tête de `main` : une fois
  au début, puis **juste avant** de toucher aux conteneurs (après le build et le
  pull des images). Si `main` a avancé entre-temps, il s'arrête **sans modifier
  les conteneurs** : le déploiement plus récent prend le relais ;
- sérialise les déploiements concurrents via un verrou serveur (`flock`), en
  plus du groupe `concurrency` GitHub Actions ;
- met à jour **uniquement** le projet Compose `passefiltre` (`-p passefiltre`) :
  les autres piles Docker du serveur ne sont jamais touchées ;
- conserve le volume nommé `passefiltre_sessions` (sessions LinkedIn).

## 6. Vérification et diagnostic

Toutes les commandes se lancent depuis `/opt/passefiltre` en tant que `cronix`.
Un alias pratique (le `--env-file deploy.env` fournit le tag d'image courant) :

```bash
cd /opt/passefiltre
pf() { docker compose -p passefiltre -f docker-compose.yml -f docker-compose.server.yml \
       --env-file .env --env-file deploy.env "$@"; }
```

| Besoin | Commande |
| --- | --- |
| État des conteneurs | `pf ps` |
| Logs API en direct | `pf logs -f api` |
| Logs frontend | `pf logs -f web` |
| Version déployée (tag) | `cat deploy.env` |
| Dernière version saine | `cat deploy.env.last-good` |
| Santé de l'API | `curl -fsS http://192.168.1.63:8100/api/health` |
| Santé via NPM (HTTPS) | `curl -fsS https://passefiltre.local.cronix.fr/api/health` |
| Config fusionnée (sans secret) | `pf config -q && echo OK` |
| Logs du runner | `journalctl -u actions.runner.Cronix2-CV_ATS_generator.serveurcasa.service -f` |

## 7. Rollback

### Automatique

**Échec avant `compose up`** (copie des fichiers Compose, `pull`, `config`,
HEAD de `main` introuvable ou réponse invalide) : les conteneurs en cours
d'exécution ne sont **pas touchés**, aucun rollback n'est lancé, `deploy.env`
est restauré tel qu'il était avant le déploiement et le job **échoue**. Si
`main` a simplement avancé, le job s'arrête proprement (succès) avec la même
restauration.

**Échec à partir de `compose up`** (`up -d`, healthcheck API **ou** frontend),
le job :

1. restaure le **dernier déploiement ayant passé TOUS les healthchecks**,
   enregistré dans `deploy.env.last-good` (jamais une simple tentative
   précédente) ;
2. relance les conteneurs puis revérifie **l'API ET le frontend** avant de
   déclarer le rollback réussi (aucune erreur n'est masquée) ;
3. **échoue explicitement** le job pour signaler le problème.

Le fichier `deploy.env.last-good` n'est mis à jour qu'après un déploiement
entièrement sain : c'est la cible de rollback garantie fonctionnelle. Les
fichiers de suivi (`deploy.env`, `deploy.env.last-good`) sont écrits de façon
atomique (fichier temporaire + renommage) puis relus. Si `deploy.env.last-good`
ne peut pas être enregistré, le job **échoue** : la nouvelle version tourne mais
n'est **pas** considérée comme validée (l'ancienne référence reste intacte).
Corriger le problème (droits, espace disque) puis relancer le workflow. Un
`deploy.env.last-good` illisible ou au contenu inattendu bloque le rollback
automatique avec une erreur explicite. Le volume des sessions LinkedIn n'est
jamais supprimé.

### Manuel

```bash
cd /opt/passefiltre
cat deploy.env            # tag actuellement visé
cat deploy.env.last-good  # dernière version 100 % saine

# Revenir à la dernière version saine :
cp -f deploy.env.last-good deploy.env
pf pull
pf up -d

# Ou fixer explicitement un tag connu :
printf 'PASSEFILTRE_IMAGE_TAG=sha-<commit>\n' > deploy.env
pf pull && pf up -d
```

Les images restent dans le cache local de Docker : un rollback n'exige pas de
réseau si l'image visée a déjà été téléchargée.

## 7bis. Tag basé sur un SHA vs digest réellement immuable

Le déploiement épingle les images par un tag `sha-<commit>` (le SHA Git du
commit validé par la CI). Ce tag est **traçable et stable par convention**, mais
ce n'est **pas** une référence cryptographiquement immuable :

- Un **tag** (`…:sha-<commit>`, `…:main`, `…:latest`) est un simple *pointeur*
  mutable. Rien n'empêche techniquement de re-pousser le même tag vers un autre
  contenu d'image (écrasement). Il garantit *d'où vient* l'image (quel commit),
  pas que son *contenu* est figé.
- Un **digest OCI** (`…@sha256:<hash>`) est l'empreinte du contenu de l'image.
  Il est **immuable par construction** : le même digest renvoie toujours
  exactement les mêmes octets, impossible à ré-associer à un autre contenu.

**Cette première version utilise uniquement des tags `sha-<commit>`** (choix de
simplicité). `PASSEFILTRE_IMAGE_TAG` ne contient donc qu'un tag : la référence
`image: …:${PASSEFILTRE_IMAGE_TAG}` n'accepte pas une valeur `@sha256:…`
directement (la forme serait `image: …@sha256:…`, incompatible avec `:${VAR}`).
Un pinning par digest demanderait de changer la forme de la référence d'image
dans `docker-compose.server.yml` : ce n'est pas fait ici.

En attendant, le digest réellement publié reste **vérifiable manuellement** pour
tracer précisément ce qui tourne :

```bash
# digest de l'image arm64 publiée pour un commit donné
docker buildx imagetools inspect ghcr.io/cronix2/passefiltre-api:sha-<commit> \
  --format '{{json .Manifest.Digest}}'
```

> Durcissement optionnel côté GHCR : activer les **tags immuables** sur
> l'organisation/dépôt empêche l'écrasement d'un tag existant, ce qui rapproche
> la garantie d'un tag `sha-<commit>` de celle d'un digest.

## 8. Comportement après un redémarrage du Raspberry Pi

Les services ont `restart: unless-stopped` (hérité de `docker-compose.yml`).
Après un reboot, Docker relance automatiquement les conteneurs `passefiltre`
avec leur dernière image, **sans** `docker compose` ni accès réseau : aucun
`PASSEFILTRE_IMAGE_TAG` n'est requis pour le redémarrage (il ne sert qu'aux
commandes `compose`).

## 9. Dépannage

### GHCR (packages privés / permissions du `GITHUB_TOKEN`)

Si les images sont **privées** et que le pull échoue sur le runner
(`denied` / `unauthorized`) :

- Vérifier que le dépôt a accès aux packages (Settings → Actions → *Workflow
  permissions* ; les packages `passefiltre-api` / `passefiltre-web` doivent être
  liés au dépôt `Cronix2/CV_ATS_generator`).
- Dans la page du package GHCR → *Package settings* → **Manage Actions access**,
  donner au dépôt le rôle *Read* (ou *Write*).
- En dernier recours, créer un PAT `read:packages` et l'utiliser pour
  `docker login ghcr.io` manuellement sur le serveur :

  ```bash
  echo "$CR_PAT" | docker login ghcr.io -u <user> --password-stdin
  ```

  (le workflow, lui, utilise `GITHUB_TOKEN` et se déconnecte en fin de job).

### Runner

- Statut : `systemctl status actions.runner.Cronix2-CV_ATS_generator.serveurcasa.service`
- Labels attendus : `self-hosted`, `Linux`, `ARM64`, **`passefiltre`** (le job
  cible `runs-on: [self-hosted, Linux, ARM64, passefiltre]`). Si le job reste
  *Queued* indéfiniment, c'est généralement que le label `passefiltre` manque sur
  le runner (voir §2 pour l'ajouter).
- Accès Docker : `docker ps` doit fonctionner en tant que `cronix` (groupe
  `docker`).

### ARM64

- Si le build échoue côté GitHub, vérifier que `docker/setup-qemu-action` s'est
  bien exécuté (émulation `arm64`).
- Sur le Pi, `docker image inspect ghcr.io/cronix2/passefiltre-api:sha-<commit>
  --format '{{.Architecture}}'` doit renvoyer `arm64`.

### `Executable doesn't exist at /ms-playwright/chromium-XXXX/...`

Le Chromium attendu par Patchright n'est pas dans l'image : voir §12. Ne
**pas** installer de navigateur à la main sur le serveur ; corriger le
`Dockerfile` et laisser la CI reconstruire l'image. Diagnostic sans rien
modifier :

```bash
pf run --rm --no-deps -T api python -m app.scraper.browser_check
```

### `!reset` non reconnu

Erreur du type *"unknown tag !reset"* → la version de Docker Compose est
antérieure à 2.24.4. Mettre à jour le plugin Compose.

## 10. Limitations de sécurité (HTTP sur le LAN)

- **Chiffrement partiel.** Via <https://passefiltre.local.cronix.fr>, le trajet
  navigateur → NPM est chiffré ; le trajet NPM → `192.168.1.63:3101`/`:8100`
  reste en **HTTP clair**, comme l'accès direct par IP. Les identifiants
  LinkedIn et le `PASSEFILTRE_TOKEN` peuvent donc encore transiter en clair
  sur le réseau local (sauf si NPM tourne sur le Pi lui-même) : à n'utiliser
  que sur un réseau de confiance, et privilégier l'URL HTTPS.
- **Le bind sur une IP privée n'est pas un pare-feu.** Publier les ports sur
  `192.168.1.63` limite l'interface d'écoute mais ne filtre pas les hôtes du
  LAN. Pour restreindre réellement l'accès, ajouter des règles de pare-feu sur
  le Pi, par exemple :

  ```bash
  # n'autoriser que le sous-réseau local vers les ports PasseFiltre
  sudo ufw allow from 192.168.1.0/24 to any port 3101 proto tcp
  sudo ufw allow from 192.168.1.0/24 to any port 8100 proto tcp
  ```

- **Aucune exposition Internet par ce workflow.** Pas de Cloudflare Tunnel, pas
  de proxy Caddy, pas d'ouverture des ports 80/443 : le HTTPS est fourni par le
  Nginx Proxy Manager existant, que le workflow ne configure ni ne redémarre.
- Le `PASSEFILTRE_TOKEN` reste **obligatoire** : l'API refuse de démarrer sans
  un jeton ≥ 32 caractères dès qu'elle est exposée au réseau (`BIND_ADDRESS`
  non-loopback).

## 11. Garanties d'isolation

Le workflow de déploiement **ne touche jamais** aux autres services du serveur :

- `-p passefiltre` cantonne toutes les commandes au projet `passefiltre`.
- Aucun `docker system prune`, `docker volume prune`, ni `compose down -v`.
- Les volumes persistants (`passefiltre_sessions`) ne sont jamais supprimés.

## 12. Navigateur Chromium du scraping (Patchright)

### Symptôme

Frontend et API opérationnels, `/api/health` en 200, mais le scraping LinkedIn
échouait au démarrage du navigateur :

```
BrowserType.launch_persistent_context: Executable doesn't exist at
/ms-playwright/chromium-1243/chrome-linux-arm64/chrome
```

alors que `/ms-playwright` contenait `chromium-1248`.

### Cause

- Scrapling 0.4.15 dépend **à la fois** de `playwright` et de `patchright`
  (`playwright>=1.62.0`, `patchright>=1.62.1`, non alignés entre eux). Le lock
  a résolu `playwright==1.64.0` et `patchright==1.63.0`.
- Chaque bibliothèque embarque son propre pilote et sa propre révision de
  Chromium (`driver/package/browsers.json`) : **Playwright 1.64.0 → 1248**,
  **Patchright 1.63.0 → 1243**. Les deux lisent le même
  `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`.
- `StealthySession` (le scraper LinkedIn) lance Chromium via **Patchright**
  (`scrapling/engines/_browsers/_stealth.py` : `from patchright.sync_api import
  sync_playwright`). Playwright n'y sert qu'aux types Python.
- Le `Dockerfile` installait le navigateur avec `python -m playwright install`
  (comme la commande `scrapling install`), donc la révision 1248 de
  Playwright, jamais la 1243 attendue par Patchright. Le problème n'est pas
  propre à ARM64 : les deux pilotes supportent `debian13-arm64` et
  `chrome-linux-arm64` ; c'est un décalage de versions, qui touchait aussi
  amd64 et le lanceur local (`npm run setup`).

### Correction

- `backend/Dockerfile` : `python -m patchright install --with-deps chromium`.
  Le navigateur est installé par le CLI du pilote réellement utilisé : sa
  révision suit **automatiquement** la version verrouillée de Patchright,
  y compris lors des futures mises à jour Dependabot. Les versions
  verrouillées ne changent pas. Le Chromium de Playwright, inutile, n'est plus
  installé (image plus légère). Si un jour `DynamicSession`/`DynamicFetcher`
  (pilote Playwright) était utilisé, il faudrait aussi
  `python -m playwright install chromium`.
- Toujours dans le `Dockerfile`, après `USER app` :
  `python -m app.scraper.browser_check --static` fait **échouer le build** si
  l'exécutable attendu par Patchright est absent (sans lancer le navigateur,
  donc compatible avec le build sous QEMU).
- `scripts/passefiltre.mjs` (`npm run setup`) : même correction en local.
- Sécurité inchangée : utilisateur non-root `uid 10001`,
  `no-new-privileges`, `shm_size: 1gb`, dépendances vérifiées par hash.

### Tests de démarrage réel du navigateur

`python -m app.scraper.browser_check` (dans l'image) affiche l'architecture et
les versions, vérifie l'exécutable attendu par Patchright, puis **démarre
Chromium via `StealthySession`** (profil persistant temporaire, comme le
scraper) et charge une page servie sur `127.0.0.1` (aucun accès réseau
externe). Code de sortie non nul en cas d'échec.

| Où | Quand | Image testée |
| --- | --- | --- |
| `ci.yml`, job `docker` (amd64) | chaque PR / push | image construite par la CI |
| `ci.yml`, job `docker-arm64` (`ubuntu-24.04-arm`, ARM64 natif) | chaque PR / push | image arm64 construite nativement |
| `deploy-serveurcasa.yml`, job `smoke` (`ubuntu-24.04-arm`) | avant `deploy` | **l'image exacte** `sha-<commit>` poussée sur GHCR |
| `deploy-serveurcasa.yml`, job `deploy` (sur le Pi) | avant `compose up` | même image, noyau du Pi, options du service (`compose run --rm --no-deps`) |

Un échec de `smoke` empêche le job `deploy` de démarrer. Un échec sur le Pi
arrête le déploiement **avant** de toucher aux conteneurs (`deploy.env`
restauré, pas de rollback nécessaire). Le conteneur de test est éphémère
(`--rm`) et appartient au projet `passefiltre` : aucun autre service Docker
n'est concerné.

Les runners `ubuntu-24.04-arm` sont gratuits pour les dépôts publics. Si le
dépôt devenait privé, il faudrait un runner ARM64 payant, ou se contenter du
test exécuté sur le Pi.
- Aucune modification des services `restic-serveurcasa.*` ni des montages
  `/mnt/storageplex` et `/mnt/backup8to`.

Depuis l'ajout du CAPTCHA à distance (§13), le même `browser_check` démarre
aussi Chromium **en mode visible sur un écran Xvfb privé**, lance x11vnc sur un
socket Unix, lit la bannière RFB, vérifie qu'**aucun port TCP** n'a été ouvert
et que le répertoire temporaire a été supprimé.

## 13. Résolution manuelle des CAPTCHA LinkedIn (noVNC)

### Architecture

Tout se passe **dans le conteneur `api`** : aucun nouveau service, aucun port
publié en plus de `8100`.

```text
navigateur ──HTTPS/WSS──> NPM ──HTTP/WS──> api:8000  /api/jobs/{id}/captcha/vnc  (pont WebSocket FastAPI)
                                               │ socket Unix 0700 (pas de TCP)
                                               ▼
                                     x11vnc ──> Xvfb :N (écran privé, -nolisten tcp)
                                                  ▲
                                     Chromium visible (même profil LinkedIn)
```

1. L'extraction démarre **sans interface** (headless, comportement inchangé).
2. Si LinkedIn affiche un CAPTCHA, elle est relancée **une fois** en mode
   visible sur un écran virtuel Xvfb privé (numéro choisi par Xvfb,
   `-displayfd`), avec le même profil persistant.
3. Quand le CAPTCHA apparaît, x11vnc démarre sur un **socket Unix** dans un
   répertoire temporaire `0700` (`-rfbport 0`, aucun port TCP). La tâche passe
   à l'état `needs_captcha` ; l'interface affiche « Résoudre le CAPTCHA ».
4. Le bouton ouvre une fenêtre intégrée (noVNC) reliée au pont WebSocket de
   l'API, qui joue le rôle de websockify.
5. La reprise est décidée **uniquement côté serveur** : le scraping continue
   lorsque LinkedIn quitte `/checkpoint` ou `/challenge`. Ouvrir ou fermer la
   fenêtre ne valide rien. Aucune résolution automatique n'est tentée.
6. À la fin (succès, expiration, annulation, erreur), x11vnc et Xvfb sont
   arrêtés (groupe de processus entier) et le répertoire temporaire supprimé ;
   les connexions noVNC ouvertes sont coupées.

### Contrôle d'accès

- Chaque tâche reçoit à sa création une **clé propre** (en-tête
  `X-PasseFiltre-Job-Key`) gardée en mémoire par l'onglet qui l'a lancée.
  Toutes les routes `/api/jobs/{id}…` l'exigent (`404` sinon) : une tâche
  n'est jamais visible depuis une autre session, même avec le jeton.
- `POST /api/jobs/{id}/captcha/ticket` (jeton `PASSEFILTRE_TOKEN` **et** clé de
  tâche, uniquement en état `needs_captcha`) délivre un ticket **à usage
  unique, valable 60 s, lié à cette tâche**.
- Le ticket est transmis dans le sous-protocole WebSocket
  (`Sec-WebSocket-Protocol`), jamais dans l'URL ; le jeton applicatif n'est
  jamais transmis au WebSocket.
- Le WebSocket exige en plus un `Origin` présent dans `CORS_ORIGINS` (protection
  contre le détournement inter-sites) ; refus = fermeture `1008`, journalisé
  (`captcha_vnc_refused`).
- `ALLOWED_HOSTS` s'applique aussi au WebSocket.

### Variables d'environnement (`/opt/passefiltre/.env`, toutes facultatives)

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `INTERACTIVE_CAPTCHA` | `1` | `0` = désactive (retour au message « relancez en mode visible ») |
| `CAPTCHA_TIMEOUT` | `300` | secondes laissées pour résoudre (minimum 60) |
| `MAX_CAPTCHA_SESSIONS` | `1` | écrans virtuels simultanés (au-delà : message d'attente) |
| `API_MEM_LIMIT` | `3g` | plafond mémoire du conteneur `api` |

`CORS_ORIGINS` doit contenir `https://passefiltre.local.cronix.fr` (déjà requis
par §2bis).

### Nginx Proxy Manager

Sur l'hôte `passefiltre.local.cronix.fr` :

- Onglet **Details** : cocher **Websockets Support**.
- Si `/api/` est une *Custom location*, NPM n'y reporte pas toujours cette
  option : dans son ⚙ (configuration avancée de la location), ajouter

  ```nginx
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_read_timeout 600s;
  ```

- Ne rien changer d'autre : `/` et `/api/` gardent leurs cibles. **Ne créer
  aucun hôte ni port** pour VNC/noVNC : ils n'existent pas hors du conteneur.

Vérification : pendant un CAPTCHA, outils de développement → Réseau → WS :
`wss://passefiltre.local.cronix.fr/api/jobs/…/captcha/vnc`, statut `101`.

### Ressources du Raspberry Pi 5

- Une seule session d'écran virtuel par défaut ; un seul scraping par compte
  LinkedIn ; au plus 2 tâches en parallèle (inchangé).
- `docker-compose.yml` : `init: true` (récupère les processus orphelins de
  Chromium), `pids_limit: 512`, `mem_limit: ${API_MEM_LIMIT:-3g}`. Si le cgroup
  mémoire est désactivé sur le Pi, Docker l'ignore avec un avertissement
  (activable via `cgroup_enable=memory` dans `/boot/firmware/cmdline.txt`,
  non fait par ce dépôt).
- L'image grossit de quelques dizaines de Mo (`xvfb`, `x11vnc`).

### Déploiement

Aucune étape manuelle côté Docker : le workflow habituel (§3 à §5) suffit. À
faire **une fois** avant de l'utiliser : l'option WebSockets dans NPM
(ci-dessus). Rollback : §7 (l'ancienne image ignore simplement ces variables).

### Limites

- La reprise relance l'extraction en mode visible depuis le début (la session
  headless n'est pas transférable) ; le profil persistant conserve les cookies.
- Fermer ou recharger l'onglet perd la clé de tâche : la tâche continue jusqu'à
  son expiration mais n'est plus pilotable (annulation comprise).
- Une seule personne peut regarder un écran à la fois (`-nevershared`).
