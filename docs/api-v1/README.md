# PasseFiltre API v1

API de service optionnelle, montée sur `/api/v1`. PasseFiltre conserve son interface Next.js,
ses moteurs Python et ses anciennes routes `/api/*`. Sans `API_V1_ENABLED=1`, aucune connexion
PostgreSQL/Redis n'est nécessaire et les routes v1 ne sont pas montées.

- [Contrat OpenAPI versionné](openapi.json) : schémas et paramètres exacts.
- [Installation, migration et rollback](OPERATIONS.md).
- [Intégration Job Control Tower](JOB_CONTROL_TOWER.md).
- [Architecture et invariants](ARCHITECTURE.md).
- [Rapport de validation](VALIDATION.md).

Avec `API_DOCS=1`, Swagger est disponible sur `/api/v1/docs` et le schéma sur
`/api/v1/openapi.json`. Ces documents ne contiennent ni clés ni données utilisateur.

## Authentification et isolation

Chaque appel métier porte deux en-têtes :

```http
Authorization: Bearer pf_v1_...
X-PasseFiltre-User-Id: user-opaque-123
```

La clé identifie un service, un tenant et ses permissions. L'identifiant utilisateur est
délégué par ce service de confiance : il doit provenir de sa session authentifiée, jamais
d'un champ libre fourni par son navigateur. Une clé de service peut agir pour les utilisateurs
de son tenant. Le même utilisateur opaque dans deux tenants désigne deux espaces différents.
Les UUID d'un autre propriétaire renvoient `404`, comme un UUID absent. PostgreSQL impose
également une politique RLS, avec un rôle applicatif non propriétaire et sans `BYPASSRLS`.

Permissions disponibles : `profiles:read/write`, `cvs:read/write`, `offers:read/write`,
`linkedin:read/write`, `ai:run`, `ats:read`, `exports:read/write`, `jobs:read/write`,
`conversations:read/write`, `workflows:read/write/approve`. Chaque forme `read/write` désigne
deux permissions distinctes. L'approbation requiert aussi `exports:write`.

Les clés restent côté serveur. L'interface PasseFiltre utilise un adaptateur `/api/workflows`
et une capacité aléatoire propre au workflow, gardée dans `sessionStorage` ; elle ne reçoit
jamais la clé `V1_UI_SERVICE_KEY`.

## Conventions

- JSON UTF-8, `schema_version: "1"`, corps limité à 2 Mio. Les champs inconnus des enveloppes
  v1 sont refusés ; les modèles CV historiques conservent leur tolérance pour compatibilité.
- `Idempotency-Key` obligatoire sur les créations, traitements, messages et approbations.
  Réutiliser la même valeur pour réessayer le même appel. Un contenu différent donne `409`.
  Portée : tenant, utilisateur et opération ; conservation par défaut 24 heures.
- Les mises à jour de ressources et de brouillons exigent `If-Match: "<version>"`.
  La lecture fournit `ETag`. Version périmée : `412` ; absence : `428`.
- Les listes paginées acceptent `limit` (1–100) et `cursor` ; suivre `next_cursor`.
  L'ordre est celui des UUID, pas un ordre chronologique.
- Erreurs JSON : `{"code":"...","message":"...","request_id":"..."}`.
  `X-Request-Id` permet la corrélation sans journaliser le contenu. `429` inclut `Retry-After`.
  Les rejets d'un proxy amont peuvent avoir leur propre format.
- HTTPS requis hors développement local. Les protections Origin/Host existantes restent actives.
  Les appels serveur à serveur n'ajoutent pas d'en-tête `Origin` artificiel.

## Routes

Tous les chemins ci-dessous sont relatifs à `/api/v1`.

| Fonction | Routes |
| --- | --- |
| Santé | `GET /health` public ; `GET /ready` authentifié, vérifie PostgreSQL/Redis |
| Profils | `POST, GET /profiles` ; `GET, PUT, DELETE /profiles/{id}` |
| CV structurés | `POST, GET /cvs` ; `GET, PUT, DELETE /cvs/{id}` ; `GET /cvs/{id}/versions` |
| Offres | `POST, GET /offers` ; `GET, PUT, DELETE /offers/{id}` ; `POST /offers/import` ; `POST /offers/{id}/analysis` |
| LinkedIn | `POST /linkedin/extractions` ; `GET /linkedin/sessions` ; `GET, DELETE /linkedin/sessions/{id}` |
| IA | `POST /review` synchrone ; `POST /enhancements` asynchrone |
| Conversation | `POST /conversations` ; `GET, DELETE /conversations/{id}` ; `POST /conversations/{id}/messages` |
| ATS | `POST /ats/analyses` |
| Export | `POST /render` synchrone ; `POST /exports` asynchrone ; `GET /exports/{id}` et `/download` |
| Tâches | `GET /jobs` ; `GET, DELETE /jobs/{id}` ; `GET /jobs/{id}/result` ; `POST /jobs/{id}/resume` |
| Interaction LinkedIn | `POST /jobs/{id}/code` ; `POST /jobs/{id}/captcha/ticket` ; WebSocket `/jobs/{id}/captcha/vnc` |
| CV ciblé | `POST /workflows` ; `GET, DELETE /workflows/{id}` ; `PUT /workflows/{id}/draft` ; `POST /workflows/{id}/approve` et `/reject` |

