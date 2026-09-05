# Integrated Curator Agent — Implementation Plan

**Goal:** intégrer dans DJ Digger un agent conversationnel de curation capable de construire une setlist depuis le catalogue local au moyen d’une surface de tools bornée, de demander des précisions à l’utilisateur en streaming, de produire un rapport complet, puis de persister la setlist uniquement après validation humaine explicite.

**Architecture:** le LLM est un orchestrateur non privilégié. Il ne reçoit ni accès SQLite, ni accès filesystem, ni chemins locaux. Il dialogue exclusivement avec des tools applicatifs typés. Les hard constraints, l’éligibilité, les identités, les transitions et la validation finale sont contrôlés par DJ Digger, pas par le modèle. `submit_set_draft` termine la phase agentique sans écrire en base. La sauvegarde est une action CLI distincte déclenchée seulement après confirmation humaine.

**Tech stack:** Python 3.12, Typer, Rich, SQLite/WAL, JSON Schema, `openai>=3,<4`, Chat Completions OpenAI-compatible avec streaming/tool calls, pytest, Ruff, mypy.

**Target implementation plan path:** `docs/superpowers/plans/2026-08-28-integrated-curator-agent.md`

## Global constraints

- La branche de départ DOIT déjà contenir Catalog V9 issu du plan `2026-08-28-duplicate-mastering-dj-analysis.md`.
- Si `CURRENT_VERSION != 9`, arrêter la tranche curator. Ne jamais modifier la migration V8→V9 pour y injecter le curator.
- Le curator introduit Catalog V10 via une migration V9→V10.
- `WorkspaceApplication` reste propriétaire de la connexion SQLite.
- Le modèle n’exécute jamais de SQL.
- Le modèle n'accède jamais aux fichiers audio ni au filesystem.
- Les tools n’exposent jamais `root_path`, database path, export path ou chemin absolu.
- L’identité exposée au modèle est exclusivement `(source_id, track_id)`.
- Les chemins relatifs ne sont résolus qu’au moment de l’export.
- Disponibilité = track `present` appartenant à une source `enabled` et `set_eligible=true`.
- Une analyse absente ou partielle reste explicitement incertaine.
- Aucun BPM, tonalité, section ou métrique manquante n’est inféré.
- Les sept stratégies restent exactement : `LONG_BLEND`, `STANDARD_BLEND`, `LATE_BASS_HANDOFF`, `SHORT_HANDOFF`, `STRUCTURAL_SWAP`, `BREAK_TRANSITION`, `CUT_OR_ECHO`.
- Aucun tool `save`, `write`, `export`, `sql`, `filesystem` ou équivalent n’est fourni au modèle.
- `submit_set_draft` valide mais ne persiste rien.
- Le rapport final est rendu par DJ Digger depuis un draft validé, et non généré librement par le modèle.
- Le transcript agentique et les payloads de tools ne sont jamais écrits dans `RunLogger`.
- La clé API n’est jamais acceptée directement dans le TOML ; seule une variable d’environnement est référencée.
- HTTP distant est refusé. `http://` est accepté uniquement pour loopback/localhost ; sinon HTTPS obligatoire.
- `curate` est interactif et ne supporte pas `--background`.
- La première version intégrée ne publie aucun fichier pendant `curate`.
- La publication se fait uniquement via `dj-digger export --set <identity>`.
- Les fichiers source audio restent read-only.
- Toute mutation SQLite est transactionnelle.
- Aucun commit ou push n’est exécuté sans autorisation Git explicite.

---

## Task 0 — Gate V9 et rebase du plan

**Files:** aucun fichier de production.

**Consumes:** le résultat du plan mastering/DJ analysis existant.

**Produces:** une base de travail Catalog V9 compatible avec le curator.

- [ ] Vérifier :

```python
from dj_digger.catalog.migrations import CURRENT_VERSION

assert CURRENT_VERSION == 9
```

- [ ] Vérifier que V9 expose les métriques mastering/DJ prévues par le plan précédent dans les projections applicatives.
- [ ] Exécuter :

