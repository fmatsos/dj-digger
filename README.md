# DJ Digger

DJ Digger is a command-line application that catalogs and analyzes local DJ music
libraries. It stores the current library state in SQLite and publishes stable export
files that other tools can use, including DJ set curation workflows.

The project is designed for local-first use. Music files stay in their original
locations and can be mounted as read-only files when DJ Digger runs in Docker.
The repository also provides the `electronic-dj-set-curator` skill. It lets an LLM
build an evidence-based DJ set from the local catalog and analysis exports.

## Objective

DJ music libraries often contain files from several sources, with different metadata
quality and no shared inventory. DJ Digger creates one reproducible view of these
libraries.

It can:

- scan one or more configured music folders;
- track present and missing files without moving or renaming them;
- extract embedded metadata with ExifTool;
- analyze rhythm, spectrum, and track structure with FFmpeg and Essentia;
- store scan, metadata, and analysis results in the current SQLite catalog schema;
- export validated TSV and JSON files for audits and DJ set tools;
- guide an LLM through source-aware, duration-aware DJ set curation;
- create portable snapshots of the published catalog data.

For the data flow, catalog model, processing boundaries, and SQLite lifecycle, see
[Architecture](docs/ARCHITECTURE.md).

The bounded read-only MCP interface for curation is documented in
[docs/mcp.md](docs/mcp.md).

## CLI output and exports

`--config` is optional when DJ Digger can discover a configuration file. The
lookup order is:

1. the path passed explicitly with `--config`;
2. `config.toml` in the current DJ Digger workspace (the directory from which
   the command is launched);
3. `config/config.toml` in that same workspace;
4. `~/.dj-digger/config.toml` in the current user's home directory.

If none of these files exists and is readable, the command exits with a usage
error asking for `--config PATH`. Workspace configuration deliberately takes
precedence over the user-level configuration, so a project can override global
defaults without changing them.

Commands print a compact Rich terminal summary by default. Add `--json` to
`scan`, `metadata`, `analyze`, `duplicates`, `export`, `snapshot`, `doctor`,
`status`, `refresh`, `jobs`, or a `database` command for the stable compact JSON
diagnostic (suitable for scripts). Background launch results and job listings
support the same switch.

`export` keeps the canonical mixed files when called without new options. Use
`--type` to select a leaf (`tracks`, `artifacts`, `analysis`, `sections`, or
`run`; `all` selects every leaf), and `--format json|csv|tsv` to choose one
format for all selected leaves. `--fields` is comma-separated, preserves the
given order, rejects blanks, duplicates, and unknown names, and requires one
leaf type. For example:

```text
dj-digger export --config config/local.toml --type tracks --fields=title,filename
dj-digger export --config config/local.toml --type analysis --fields=bpm
```

The [complete list of all 187 available fields](docs/export-fields.md) is grouped
by export type and follows the packaged schemas used by CLI validation. Nested
values in CSV/TSV are compact JSON cells.

Duplicate fingerprinting is available through `duplicates --analyze`; automatic
move or rename reconciliation remains outside the current scope.

## Installation

### Requirements

The recommended installation uses Docker Compose. It requires:

- Docker with the Compose plugin;
- a local folder that contains your music library.

For a native installation, use Python 3.12. ExifTool is required for
metadata extraction. FFmpeg, FFprobe, and Essentia are required by the default
audio-analysis workflow.

Install the native system packages for your platform before creating the Python
virtual environment. FFprobe is included in the FFmpeg package.

