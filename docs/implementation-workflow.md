# Workflow d’implémentation multi-agent allégé

**Version :** 1.0 — 24 août 2026
**Objet :** fournir une procédure réutilisable pour exécuter une suite de tâches rapidement, avec une consommation maîtrisée de contexte et de quota, sans sacrifier la robustesse.

## Principes directeurs

Le travail avance par petites tranches verticales indépendantes. Une tâche n’est clôturée que lorsque son comportement attendu est démontré sur le chemin réellement exécuté par le produit.

- Une seule tâche est active à la fois, sauf si plusieurs travaux sont manifestement indépendants.
- Le plus petit modèle capable d’accomplir correctement le travail est privilégié.
- Une seule boucle implémentation/revue est utilisée par défaut. Une seconde revue n’est déclenchée que par le risque ou par un doute concret.
- Les tests observent le comportement produit. Les mocks et fakes servent aux tests unitaires, mais ne prouvent pas à eux seuls une intégration.
- Chaque tâche laisse un état Git lisible et une preuve de vérification reproductible.
- Les documents de spécification historiques ne sont pas modifiés pour faire correspondre les affirmations à l’implémentation. Les écarts sont consignés séparément.

### Vocabulaire de clôture

- **Chemin de production réel** : composition et point d’entrée utilisés par l’utilisateur, exécutés sans remplacer le composant vérifié par un double de test. La preuve minimale est la commande publique ou un test d’intégration qui instancie cette même composition et observe sa sortie, son état ou ses artefacts.
- **COMPLETE** : comportement nominal et échec significatif démontrés sur ce chemin, contrôles verts et aucun reste requis pour le périmètre.
- **PARTIAL** : une partie exécutable existe, mais le raccordement, une preuve requise ou un critère d’acceptation manque.
- **MISSING** : aucun chemin exécutable ne fournit le comportement demandé.
- **BLOCKED** : la suite exige une décision, une autorisation ou une dépendance externe indisponible. Le blocage et son propriétaire sont consignés ; il ne vaut pas acceptation.

## Répartition des rôles

| Rôle | Modèle | Effort | Usage |
|---|---|---:|---|
| Supervision et revue L2 | GPT-5.6 Terra | medium | Comprendre la tâche, borner le périmètre, arbitrer, contrôler les preuves et clôturer |
| Implémentation complexe ou revue L1 | GPT-5.6 Terra | low | Tranche nécessitant plusieurs fichiers, décisions locales ou exploration approfondie |
| Implémentation simple ou exploration | GPT-5.6 Luna | low à medium | Changement mécanique, test ciblé, repérage de code ou vérification isolée |

Un agent n’est pas créé pour reproduire une analyse déjà disponible. Le superviseur conserve l’orchestration globale ; l’agent d’implémentation reçoit une mission autonome, bornée et accompagnée des critères d’acceptation utiles.

Si le modèle préféré n’est pas disponible, utiliser le modèle disponible de capacité immédiatement supérieure, avec le même effort cible. Ne jamais réduire les critères de preuve pour s’adapter au modèle.

## Boucle d’une tâche

### 1. Cadrer

Le superviseur lit la tâche, ses dépendances et l’état courant du dépôt. Il formule avant toute modification :

- le comportement observable à obtenir ;
- les fichiers ou sous-systèmes probablement concernés ;
- le test ciblé qui prouvera le changement ;
- le niveau de risque : faible, moyen ou élevé.

L’exploration reste courte. Dans un dépôt indexé, utiliser CodeGraph avant une recherche textuelle ; utiliser la recherche sémantique lorsque le bon symbole n’est pas connu. Ne pas multiplier les recherches une fois le chemin d’exécution identifié.

### 2. Choisir l’exécutant minimal

- **Luna** : changement local et mécanique, contrat clair, faible blast radius.
- **Terra low** : logique métier, plusieurs composants, migration ou investigation plus profonde.
- **Superviseur directement** : correction triviale déjà entièrement comprise, ou ajustement issu de la revue.