```bash
uv run --python 3.12 --with pytest pytest \
  tests/test_catalog_migrations.py \
  tests/test_read_repositories.py \
  tests/test_tracks_export.py -q
```

- [ ] Si V9 n’est pas présent : STOP. Implémenter/fusionner le plan V9 avant le curator.

Aucun fallback V8→V10 n’est autorisé.

---

## Task 1 — Configuration curator et port fournisseur LLM

**Files:**

- Modify: `pyproject.toml`
- Modify: `src/dj_digger/config.py`
- Create: `src/dj_digger/curation/__init__.py`
- Create: `src/dj_digger/curation/model.py`
- Create: `src/dj_digger/curation/openai_client.py`
- Test: `tests/test_config.py`
- Create test: `tests/test_curator_model_client.py`

### Public interfaces

```python
@dataclass(frozen=True)
class CuratorConfig:
    model: str
    base_url: str
    api_key_env: str
    request_timeout_seconds: float = 120.0
    max_tool_rounds: int = 32
```

`WorkspaceConfig` reçoit :

```python
curator: CuratorConfig | None
```

Port fournisseur :

```python
class ChatModelClient(Protocol):
    def stream_turn(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[ToolDefinition],
    ) -> Iterator[ModelEvent]: ...
```

Types internes :

```python
@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments_json: str

@dataclass(frozen=True)
class AssistantTurn:
    content: str | None
    tool_calls: tuple[ToolCall, ...]

@dataclass(frozen=True)
class TextDelta:
    text: str

@dataclass(frozen=True)
class TurnCompleted:
    turn: AssistantTurn
```

### Configuration TOML

```toml
[curator]
model = "gpt-5.6-sol"
base_url = "https://api.openai.com/v1"
api_key_env = "DJ_DIGGER_CURATOR_API_KEY"
request_timeout_seconds = 120
max_tool_rounds = 32
```

### RED

Ajouter notamment :

```python
def test_workspace_without_curator_keeps_curator_disabled(...):
    config = WorkspaceConfig.load(path)
    assert config.curator is None


def test_curator_config_reads_provider_settings(...):
    ...
    assert config.curator == CuratorConfig(
        model="test-model",
        base_url="https://llm.example/v1",
        api_key_env="DJ_DIGGER_CURATOR_API_KEY",
        request_timeout_seconds=120.0,
        max_tool_rounds=32,
    )
```

Tester explicitement :

- model vide ;
- URL invalide ;
- remote HTTP ;
- localhost HTTP autorisé ;
- timeout ≤ 0 ;
- `max_tool_rounds < 1`;
- nom de variable d’environnement invalide.

### Implementation

Ajouter :

```toml
"openai>=3,<4",
```

`OpenAICompatibleChatClient` reçoit la clé résolue par le runtime :

```python
OpenAI(
    api_key=api_key,
    base_url=config.base_url,
    timeout=config.request_timeout_seconds,
)
```

Utiliser `chat.completions.create(..., stream=True)` et accumuler soi-même les fragments `delta.tool_calls`.

Ne jamais exposer les types `openai.*` hors de `openai_client.py`.

### GREEN

```bash
uv run --python 3.12 --with pytest pytest \
  tests/test_config.py tests/test_curator_model_client.py -q

uvx ruff check src/dj_digger/config.py src/dj_digger/curation
uvx --with typer --with openai mypy src/dj_digger
```

Commit éventuel : `feat: add curator model provider boundary`

---

## Task 2 — Modèle métier interne et schemas de tools

**Files:**

- Create: `src/dj_digger/curation/models.py`
- Create: `src/dj_digger/curation/tool_schemas.py`
- Create: `src/dj_digger/curation/system_prompt.md`
- Modify: `pyproject.toml` pour garantir l’empaquetage de la ressource
- Create test: `tests/test_curator_contracts.py`

### Domain identities

```python
@dataclass(frozen=True, order=True)
class TrackRef:
    source_id: str
    track_id: int
```

Aucun `path` dans `TrackRef`.

Créer les DTO :