#### Debian / Ubuntu

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ffmpeg libimage-exiftool-perl
```

#### Fedora

```bash
sudo dnf install python3 python3-pip ffmpeg-free perl-Image-ExifTool
```

#### macOS

Install [Homebrew](https://brew.sh/) first if it is not already available, then run:

```bash
brew install python@3.12 ffmpeg exiftool
```

#### Windows

Run the following commands in PowerShell:

```powershell
winget install --exact --id Python.Python.3.12
winget install --exact --id Gyan.FFmpeg
winget install --exact --id OliverBetz.ExifTool
```

Restart PowerShell after installation so the new commands are available on `PATH`.
The pinned Essentia release does not provide a Windows wheel, so a native Windows
installation supports cataloging and metadata extraction but not the complete audio
analysis workflow. Use Docker Compose or WSL2 with the Debian / Ubuntu instructions
for complete analysis support.

The pinned Essentia wheels support Linux x86_64 and macOS on Intel or Apple Silicon.
On other native platforms, use Docker Compose. You can verify the system dependencies
with:

```bash
python3 --version
exiftool -ver
ffmpeg -version
ffprobe -version
```

### Docker Compose

1. Clone the repository and enter its directory.

   ```bash
   git clone <repository-url>
   cd dj-digg
   ```

2. Create a local configuration from the example.

   ```bash
   cp config/dj-digger.example.toml config/local.toml
   ```

3. Edit `config/local.toml`. Inside Docker, music sources must use paths below
   `/music`. The database and exports should remain below `/workspace`.

4. Build the image and check the configuration. Replace `/path/to/music` with the
   parent folder of the source paths configured in `config/local.toml`.

   ```bash
   export DJ_DIGGER_MUSIC_ROOT=/path/to/music
   docker compose build
   docker compose run --rm dj-digger doctor --config /config/local.toml
   ```

5. Build or refresh the complete catalog.

   ```bash
   docker compose run --rm dj-digger refresh --config /config/local.toml
   ```

The SQLite database is written to `workspace/dj-digger.sqlite`. Published files are
written to `workspace/exports/` with the example configuration.

DJ Digger uses Catalog V9. It creates fresh V9 catalogs and upgrades V6 catalogs in
place. Catalogs from V1 through V5 remain unsupported; preserve them as backups and
move them out of the configured workspace before creating a fresh V9 catalog.

### Native Python installation

Create and activate a virtual environment, then install the project:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`. Because Essentia is unavailable natively on Windows,
install the metadata-only application there with `python -m pip install -e .`.

Copy the example configuration and replace its container paths with paths available
on the host machine:

```bash
cp config/dj-digger.example.toml config/local.toml
dj-digger doctor --config config/local.toml
dj-digger refresh --config config/local.toml
```

### Development with uv

The repository lockfile is the source of truth for contributor and agent
environments. With Python 3.12 and the native system packages installed, run:

```bash
python3.12 -m pip install --upgrade pip
python3.12 -m pip install uv==0.11.19
uv sync --frozen --group dev
```

This installs the complete development toolchain (pytest, Ruff, and mypy) from
`uv.lock`; normal development and QA must not rely on implicit `uv run --with`
downloads. The deterministic harness entry points are under `.agents/scripts/`.

### Running with uvx

For development, keep using the lockfile-backed environment:

```bash
uv sync --frozen --group dev
uv run dj-digger ...
```

To run the published CLI directly from GitHub without cloning it:

```bash
uvx --from git+https://github.com/fmatsos/dj-digger dj-digger ...
```

After a release on PyPI, the same commands can use the published package:

```bash
uvx dj-digger ...
```

For example, `doctor` and `refresh` are available through either `uvx` form:

```bash
uvx dj-digger doctor --config /path/to/config.toml
uvx dj-digger refresh --config /path/to/config.toml
```

`uvx` installs Python dependencies declared by the package, including the audio
analysis dependencies. It does not install operating-system programs. Native
`doctor`, `refresh`, and analysis workflows require these commands on `PATH`:

```text
ffmpeg
ffprobe
exiftool
```

### Codex Cloud

Codex Cloud can consume the same repository-defined contract without Docker or a
real music library:

```bash
./.codex/cloud/setup.sh
./.codex/cloud/maintenance.sh
./.codex/cloud/check.sh --runtime
```