Par défaut, un seul agent réalise l’implémentation et sa vérification ciblée. Les agents parallèles sont réservés à des sous-tâches qui ne modifient pas les mêmes fichiers, n’attendent pas le résultat l’une de l’autre et peuvent être vérifiées séparément. Sinon, les exécuter séquentiellement.

### 3. Obtenir un RED pertinent

Avant le code de production, ajouter ou sélectionner un test qui échoue pour la raison attendue. Le RED doit porter sur un résultat observable : sortie CLI, état persistant, artefact exporté, code de retour ou erreur métier.

Un test déjà vert, un mock qui vérifie seulement un appel ou une injection de faux contournant la composition de production ne constituent pas un RED valable pour une tâche d’intégration.

Le RED n’est pas artificiellement imposé aux changements purement documentaires ou mécaniques sans comportement exécutable. Dans ce cas, définir avant l’édition une validation objective — rendu, lien, format, recherche d’ancienne valeur ou `git diff --check` — puis démontrer qu’elle passe après l’édition.

### 4. Implémenter le minimum robuste

Écrire le plus petit changement qui rend le test vert tout en respectant les contrats existants. Éviter les abstractions anticipées, les refactorings sans lien avec la tâche et les dépendances supplémentaires non nécessaires.

L’agent ne modifie que son périmètre et préserve les changements existants du dépôt. Il rapporte : fichiers changés, preuve RED, preuve GREEN et éventuels risques résiduels.

### 5. Effectuer la revue L1

Pour une tâche simple, la revue L1 est une auto-vérification structurée de l’implémenteur :

- conformité au critère d’acceptation ;
- cas d’erreur et valeurs limites ;
- absence de régression évidente ;
- diff limité au périmètre ;
- test ciblé vert.

Un agent L1 distinct n’est utilisé que si la tâche est de risque moyen ou élevé, si le diff est difficile à relire, ou si l’implémenteur signale une incertitude.

### 6. Passer la revue L2

Le superviseur relit le diff et vérifie la preuve, sans refaire toute l’exploration. Il contrôle en priorité :

- que le test aurait bien échoué sans la correction ;
- que le chemin de production est raccordé ;
- que les échecs sont visibles par l’appelant ;
- que les artefacts annoncés sont réellement produits ;
- que la tâche ne repose pas uniquement sur des doubles de test.

Si le risque est faible et les preuves nettes, cette revue reste courte. Si une faille concrète apparaît, l’implémenteur corrige puis le superviseur revalide le point concerné.

### 7. Vérifier et clôturer

Exécuter d’abord le test ciblé, puis les contrôles proportionnés au risque. Pour une tâche touchant plusieurs couches ou avant un jalon, lancer la suite complète ainsi que le lint et le typage.

Une tâche est **COMPLETE** seulement si :

1. le chemin de production existe ;
2. le comportement nominal est prouvé ;
3. au moins l’échec significatif est prouvé ;
4. les contrôles pertinents sont verts ;
5. le diff ne contient pas de changement hors périmètre.

Sinon elle reste **PARTIAL** ou **MISSING**, même si les tests unitaires sont verts.

Après validation, créer un commit atomique au libellé orienté comportement. Ne jamais inclure des fichiers utilisateur ou des documents de spécification non autorisés.

Une autorisation doit venir de la demande utilisateur ou des règles explicites du dépôt. En cas de doute sur un fichier ou une opération externe, laisser la tâche `BLOCKED` avec la décision précise attendue.

### Profil QA de ce dépôt

