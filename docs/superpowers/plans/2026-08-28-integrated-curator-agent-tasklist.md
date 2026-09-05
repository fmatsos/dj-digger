# Integrated Curator Agent — Suggestive Implementation Tasklist

> Cette tasklist est **indicative, pas normative**.
>
> Avant toute implémentation, l’agent DOIT inspecter le dépôt réel, lire les instructions locales (`AGENTS.md`, `CLAUDE.md`, documentation d’architecture), vérifier l’état des migrations et du code déjà présent, puis confronter :
>
> 1. le code réel ;
> 2. le plan `2026-08-28-integrated-curator-agent.md` ;
> 3. cette tasklist.
>
> Si le dépôt a évolué ou si une hypothèse du plan est devenue fausse, l’agent doit **corriger/affiner son ordre d’exécution et ses choix techniques avant de coder**. Le code réel et les invariants du dépôt priment sur cette liste.

---

## 0. Preflight — Réconcilier le plan avec le dépôt réel

- [ ] Lire les instructions applicables à la racine et dans les sous-répertoires concernés :
  - `AGENTS.md`
  - `CLAUDE.md`
  - `src/dj_digger/AGENTS.md`
  - `src/dj_digger/catalog/AGENTS.md`
  - `tests/AGENTS.md`
  - toute instruction plus locale découverte pendant l’exploration.
- [ ] Lire :
  - `docs/ARCHITECTURE.md`
  - le plan mastering/DJ analysis V9 ;
  - le plan curator intégré ;
  - les contracts actuels du skill `electronic-dj-set-curator`.
- [ ] Vérifier la version réelle du catalogue :
  - `CURRENT_VERSION`
  - `CURRENT_SCHEMA`
  - migrations disponibles ;
  - état réel de V9 mastering/DJ analysis.
- [ ] Vérifier si certaines parties prévues par le plan curator ont déjà été implémentées depuis sa rédaction.
- [ ] Cartographier les fichiers et APIs réellement concernés avant modification :
  - config ;
  - application/composition root ;
  - CLI ;
  - catalog/repositories ;
  - exports ;
  - schemas ;
  - tests ;
  - packaging.
- [ ] Identifier les divergences entre code réel et plan :
  - noms/types devenus obsolètes ;
  - migrations renumérotées ;
  - fichiers déplacés ;
  - responsabilités déjà refactorées ;
  - primitives réutilisables apparues entre-temps.
- [ ] Produire avant codage une courte note d’exécution interne :
  - hypothèses confirmées ;
  - hypothèses corrigées ;
  - tâches fusionnées/séparées ;
  - nouveaux risques ;
  - ordre final retenu.
- [ ] Si Catalog V9 n’est pas effectivement disponible, **ne pas démarrer la migration curator V10**.
- [ ] Exécuter un baseline de tests ciblés avant toute modification et noter les éventuelles défaillances préexistantes.

**Gate :** aucune implémentation curator ne commence avant cette réconciliation.

---

## 1. Stabiliser le contrat de configuration LLM

- [ ] Vérifier le modèle de configuration actuel et sa façon de charger/valider le TOML.
- [ ] Ajouter ou adapter un `CuratorConfig` uniquement si cela reste cohérent avec le code réel.
- [ ] Prévoir au minimum :
  - modèle ;
  - endpoint OpenAI-compatible ;
  - nom de variable d’environnement contenant l’API key ;
  - timeout ;
  - nombre maximum de tours agentiques.
- [ ] Ne jamais stocker la clé API directement dans le TOML.
- [ ] Autoriser `http://` seulement pour localhost/loopback ; exiger HTTPS à distance.
- [ ] Laisser le curator optionnel : l’absence de `[curator]` ne doit casser aucune autre commande.
- [ ] Ajouter les tests de parsing/validation nécessaires.
- [ ] Vérifier le packaging de la config et les examples TOML.

**Acceptance :** une workspace sans curator fonctionne comme avant ; `curate` échoue proprement si sa configuration manque.

---

## 2. Isoler le fournisseur OpenAI-compatible