`setup.sh` provisions FFmpeg, FFprobe, ExifTool, and the pinned `uv` tool, then
synchronizes the active lockfile. `maintenance.sh` repeats the lockfile sync for
warm starts and branch changes. The runtime check creates private, synthetic WAV
fixtures in a temporary directory and exercises the public `doctor`, `refresh`,
`duplicates`, and `export` commands through SQLite Catalog V9. It never requires
or exposes the real media library. Docker and Docker Agent remain optional paths
for image distribution and orchestration; offline development uses the prepared
environment and local fixtures.

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

Catalog commands print compact JSON diagnostics. Exit code `0` means success, `1`
means failure, and `2` means that the command completed only partially. `copy` reports
its own file progress: `0` means success, `1` a runtime/filesystem failure, and `2`
invalid command usage.

### Run a long command in the background

`analyze`, `duplicates --analyze`, and `refresh` accept `--background`. Instead of
running the analysis, the command detaches a copy of itself (same arguments, minus
`--background`) into its own process group and returns immediately with a job id:

```json
{"event":"analyze","status":"background","job_id":"15ac91341eeb","pid":1079394,"log":"/path/to/workspace/jobs/15ac91341eeb.log"}
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
`01 - opening.flac`. The output also contains:

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
  --library /media/music \
  --output /srv/share/my-set \
  --playlist sets/my-set.m3u8 \
  --track "Encore/closing.flac" \
  --owner share:share \
  --verbose
```

Copy explicit tracks without an input playlist:

```bash
dj-digger copy \
  -l /media/music \
  -o /srv/share/closing-set \
  -t "Closing/first.flac" \
  -t "Closing/last.flac" \
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
dj-digger duplicates --analyze [--mark-best-quality] [--source NAME]
                     [--workers N] [--track-timeout SECONDS] --config PATH

dj-digger duplicates --list [--source NAME] --config PATH

dj-digger duplicates --mark-best-quality [--source NAME] --config PATH
```

`--analyze` and `--list` are mutually exclusive, and at least one action is required.
`--mark-best-quality` is valid alone or combined with `--analyze`. `--workers` and
`--track-timeout` are only valid with `--analyze`; both default to the same values as
`analyze`. Invalid combinations fail as usage errors (exit code `2`) before the catalog
is opened.

```bash
dj-digger duplicates --analyze --mark-best-quality --config config/local.toml
dj-digger duplicates --list --config config/local.toml
dj-digger duplicates --list --source djing --config config/local.toml
```

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
- `schemas/dj-set.schema.json`.

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

## FAQ

### Does DJ Digger modify my music files?

No. Scanning, metadata extraction, and analysis read the source files. The Docker
configuration mounts the music folder as read-only. DJ Digger writes only to its
workspace database, exports, and requested snapshot destinations.

### Can I configure more than one music library?

Yes. Add one `[[library.sources]]` block per source in the TOML configuration. Each
source needs a unique `id` and can be enabled, analyzed, or made eligible for set
curation independently.

### What does `set_eligible` mean?

It marks tracks that may be used by the set curator. A track must be present in the
current `tracks.tsv` export and belong to a source with `set_eligible = true` before
it can become a set candidate.

### What does `analyze` mean in a source configuration?

It enables audio analysis for that source. Sources that are useful for inventory or
metadata only can use `analyze = false`.

### Why was an analysis process reported as `Killed`?

On Linux, a bare `Killed` message commonly means that the kernel or container stopped
the process after memory exhaustion. Check the cgroup counters with
`cat /sys/fs/cgroup/memory.events`; a positive `oom_kill` value confirms an OOM kill.

The current analyzer avoids whole-library result accumulation and whole-track spectrum
matrices. Keep `--workers 1` on memory-constrained systems. Completed tracks are committed
immediately and will be reused after restarting the command.

### Why is my existing SQLite catalog rejected?

