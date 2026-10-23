# Validation API v1

Base inspectée : `dc9a33a` (main). Aucun déploiement effectué.

- Référence : 146 tests backend, 2 fichiers de tests frontend, TypeScript : réussis.
- Services partagés et export déterministe : 149 tests backend réussis.
- Port ATS : 5 tests ciblés ATS/export réussis, fixtures produites par le moteur TypeScript original.

Les résultats des phases suivantes seront ajoutés après exécution. Les tests simulés ne prouvent pas
une connexion LinkedIn réelle, un fournisseur LLM réel ou le fonctionnement sur le Raspberry Pi.
- Première tranche v1 : 162 tests backend réussis, dont 11 sur PostgreSQL 17 réel avec rôle `pf_app` non privilégié ; 3 fichiers de tests frontend et TypeScript réussis.
- Vérifications couvertes : IDOR inter-utilisateurs/inter-tenants, RLS sans contexte, clés révoquées, contrôle de versions, idempotence, quotas, annulation, export déterministe, validation humaine et invalidation d’export.