- [ ] Vérifier la meilleure intégration avec le SDK réellement retenu dans le projet.
- [ ] Introduire un port applicatif indépendant du SDK, par exemple `ChatModelClient`.
- [ ] Encapsuler complètement l’implémentation OpenAI-compatible derrière ce port.
- [ ] Supporter :
  - streaming de texte ;
  - tool calls ;
  - arguments de tool calls fragmentés sur plusieurs chunks.
- [ ] Ne laisser aucun type `openai.*` fuiter dans le domaine/curation.
- [ ] Gérer proprement :
  - erreurs fournisseur ;
  - timeout ;
  - stream interrompu ;
  - réponse protocolaire incomplète.
- [ ] Ajouter des tests unitaires avec doubles/fakes, sans réseau externe.

**Acceptance :** le runtime curator peut être testé sans dépendre d’OpenAI et sans modifier le domaine si le SDK change.

---

## 3. Formaliser les types métier du curator

- [ ] Vérifier les identités canoniques actuelles du catalogue.
- [ ] Utiliser `(source_id, track_id)` comme référence agentique si cette hypothèse est toujours confirmée par le code.
- [ ] Ne pas utiliser le path comme identité interne.
- [ ] Définir des DTO compacts pour :
  - contexte bibliothèque ;
  - candidat résumé ;
  - détail de candidat ;
  - transition évaluée ;
  - set draft ;
  - alternative ;
  - validation.
- [ ] Conserver explicitement les données manquantes comme `None`/unknown.
- [ ] Ajouter une rationale factuelle aux choix sans demander ni stocker de chain-of-thought.
- [ ] Vérifier que les structures sont compatibles avec strict mypy/Ruff et les conventions existantes.

**Acceptance :** les structures du curator ne dépendent ni de SQLite row objects, ni du SDK LLM, ni du filesystem.

---

## 4. Définir la surface de tools minimale

- [ ] Revalider que six tools suffisent après inspection du code réel :
  - `get_library_context`
  - `search_candidates`
  - `get_candidates`
  - `evaluate_sequence`
  - `ask_user`
  - `submit_set_draft`
- [ ] N’ajouter un tool supplémentaire que si le code réel démontre un besoin non couvert, et documenter pourquoi.
- [ ] Interdire toute surface générique :
  - SQL ;
  - filesystem ;
  - arbitrary query ;
  - save ;
  - export ;
  - write.
- [ ] Définir des schemas JSON bornés :
  - tailles maximales ;
  - listes limitées ;
  - propriétés inconnues refusées.
- [ ] Valider localement les arguments des tools.
- [ ] Vérifier que les payloads envoyés au LLM sont compacts et ne contiennent pas de chemins absolus.
- [ ] Ajouter les tests de sécurité/contrat des tools.

**Acceptance :** le modèle ne peut ni lire arbitrairement le catalogue, ni écrire, ni contourner les services applicatifs.

---

## 5. Créer/adapter le read model de curation

- [ ] Examiner `library_tracks`, les read repositories existants et les projections V9.
- [ ] Réutiliser les projections existantes dès que possible au lieu de recréer une seconde logique de lecture.
- [ ] Ajouter un repository dédié uniquement si cela clarifie réellement la surface curator.
- [ ] Fournir un résumé de bibliothèque compact :
  - volumétrie ;
  - couverture d’analyse ;
  - plages BPM/durée ;
  - qualité ;
  - couverture mastering/DJ.
- [ ] Fournir une recherche de candidats bornée avec filtres pertinents.
- [ ] Utiliser keyset pagination si le code existant confirme ce pattern.
- [ ] Ajouter un chargement détaillé limité à une petite liste de `TrackRef`.
- [ ] Ne jamais exposer le gros payload brut d’analyse si quelques champs suffisent.
- [ ] Intégrer les informations V9 utiles :
  - mastering ;
  - gain requis/disponible ;
  - déficit éventuel ;
  - comparaison duplicate/version.