```python
LibraryContext
CandidateSummary
CandidateDetails
TransitionEvidence
SequenceEvaluation
CuratedTrackDraft
CuratedAlternativeDraft
CuratedTransitionDraft
CuratedSetDraft
DraftValidationResult
```

`CuratedSetDraft` contient notamment :

```python
identity: str
series: str
set_name: str
brief: CuratedBrief
core: tuple[CuratedTrackDraft, ...]
alternatives: tuple[CuratedAlternativeDraft, ...]
transitions: tuple[CuratedTransitionDraft, ...]
summary_rationale: str
uncertainties: tuple[str, ...]
```

Chaque choix de morceau contient une `rationale` factuelle.

### Tool schemas

Définir exactement six tools :

```text
get_library_context
search_candidates
get_candidates
evaluate_sequence
ask_user
submit_set_draft
```

Aucun septième tool.

Les schemas JSON interdisent les propriétés inconnues.

Limites :

```text
search_candidates.limit: 1..20
get_candidates.tracks: 1..12
evaluate_sequence.tracks: 1..30
ask_user.question: max 1000 chars
submit_set_draft core: max 30 tracks
submit_set_draft alternatives: max 30 tracks
```

Ne pas utiliser `strict=true` côté fournisseur : certains endpoints OpenAI-compatible ne le supportent pas. Validation locale avec `jsonschema`.

### System prompt

Le prompt doit expliquer au modèle uniquement :

- sa mission ;
- comment utiliser les six tools ;
- qu’il doit questionner lorsque le brief est insuffisant ;
- qu’il doit distinguer hard constraints / préférences / narration ;
- qu’il ne doit pas inventer de facts ;
- qu’il doit soumettre un draft structuré ;
- qu’il ne sauvegarde jamais lui-même ;
- qu’il ne doit pas exposer de chain-of-thought.

Les invariants critiques restent imposés par le code.

### Tests

Vérifier :

- aucun schema ne contient de champ path/root/sql ;
- aucun tool interdit n’existe ;
- propriétés inconnues refusées ;
- limites de taille ;
- stratégie hors enum refusée ;
- `TrackRef` vide/invalide refusé ;
- system prompt chargé via `importlib.resources` depuis un wheel installé.

Commit éventuel : `feat: define curator agent contracts`

---

## Task 3 — Read model dédié à la curation

**Files:**

- Create: `src/dj_digger/curation/repository.py`
- Create test: `tests/test_curator_repository.py`
- Modify si nécessaire : `tests/test_query_plans.py`

### Interface

```python
class CuratorReadRepository:
    def library_context(self) -> LibraryContext: ...

    def search(
        self,
        criteria: CandidateSearch,
    ) -> CandidatePage: ...

    def details(
        self,
        refs: Sequence[TrackRef],
    ) -> tuple[CandidateDetails, ...]: ...

    def resolve_current_tracks(
        self,
        refs: Sequence[TrackRef],
    ) -> tuple[ResolvedTrack, ...]: ...
```

### `library_context()`

Retourner seulement des agrégats utiles :

- nombre de tracks set-eligible ;
- source IDs disponibles ;
- nombre avec analyse courante ;
- nombre avec analyse partielle/manquante ;
- BPM min/max ;
- durée connue/inconnue ;
- qualité lossless/lossy/unknown ;
- couverture mastering/DJ si V9 disponible.

Aucun titre/artiste ni chemin ici.

### `search()`

Filtres supportés V1 :

```text
text
source_id
genre
bpm_min
bpm_max
duration_min_seconds
duration_max_seconds
lossless
analysis_required
max_gain_deficit_db
limit
after_track_id
```

Recherche texte uniquement sur les colonnes déjà normalisées :

```text
title
artist
album
genre
filename
```

Le résultat expose :

```text
source_id
track_id
title
artist
genre
duration_seconds
bpm
bpm_confidence
key
key_confidence
lossless
analysis_status/confidence
gain_deficit_db
duplicate_best_quality
```

Aucun path.

Utiliser keyset pagination, pas OFFSET.

### `details()`

Ajouter uniquement lorsque demandé :

