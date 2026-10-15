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
- Docker Engine + plugin `docker compose` **≥ 2.24.4** (nécessaire pour le tag
  YAML `!reset` utilisé par `docker-compose.server.yml`).
- Répertoire `/opt/passefiltre/` appartenant à `cronix`.
- `/opt/passefiltre/.env` (permissions `600`, appartenant à `cronix`) contenant
  au minimum :

  ```dotenv
  BACKEND_PORT=8100
  FRONTEND_PORT=3101
  BIND_ADDRESS=192.168.1.63
  NEXT_PUBLIC_API_URL=http://192.168.1.63:8100
  CORS_ORIGINS=http://192.168.1.63:3101
  ALLOWED_HOSTS=192.168.1.63
  PASSEFILTRE_TOKEN=<jeton secret ≥ 32 caractères>
  ```

  Ce fichier **n'est jamais** modifié, affiché ni copié par le workflow : il est
  seulement vérifié présent (`test -f`).

### Sur GitHub (à configurer une fois)

- Rien d'obligatoire : le workflow utilise `GITHUB_TOKEN` (aucun secret à créer).
- Variable de dépôt **facultative** `SERVEURCASA_API_URL` pour surcharger
  l'URL de l'API intégrée au build du frontend (défaut :
  `http://192.168.1.63:8100`).

> **Important — construction du frontend.** `NEXT_PUBLIC_API_URL` est **figé au
> moment du build** Next.js (voir `frontend/Dockerfile`). Le job `build`
> construit donc l'image `web` avec `NEXT_PUBLIC_API_URL=http://192.168.1.63:8100`
> pour que le navigateur appelle bien l'API du réseau local. Changer de port ou
> d'IP impose de **reconstruire** l'image `web` (un nouveau push sur `main`
> suffit).

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
5. Au succès : <http://192.168.1.63:3101> (frontend) et
   <http://192.168.1.63:8100/api/health> (API).

Le premier build `arm64` sous QEMU est lent (installation de Chromium /
Playwright émulée). Les builds suivants réutilisent le cache GitHub Actions.

## 5. Mise à jour automatique

Rien à faire : un `push` sur `main` qui passe la CI met à jour PasseFiltre.
Le workflow :

- vérifie que le commit est **toujours la tête de `main`** (sinon il s'arrête
  proprement : un déploiement plus récent s'en chargera) ;
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
| Santé de l'API | `curl -fsS http://192.168.1.63:8100/api/health` |
| Config fusionnée (sans secret) | `pf config -q && echo OK` |
| Logs du runner | `journalctl -u actions.runner.Cronix2-CV_ATS_generator.serveurcasa.service -f` |

## 7. Rollback

### Automatique

Si un `pull`, le `up -d` ou un healthcheck échoue, le job restaure
automatiquement le tag précédent (`deploy.env.previous`), relance les
conteneurs, revérifie l'API, puis **échoue explicitement** pour signaler le
problème. Le volume des sessions LinkedIn n'est jamais supprimé.

### Manuel

```bash
cd /opt/passefiltre
cat deploy.env            # tag actuel
cat deploy.env.previous   # tag précédent

# Revenir au tag précédent :
cp -f deploy.env.previous deploy.env
pf pull
pf up -d

# Ou fixer explicitement un tag connu :
printf 'PASSEFILTRE_IMAGE_TAG=sha-<commit>\n' > deploy.env
pf pull && pf up -d
```

Les images restent dans le cache local de Docker : un rollback n'exige pas de
réseau si l'image visée a déjà été téléchargée.

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
- Labels attendus : `self-hosted`, `Linux`, `ARM64` (le job cible
  `runs-on: [self-hosted, Linux, ARM64]`).
- Accès Docker : `docker ps` doit fonctionner en tant que `cronix` (groupe
  `docker`).

### ARM64

- Si le build échoue côté GitHub, vérifier que `docker/setup-qemu-action` s'est
  bien exécuté (émulation `arm64`).
- Sur le Pi, `docker image inspect ghcr.io/cronix2/passefiltre-api:sha-<commit>
  --format '{{.Architecture}}'` doit renvoyer `arm64`.

### `!reset` non reconnu

Erreur du type *"unknown tag !reset"* → la version de Docker Compose est
antérieure à 2.24.4. Mettre à jour le plugin Compose.

## 10. Limitations de sécurité (HTTP sur le LAN)

- **Pas de chiffrement.** L'accès se fait en **HTTP clair** sur
  `192.168.1.63:3101`/`:8100`. Les identifiants LinkedIn et le
  `PASSEFILTRE_TOKEN` transitent **en clair sur le réseau local** : quiconque
  peut écouter le LAN (Wi-Fi, switch compromis) peut les intercepter. À
  n'utiliser que sur un réseau de confiance.
- **Le bind sur une IP privée n'est pas un pare-feu.** Publier les ports sur
  `192.168.1.63` limite l'interface d'écoute mais ne filtre pas les hôtes du
  LAN. Pour restreindre réellement l'accès, ajouter des règles de pare-feu sur
  le Pi, par exemple :

  ```bash
  # n'autoriser que le sous-réseau local vers les ports PasseFiltre
  sudo ufw allow from 192.168.1.0/24 to any port 3101 proto tcp
  sudo ufw allow from 192.168.1.0/24 to any port 8100 proto tcp
  ```

- **Aucune exposition Internet.** Pas de Cloudflare Tunnel, pas de proxy Caddy,
  pas d'ouverture des ports 80/443. Pour un accès chiffré, utiliser le profil
  `https` de `docker-compose.yml` (Caddy + certificat), hors périmètre de ce
  déploiement.
- Le `PASSEFILTRE_TOKEN` reste **obligatoire** : l'API refuse de démarrer sans
  un jeton ≥ 32 caractères dès qu'elle est exposée au réseau (`BIND_ADDRESS`
  non-loopback).

## 11. Garanties d'isolation

Le workflow de déploiement **ne touche jamais** aux autres services du serveur :

- `-p passefiltre` cantonne toutes les commandes au projet `passefiltre`.
- Aucun `docker system prune`, `docker volume prune`, ni `compose down -v`.
- Les volumes persistants (`passefiltre_sessions`) ne sont jamais supprimés.
- Aucune modification des services `restic-serveurcasa.*` ni des montages
  `/mnt/storageplex` et `/mnt/backup8to`.
