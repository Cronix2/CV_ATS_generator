# Installation, migration et rollback

La v1 est facultative. Cette procédure décrit une installation de développement ou de recette
séparée ; aucune commande de déploiement sur serveurcasa n'a été exécutée pendant cette mission.
Le workflow de déploiement existant n'active pas l'overlay v1.

## Configuration

Conserver la configuration historique dans `.env`. Copier `.env.v1.example` vers `.env.v1`,
hors Git, puis générer des secrets **nouveaux** dans le gestionnaire de secrets de l'installation.
Ne pas copier les secrets de production dans une recette.

| Variable | Usage |
| --- | --- |
| `API_V1_ENABLED=1` | Monte la v1 ; l'overlay la définit seulement pour l'API |
| `V1_DATABASE_URL` | `postgresql+psycopg://pf_app:…@v1-postgres:5432/passefiltre` |
| `V1_MIGRATION_DATABASE_URL` | Connexion administrateur, exclusivement pour migration/CLI opérateur |
| `V1_POSTGRES_PASSWORD` / `V1_APP_DB_PASSWORD` | Deux secrets différents pour administrateur et rôle applicatif |
| `V1_REDIS_PASSWORD` / `V1_REDIS_URL` | Secret Redis et URL `redis://:…@v1-redis:6379/0` |
| `V1_ENCRYPTION_KEY` | 32 octets aléatoires encodés Base64, partagés par API et workers |
| `V1_UI_SERVICE_KEY` | Facultative : active le parcours de validation persistante dans PasseFiltre |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Fournisseur serveur par défaut |
| `V1_LLM_PROVIDERS` | Registre JSON de références de fournisseurs autorisés |
| `PASSEFILTRE_IMAGE_TAG` | Même version d'image pour API, workers, sidecars et frontend |
| `API_DOCS=1` | Documentation HTTP ; sinon utiliser le fichier OpenAPI versionné |

Utiliser des secrets URL-safe ou encoder les caractères réservés dans les URL. Exemple de
génération de clé de chiffrement, à exécuter dans un terminal opérateur privé :

```sh
python -c 'import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

Ne jamais placer `V1_MIGRATION_DATABASE_URL` dans le `.env` historique chargé par `api.env_file`.
`.env.v1` sert à l'interpolation Compose : l'overlay ne transmet la connexion privilégiée
qu'au service `v1-migrate`. Les workers utilisent `pf_app`, sans propriété des tables,
sans superuser et sans BYPASSRLS. L'API refuse un rôle incompatible au démarrage.

Le registre des fournisseurs accepte, par exemple :

```json
{"jct":{"key_env":"LLM_API_KEY","base_url_env":"LLM_BASE_URL","model_env":"LLM_MODEL","tenants":["jct"]}}
```

Un nom de variable différent nécessite sa transmission explicite aux conteneurs concernés
dans un overlay local. Le client ne peut envoyer ni clé LLM ni URL de fournisseur. Les
adresses internes ne sont acceptées que par la configuration serveur de confiance déjà
prévue par l'application, jamais à partir d'une offre ou d'un appel client.

## Première installation de recette

Exécuter depuis la racine du dépôt. Définir une fonction pour employer systématiquement
les mêmes fichiers et le même projet isolé :

```sh
pfcompose() {
  docker compose -p passefiltre-v1-recette --env-file .env --env-file .env.v1 \
    -f docker-compose.yml -f docker-compose.v1.yml "$@"
}
pfcompose config -q
pfcompose build api web
pfcompose up -d v1-postgres v1-redis
pfcompose --profile v1-tools run --rm v1-migrate
```

Le script PostgreSQL d'initialisation crée `pf_app` uniquement sur un **nouveau** volume.
Alembic applique `0001_v1` puis `0002_maintenance`, sans importer ni modifier les cookies
ou fichiers historiques. La fonction de purge est `SECURITY DEFINER`, à portée fixe,
non exécutable par PUBLIC. Exécuter les migrations avec l'administrateur dédié PostgreSQL
pour qu'elle puisse purger les lignes expirées de tous les tenants malgré FORCE RLS.

Créer une clé pour chaque service avec les permissions minimales. La CLI affiche la clé
une seule fois : transférer cette sortie directement vers le coffre de secrets, sans la
conserver dans les logs CI. Exemple Job Control Tower :

```sh
pfcompose --profile v1-tools run --rm v1-migrate python -m app.v1.cli create-key \
  --tenant jct --service job-control-tower \
  --scopes cvs:read,cvs:write,offers:read,offers:write,ats:read,ai:run,exports:read,exports:write,jobs:read,jobs:write,workflows:read,workflows:write,workflows:approve