- sections intro/outro/break/drop ;
- métriques spectrales utiles ;
- kick/bass density ;
- beat stability ;
- loudness/mastering ;
- métriques DJ ;
- duplicate group/quality ;
- incertitudes explicites.

Ne jamais renvoyer le gros `payload_json` complet au modèle.

### Tests

Prouver :

- `set_eligible=false` inaccessible ;
- source disabled inaccessible ;
- missing track inaccessible ;
- pagination déterministe ;
- filtres combinables ;
- duplicate non-preferred identifiable ;
- données partielles conservées comme `None`;
- aucune colonne filesystem dans les DTO ;
- query plans indexés sur les recherches fréquentes.

Commit éventuel : `feat: add curator read model`

---

## Task 4 — Évaluation déterministe des séquences et validation de draft

**Files:**

- Create: `src/dj_digger/curation/evaluator.py`
- Create: `src/dj_digger/curation/validator.py`
- Create test: `tests/test_curator_evaluator.py`
- Create test: `tests/test_curator_validator.py`

Le skill actuel exprime déjà le principe essentiel : hard constraints non compensables, incertitude explicite et seulement sept stratégies. Cette logique passe maintenant du prompt au code.

### Evaluator

Interface :

```python
class SequenceEvaluator:
    def evaluate(
        self,
        refs: Sequence[TrackRef],
    ) -> SequenceEvaluation: ...
```

Pour chaque frontière A→B, calculer des faits :

```text
from_bpm
to_bpm
target_bpm
from_pitch_percent
to_pitch_percent
beat_stability
available outgoing regions
available incoming regions
key information
low-end difference
loudness/DJ gain difference
allowed transition strategies
confidence
warnings
```

Politique BPM initiale pour préserver un comportement simple :

```python
target_bpm = to_bpm
from_pitch_percent = ((to_bpm / from_bpm) - 1.0) * 100
to_pitch_percent = 0.0
```

Si BPM absent : valeurs pitch/target non vérifiables.

Ne pas synthétiser un score de compatibilité lorsque les données nécessaires sont absentes. `compatibility=None` est valide.

### Allowed strategies

Déterminer les stratégies à partir de l’existence réelle des régions.

Exemples :

```text
long outgoing + long incoming -> LONG_BLEND possible
16/32-bar stable regions       -> STANDARD_BLEND possible
usable bass handoff regions    -> LATE_BASS_HANDOFF possible
short usable regions           -> SHORT_HANDOFF possible
structural sections            -> STRUCTURAL_SWAP possible
break available                -> BREAK_TRANSITION possible
CUT_OR_ECHO                     -> fallback structurel
```

Ne pas considérer le fallback comme une preuve de compatibilité.

### Validator

```python
class CuratedSetValidator:
    def validate(self, draft: CuratedSetDraft) -> DraftValidationResult: ...
```

Validation obligatoire :

- identity non vide et slug-safe ;
- positions core continues à partir de 1 ;
- aucune identité dupliquée dans core ;
- tous les tracks existent encore ;
- tous set-eligible ;
- hard constraints vérifiées ;
- transition N correspond bien core[N] → core[N+1] ;
- stratégie proposée présente dans `allowed_strategies`;
- alternative éligible ;
- `replace_position` existante ;
- durée connue comparée à cible ;
- métriques inconnues ne deviennent jamais des valeurs ;
- alternatives distinctes du core ;
- toutes les incertitudes calculables remontées.

Une incompatibilité du draft produit des erreurs structurées renvoyables au modèle.

Commit éventuel : `feat: validate curated set drafts`

---

## Task 5 — Tool registry applicatif

**Files:**

- Create: `src/dj_digger/curation/tools.py`
- Create test: `tests/test_curator_tools.py`

### Interface

```python
class CuratorToolRegistry:
    @property
    def definitions(self) -> tuple[ToolDefinition, ...]: ...

    def execute(
        self,
        name: str,
        arguments_json: str,
    ) -> ToolExecutionResult: ...
```

Composition :