Les ressources retournent `id`, `kind`, `version`, `data`, dates de création/modification et
éventuelle expiration. L'export synchrone retourne directement le PDF/DOCX, avec
`Content-Disposition`, `X-Content-SHA256` et `X-PasseFiltre-Version`.

## Exemple curl

Configurer `PF_URL`, `PF_KEY` et `PF_USER` dans l'environnement du client. Ne pas activer
`set -x`, `curl -v` ou la journalisation des en-têtes d'authentification.

```sh
export PF_URL=http://localhost:8000/api/v1
export PF_USER=user-demo
# PF_KEY provient du coffre de secrets du service.
curl --fail-with-body "$PF_URL/cvs" \
  -H "Authorization: Bearer $PF_KEY" \
  -H "X-PasseFiltre-User-Id: $PF_USER" \
  -H 'Idempotency-Key: demo-cv-001' \
  -H 'Content-Type: application/json' \
  --data-binary @docs/api-v1/examples/cv.json

curl --fail-with-body "$PF_URL/ats/analyses" \
  -H "Authorization: Bearer $PF_KEY" \
  -H "X-PasseFiltre-User-Id: $PF_USER" \
  -H 'Content-Type: application/json' \
  --data-binary @docs/api-v1/examples/cv.json

# Le format par défaut est PDF ; ajouter "format":"docx" au JSON pour DOCX.
curl --fail-with-body "$PF_URL/render" \
  -H "Authorization: Bearer $PF_KEY" \
  -H "X-PasseFiltre-User-Id: $PF_USER" \
  -H 'Idempotency-Key: demo-render-001' \
  -H 'Content-Type: application/json' \
  --data-binary @docs/api-v1/examples/cv.json --output /tmp/cv-demo.pdf
```

Exemple Python exécutable : [examples/targeted_cv.py](examples/targeted_cv.py).
Il crée un workflow sans IA pour fonctionner sans fournisseur, attend le brouillon,
l'enregistre pour lecture, puis exige une confirmation humaine avant les exports.

## Tâches, LinkedIn et CAPTCHA

Un traitement asynchrone retourne `202`, un `JobView` et `Location: /api/v1/jobs/{id}`.
Interroger cette URL avec les mêmes en-têtes. États : `queued`, `running`, `needs_code`,
`needs_captcha`, `succeeded`, `failed`, `cancelled`. Après expiration, la lecture renvoie `404`.
Un résultat peut contenir directement des propositions IA, ou un couple
`resource_type`/`resource_id` à lire sur la route correspondante.

`DELETE /jobs/{id}` marque l'annulation ; un résultat tardif ne peut plus être publié.
Un appel externe déjà en cours peut néanmoins se terminer et être facturé. Les erreurs
transitoires sont réessayées avec délai, au maximum trois tentatives. La reprise manuelle
est limitée aux tâches en échec avec moins de trois tentatives, hors extraction LinkedIn.
Une extraction interrompue requiert généralement une nouvelle interaction humaine.

Une extraction accepte `profile_url` et soit `session_id`, soit `email`/`password`. Ces derniers
sont chiffrés temporairement, jamais renvoyés. Les sessions exposent uniquement ID et expiration.
À l'état `needs_code`, envoyer `{"code":"..."}` sur `/jobs/{id}/code` ; le code est chiffré,
consommé une fois puis effacé. À l'état `needs_captcha`, demander un ticket avec un POST JSON `{}`.
Le client noVNC ouvre la WebSocket avec les sous-protocoles `binary` et
`pf-ticket.<ticket>`. Ne jamais mettre le ticket dans l'URL ou les logs. Il est valable
60 secondes, utilisable une fois, lié au propriétaire et à une origine autorisée.
L'expiration, l'annulation ou la révocation ferme l'accès. Le navigateur interactif reste
dans le conteneur CAPTCHA isolé et utilise le proxy d'egress existant.

## Validation humaine et provenance

Le workflow conserve le CV source, le brouillon, les suggestions, les scores ATS et les
changements. Les suggestions de prose ne modifient pas automatiquement les qualifications.
Les compétences nouvelles et les références d'expérience inconnues sont filtrées ; les
propositions gardent leurs références source. `prose_verified=false` signifie qu'une lecture
humaine reste nécessaire : un modèle peut toujours proposer une phrase inexacte.

Pour modifier un brouillon, envoyer le CV complet sur `/workflows/{id}/draft` avec `If-Match`.
Pour approuver, envoyer `version`, `digest` lus sur le dernier brouillon et `confirmed:true`.
Le serveur crée alors deux tâches d'export. Une modification ultérieure invalide l'approbation
et bloque aussi le téléchargement des anciens exports liés à ce workflow.

Les routes `/render` et `/exports` rendent un CV fourni explicitement par un service ; elles
ne constituent pas une attestation de validation humaine. Le service appelant doit les réserver
aux faits qu'il a lui-même validés. Pour imposer le contrôle de version et d'approbation,
utiliser le workflow. Les conversations renvoient des propositions séparées ; leur adoption
se fait explicitement dans le CV/brouillon, pas par mutation silencieuse de la conversation.
