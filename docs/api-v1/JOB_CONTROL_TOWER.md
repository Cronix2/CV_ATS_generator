# Intégration Job Control Tower

Ce dépôt fournit les façades `/api/v1/render` et `/api/v1/review` prévues par l'audit
PasseFiltre de Job Control Tower, ainsi que des ressources et workflows asynchrones.
Aucune modification du dépôt Job Control Tower n'est incluse dans cette PR.

## Contrat du service appelant

Configurer côté serveur JCT : URL de PasseFiltre, clé de service tenant `jct` et référence
de fournisseur autorisée. Le worker JCT transmet `X-PasseFiltre-User-Id` à partir de son
utilisateur authentifié. Ne pas réutiliser un identifiant global pour tous les utilisateurs,
ne pas envoyer une adresse email comme identifiant et ne jamais exposer la clé au navigateur.

| Besoin JCT | Appel PasseFiltre | Responsabilité JCT |
| --- | --- | --- |
| PDF/DOCX sur des faits validés | `POST /render` | Ajouter les coordonnées seulement à l'étape de rendu ; stocker hash/version du résultat |
| Relecture et propositions | `POST /review` ou `/enhancements` | Retirer les données inutiles, afficher les suggestions pour validation |
| Comparaison ATS | `POST /ats/analyses` | Fournir l'offre dans `cv.settings.target.offer_text` |
| Import d'offre | `POST /offers/import` puis lecture du job | Conserver la provenance ; gérer les erreurs de téléchargement protégé |
| Workflow ciblé | `POST /workflows`, lecture, édition, approbation | Présenter source/brouillon/changements et recueillir une confirmation humaine explicite |

JCT n'a pas besoin de permissions LinkedIn ni d'identifiants LinkedIn. Utiliser des clés
distinctes pour les autres intégrateurs. Une clé JCT compromise permet d'agir pour les
utilisateurs du tenant JCT : sa conservation et l'authentification en amont sont essentielles.

## Façades synchrones

`render` prend `schema_version`, `cv` et `format` (`pdf` ou `docx`). La réponse est binaire.
À entrée normalisée et version d'image identiques, le rendu est déterministe ; vérifier
`X-Content-SHA256` et conserver `X-PasseFiltre-Version`. Un changement de bibliothèque ou de
version peut légitimement produire un autre hash.

`review` prend `schema_version`, `cv`, une `offer` facultative, `agents` et
`llm: {"provider_ref":"jct"}`. La réponse contient `suggestions`, `grounding`, `usage`,
`passefiltre_version` et une notice de validation humaine. `usage.known=false` et des compteurs
`null` signifient que le fournisseur n'a pas transmis ses mesures ; ne pas les compter comme
une consommation nulle. La référence est résolue exclusivement côté PasseFiltre ; les clés
et URL arbitraires ne sont pas des paramètres client.

La relecture ne garantit pas la vérité de la prose. Les compétences inconnues et références
structurelles sans source sont filtrées, les qualifications du CV source restent inchangées,
mais les reformulations proposées exigent une revue humaine. JCT ne doit pas appliquer les
suggestions automatiquement à son profil de référence.

## Idempotence et erreurs

Enregistrer un `Idempotency-Key` stable dans la tâche JCT **avant** l'appel réseau. Réutiliser
ce même en-tête et le même corps après un timeout. Ne pas générer une nouvelle clé à chaque
retry. La garantie dure la période de rétention (24 h par défaut) et concerne la publication
du résultat, pas une garantie de facturation unique chez un fournisseur externe.

Traiter `401/403` comme un problème de clé/permissions ; `404` comme absent ou inaccessible ;
`409/412/428` comme un conflit qui nécessite une nouvelle lecture ; `422` comme une entrée à
corriger ; `429` selon `Retry-After` ; `503` comme une dépendance indisponible. Ne pas logger
les corps CV, les clés ou les erreurs brutes de fournisseurs. Conserver le `request_id`.

Pour les traitements longs, privilégier `202` + polling avec délai. Conserver le `job_id`,
le `resource_id`, la version et le digest du brouillon dans les métadonnées JCT. L'approbation
doit envoyer exactement le digest présenté à l'humain. Une édition après approbation invalide
les exports liés au workflow, y compris si un worker est encore en train de les produire.

Les fichiers sont conservés temporairement dans PostgreSQL et téléchargeables seulement
avec le contexte propriétaire. JCT peut importer le fichier dans son propre stockage après
validation, selon sa politique de rétention. Les routes de rendu direct restent destinées
aux CV déjà validés par JCT ; seul le workflow impose la validation humaine côté PasseFiltre.
