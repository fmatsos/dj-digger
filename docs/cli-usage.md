# CLI usage

This is the detailed command reference for DJ Digger. For installation and the
shortest first-run path, start with the [project README](../README.md).

### Main commands

Catalog commands require `--config`. The standalone `copy` command instead takes an
explicit read-only library root and output directory.

| Command | Purpose |
| --- | --- |
| `scan` | Scan configured sources and update file presence. |
| `metadata` | Extract or refresh embedded metadata. |
| `analyze` | Analyze eligible audio files. |
| `duplicates` | Fingerprint audio, list duplicate recordings, and mark the best-quality copy. |
| `export` | Publish catalog and analysis files. |
| `refresh` | Run scan, metadata, analysis, and export in order. |
| `status` | Report catalog, source, and export status. |
| `doctor` | Check paths, dependencies, and the current database schema. |
| `snapshot` | Create a validated export snapshot. |
| `copy` | Copy and renumber a playlist or explicit tracks into a portable set directory. |
| `jobs` | List background jobs started with `--background` and their status. |
| `curation create` | Run the bounded catalog-grounded agent and persist a draft. |
| `curation show` / `curation list` | Review a creation or list it by `draft`/`validated` status. |
| `curation validate` | Record the explicit human-reviewed `draft` → `validated` transition. |
| `curation export` | Publish a report, playlist, or both, with optional portable track copies. |
| `mcp` | Serve the bounded curation tools to a local external agent over stdio. |

DJ Digger catalog identities and facts are authoritative during native curation.
General model knowledge may guide strategy and explanation only; no track absent
from current catalog tool results can be persisted. A model-created selection is
always a `draft`, requiring human review before `curation validate` marks it
`validated`. Multi-source playlists require `curation export --copy-files`.

Catalog commands print compact JSON diagnostics. Exit code `0` means success, `1`
means failure, and `2` means that the command completed only partially. `copy` reports
its own file progress: `0` means success, `1` a runtime/filesystem failure, and `2`
invalid command usage.

### Run a long command in the background

`analyze`, `duplicates --analyze`, and `refresh` accept `--background`. Instead of
running the analysis, the command detaches a copy of itself (same arguments, minus
`--background`) into its own process group and returns immediately with a job id:

```json
{"event":"analyze","status":"background","job_id":"15ac91341eeb","pid":1079394,"log":"demo-workspace/jobs/15ac91341eeb.log"}
```

The detached process keeps running after the launching shell exits or an SSH
connection is closed. Its JSON output is written to the `log` path, and its
progress/result is tracked in `<database directory>/jobs/<job_id>.json` (status
`running`, then `succeeded`/`partial`/`failed` with the full result once it exits).
Run `dj-digger jobs --config <config>` at any time to list every job and its current
status — a job whose process died without reporting a result is shown as `unknown`.

### Copy a portable set

`copy` integrates the `references/copy-set.sh` workflow directly into the CLI. It does
not use the workspace configuration or catalog database: the library, destination,
playlist, and tracks are supplied explicitly.

```text
dj-digger copy --library PATH --output PATH \
  [--playlist FILE] [--track FILE ...] \
  [--owner USER:GROUP] [--verbose]
```

| Option | Short | Required | Description |
| --- | --- | --- | --- |
| `--library PATH` | `-l` | Yes | Root of the read-only media library. |
| `--output PATH` | `-o` | Yes | Portable set directory, which must be outside the library. |
| `--playlist FILE` | `-p` | Unless a track is provided | One `.m3u` or `.m3u8` input playlist. |
| `--track FILE` | `-t` | Unless a playlist is provided | Additional track; repeat the option to add several tracks. |
| `--owner USER:GROUP` | | No | Recursive output owner; defaults to `share:share`. Numeric `UID:GID` values are accepted. |
| `--verbose` | `-v` | No | Show the source, group, and destination of each copy. |
| `--help` | `-h` | No | Display command help. |

