# Registre de requalification de l’implémentation v1

**Version :** 1.3 — 27 août 2026
**Tranche :** 8 et Catalog V7 (QA et requalification)
**Objet :** requalifier l’état démontré par le code, les tests et les essais disponibles, sans modifier ni réinterpréter les plans historiques.

## Périmètre et méthode

- **COMPLETE** signifie qu’un chemin exécutable est couvert par une preuve vérifiable (test de contrat, intégration ou artefact contrôlé).
- **PARTIAL** signifie qu’une implémentation existe mais qu’une preuve de production ou un gate externe manque.
- **MISSING** signifie qu’aucune implémentation exécutable ne couvre la tâche.

Les tests à doubles établissent des contrats isolés ; ils ne valent pas, seuls, acceptation d’un runtime externe. Le curateur est requalifié comme skill LLM reconstruit et évalué par son harness hors ligne : cette requalification est **sans prétention de parité moteur absent**.

## Matrice de requalification

| Domaine | Tâches (ordre global) | Statut |
|---|---:|---|
| Catalogue | 1 | COMPLETE |
| Catalogue | 2 | COMPLETE |
| Catalogue | 3 | COMPLETE |
| Catalogue | 4 | COMPLETE |
| Catalogue | 5 | COMPLETE |
| Catalogue | 6 | COMPLETE |
| Catalogue | 7 | COMPLETE |
| Catalogue | 8 | COMPLETE |
| Catalogue | 9 | COMPLETE |
| Analyse | 10 | COMPLETE |
| Analyse | 11 | COMPLETE |
| Analyse | 12 | COMPLETE |
| Analyse | 13 | COMPLETE |
| Analyse | 14 | COMPLETE |
| Analyse | 15 | COMPLETE |
| Analyse | 16 | COMPLETE |
| Analyse | 17 | COMPLETE |
| Curateur | 18 | COMPLETE |
| Curateur | 19 | COMPLETE |
| Curateur | 20 | COMPLETE |
| Curateur | 21 | COMPLETE |
| Curateur | 22 | COMPLETE |
| Curateur | 23 | COMPLETE |
| Intégration | 24 | COMPLETE |
| Intégration | 25 | COMPLETE |
| Intégration | 26 | COMPLETE |
| Intégration | 27 | COMPLETE |
| Intégration | 28 | COMPLETE |
| Intégration | 29 | COMPLETE |
| Intégration | 30 | COMPLETE |

## Preuves vérifiables

### Catalogue et analyse

- `tests/test_strict_current_contracts.py` vérifie le schéma catalogue consolidé courant, le rejet explicite des catalogues anciens, la configuration stricte et la publication canonique.
- `tests/integration/test_v1a_pipeline.py` vérifie la composition publique, la réutilisation, le snapshot et les schémas.
- `tests/test_analysis_eligibility.py`, `test_ffmpeg.py`, `test_rhythm.py`, `test_spectrum.py`, `test_windows.py`, `test_segmentation.py`, `test_semantics.py`, `test_analysis_persistence.py` et `test_analysis_exporters.py` couvrent les contrats des tâches 11–17.
- Le pilote réel local `scripts/acceptance_library_pilot.py` a été exécuté via l’environnement Python 3.12 avec l’extra d’analyse. Le rapport agrégé est `accepted` : 9 pistes bornées, scan/metadata/export/snapshot/archive réussis, deux analyses `partial` en sortie 2, réutilisation à la seconde analyse, source inchangée, deux échecs de décodage contrôlés sur les deux runs, 2 runs et 11 tentatives. Aucun chemin, nom de fichier ou identifiant privé n’est versionné ici.

### Curateur (tâches 18–23)

- `skills/electronic-dj-set-curator/SKILL.md` définit le nouveau contrat LLM source-aware.
- `skills/electronic-dj-set-curator/evals/harness.py`, les cas `acid-rave` et `adversarial`, et `tests/test_skill_tranche6.py` valident les entrées, contraintes, trois artefacts et le rejet d’artefacts inventés.
- `tests/integration/test_tranche7_acceptance.py::test_reconstructed_curator_consumes_canonical_facets_and_emits_three_valid_outputs` vérifie l’évaluation hors ligne. Cette preuve concerne le skill reconstruit, pas un moteur de parité non présent.

### Intégration

- Tâches 24–27 : historique de scan, pipeline V1A, snapshot et publication sont couverts par les tests d’intégration dédiés.
- Tâche 29 : `tests/integration/test_v1b_cutover.py` prouve la consommation directe de `tracks.tsv`.
- Tâche 30 : `tests/integration/test_copy_set_compatibility.py` et `test_validated_curator_m3u8_is_consumed_by_copy_set` vérifient les chemins relatifs, le nombre de fichiers et l’immuabilité de la source.
- Tâche 28 est **COMPLETE** : le pilote local borné traverse la composition réelle, publie les artefacts attendus, démontre l’analyse partielle et sa réutilisation, et confirme l’immuabilité de la source.