```text
get_library_context -> CuratorReadRepository.library_context
search_candidates   -> CuratorReadRepository.search
get_candidates      -> CuratorReadRepository.details
evaluate_sequence   -> SequenceEvaluator.evaluate
ask_user             -> special runtime event
submit_set_draft     -> CuratedSetValidator.validate
```

`ask_user` et `submit_set_draft` ne sont pas exécutés comme un simple repository call : ils retournent un résultat typé que le runtime intercepte.

### Failure policy

Unknown tool :

```json
{
  "ok": false,
  "error": "unknown_tool"
}
```

Arguments invalides :

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "details": []
}
```

Jamais de traceback envoyé au modèle.

Les exceptions internes sont classifiées et bornées.

Tests :

- SQL-like tool name impossible ;
- unknown tool refusé ;
- JSON malformed refusé ;
- limites appliquées ;
- résultat `ask_user` distinguable ;
- draft invalide retourné au modèle ;
- draft valide retourné comme terminal candidate mais non sauvegardé.

Commit éventuel : `feat: expose bounded curator tools`

---

## Task 6 — Boucle agentique streaming

**Files:**

- Create: `src/dj_digger/curation/agent.py`
- Create: `src/dj_digger/curation/session.py`
- Create test: `tests/test_curator_agent.py`

### Interfaces

```python
class CuratorAgent:
    def run(
        self,
        request: str,
        interaction: CuratorInteraction,
    ) -> CuratorAgentResult: ...
```

```python
class CuratorInteraction(Protocol):
    def text_delta(self, text: str) -> None: ...
    def ask(self, question: CuratorQuestion) -> str: ...
```

Résultat :

```python
@dataclass(frozen=True)
class CuratorAgentResult:
    draft: CuratedSetDraft
    model: str
    tool_rounds: int
```

### Loop

Pseudo-code canonique :

```python
messages = [system_message, user_message]

for round_number in range(config.max_tool_rounds):
    turn = stream_one_model_turn(messages)

    if not turn.tool_calls:
        raise CuratorProtocolError(
            "model ended without submitting a validated draft"
        )

    messages.append(turn.as_message())

    for call in turn.tool_calls:
        result = tools.execute(call.name, call.arguments_json)

        if result.is_question:
            answer = interaction.ask(result.question)
            messages.append(tool_result(call.id, answer))
            continue

        if result.is_valid_draft:
            return CuratorAgentResult(
                draft=result.draft,
                model=config.model,
                tool_rounds=round_number + 1,
            )

        messages.append(tool_result(call.id, result.payload))

raise CuratorProtocolError("maximum curator tool rounds exceeded")
```

### Streaming

Afficher uniquement les `content` deltas explicitement produits par le modèle.

Le system prompt doit lui interdire de fournir son raisonnement interne.

Les tool calls ne sont pas imprimés par défaut.

En `-v`, on peut afficher seulement :

```text
Searching candidates…
Inspecting 8 candidates…
Evaluating 14-track sequence…
```

Pas les arguments complets.

### Tests

Scénarios déterministes avec fake `ChatModelClient` au niveau unit :

1. brief suffisant → search → evaluate → submit ;
2. brief vague → `ask_user` → réponse → reprise ;
3. draft invalide → validator errors → correction → resubmit ;
4. unknown tool ;
5. malformed JSON ;
6. max rounds ;
7. provider failure ;
8. aucun `submit_set_draft`;
9. draft accepté ne déclenche aucune écriture DB.

Commit éventuel : `feat: run interactive curator agent loop`

---

## Task 7 — Reporting déterministe et commande `curate`

**Files:**

- Create: `src/dj_digger/curation/report.py`
- Modify: `src/dj_digger/application.py`
- Modify: `src/dj_digger/cli.py`
- Create test: `tests/test_cli_curate.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_cli_completion.py`

### CLI

```text
dj-digger curate "Create a dark 60-minute warehouse acid set"
                 [--config PATH]