- [ ] Vérifier les query plans et indexes si de nouvelles requêtes sont ajoutées.
- [ ] Couvrir les politiques :
  - track présent ;
  - source enabled ;
  - `set_eligible=true`.

**Acceptance :** les tools disposent des facts nécessaires sans donner un accès généraliste à SQLite.

---

## 6. Porter les invariants de curation en code déterministe

- [ ] Relire le skill curator actuel et distinguer :
  - ce qui est simple instruction éditoriale pour le LLM ;
  - ce qui doit devenir une règle applicative.
- [ ] Centraliser les sept stratégies de transition dans un enum/type unique.
- [ ] Implémenter ou adapter l’évaluation déterministe des transitions :
  - BPM/pitch ;
  - régions disponibles ;
  - stabilité ;
  - low-end ;
  - mastering/gain ;
  - avertissements ;
  - confiance.
- [ ] Ne pas inventer de score quand les facts sont insuffisants.
- [ ] Déterminer les stratégies possibles à partir des données réellement observées.
- [ ] Implémenter la validation de draft :
  - identité ;
  - positions ;
  - disponibilité ;
  - éligibilité ;
  - hard constraints ;
  - cohérence des transitions ;
  - alternatives ;
  - durée ;
  - données manquantes ;
  - duplication du core ;
  - politique mono/multi-source réelle retenue.
- [ ] Retourner des erreurs structurées exploitables par l’agent pour corriger son draft.
- [ ] Reprendre autant que possible les fixtures/evals existantes.

**Acceptance :** une proposition incorrecte du LLM est rejetée par le code avant toute persistance.

---

## 7. Implémenter la registry des tools

- [ ] Construire une registry explicite entre schemas et handlers.
- [ ] Vérifier le nom du tool avant dispatch.
- [ ] Valider les arguments JSON avant appel métier.
- [ ] Mapper les exceptions internes vers des erreurs bornées.
- [ ] Ne jamais exposer traceback ou SQL au LLM.
- [ ] Traiter `ask_user` comme un événement de contrôle.
- [ ] Traiter `submit_set_draft` comme une tentative de terminaison/validation, pas comme une sauvegarde.
- [ ] Ajouter des tests pour :
  - tool inconnu ;
  - JSON invalide ;
  - arguments hors limites ;
  - handler en échec ;
  - question utilisateur ;
  - draft valide/invalide.

**Acceptance :** tous les appels du modèle passent par une unique frontière contrôlée et testée.

---

## 8. Implémenter la boucle agentique interactive

- [ ] Vérifier l’architecture CLI actuelle pour choisir le bon point d’intégration.
- [ ] Construire la conversation :
  - system prompt ;
  - demande utilisateur ;
  - assistant turns ;
  - tool results ;
  - réponses utilisateur aux clarifications.
- [ ] Streamer le contenu utile vers le terminal.
- [ ] Accumuler les tool calls proprement.
- [ ] Supporter plusieurs tours jusqu’à :
  - clarification ;
  - correction d’un draft ;
  - `submit_set_draft` validé.
- [ ] Imposer `max_tool_rounds`.
- [ ] Refuser une terminaison libre sans draft validé.
- [ ] Ne jamais déduire une question utilisateur depuis une simple phrase avec `?` : utiliser le tool `ask_user`.
- [ ] Garder le transcript en mémoire uniquement pendant la session, sauf besoin réel revalidé.
- [ ] Tester la boucle avec un faux fournisseur déterministe.

**Acceptance :** une demande vague provoque une vraie question interactive puis reprend la même session.

---

## 9. Ajouter le system prompt embarqué

- [ ] Réévaluer le contenu du skill existant et n’en transférer que ce qui est utile à l’orchestration LLM.
- [ ] Expliquer :
  - rôle de curator ;
  - hard constraints ;
  - narration ;
  - usage des tools ;
  - incertitude ;
  - obligation de questionner quand nécessaire ;
  - `submit_set_draft` comme terminaison.
- [ ] Interdire :
  - facts inventés ;
  - accès non fourni ;
  - sauvegarde ;
  - export ;
  - exposition de chain-of-thought.
