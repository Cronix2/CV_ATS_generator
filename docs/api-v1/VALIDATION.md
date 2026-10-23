# Rapport de validation API v1

Base auditée : `dc9a33a` (`main`). Travail réalisé sur `feature/passefiltre-api-v1`.
Aucun déploiement, aucune fusion, aucune modification de secret ou donnée de production.

## Résultats locaux

| Vérification | Résultat |
| --- | --- |
| Référence avant modifications | 146 tests backend, 2 fichiers de tests frontend et TypeScript réussis |
| Services partagés, ATS et exports | Fixtures ATS comparées au moteur TypeScript initial ; exports déterministes entre processus |
| Suite backend finale | **180 tests réussis**, Python 3.12, PostgreSQL 17 et Redis 7 réels, 20,50 s |
| Migration sur base vide | `0001_v1` puis `0002_maintenance` appliquées ; rôle `pf_app` non privilégié |
| Frontend | 3 fichiers de tests réussis ; TypeScript `--noEmit` réussi |
| Build Next.js | Construction de production réussie lors de la validation frontend ; aucun changement frontend depuis |
| OpenAPI | Artefact généré puis vérifié par `export_openapi.py --check` |
| Compose v1 | `docker compose ... config -q` réussi avec valeurs fictives |
| Image API amd64 | Construction et contrôle statique du chemin Chromium réussis |
| Lancement navigateur dans l'image locale | **Bloqué** : Docker a épuisé le disque de l'environnement au démarrage du conteneur |
| ARM64 natif et isolation navigateur complète | À confirmer par les jobs GitHub Actions ; non exécutés localement sur Raspberry Pi |

La construction locale a utilisé un montage temporaire du certificat CA du proxy de session,
avec vérification TLS active. Les permissions de fichiers copiés ont été normalisées aux
permissions d'un checkout Git. L'image et les caches de cette mission ont été supprimés pour
récupérer l'espace disque ; le code et les bases de test ont été conservés.

## Couverture significative

- Compatibilité des routes historiques, protection réseau/SSRF, origine, jeton historique,
  helpers de rendu et fermeture du pont CAPTCHA.
- Accès croisés utilisateurs et tenants refusés, RLS sans contexte, refus de rôle privilégié,
  permissions insuffisantes, révocation de clé et quotas.
- Création et versionnement de CV, conflit `If-Match`, idempotence concurrente et réessai de
  JSON sans identifiants d'items, rejet d'IDs dupliqués et d'entrées mal formées.
- Tâche Celery réelle via Redis : interruption du processus en cours, perte du contenu du
  broker, reconstruction via outbox, reprise avec tentative 2 et un seul export publié.
- Annulation pendant exécution, refus de publication par un ancien lease, retries bornés,
  purge des secrets et résultats expirés, conversation réutilisable après expiration du job.
- Workflow arrêté pour revue humaine, consentement explicite, version/digest vérifiés,
  invalidation des exports après modification du brouillon.
- Filtrage de qualifications/références nouvelles proposées par l'IA, conservation des faits
  source, prose proposée séparément avec obligation de revue humaine.
- 2FA avec contexte propriétaire, effacement du code consommé, cookies non exposés ; CAPTCHA
  avec vraie socket Unix et WebSocket, origine contrôlée, ticket unique et fermeture après annulation.
- Adaptateur UI à capacité aléatoire, clé de service non exposée, état frontend empêchant une
  approbation sans consentement ou après une édition locale non enregistrée.

## Reproduire

Dans `backend`, installer `requirements-dev.lock` avec `pip --require-hashes`.
Fournir `PF_TEST_ADMIN_URL`, `PF_TEST_APP_URL` et `PF_TEST_REDIS_URL` pointant exclusivement
vers PostgreSQL/Redis de test. Le nom de base doit se terminer par `_test` ; le rôle applicatif
doit être `pf_app`. La suite tronque ses tables et le test Redis vide sa base réservée : ne
jamais employer une base partagée ou de production.

```sh
python scripts/prepare_v1_test_db.py
PF_REQUIRE_V1_TESTS=1 python -m pytest -q
python scripts/export_openapi.py --check
```

`prepare_v1_test_db.py --reset` peut recréer le schéma public **uniquement dans cette base de
test** pour vérifier les migrations depuis zéro. Sans variables de test, les tests nécessitant
PostgreSQL/Redis sont ignorés ; `PF_REQUIRE_V1_TESTS=1` rend leur absence bloquante en CI.

La CI exécute ces contrôles, les tests/types/build frontend, les constructions Docker et les
tests Chromium/isolation sur amd64 et ARM64 natif. Un job non exécuté ou interrompu ne constitue
pas une validation réussie. Consulter les statuts attachés au commit final de la PR.

## Limites de validation

Aucun compte LinkedIn réel ni fournisseur LLM payant n'a été utilisé. Les tests d'interaction
simulent ces moteurs, sans désactiver les protections de sécurité. Aucun test navigateur complet
de l'interface Next.js n'a été réalisé ; les tests frontend couvrent la logique de consentement,
et l'intégration HTTP couvre son adaptateur serveur. La vérité des reformulations IA ne peut
pas être prouvée par ces tests : la revue humaine demeure nécessaire.

La livraison externe reste au moins une fois et l'annulation coopérative. La rétention des
sauvegardes, la rotation de la clé de chiffrement, les quotas de volume de données et les
alertes d'exploitation demandent une politique opérateur, détaillée dans `OPERATIONS.md`.