Le guide est réutilisable, mais chaque dépôt doit définir son profil QA avant la première tâche. Pour DJ Digger :

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx --with typer --with jsonschema --with pytest --with numpy pytest -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx ruff check src tests
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx --with typer --with jsonschema --with numpy mypy src
python3 tests/validate_fixtures.py
git diff --check
```

Dans un autre dépôt, remplacer ce bloc par les commandes officielles de tests, lint, typage, validation d’artefacts et contrôle du diff. Le rapport de tâche cite les commandes réellement exécutées ; « QA OK » seul n’est pas une preuve.

## Niveau de contrôle selon le risque

| Risque | Exemples | Contrôle attendu |
|---|---|---|
| Faible | Documentation, renommage local, fixture | Test ou validation ciblée, diff check, revue L2 rapide |
| Moyen | Logique métier, export, persistance | RED/GREEN ciblé, revue L1 explicite, tests du sous-système, revue L2 |
| Élevé | Composition runtime, migration, CLI, parcours réel | RED/GREEN d’intégration, revue indépendante si utile, suite complète, essai du chemin réel |

La revue supplémentaire dépend donc du risque, pas du numéro de la tâche ni d’un rituel fixe.

## Exécution automatique d’une série

Pour dérouler plusieurs tâches automatiquement :

1. traiter les tâches dans l’ordre de leurs dépendances ;
2. appliquer la boucle complète à chacune ;
3. arrêter la série dès qu’un critère requiert une décision produit, une autorisation externe ou une dépendance indisponible, et consigner qui peut lever le blocage ;
4. ne jamais convertir silencieusement un blocage en acceptation ;
5. produire un bref état après chaque tâche : statut, commit, vérifications et réserve éventuelle.

Les lots annoncés, par exemple « jusqu’à la tâche 20 incluse », sont une borne d’exécution et non une autorisation à affaiblir les critères de clôture.

## Gestion du contexte et du quota

- Viser un seul agent par tâche ; zéro agent pour une correction triviale déjà comprise.
- Transmettre à l’agent uniquement la tâche, les critères, les fichiers connus et les commandes de test utiles.
- Ne pas demander à plusieurs agents la même exploration ou une revue générale systématique.
- Préférer les tests ciblés pendant la boucle ; réserver la QA complète aux tâches transverses et aux jalons.
- Résumer les résultats, sans recopier les longs contenus de fichiers ou sorties de tests.
- Réutiliser un agent existant pour une correction directement liée lorsqu’il possède encore le contexte utile.

Lorsque l’indicateur de contexte de l’interface atteint **30 % d’usage ou davantage**, terminer la tâche en cours, consigner son état et s’arrêter avant la suivante. Si l’interface ne fournit pas cet indicateur, faire un point de reprise à chaque jalon annoncé ou dès que le contexte est compacté automatiquement.

Le point de reprise destiné au compactage manuel doit contenir : dernière tâche et statut, commit éventuel, prochain objectif, état Git, commandes QA exécutées, risques et blocages ouverts. La session suivante relit ce point et vérifie l’état Git avant de reprendre ; elle ne réexécute pas les tâches déjà clôturées.

## Rapport minimal par tâche

```text
Task N — COMPLETE | PARTIAL | BLOCKED
Commit : <hash et sujet, ou aucun>
Preuve : <RED observé puis GREEN / parcours réel>
QA     : <commandes ou contrôles exécutés>
Reste  : <aucun, ou risque précis>
```

## Leçons à conserver

Le run initial des tâches 1 à 30 a montré qu’une succession de commits et une suite verte peuvent masquer des composants non raccordés. En particulier, un faux extracteur injecté dans un test peut valider le pipeline sans prouver que la commande utilisateur sait construire et exécuter l’extracteur réel.

Le workflow réutilisable doit donc optimiser le nombre d’agents et la quantité d’exploration, jamais la preuve finale. Pour les tâches d’intégration, la clôture repose sur un parcours réel de la composition de production et sur une sémantique d’échec observable.

## Prompt de reprise recommandé

```text
Continuer de la task <N> à la task <M> automatiquement avec le workflow
docs/implementation-workflow.md.

Supervision : GPT-5.6 Terra medium.
Implémentation : GPT-5.6 Terra low ou GPT-5.6 Luna selon la complexité.

Appliquer un vrai RED/GREEN, une revue proportionnée au risque et une preuve du
chemin de production. Viser un seul agent par tâche. À 30 % de contexte, finir
la tâche active puis s’arrêter avant la suivante avec un point de reprise.
```