- [ ] Ne pas dupliquer dans le prompt les règles déjà garanties par le code sauf rappel court.
- [ ] Charger le prompt via `importlib.resources`.
- [ ] Tester son inclusion dans le wheel.

**Acceptance :** le prompt reste mince ; la sécurité et la validation ne reposent pas sur lui.

---

## 10. Construire le reporting final déterministe

- [ ] Examiner les renderers Rich existants avant d’en créer un nouveau.
- [ ] Produire le rapport à partir du draft validé et des facts applicatifs.
- [ ] Inclure :
  - brief compris ;
  - résumé de validation ;
  - core setlist ;
  - transitions ;
  - alternatives ;
  - trajectoire/narration ;
  - mastering/gain si pertinent ;
  - incertitudes ;
  - checks finaux.
- [ ] Pour chaque morceau, afficher une rationale synthétique fondée sur les facts.
- [ ] Ne pas exposer de chain-of-thought.
- [ ] Rendre clairement visibles les informations manquantes.
- [ ] Ajouter les tests de rendu stables sur les informations critiques, sans surtester la mise en forme.

**Acceptance :** le rapport est reproductible depuis le draft validé sans nouvel appel LLM.

---

## 11. Ajouter la commande `curate`

- [ ] Vérifier la convention Typer réelle du projet.
- [ ] Ajouter :
  - prompt utilisateur ;
  - `--config`.
- [ ] Ne pas ajouter `--background`.
- [ ] Vérifier si un mode non-TTY est nécessaire ; sinon, le refuser proprement.
- [ ] Initialiser le client LLM uniquement pour cette commande.
- [ ] Résoudre l’API key au runtime depuis l’environnement.
- [ ] Exécuter la boucle interactive.
- [ ] Afficher le reporting final.
- [ ] Demander :
  - `Save this curated set? [y/N]`
- [ ] Si refus :
  - ne rien écrire ;
  - sortir avec succès.
- [ ] Si accepté :
  - déléguer la persistance à l’application/repository.
- [ ] Ne pas faire passer le transcript/prompt par le logging générique si celui-ci sérialise le diagnostic complet.

**Acceptance :** `curate` réalise une curation complète mais aucune sauvegarde n’est possible sans confirmation explicite.

---

## 12. Durcir la confidentialité et les logs

- [ ] Auditer le logging actuel avant intégration.
- [ ] Ne jamais logger :
  - prompt utilisateur ;
  - transcript ;
  - résultats complets des tools ;
  - titres/artistes/paths ;
  - API key ;
  - réponse utilisateur à une clarification.
- [ ] Autoriser uniquement une télémétrie opérationnelle minimale :
  - event ;
  - status ;
  - model ;
  - tool round count ;
  - identity du set si acceptable selon les règles du repo ;
  - saved true/false.
- [ ] Si l’identity du set peut elle-même contenir une donnée sensible, la retirer du log.
- [ ] Ajouter des tests négatifs par recherche de contenu sensible dans les logs.

**Acceptance :** aucune donnée de bibliothèque privée ne fuit dans les fichiers de logs.

---

## 13. Ajouter la persistance Catalog V10

- [ ] Re-vérifier au moment d’implémenter que V9 est bien la version précédente réelle.
- [ ] Si le catalogue a encore évolué, renuméroter proprement la migration au lieu de forcer V10.
- [ ] Concevoir les tables à partir du modèle actuel du catalogue, en gardant :
  - set metadata ;
  - approved structured draft ;
  - membres core/alternatives ;
  - FKs vers les tracks ;
  - références vers les analyses courantes si pertinent.
- [ ] Éviter de persister les paths comme identité canonique.
- [ ] Capturer assez d’evidence IDs pour détecter une setlist devenue stale après réanalyse.
- [ ] Revalider le draft juste avant la transaction.
- [ ] Sauvegarder set + membres atomiquement.
- [ ] Ne pas autoriser overwrite silencieux d’une identity existante en V1 sauf décision contraire issue de la réconciliation.
- [ ] Ajouter les tests :
  - fresh schema ;
  - migration ;
  - rollback ;
  - FK check ;
  - collision identity ;
  - all-or-nothing ;
  - conservation des anciennes données.