## Gate bibliothèque locale : implémentation distincte de l’acceptation

Le pilote est implémenté dans `scripts/acceptance_library_pilot.py` et borné/documenté dans `docs/acceptance/tranche-7-real-gate.md`. Il exige `DJ_DIGGER_LIBRARY_ROOT`, une empreinte stable, puis scan, metadata, export, snapshot et deux analyses réelles.

La preuve locale agrégée est `{"status": "accepted", "bounded_tracks": 9, "scan": true, "metadata": true, "export": true, "snapshot": true, "archive_created": true, "first_analysis_partial": true, "second_analysis_partial": true, "first_exit_code": 2, "second_exit_code": 2, "second_reused": true, "source_unchanged": true, "decode_failures": 2, "runs": 2, "attempts": 11}`. Le rapport ne contient aucun chemin ni nom de fichier privé.

## Commandes et résultats de la tranche 8

Les commandes suivantes sont reproductibles depuis la racine du dépôt :

```text
python3 -m pytest -q
ruff check .
mypy src
python3 tests/validate_fixtures.py
python3 -m build --wheel
python3 scripts/acceptance_library_pilot.py
git diff --check
```

Le résultat détaillé et la présence éventuelle d’outils externes doivent être reportés par l’agent qui exécute la QA finale. Le test documentaire `tests/test_requalification_documentation.py` verrouille la matrice, la preuve locale agrégée et l’absence de revendication trompeuse.

## Historique honnête

Les plans sous `docs/superpowers/plans/` et les spécifications sous `docs/superpowers/specs/` restent inchangés. Les anciennes observations de déconnexion de la composition et d’export d’analyse sont remplacées ici par les preuves des tranches 6–8 ; le pilote local réel est désormais accepté sur ses preuves agrégées, sans divulgation de données privées.

## Requalification Catalog V7 — 27 août 2026

### Verdict et protocole

Le gate obligatoire **100 000 pistes / 500 000 analyses est COMPLETE**. La qualification locale
**250 000 pistes / 2 500 000 analyses est également COMPLETE** sur la machine mesurée ; elle ne
devient pas une fixture CI. Les quatre scénarios demandés (10k/1, 50k/5, 100k/5 et 250k/10) ont
utilisé `tests/performance/fixtures.py` et les cas nommés de
`tests/performance/benchmark_queries.py`.

La base V6 de chaque paire contient les tables et données canoniques, sans les sept indexes V7,
sans `current_track_analysis` et sans `library_tracks`. Après `VACUUM`/`ANALYZE`, une copie exacte
est migrée par `Database.migrate()` : V6 et V7 comparent donc les mêmes lignes. Le driver temporaire
de `/tmp` a ajouté l’orchestration qui manque au harness versionné ; il n’a pas modifié le code du
projet. Pour `library_listing` et `pagination`, V6 exécute un CTE dernier succès SQL-équivalent aux
colonnes et au tri de la vue V7.

Machine : Linux 7.0.0-30-generic x86_64, 14 CPU logiques, Python 3.12.13 (Clang 22.1.3), SQLite
3.53.1. Méthode : un échauffement puis médiane de trois répétitions ; lecture complète du curseur ;
mutation annulée ; connexion stable pour « warm » et nouvelle connexion/page-cache SQLite pour
« cold-connection ». Le cache OS n’a pas été purgé. Les données et bases étaient sous `/tmp` ; au
maximum mesuré, V6 occupait 610,59 MiB et V7 880,32 MiB, sans swap consommé ni pression mémoire.

| Scénario | Analyses | Événements | V6 MiB | V7 MiB | Projection V7 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10k / 1 | 10 000 | 20 000 | 7,63 | 11,14 | 10 000 |
| 50k / 5 | 250 000 | 100 000 | 75,48 | 110,21 | 50 000 |
| 100k / 5 — gate | 500 000 | 200 000 | 150,96 | 221,09 | 100 000 |
| 250k / 10 — qualification | 2 500 000 | 500 000 | 610,59 | 880,32 | 250 000 |

Les médianes complètes warm/cold des douze cas et les plans normalisés sont enregistrés dans
`tests/performance/README.md`. Résultats warm représentatifs au gate 100k :

| Cas | V6 ms | V7 ms | Observation |
| --- | ---: | ---: | --- |
| analysis_eligibility | 474,701 | 116,618 | index couvrant V7 |
| analysis_history | 39,950 | 0,011 | scan V6 remplacé par `idx_audio_analysis_track_history` |
| analysis_export_selection | 1 480,283 | 1 211,042 | index d’historique, tri temporaire supprimé |
| library_listing (1 000) | 483,595 | 5,581 | historique matérialisé à la volée remplacé par la projection |
| pagination (1 000 après id 50 000) | 471,882 | 5,148 | recherche PK et jointures PK |
| scan_reconciliation_select | 44,073 | 37,186 | recherche par index partiel |
| scan_reconciliation_update | 95,408 | 188,815 | régression locale all-match, voir concern ci-dessous |