DJ Digger creates fresh V9 catalogs and upgrades V6 catalogs in place. Catalogs created
with versions V1 through V5 are not upgraded. Preserve an unsupported database as a
backup, move it out of the configured workspace location, and rerun DJ Digger to create
a fresh V9 catalog.

### Why does `doctor` report missing programs?

Metadata extraction requires `exiftool`. Analysis also requires `ffmpeg`, `ffprobe`,
and Essentia. Duplicate detection reuses `ffmpeg`/`ffprobe` and additionally requires
an FFmpeg build providing the `chromaprint` muxer, but does not require Essentia. The
Docker image installs these dependencies. For a native setup, they must be installed
on the host.

### Can I run only one part of the workflow?

Yes. Use `scan`, `metadata`, `analyze`, or `export` separately. These commands accept
filters such as a source ID, a path prefix, or an analysis limit where relevant.
Run `dj-digger COMMAND --help` to see the available options.

### What happens when a source is temporarily unavailable?

Each source scan has its own lifecycle. A failed scan is recorded and does not
silently replace a successful observation. The `refresh` command stops publication
when a required set-eligible source fails; failures in other sources can produce a
partial result.

### Which files should downstream tools read?

Use `tracks.tsv` as the source of truth for current availability. Analysis consumers
can also read `dj-analysis.tsv`, `dj-sections.jsonl`, and `dj-analysis-run.json`.
Library artifact consumers can read `library-artifacts.tsv`.

### Does the LLM choose tracks freely?

No. The LLM creates the narrative and evaluates possible transitions, but the skill
limits it to evidence from the local exports. It preserves each track's `source_id`,
`track_id`, and exact path. It must refuse an ambiguous selection or an unproven hard
constraint instead of guessing.

### How does the curator handle transitions and alternatives?

It uses technical and structural facts to select a supported transition strategy.
For each set position, it keeps three candidate branches and explains why each one is
viable or uncertain. The final files include the selected sequence, alternatives,
improvisation branches, transition regions, confidence levels, and known unknowns.

### Can a curated set contain tracks from several sources?

Yes, but only when the caller provides an explicit common library root. This prevents
ambiguous paths. The generated M3U8 file still contains exact relative paths and does
not include the common root or source IDs.

## Docker Agent orchestration

The repository includes a bounded Docker Agent workflow that keeps the lead on
repository-scoped read-only exploration and delegates implementation through explicit
task transfers. Its main files are:

- `docker-agent.yaml` for the agent configuration;
- `.docker-agent/instructions/lead.md` and `reviewer.md` for role contracts;
- `.docker-agent/scripts/next-plan-task` for bounded plan extraction;
- `.docker-agent/scripts/change-summary` for privacy-aware Git summaries;
- `.docker-agent/scripts/lead-qa` for the Python 3.12 QA gate.

Pass a bounded brief path as plain text rather than attaching the whole file to the lead context:

```text
Implémente la prochaine tâche décrite dans le brief local :
<path-vers-un-brief-borne>

Pas de commit ni de push.
```

Validate the workflow with:

```bash
pytest -q tests/test_lead_tools.py
docker agent doctor ./docker-agent.yaml
docker agent debug toolsets ./docker-agent.yaml --working-dir "$PWD"
```

## Architecture

See [Architecture](docs/ARCHITECTURE.md) for the current Catalog V9 data model,
migration path, connection and concurrency lifecycle, processing flows, publication
contracts, maintenance commands, and extension invariants.
## Duplicate mastering review

Exact duplicate groups can optionally be measured with FFmpeg EBU R128:
`dj-digger duplicates --analyze --mastering`. Use `--list --dj-review` to
filter groups whose descriptive loudness, peak, PLR, or gain metrics warrant
listening review. The default DJ targets are -9 LUFS and -1 dBTP; metrics are
nullable and analysis failures produce a partial result. Existing
`best_quality` remains a technical-only selection and mastering analysis never
changes it. Analysis is idempotent for unchanged inputs and exact
Chromaprint identity does not discover all remasters.