**Acceptance :** seul un draft encore valide et explicitement approuvé peut devenir un `dj_set` persistant.

---

## 14. Ajouter la lecture des sets persistés

- [ ] Fournir le minimum nécessaire pour :
  - retrouver un set par identity ;
  - récupérer ses membres ;
  - vérifier leur disponibilité actuelle ;
  - récupérer les evidence IDs sauvegardés.
- [ ] Détecter explicitement :
  - track supprimé/non présent ;
  - source devenue inéligible ;
  - analyse devenue stale ;
  - mastering devenu stale si cela modifie les recommandations.
- [ ] Décider ce qui bloque l’export et ce qui ne produit qu’un warning.
- [ ] Couvrir cette politique par tests.

**Acceptance :** l’export ne dépend pas aveuglément d’un vieux JSON sauvegardé.

---

## 15. Ajouter `export --set`

- [ ] Examiner la commande `export` actuelle et ses conflits d’options réels.
- [ ] Ajouter une option `--set <identity>`.
- [ ] Rendre `--set` incompatible avec les options d’export de facets qui n’ont pas de sens dans ce mode.
- [ ] Charger le set persistant.
- [ ] Résoudre les paths relatifs **au moment de l’export**.
- [ ] Vérifier la disponibilité/éligibilité actuelle des tracks.
- [ ] Générer :
  - `.set.json`
  - `.m3u8`
  - `.md`
- [ ] Réutiliser les emitters existants si possible.
- [ ] Valider le `.set.json` contre le schema public.
- [ ] Publier les trois fichiers de façon atomique/groupée.
- [ ] Ne remplacer aucun export existant si la génération échoue à mi-chemin.
- [ ] Vérifier le cas mono-source/multi-source selon la politique réellement retenue.
- [ ] Ajouter les tests CLI et publication.

**Acceptance :** aucune publication de fichier n’a lieu pendant `curate`; elle n’a lieu que via `export --set`.

---

## 16. Corriger le packaging du schema de set si nécessaire

- [ ] Vérifier dans le code actuel si `schemas/dj-set.schema.json` est réellement présent dans le wheel.
- [ ] Si le bug existe toujours, l’ajouter aux ressources packagées.
- [ ] Vérifier `schema-bundle.json`.
- [ ] Ajouter un test sur wheel installé plutôt qu’un simple test depuis le checkout.

**Acceptance :** `dj-set.schema.json` est disponible via les resources dans une installation réelle.

---

## 17. Recycler les evals curator existantes

- [ ] Ne pas supprimer les evals actuelles.
- [ ] Identifier lesquelles testent :
  - membership ;
  - paths ;
  - contraintes ;
  - facts ;
  - stratégies ;
  - incertitude ;
  - branches ;
  - ambiguïtés ;
  - artifacts.
- [ ] Réutiliser les mêmes datasets pour tester :
  - read model ;
  - validator ;
  - evaluator ;
  - exporter.
- [ ] Adapter uniquement ce qui dépend spécifiquement de l’ancien skill/export workflow.
- [ ] Garder un test de compatibilité avec `dj-set.schema.json` V2.

**Acceptance :** les protections acquises par l’ancien curator ne sont pas perdues avec l’intégration.

---

## 18. Ajouter un smoke OpenAI-compatible local

- [ ] Créer un faux serveur local HTTP/SSE ; aucune requête externe CI.
- [ ] Faire passer le vrai client OpenAI-compatible contre ce serveur.
- [ ] Simuler plusieurs tours :
  - contexte ;
  - recherche ;
  - question utilisateur ;
  - évaluation ;
  - soumission.
- [ ] Fragmenter volontairement les arguments JSON d’un tool call sur plusieurs chunks.
- [ ] Tester une erreur fournisseur.
- [ ] Tester un stream interrompu.
- [ ] Si le SDK choisi ne permet pas facilement ce type de test, réévaluer la frontière fournisseur avant d’empiler des mocks fragiles.

