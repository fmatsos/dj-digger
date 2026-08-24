# Registre de requalification de l’implémentation v1

**Version :** 1.0 — 24 août 2026
**Objet :** requalifier l’état réellement démontré de l’implémentation, sans modifier ni réinterpréter les plans historiques.

## Périmètre et méthode

Ce registre distingue les artefacts produits de l’acceptation du produit en condition réelle. Il s’appuie sur la revue des chemins d’exécution, des tests et des essais de runtime disponibles.

- **COMPLETE** : un chemin de production réel existe et une preuve directe établit son fonctionnement.
- **PARTIAL** : une implémentation existe, mais elle n’est pas raccordée opérationnellement, ou l’acceptation a contourné ce raccordement.
- **MISSING** : aucune implémentation exécutable ne couvre la tâche.

Une suite de tests verte, des doubles injectés ou un historique de commits ne constituent pas, seuls, une preuve d’acceptation.

## Matrice de requalification

| Domaine | Tâches (ordre global) | Statut |
|---|---:|---|
| Catalogue | 1 | PARTIAL |
| Catalogue | 2 | COMPLETE |
| Catalogue | 3 | COMPLETE |
| Catalogue | 4 | COMPLETE |
| Catalogue | 5 | PARTIAL |
| Catalogue | 6 | COMPLETE |
| Catalogue | 7 | PARTIAL |
| Catalogue | 8 | COMPLETE |
| Catalogue | 9 | PARTIAL |
| Analyse | 10 | COMPLETE |
| Analyse | 11 | PARTIAL |
| Analyse | 12 | PARTIAL |
| Analyse | 13 | PARTIAL |
| Analyse | 14 | PARTIAL |
| Analyse | 15 | PARTIAL |
| Analyse | 16 | PARTIAL |
| Analyse | 17 | MISSING |
| Curateur | 18 | PARTIAL |
| Curateur | 19 | PARTIAL |
| Curateur | 20 | PARTIAL |
| Curateur | 21 | PARTIAL |
| Curateur | 22 | PARTIAL |
| Curateur | 23 | PARTIAL |
| Intégration | 24 | COMPLETE |
| Intégration | 25 | PARTIAL |
| Intégration | 26 | COMPLETE |
| Intégration | 27 | PARTIAL |
| Intégration | 28 | PARTIAL |
| Intégration | 29 | PARTIAL |
| Intégration | 30 | PARTIAL |

## Éléments de preuve déterminants

- L’application instancie par défaut un extracteur non configuré (lignes 41 et 227) : le composant existe, mais la composition de production ne lui fournit pas les dépendances nécessaires.
- Le flux de rafraîchissement (lignes 128 à 151) emprunte ce chemin de composition ; il ne démontre donc pas l’extraction utilisable avec des dépendances réelles.
- L’export ne couvre que les pistes et l’audit (lignes 107 à 123) ; les sorties d’analyse attendues ne sont pas exportées par ce flux.
- Lors de l’audit de runtime, les commandes d’analyse et de rafraîchissement retournent le code 0 malgré un échec d’analyse. Le signal opérationnel est donc trompeur.
- Les tests d’acceptation injectent des faux : ils établissent des contrats isolés, pas le raccordement complet avec les composants concrets.
- Des composants concrets sont présents mais déconnectés de la composition exécutée. L’exporteur d’analyse est lui aussi déconnecté.

## Correction des affirmations historiques

Les plans et leurs affirmations historiques restent des références de conception et de suivi. En revanche, « 30 commits » et « tests verts » ne valent pas acceptation du périmètre : l’acceptation exige un parcours de production réel, des dépendances réelles et une preuve directe de son résultat ainsi que de ses échecs.

## Backlog de remédiation priorisé

### Critique — composition de production et sémantique des échecs

Raccorder l’extracteur et ses dépendances de runtime dans la composition réellement exécutée, puis rendre les échecs d’analyse et de rafraîchissement explicitement détectables par l’appelant.

Critères d’acceptation : un lancement standard avec dépendances réelles exécute l’extraction ; un échec provoqué est visible et retourne un statut non ambigu ; les deux cas sont vérifiés sans faux d’intégration.

### Majeur — export d’analyse et schémas de paquets

Raccorder l’export d’analyse au flux produit et stabiliser les schémas des paquets concernés.

Critères d’acceptation : une analyse réelle génère les sorties exportées attendues ; les paquets produits respectent leurs schémas ; un contrôle d’intégration vérifie les données exportées de bout en bout.

### Majeur — produit curateur ou réduction explicite du périmètre

Rendre le curateur exécutable comme produit intégré, ou requalifier explicitement ce sous-périmètre comme non livré.

Critères d’acceptation : soit un utilisateur peut exécuter le parcours curateur réel et observer son résultat, soit les documents de périmètre et la matrice indiquent clairement son report, sans revendication d’acceptation.

### Majeur — intégration sur échantillon réel

Ajouter une vérification de bout en bout sur un échantillon réel représentatif, sans injection de dépendances de test dans le parcours vérifié.

Critères d’acceptation : le scénario traverse la composition de production, produit les artefacts attendus et échoue de façon traçable lorsque sa dépendance réelle est indisponible ou invalide.

### Mineur — parité historique

Mettre à jour les éléments de suivi pour aligner les statuts historiques sur la preuve disponible, sans altérer les plans originaux.

Critères d’acceptation : le présent registre est versionné ; chaque revendication d’acceptation renvoie à une preuve de parcours réel ; les plans initiaux demeurent inchangés.
