# Architecture et invariants de compatibilité

Base auditée : commit `dc9a33a`. Le dépôt conserve FastAPI/Python, Next.js et les moteurs
LinkedIn, LangChain, ATS, PDF et DOCX. La v1 s'ajoute à l'application existante ; elle ne
remplace pas le frontend et n'active aucun déploiement automatique.

## Frontières

- `app/services/operations.py` expose les opérations des moteurs existants ; `cv.py` centralise
  le rendu et le nom des fichiers ; `ats.py` porte le calcul historique TypeScript en Python.
  Le frontend appelle `/api/ats` pour partager ce même calcul avec `/api/v1/ats/analyses`.
- `app/main.py` conserve les routes historiques et leurs contrats. Les sessions/jobs
  historiques restent distincts des ressources v1. Le proxy CAPTCHA partagé est extrait
  dans `services/captcha_bridge.py`, avec les mêmes protections Origin/socket/annulation.
- `app/v1/api.py` fournit schémas, erreurs, authentification, autorisations et orchestration.
  `business.py` réutilise les moteurs ; `grounding.py` sépare faits source et propositions.
- `store.py` accède à PostgreSQL sous contexte tenant/utilisateur transactionnel. Les ressources
  sont des documents JSONB versionnés avec schéma API, index propriétaire/type et index d'expiration.
  Ce choix permet de conserver les structures CV existantes sans les dupliquer en tables métier.
- `worker.py` utilise Celery/Redis pour le transport et PostgreSQL pour l'état durable.
  L'outbox est écrite dans la transaction qui crée la tâche. `scheduler.py` republie et purge.
  Les queues `default` et `browser` ont chacune un worker à concurrence 1 par défaut.
- `legacy.py` adapte le workflow à l'interface PasseFiltre avec des capacités par workflow,
  indépendantes des clés serveur. La page d'export affiche les propositions et exige un consentement.

## Invariants contrôlés

Les anciennes routes, formats PDF/DOCX et protections de réseau interne restent disponibles.
Le passage ATS au backend est comparé à des fixtures produites par le moteur TypeScript
initial. Le rendu n'utilise plus de date/ZIP aléatoire ; les sections exclues restent exclues.
Les champs CV historiques restent compatibles.

La v1 ne fait confiance ni aux UUID reçus ni aux données de l'offre. L'accès à une ressource
passe par RLS et le contexte authentifié ; le contenu d'offre/CV est explicitement traité
comme donnée non fiable dans les prompts. Les destinations téléchargées continuent d'utiliser
les validateurs réseau existants. La configuration LLM serveur constitue une frontière de
confiance explicite ; elle n'est pas contrôlée par un appelant v1.

Les mots de passe, cookies et codes temporaires sont chiffrés AES-GCM avec contexte de
ressource ; l'empreinte d'idempotence des identifiants utilise HMAC. Les clés de service sont
stockées sous forme de hash. Les logs métier n'incluent plus les exceptions brutes, URL de
profil ou messages de fournisseur susceptibles de contenir des secrets. Les audits v1 ne
contiennent que références techniques, action, résultat et acteur pseudonymisé.

La confirmation humaine est liée à une version et à un digest. Aucun worker ne peut
transformer seul une proposition en qualification confirmée. Les exports d'un workflow
revérifient son approbation à la publication et au téléchargement.

## Limites assumées

Le service délègue l'identité utilisateur à l'intégrateur détenteur de la clé ; ce n'est pas
un système de login utilisateur/OAuth. Le rôle applicatif et la configuration serveur sont
de confiance ; RLS protège les chemins applicatifs, pas une compromission complète de ce rôle.
Les clés API sont gérées par CLI opérateur, sans endpoint public d'administration.

La livraison Celery est au moins une fois ; les leases empêchent la publication double,
mais pas tous les appels externes doublés après un crash. L'annulation est coopérative.
Les secrets temporaires peuvent rester dans les sauvegardes jusqu'à leur expiration propre.
Les textes IA restent des propositions à vérifier, pas une preuve sémantique d'exactitude.

La campagne locale ne contacte aucun compte LinkedIn ni fournisseur LLM réel. Les tests
2FA/CAPTCHA simulent le moteur mais exercent l'état persistant et la vraie WebSocket/socket.
Le lancement Chromium dans l'image et les constructions ARM64 sont aussi prévus en CI ;
leurs résultats doivent être consultés avant toute décision de déploiement.