Playlist entries are resolved relative to `--library`. Absolute paths and `file:///…`
URIs are accepted only when their canonical target remains inside the library; remote
URIs are rejected. Blank lines and playlist comments are ignored. A safe
`#EXTGRP:<name>` entry assigns subsequent tracks to a relative subdirectory. Explicit
`--track` arguments are appended after all playlist entries, in argument order, and
inherit the playlist's last group.

The copied files are prefixed with their set order, for example
`01 - Aurora Pulse.flac`. The output also contains:

- the input playlist filename, or `playlist.m3u8` when only `--track` is used;
- a same-stem `.txt` manifest containing order, group, copied filename, and original
  library-relative path.

Track and manifest replacements are atomic. Existing regular files with the same
generated names are replaced, while symbolic links and non-file destinations are
refused. Unrelated files already present in the output directory are left untouched.
The source library is never modified, and an output path inside it is rejected.

Copy a playlist and append an encore track:

```bash
dj-digger copy \
  --library demo-library/neon-archive \
  --output demo-exports/neon-observatory \
  --playlist examples/neon-observatory.m3u8 \
  --track "Fictional Encore/Aurora Pulse.flac" \
  --owner share:share \
  --verbose
```

Copy explicit tracks without an input playlist:

```bash
dj-digger copy \
  -l demo-library/lunar-radio \
  -o demo-exports/lunar-closing \
  -t "Fictional Closing/Moonlit Relay.flac" \
  -t "Fictional Closing/Quiet Comet.flac" \
  --owner 1000:1000
```

After all files and manifests are published, `copy` applies the requested ownership
recursively without following symbolic links. This step requires a POSIX platform and
the operating-system permission to change ownership. Exit code `0` means success, `1`
means a runtime, validation, or filesystem failure, and `2` means invalid CLI usage.

In an interactive terminal, `refresh` also displays a transient Rich progress area. It
shows the current phase offset and, during analysis, the completed-track offset, speed,
and estimated time remaining. The display is rewritten in place and cleared when the
command finishes. It uses stderr, while the final JSON diagnostic remains on stdout;
redirected and non-interactive executions therefore keep clean JSON output without a
progress display.

### Analyze large libraries

