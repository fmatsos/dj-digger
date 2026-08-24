# Registre de requalification de l’implémentation v1

**Version :** 1.1 — 25 août 2026
**Tranche :** 8 (QA et requalification)
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

- `tests/integration/test_audit_parity.py` couvre les catégories historiques et les facettes publiques.
- `tests/integration/test_tranche5_acceptance.py` et `tests/integration/test_v1a_pipeline.py` vérifient la composition publique, la réutilisation, le snapshot et les schémas.
- `tests/test_analysis_eligibility.py`, `test_ffmpeg.py`, `test_rhythm.py`, `test_spectrum.py`, `test_windows.py`, `test_segmentation.py`, `test_semantics.py`, `test_analysis_persistence.py` et `test_analysis_exporters.py` couvrent les contrats des tâches 11–17.
- Le pilote réel local `scripts/acceptance_library_pilot.py` a été exécuté via l’environnement Python 3.12 avec l’extra d’analyse. Le rapport agrégé est `accepted` : 9 pistes bornées, scan/metadata/export/snapshot/archive réussis, deux analyses `partial` en sortie 2, réutilisation à la seconde analyse, source inchangée, deux échecs de décodage contrôlés sur les deux runs, 2 runs et 11 tentatives. Aucun chemin, nom de fichier ou identifiant privé n’est versionné ici.

### Curateur (tâches 18–23)

- `skills/electronic-dj-set-curator/SKILL.md` définit le nouveau contrat LLM source-aware.
- `skills/electronic-dj-set-curator/evals/harness.py`, les cas `acid-rave` et `adversarial`, et `tests/test_skill_tranche6.py` valident les entrées, contraintes, trois artefacts et le rejet d’artefacts inventés.
- `tests/integration/test_tranche7_acceptance.py::test_reconstructed_curator_consumes_canonical_facets_and_emits_three_valid_outputs` vérifie l’évaluation hors ligne. Cette preuve concerne le skill reconstruit, pas un moteur de parité non présent.

### Intégration

- Tâches 24–27 : fixtures de parité, historique de scan, pipeline V1A, snapshot et publication sont couverts par les tests d’intégration dédiés.
- Tâche 29 : `tests/integration/test_v1b_cutover.py` prouve la consommation de `tracks.tsv` sans facettes d’inventaire legacy.
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

Les plans sous `docs/superpowers/plans/` et les spécifications sous `docs/superpowers/specs/` restent inchangés. Les anciennes observations de déconnexion de la composition et d’export d’analyse sont remplacées ici par les preuves des tranches 5–8 ; le pilote local réel est désormais accepté sur ses preuves agrégées, sans divulgation de données privées.