```

Pas de `--json` V1 : la commande est conversationnelle et streamée.

Pas de `--background`.

TTY requis.

Si aucune config `[curator]` :

```text
Curator is not configured. Add [curator] to the workspace configuration.
```

Si la variable API key est absente :

```text
Curator API key environment variable DJ_DIGGER_CURATOR_API_KEY is not set.
```

Ne jamais imprimer la valeur.

### Reporting

Le rapport doit être construit depuis `CuratedSetDraft` + validation calculée.

Sections :

```text
Brief understood
Validation summary
Core setlist
Transition plan
Alternatives
Narrative / energy trajectory
Uncertainties and missing analysis
Final checks
```

Pour chaque core track :

```text
position
artist/title
role
BPM/key si connus
important DJ/mastering metrics
rationale factuelle
```

Pour chaque transition :

```text
A -> B
strategy
regions
target BPM / pitch si vérifiables
bass handoff
confidence
facts/reasons
warnings
```

Ne pas afficher une « pensée interne » du LLM.

### Approval gate

Après le rapport :

```python
approved = typer.confirm("Save this curated set?", default=False)
```

Si `False` :

```text
Set not saved.
```

Exit 0.

Si `True`, appeler seulement alors :

```python
service.save_curated_set(...)
```

### Logging

NE PAS utiliser `_run()` avec le rapport complet.

Le log autorisé est uniquement :

```json
{
  "event": "curate",
  "status": "succeeded",
  "model": "configured-model",
  "tool_rounds": 14,
  "set_identity": "dark-warehouse-acid-hour",
  "saved": true
}
```

Tests d’absence obligatoire :

```python
assert user_prompt not in log_text
assert track_title not in log_text
assert api_key not in log_text
assert "tool_calls" not in log_text
```

Commit éventuel : `feat: add interactive curate command`

---

## Task 8 — Catalog V10 et sauvegarde des sets validés

**Files:**

- Create: `src/dj_digger/catalog/sql/catalog-v10.sql`
- Create: `src/dj_digger/catalog/sql/migrate-v9-to-v10.sql`
- Create: `schemas/catalog-v10.sql`
- Modify: `src/dj_digger/catalog/migrations.py`
- Create: `src/dj_digger/curation/set_repository.py`
- Modify: `src/dj_digger/application.py`
- Modify: `tests/test_catalog_migrations.py`
- Create test: `tests/test_curated_set_persistence.py`

### Migration

```python
CURRENT_VERSION = 10
CURRENT_SCHEMA = "catalog-v10.sql"