```

Pour l'interface PasseFiltre, créer séparément une clé tenant `passefiltre-ui`, avec
`ai:run,jobs:read,workflows:read,workflows:write,workflows:approve,exports:read,exports:write`,
puis renseigner `V1_UI_SERVICE_KEY`. Une clé manquante laisse le parcours historique disponible.

```sh
pfcompose up -d api web captcha-browser captcha-egress v1-worker v1-browser-worker v1-scheduler
```

Vérifier `/api/health`, `/api/v1/health`, puis `/api/v1/ready` avec une clé et un utilisateur
opaque. Envoyer un export de données fictives et vérifier qu'il passe de `queued` à
`succeeded` : `/ready` vérifie les dépendances, pas l'exécution effective d'un worker.
Exécuter ensuite le contrôle Chromium dans l'image :

```sh
pfcompose run --rm --no-deps api python -m app.scraper.browser_check
```

Les images PostgreSQL, Redis et les dépendances navigateur sont disponibles en ARM64.
Chromium est installé par **Patchright**, sous `/ms-playwright`, avec sa révision verrouillée.
La CI conserve les constructions natives ARM64, le lancement Chromium et les contrôles
d'isolation CAPTCHA. Sur Raspberry Pi 5, vérifier la mémoire disponible : les plafonds
Compose cumulés peuvent dépasser la RAM d'un modèle 4 Go. La capacité globale par défaut
est deux tâches lourdes, partagée entre les workers et les jobs historiques quand la v1 est active.
Dimensionner d'abord en recette ; ne pas augmenter la concurrence pour masquer un manque de RAM.

## Tâches et conservation

PostgreSQL est la source de vérité pour ressources, idempotence, tâches, leases et outbox.
Redis transporte des identifiants ; les documents et identifiants LinkedIn n'y sont pas mis.
L'outbox republie les tâches éligibles toutes les cinq secondes. Un heartbeat absent depuis
90 secondes déclenche une reprise bornée. Une ancienne tentative ne peut publier avec un
lease périmé. La livraison est **au moins une fois** : un fournisseur externe peut avoir
traité/facturé un appel avant un crash, même si aucun résultat n'a été enregistré.

Le scheduler purge indépendamment des files de travail. Après expiration, les lectures
refusent immédiatement la ressource ; la suppression physique se fait au prochain passage
de purge réussi (environ une minute hors panne).

| Variable | Défaut | Maximum |
| --- | ---: | ---: |
| `V1_MAX_JOBS` | 2 | 16 |
| `V1_RATE_SERVICE_PER_MINUTE` | 120 | 10000 |
| `V1_RATE_USER_PER_MINUTE` | 60 | 10000 |
| `V1_HEAVY_PER_DAY` | 20 | 10000 |
| `V1_RESULT_TTL_SECONDS` | 86400 | 2592000 |
| `V1_SECRET_TTL_SECONDS` | 1800 | 3600 |
| `V1_SESSION_TTL_SECONDS` | 2592000 | 31536000 |
| `V1_REVIEW_TTL_SECONDS` | 604800 | 2592000 |

La valeur minimale est 1. Les tâches, exports et réponses d'idempotence expirent ; les
profils, CV, versions, offres et conversations persistent jusqu'à leur suppression explicite.
L'audit technique pseudonymisé est conservé 90 jours. Les cookies sont chiffrés jusqu'à
expiration/suppression de la session. Les mots de passe et codes sont effacés au terme du
traitement, de l'annulation ou de leur rétention temporaire.

Les quotas comptent par clé de service et par tenant/utilisateur ; les tâches lourdes ont
un budget journalier partagé. L'approbation consomme deux tâches d'export. Prévoir ce budget
pour éviter un `429` au moment de valider. Il n'existe pas encore de quota d'octets cumulés
pour les ressources persistantes : suivre la taille de PostgreSQL et définir une politique
de suppression côté intégrateur.

Surveiller les états des jobs, l'âge des entrées de l'outbox, les redémarrages des workers,
l'espace disque et les messages statiques `v1 outbox dispatch failed` / `v1 retention maintenance failed`.
Ne pas activer de logs SQL détaillés, de capture de corps HTTP ou de traces LLM contenant les CV.
Le scheduler n'expose pas encore de métriques Prometheus ni de preuve d'exécution via `/ready`.

## Révocation et sauvegarde

```sh
pfcompose --profile v1-tools run --rm v1-migrate python -m app.v1.cli list-keys
pfcompose --profile v1-tools run --rm v1-migrate python -m app.v1.cli revoke-key UUID_DE_CLE
```

La révocation est relue à chaque appel et avant publication d'un résultat ; l'accès CAPTCHA
est aussi recontrôlé. Un appel fournisseur déjà commencé ne peut pas toujours être interrompu.

Sauvegarder PostgreSQL et la clé de chiffrement séparément, de façon chiffrée et avec accès
restreint. Une sauvegarde contient encore les données présentes à sa création : la purge
active n'efface pas les anciennes sauvegardes. Aligner leur rétention sur la politique de
données. Sans la clé de chiffrement, cookies/tâches secrètes ne sont pas récupérables.
Il n'existe pas encore de rotation automatique de cette clé : arrêter l'admission, laisser
finir/expirer les tâches, supprimer les sessions chiffrées et réauthentifier après changement.
Ne pas remplacer la clé pendant des tâches actives.

## Mise à jour et rollback

Avant mise à jour : sauvegarder la base et la configuration, relever les versions d'images,
arrêter l'admission v1 et les workers/scheduler, appliquer la migration avec l'image cible,
puis démarrer tous les composants sur la même version. Valider avec des données fictives
avant de rouvrir l'accès aux services appelants.

Pour revenir au PasseFiltre historique, arrêter explicitement les services `v1-worker`,
`v1-browser-worker` et `v1-scheduler`, puis relancer les images historiques avec le Compose
de base uniquement, sans `API_V1_ENABLED=1`. Conserver les volumes PostgreSQL/Redis et leur
configuration pour reprise ultérieure. Ne pas utiliser `down -v` et ne pas exécuter de
downgrade destructif : Alembic le refuse volontairement. Les routes `/api/v1` redeviennent
indisponibles ; l'application historique retrouve son fonctionnement sans PostgreSQL/Redis.
