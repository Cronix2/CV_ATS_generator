# Feuille de route sécurité

Suivi des actions issues de l'audit OWASP Top 10 et des revues de sécurité. Les numéros (n°X) renvoient aux constats de l'audit initial.

## Fait

| N° | Correction | Vérification |
| --- | --- | --- |
| 8 | Dumps HTML du profil supprimés de `debug/`. | — |
| 1, 10 | API et interface sur `127.0.0.1` par défaut (lanceur et Docker). | Instance de test : écoute sur `127.0.0.1` uniquement. |
| 2 | Session LinkedIn liée à e-mail + mot de passe (HMAC, secret d'installation, `0o700`). | Tests. |
| 3 | URL de LLM saisie dans l'interface : adresses locales/privées refusées sauf `ALLOW_LOCAL_LLM=1` ; plus d'écho du corps des réponses distantes. | Tests. |
| 1 | Jeton `PASSEFILTRE_TOKEN`, `TrustedHostMiddleware` (DNS rebinding). | Tests + instance de test (401 / 400). |
| 4 | Agent : liste blanche d'URL (demande, lien de l'offre, résultats de recherche — plus le texte d'une offre importée), e-mail et téléphone masqués. | Tests. |
| 5 | `read_webpage` : contrôle `is_global`, recontrôle de l'URL finale, 3 Mo maximum. | Tests. |
| 6 | 2 tâches simultanées maximum (`MAX_JOBS`), réponse 429. | Tests. |
| 7 | CSP et en-têtes de sécurité, `no-store` sur l'API, HSTS via le proxy HTTPS. | Navigateur réel : aperçu PDF OK, aucune violation CSP. |
| 11, 12 | Erreurs génériques côté client, nom de fichier téléchargé assaini. | Tests. |
| Revue | **Bug `LLM_BASE_URL` local refusé** (double résolution) : configuration résolue une seule fois ; un client ne peut pas se faire passer pour une configuration résolue. | Tests de non-régression. |
| Revue | **POST cross-site sans preflight** : `Content-Type: application/json` exigé (415) et en-tête `Origin` vérifié (403). | Tests + instance de test. |
| 9 | Conteneur API non-root (`uid 10001`), `no-new-privileges`, Chromium dans `/ms-playwright`. | ⚠️ Docker non disponible sur le poste de dev : validé au premier passage de la CI. |
| 13 | Dépendances Python figées avec empreintes (`requirements*.lock`, `--require-hashes` partout), actions GitHub figées par SHA, permissions minimales par job, Dependabot (pip, npm, actions, docker). | Installation depuis le lock dans un environnement neuf + 52 tests. |
| 8 | Route `POST /api/linkedin/logout` (identifiants requis) et bouton « Oublier ma session LinkedIn ». | Tests + interface. |
| 14 | `/docs` désactivé hors développement (`API_DOCS=1` pour l'activer) ; clé LLM en `sessionStorage` conservée (effacée à la fermeture de l'onglet, protégée par la CSP). | Instance de test : `/docs` → 404. |
| Réseau | **Garde-fou** : l'API refuse de démarrer si elle est exposée au réseau sans jeton de 32 caractères ou plus. | Testé (démarrage refusé, message explicite). |
| Réseau | **HTTPS** : profil Docker `https` (Caddy, Let's Encrypt ou autorité locale), interface et API sur une même origine. | ⚠️ Non testé localement (pas de Docker). |
| Réseau | **Journal d'audit** (`passefiltre.audit`, option `AUDIT_LOG_FILE`) : IP, action, empreinte du compte ; jamais de mot de passe, clé ni contenu de CV. | Tests + instance de test. |
| Réseau | **Navigateur visible** réservé à la machine hôte (un client distant ne peut pas ouvrir de fenêtre sur le serveur). | Tests. |

## À faire

| Priorité | Action | Pourquoi ce n'est pas fait |
| --- | --- | --- |
| Haute | **Valider la chaîne Docker** : premier passage de la CI (build des images non-root depuis le lock), puis un `docker compose --profile https up` sur la machine cible avant l'ouverture au réseau. Vérifier qu'une extraction LinkedIn fonctionne dans le conteneur non-root. | Docker n'est pas installé sur le poste de développement. |
| Moyenne | **Après la première release** : rendre publics les packages GHCR, et vérifier que Dependabot ouvre bien ses PR. | Nécessite un push et un tag. |
| Basse | **Conteneurs en lecture seule** (`read_only: true` + `tmpfs`) : à réactiver une fois les chemins écrits par Chromium et Next.js confirmés sur la machine cible. | Retiré tant qu'il n'est pas testable : risque de casser le premier lancement. |
| Basse | **Images de base figées par empreinte** (`python:3.12-slim@sha256:…`, `node:22-alpine@sha256:…`, `caddy@sha256:…`). Dependabot `docker` les maintiendra ensuite. | Nécessite l'accès au registre Docker. |

## Avant chaque ouverture au réseau

- `PASSEFILTRE_TOKEN` d'au moins 32 caractères aléatoires (l'API ne démarre pas sinon).
- `SITE_ADDRESS`, `NEXT_PUBLIC_API_URL` et `CORS_ORIGINS` cohérents (même adresse), images reconstruites (`--build`) après tout changement de `NEXT_PUBLIC_API_URL`.
- Racine de l'autorité locale Caddy importée sur les postes clients si l'adresse n'est pas un vrai domaine.
- Journal d'audit conservé (`AUDIT_LOG_FILE` sur un volume) et consulté.