**Acceptance :** le chemin protocolaire réel est testé sans dépendance réseau externe.

---

## 19. Mettre à jour la documentation

- [ ] Mettre à jour `README.md`.
- [ ] Mettre à jour `docs/ARCHITECTURE.md`.
- [ ] Mettre à jour `config/dj-digger.example.toml`.
- [ ] Mettre à jour le skill curator existant pour expliquer son nouveau rôle :
  - legacy/external workflow ;
  - ou compatibilité ;
  - ou documentation downstream, selon la décision réelle.
- [ ] Corriger les références de version de catalog devenues obsolètes.
- [ ] Corriger les passages disant que duplicate/fingerprint/mastering n’existent pas si ce n’est plus vrai.
- [ ] Documenter explicitement :
  - `curate != export`
  - `validation != persistence`
  - `persistence != publication`
- [ ] Ajouter exemples :
  - config ;
  - API key ;
  - curate ;
  - export --set.

**Acceptance :** un nouvel utilisateur peut comprendre le lifecycle sans lire le code.

---

## 20. QA finale et revue des invariants

- [ ] Exécuter les tests ciblés curator.
- [ ] Exécuter la suite complète.
- [ ] Exécuter Ruff.
- [ ] Exécuter le format check.
- [ ] Exécuter mypy strict.
- [ ] Exécuter les scripts QA du dépôt réellement présents.
- [ ] Vérifier le wheel/package.
- [ ] Vérifier `foreign_key_check`.
- [ ] Vérifier les migrations sur :
  - base fraîche ;
  - copie migrée depuis la version précédente.
- [ ] Vérifier qu’aucun fichier source audio n’est modifié.
- [ ] Vérifier qu’aucun path privé ou titre réel n’a été ajouté dans des fixtures/docs/logs commitables.
- [ ] Vérifier qu’aucune clé API ou variable secrète n’est présente dans le diff.
- [ ] Vérifier que les tools réels correspondent à la surface approuvée.
- [ ] Vérifier qu’aucun write n’est accessible au LLM.
- [ ] Vérifier qu’un `n` à la confirmation laisse SQLite inchangé.
- [ ] Vérifier qu’un `y` persiste sans exporter.
- [ ] Vérifier que seul `export --set` écrit les trois publications.

---

# Suggested milestones

## Milestone A — Curator read-only fonctionnel

Tasks indicatives :

- 0 à 10

Résultat attendu :

- agent connecté ;
- tools bornés ;
- questions interactives ;
- set draft validé ;
- rapport final ;
- aucune persistance.

## Milestone B — Validation humaine + persistance

Tasks indicatives :

- 11 à 14

Résultat attendu :

- commande `curate` complète ;
- confirmation explicite ;
- Catalog version suivante ;
- set approuvé stocké ;
- aucun export automatique.

## Milestone C — Publication et compatibilité

Tasks indicatives :

- 15 à 19

Résultat attendu :

- `export --set`;
- schema/playlist/report ;
- evals recyclées ;
- intégration OpenAI-compatible testée ;
- documentation cohérente.

## Milestone D — Release gate

Task :

- 20

Résultat attendu :

- suite QA complète verte ;
- invariants de confidentialité et d’autorité vérifiés ;
- aucune hypothèse obsolète du plan laissée dans le code.

---

# Agent execution rule

Avant chaque milestone, et particulièrement après des changements structurants dans le dépôt :

- [ ] relire les fichiers touchés ;
- [ ] revalider que la prochaine tâche correspond encore au code réel ;
- [ ] ajuster les tâches restantes si une meilleure primitive existe désormais ;
- [ ] ne pas implémenter mécaniquement un nom de classe, un numéro de migration ou une structure SQL uniquement parce qu’ils figurent dans le plan ;
- [ ] préserver le comportement observable et les invariants approuvés, même si l’implémentation exacte diffère.

Le plan fixe **l’intention et les contraintes**.  
Cette tasklist fixe **un chemin suggéré**.  
Le dépôt réel fixe **la manière correcte de l’implémenter**.