À 250k/2,5M, les warm medians correspondantes sont : éligibilité 1 870,013 → 387,196 ms,
historique 200,876 → 0,016 ms, sélection export 7 147,387 → 5 018,050 ms, listing
1 628,592 → 5,842 ms et pagination 1 620,747 → 6,195 ms. Cette qualification a été menée à son
terme en 39,992 s pour la construction/migration, puis les mesures ; aucun succès n’est extrapolé.

### Plans et concurrence

Commande ciblée :

```text
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 --with pytest python -m pytest \
  tests/test_query_plans.py tests/test_current_analysis.py \
  tests/test_read_repositories.py tests/test_sqlite_concurrency.py -q
```

Résultat : **30 réussis en 0,91 s**. Les plans du gate 100k confirment notamment :
`analysis_history` passe de `SCAN audio_analysis` à `SEARCH ... USING INDEX
idx_audio_analysis_track_history`; l’éligibilité utilise
`idx_audio_analysis_success_lookup`; les réconciliations utilisent les indexes partiels ; le
listing V7 joint `current_track_analysis` par clé primaire. Les tests dédiés confirment aussi
l’absence de full scan critique de l’historique par run et des événements par run/type. Les quatre
cas de concurrence WAL sont inclus dans ce résultat ; aucun contrôle manuel reste en attente.

### Gates Python 3.12 et environnement

Les commandes littérales du plan sans dépendances éphémères n’étaient pas autonomes dans cet
environnement : `uv run --python 3.12 pytest -q` a résolu le `pytest` système Python 3.14 et échoué
à la collecte faute de Typer ; `ruff` et `mypy` n’étaient pas installés dans le projet. Les commandes
corrigées et leurs résultats sont :

```text
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 --with pytest python -m pytest -q -rs
# 318 réussis en 17,44 s ; 1 smoke Docker opt-in non exécuté

UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx ruff check src tests
# All checks passed!

UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx --with typer --with numpy mypy src
# Success: no issues found in 46 source files
```

Sans accès réseau, la suite complète peut échouer uniquement dans
`test_wheel_contains_snapshot_schema_for_resource_lookup`, car ce test impose son propre cache uv
vide et doit résoudre `hatchling`. Avec l’accès réseau autorisé, la suite ci-dessus passe. Ruff et
mypy passent après résolution des outils ; aucune erreur produit n’a été masquée.

### Wheel, migration, intégrité et exports

Commandes d’acceptation :

```text
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv build --wheel --out-dir /tmp/dj-digger-v7-wheel-gate/dist

PYTHONPATH=/tmp/dj-digger-v7-wheel-gate/installed \
  /home/fmatsos/www/dj-digg/.venv/bin/python \
  /tmp/dj-digger-v7-wheel-gate/gate.py
```

Le wheel frais `dj_digger-0.1.0-py3-none-any.whl` fait 91 234 octets, SHA-256
`882975004f2bf23b61fe6deec42f7f6e8a6decedb6d37ff60cc12a12a0cb1e2b`. Il a été extrait dans un
répertoire isolé ; `dj_digger.__file__` pointait sur ce répertoire, pas sur le checkout.

- Fresh V7 : `user_version=7`, `foreign_key_check=[]`, `quick_check=ok`; exports installés
  `tracks.tsv` (0 ligne, 281 octets) et `library-artifacts.tsv` (0 ligne, 109 octets).
- Upgrade préservé : avant migration `user_version=6`, 1 piste et 3 analyses ; après migration
  `user_version=7`, les cardinalités des 11 tables V6 sont strictement identiques (dont 3 runs,
  3 analyses, 2 événements et 1 section), 1 projection courante, `foreign_key_check=[]`,
  `quick_check=ok`; exports installés `tracks.tsv` (1 ligne, 503 octets) et
  `library-artifacts.tsv` (1 ligne, 217 octets).

### Concern conservé

La fixture de performance marque toutes les pistes présentes avec un `last_seen_scan_id` différent
du paramètre ; l’update de réconciliation touche donc 100 % des pistes. Dans ce cas extrême, V7 est
environ 2 fois plus lent (100k : 188,815 contre 95,408 ms ; 250k : 533,315 contre 247,018 ms), coût
de maintenance de l’index inclus. L’expérience dédiée antérieure à 1 % de lignes présentes et
obsolètes favorisait l’index partiel à 250k. Le gate est accepté pour la scalabilité des lectures,
de l’historique, de la projection et de l’éligibilité, avec cette limite d’update all-match
explicitement ouverte ; les temps locaux ne sont pas des seuils CI.