MIGRATIONS = {
    ...,
    8: "migrate-v8-to-v9.sql",
    9: "migrate-v9-to-v10.sql",
}
```

### Tables

```sql
CREATE TABLE dj_sets (
    id INTEGER PRIMARY KEY,
    identity TEXT NOT NULL UNIQUE,
    set_schema_version INTEGER NOT NULL,
    series TEXT NOT NULL,
    set_name TEXT NOT NULL,
    request_text TEXT NOT NULL,
    brief_json TEXT NOT NULL,
    approved_draft_json TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

```sql
CREATE TABLE dj_set_members (
    set_id INTEGER NOT NULL REFERENCES dj_sets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('core','alternative')),
    position INTEGER NOT NULL,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    replace_position INTEGER NULL,
    audio_analysis_id INTEGER NULL REFERENCES audio_analysis(id),
    mastering_analysis_id INTEGER NULL REFERENCES mastering_analysis(id),
    PRIMARY KEY (set_id, kind, position)
);
```

Indexes :

```sql
CREATE INDEX idx_dj_set_members_track
ON dj_set_members(track_id);

CREATE INDEX idx_dj_sets_created
ON dj_sets(created_at DESC);
```

### Persistence contract

```python
class CuratedSetRepository:
    def save(
        self,
        *,
        request_text: str,
        draft: CuratedSetDraft,
        model: str,
    ) -> SavedCuratedSet: ...

    def get_by_identity(self, identity: str) -> SavedCuratedSet | None: ...
```

Avant écriture :

1. revalider le draft ;
2. résoudre chaque `TrackRef`;
3. capturer les IDs d’analyse courante ;
4. ouvrir transaction ;
5. insert `dj_sets`;
6. insert members ;
7. commit.

Une collision `identity` doit être explicite :

```text
curated set identity already exists: dark-warehouse-acid-hour
```

Pas d’overwrite V1.

Cela garde le modèle append-only : pour une nouvelle version, utiliser une nouvelle identity.

### Migration tests

Prouver :

- V9→V10 préserve toutes les données ;
- rollback atomique ;
- foreign key check ;
- fresh V10 = migrated V10 ;
- schema source/package parity ;
- suppression d’un track référencé par une setlist refusée ;
- persistence all-or-nothing ;
- draft invalidable n’écrit aucune ligne.

Commit éventuel : `feat: persist approved curated sets`

---

## Task 9 — `export --set`

**Files:**

- Create: `src/dj_digger/exports/sets.py`
- Modify: `src/dj_digger/application.py`
- Modify: `src/dj_digger/cli.py`
- Modify: `pyproject.toml`
- Modify: `schema-bundle.json`
- Test: `tests/test_set_schema.py`
- Test: `tests/test_playlist_emission.py`
- Create test: `tests/test_set_export.py`
- Create test: `tests/test_cli_export_set.py`

### CLI

Ajouter :

```text
dj-digger export --set dark-warehouse-acid-hour
```

`--set` est mutuellement exclusif avec :

```text
--facet
--type
--format
--fields
```

### Export flow

```python
def export_set(self, identity: str) -> list[str]:
    return SetExporter(self.database).export(
        identity,
        self.config.exports / "sets",
    )
```

Le set exporter :

1. charge `dj_sets`;
2. charge members ;
3. résout les tracks actuellement présents ;
4. vérifie toujours `set_eligible`;
5. récupère leur `relative_path` courant ;
6. transforme le draft interne en `dj-set.schema.json` V2 ;
7. génère Markdown ;
8. génère M3U8 ;
9. valide tout ;
10. stage tout ;
11. publie avec les primitives atomiques existantes.

Sorties :

```text
exports/sets/<identity>.set.json
exports/sets/<identity>.m3u8
exports/sets/<identity>.md
```

### Important

Le `.set.json` externe continue d’utiliser :

```text
source_id
track_id
path
```

mais le `path` est résolu au moment de l’export et non réutilisé depuis le modèle.

### Source policy V1

La setlist intégrée est mono-source.

Le validator refuse :

```text
core tracks span multiple source ids
```

Cela supprime l’ambiguïté du M3U8 et évite d’ajouter maintenant un mécanisme `common_library_root`.

Le support multi-source pourra revenir ultérieurement avec un vrai mapping de racines.

### Publication failure

Si un track a disparu depuis la validation :

```text
set export refused: track <source_id>/<track_id> is no longer available
```

Aucun fichier staged ne remplace les exports existants.

### Packaging bug existant

Ajouter impérativement `schemas/dj-set.schema.json` aux ressources du wheel. Il est référencé dans le schema bundle mais n’est actuellement pas explicitement forcé dans le packaging.

Commit éventuel : `feat: export persisted curated sets`

---

## Task 10 — Evals agentiques, OpenAI-compatible smoke et documentation

**Files:**

- Reuse: `skills/electronic-dj-set-curator/evals/**`
- Create: `tests/test_curator_evals.py`
- Create: `tests/integration/test_curator_openai_compatible.py`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `config/dj-digger.example.toml`
- Modify: `skills/electronic-dj-set-curator/SKILL.md`
- Modify package/completion tests as necessary

### Existing eval reuse

Conserver les cas :

```text
acid-rave
adversarial
```

mais faire tourner le validator et les tools intégrés directement contre leurs fixtures.

Le harness externe reste utile pour vérifier la compatibilité du format V2.

Les assertions doivent couvrir :

```text
membership
source identity
no fabricated facts
hard constraints
uncertainty
valid strategy enum
valid alternatives
duration
ambiguous identity rejection
```

### Real protocol integration without external network

Ne pas appeler OpenAI dans la CI.

Créer un serveur HTTP local déterministe implémentant :

```text
POST /v1/chat/completions
Content-Type: text/event-stream
```

Scenario :

```text
turn 1 -> get_library_context
turn 2 -> search_candidates
turn 3 -> ask_user
turn 4 -> evaluate_sequence
turn 5 -> submit_set_draft
```

Faire passer le vrai :

```text
Typer CLI
→ WorkspaceConfig
→ OpenAICompatibleChatClient
→ HTTP/SSE
→ Tool registry
→ repositories
→ validator
→ report
```

Le serveur de test ne remplace aucun composant de cette chaîne : il joue uniquement le rôle du fournisseur externe.

Vérifier également l’accumulation de tool arguments fragmentés sur plusieurs chunks SSE.

### Documentation

Documenter :

```bash
export DJ_DIGGER_CURATOR_API_KEY=...
dj-digger curate "..."
dj-digger export --set <identity>
```

Expliquer clairement :

```text
curate ≠ export
validation ≠ persistence
persistence ≠ publication
```

Mettre à jour `ARCHITECTURE.md` :

```text
Sources
   ↓
Catalog V10
   ↓
Curator read model
   ↓
bounded tools
   ↓
LLM
   ↓
validated draft
   ↓
human approval
   ↓
dj_sets
   ↓
export --set
```

Mettre également à jour les références obsolètes V7/V8 et la documentation duplicate qui ne reflète plus `main`.

### Full QA

```bash
uv run --python 3.12 --with pytest pytest -q
uvx ruff check src tests
uvx ruff format --check src tests
uvx --with typer --with openai mypy src
```

Puis exécuter les scripts QA du dépôt :

```bash
.codex/scripts/qa-select
.codex/scripts/qa-run full
.codex/scripts/package-check
.codex/scripts/staged-check
```

Expected:

```text
all tests PASS
Ruff PASS
format PASS
mypy strict PASS
package resource test PASS
foreign_key_check PASS
public CLI integration PASS
```

---

# Acceptance criteria

La tranche est terminée uniquement si les scénarios suivants sont observables depuis le CLI réel.

### Brief suffisant

```bash
dj-digger curate \
  "Build a 60-minute dark warehouse acid techno set with a progressive rise and a short release."
```

L’agent consulte le catalogue, construit une proposition, affiche son rapport, puis :

```text
Save this curated set? [y/N]
```

`n` laisse SQLite inchangé.

### Brief insuffisant

```bash
dj-digger curate "Fais-moi un set techno."
```

L’agent pose au moins une question pertinente avant de soumettre un draft.

### Validation

Un modèle qui tente d’utiliser :

```text
source_id = unknown
track_id = 999999
strategy = MAGIC_TRANSITION
```

reçoit un résultat de validation négatif et ne peut provoquer aucune écriture.

### Save

Après `y`, `dj_sets` et `dj_set_members` sont écrits dans une seule transaction.

Aucun fichier n’est produit.

### Export

```bash
dj-digger export --set dark-warehouse-acid-hour
```

produit uniquement à ce moment :

```text
dark-warehouse-acid-hour.set.json
dark-warehouse-acid-hour.m3u8
dark-warehouse-acid-hour.md
```

### Privacy

Après une curation contenant des noms réels de tracks :

```bash
grep -R "<track title>" workspace/logs
```

ne retourne rien.

La clé API, le prompt, le transcript et les payloads de tools sont également absents des logs.

---

# Recommended implementation order

```text
V9 prerequisite
      ↓
1 Provider/config
      ↓
2 Domain/tool contracts
      ↓
3 Curator read model
      ↓
4 Evaluator + validator
      ↓
5 Tool registry
      ↓
6 Agent loop
      ↓
7 CLI/report
      ↓
8 Catalog V10 persistence
      ↓
9 export --set
      ↓
10 evals + protocol smoke + docs
```

La première vraie milestone exploitable est après Task 7 : l’agent peut alors effectuer une curation complète mais ne peut encore rien persister. C’est une frontière intéressante pour faire un essai sur une copie de catalogue avant d’introduire V10.

La seconde milestone est Task 8 : curation + sauvegarde validée.

Task 9 termine le workflow demandé : curation, validation, persistance puis export explicitement séparé.