Audio analysis supports bounded worker concurrency, per-track timeouts, resumable
results, and source/path filters. The child-process isolation, parent-owned SQLite
persistence, and DSP memory model are described in
[Architecture](docs/ARCHITECTURE.md#isolated-audio-analysis).

The default is one worker, which gives the lowest memory usage:

```bash
dj-digger analyze --config config/local.toml --workers 1
```

Each track has a default timeout of 1,800 seconds. A timeout terminates the child's
whole process group, including FFmpeg, records that track as failed, and continues the
queue. Override it with a strictly positive number of seconds:

```bash
dj-digger analyze --config config/local.toml --track-timeout 900
dj-digger refresh --config config/local.toml --workers 2 --track-timeout 900
```

Keep `--workers 1` for spinning HDDs and memory-constrained systems, where concurrent
reads usually add contention. SSDs can benefit from a small explicit worker count;
increase it gradually while watching memory and I/O pressure.

Use `--limit` for an intentionally bounded run, or `--path` to analyze a path prefix:

```bash
dj-digger analyze --config config/local.toml --limit 25 --workers 1
dj-digger analyze --config config/local.toml --path "Techno" --workers 1
```

Completed tracks remain reusable after an interruption. Only one analysis command may
use a catalog at a time; a concurrent invocation fails immediately.

### Find and resolve duplicate recordings

`duplicates` fingerprints present audio with FFmpeg's Chromaprint muxer, groups tracks
that share a complete fingerprint, and can elect the best-quality copy per group and
per source. It requires an FFmpeg build providing the `chromaprint` muxer; it does not
require Essentia.

```text
dj-digger duplicates analyze [--mark-best-quality] [--source NAME]
                            [--workers N] [--track-timeout SECONDS] --config PATH

dj-digger duplicates list [--source NAME] --config PATH

dj-digger duplicates mark-best-quality [--source NAME] --config PATH
```

Each workflow is a subcommand, so options that do not apply are not accepted.
`--mark-best-quality` on `analyze` elects winners after fingerprinting. `--workers` and
`--track-timeout` belong only to `analyze`; both default to the same values as the main
`analyze` command. Invalid options fail as usage errors (exit code `2`) before the
catalog is opened.

```bash
dj-digger duplicates analyze --mark-best-quality --config config/local.toml
dj-digger duplicates list --config config/local.toml
dj-digger duplicates list --source djing --config config/local.toml
```

The former hidden flag syntax (`duplicates --analyze`, `duplicates --list`, and
`duplicates --mark-best-quality`) remains available only for legacy script
compatibility and emits a deprecation warning. New scripts should use the subcommands.

Grouping is conservative: two present tracks are duplicates only when their complete
Chromaprint fingerprints match exactly. Perceptually similar but distinct recordings
(different edits, remixes, live versions) are never grouped. Without `--source`, groups
may span multiple sources; with `--source`, only that source's tracks are considered.

Quality ranking is deterministic: known-lossless copies outrank known-lossy copies,
which outrank copies with unknown technical facts. Within the lossless tier, higher bit
depth wins, then higher sample rate. Within the lossy tier, higher bitrate wins, then
higher sample rate. Remaining ties break on relative path, ascending. One winner is
elected per `(source, fingerprint)` pair, so a cross-source group can have a different
winner in each source. Standalone `--mark-best-quality` refuses to run, without changing
any existing selection, when a present track in the requested scope lacks a current
fingerprint or current technical facts — analyze that scope first.

`--list` prints ordered duplicate groups as JSON, each with a `group_id` and member
objects carrying `source`, `track_id`, `relative_path`, `technical_facts`, and
`best_quality` (`true` for the elected copy, `false` for other members of a marked
group, `null` when the group is not marked or scoped to another source). `tracks.tsv`
exposes the same state as `duplicate_group_id` (empty when the track is not part of a
duplicate group) and `duplicate_best_quality` (`true`, `false`, or empty).

Exit codes match the other analysis commands: `0` on success, `1` on a command-level
failure (including a refused `--mark-best-quality` on an incomplete scope), and `2` when
a per-track analysis pass is only partially complete.

### Configure a ChatGPT or Claude project

The curator can run in a [ChatGPT Project](https://help.openai.com/en/articles/10169521)
or a [Claude Project](https://support.claude.com/en/articles/9519177-how-can-i-create-and-manage-projects).
A project keeps the curation rules and DJ Digger exports available across multiple
curation chats. The project does not receive direct access to your music folders or
SQLite database.

#### Files to add

Add these stable files to the project sources or knowledge base:

- `skills/electronic-dj-set-curator/SKILL.md`;
- `skills/electronic-dj-set-curator/references/source-contracts.md`;
- `skills/electronic-dj-set-curator/references/compatibility-engine.md`;
- `skills/electronic-dj-set-curator/references/set-emission.md`;
- `src/dj_digger/core/schemas/dj-set.schema.json`.

Before each curation, replace the previous runtime exports with the files from the
same successful or partial DJ Digger export run:

- `workspace/exports/tracks.tsv`;
- `workspace/exports/dj-analysis.tsv`;
- `workspace/exports/dj-sections.jsonl`;
- `workspace/exports/dj-analysis-run.json`.

Do not mix exports from different runs. Treat library filenames and metadata as
private data when choosing the project account, sharing settings, and collaborators.

#### ChatGPT Project

1. Select **New project** in the ChatGPT sidebar and name it `DJ Digger Curator`.
2. Choose **Project-only memory** when available, so unrelated chats and memories do
   not influence curation.
3. Add the nine files listed above to the project sources.
4. Open the project menu, select **Project settings**, and paste the project
   instructions from the next section.
5. Start one new project chat per set brief. Download the three generated artifacts
   before replacing exports or starting another curation.

Project instructions apply only inside that ChatGPT Project and override global
custom instructions. Upload limits and available memory settings depend on the
ChatGPT plan and workspace configuration.

#### Claude Project

1. Open **Projects**, select **New Project**, and name it `DJ Digger Curator`.
2. Keep the project private unless other collaborators need access.
3. Add the nine files listed above to **Project Knowledge**. Files stored only in an
   individual chat are not shared automatically with other project chats.
4. Select **Set project instructions**, paste the instructions from the next section,
   and save them.
5. Start one new project chat per set brief. Download the three generated artifacts
   before replacing exports or starting another curation.

On paid Claude plans, Project Knowledge can automatically use retrieval-augmented
generation when it approaches the context limit. This increases capacity, but it
does not change the curator's evidence and validation rules.

#### Project instructions

Use the following text as the ChatGPT or Claude project instructions. In a Project
interface, these instructions are the persistent equivalent of a system prompt for
this workflow.

```text
You are an evidence-based electronic DJ set curator.

Follow the uploaded electronic-dj-set-curator skill and its reference files. The
uploaded DJ Digger exports are the only authority for library availability and
technical facts.

Read inputs in this exact order:
1. tracks.tsv
2. dj-analysis.tsv
3. dj-sections.jsonl
4. dj-analysis-run.json

Rules:
- A candidate must exist in tracks.tsv and have set_eligible=true.
- Identify every track by the exact source_id, track_id, and path from the exports.
- Join facts using (source_id, track_id, path).
- Never infer availability from model knowledge, web results, or filenames.
- Never invent BPM, key, duration, compatibility, sections, or transition facts.
- Mark missing or partial analysis as uncertain.
- Treat the user's duration, musical direction, and hard constraints as mandatory.
- Build a duration-aware opening, development, peak, and release.
- Keep exactly three factual or explicitly uncertain candidates for every position.
- Use only transition strategies allowed by the uploaded skill.
- Refuse the curation when a path is ambiguous or a hard constraint cannot be proven.
- Do not claim that files were written to the user's computer or repository.

Always produce three downloadable artifacts with the same identity:
1. <identity>.set.json, valid against dj-set.schema.json
2. <identity>.m3u8, with exact source-relative paths only
3. <identity>.md, with the transition sheet, three candidates per position,
   improvisation branches, confidence, uncertainties, and validation notes

Before finalizing, validate identities, paths, eligibility, duration, hard
constraints, transition references, and all three artifact formats. Report partial
or stale analysis clearly. Ask for missing brief information instead of guessing.
```

### LLM-assisted set curation

The skill is stored in `skills/electronic-dj-set-curator/`. Use it with a compatible
LLM agent after DJ Digger has published the catalog and analysis exports. Give the
agent a clear set brief, including the musical direction, target duration, desired
energy curve, and any hard constraints.

For example:

```text
Create a set named dark-warehouse-acid-hour with a target duration of 60 minutes.
Use a dark warehouse acid direction. Start with a restrained atmosphere, develop
the intensity progressively, reach one strong peak, and finish with a short release.
Use only tracks available in the uploaded DJ Digger exports. Generate and attach the
JSON, M3U8, and Markdown artifacts.
```

The skill reads the generated files in this order:

1. `tracks.tsv` for current availability, source identity, exact paths, and
   `set_eligible` values;
2. `dj-analysis.tsv` for technical track and window facts;
3. `dj-sections.jsonl` for structural sections such as intros, breaks, and drops;
4. `dj-analysis-run.json` for freshness and partial-analysis information.

It then creates three files:

- `<set-name>.set.json`: the machine-readable set, alternatives, and transitions;
- `<set-name>.m3u8`: a playlist containing exact source-relative track paths;
- `<set-name>.md`: a human-readable transition sheet, candidate branches, and
  uncertainty notes.

The LLM must not use its own knowledge or web results to decide whether a track is
available. A track can enter the set only when it exists in `tracks.tsv` and has
`set_eligible = true`. Missing or partial analysis remains explicitly uncertain; the
skill must not invent BPM, key, duration, compatibility, or track sections.

## Legacy copy-set wrapper

`references/copy-set.sh` is retained as a compatibility wrapper for existing shell
workflows. New integrations should use `dj-digger copy`, which owns the supported
validation and atomic-copy behavior. The wrapper may be removed in a future major
release after downstream callers have migrated.
