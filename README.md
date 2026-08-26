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

The canonical data flow is:

```text
Configured music sources
        |
        v
File scan and metadata extraction
        |
        v
Current SQLite catalog
        |
        +--> Audio analysis
        |
        v
Validated exports and snapshots
        |
        v
DJ set curation and other consumers
```

Audio fingerprinting, automatic move or rename reconciliation, and duplicate
detection are not part of the current scope.

## Installation

### Requirements

The recommended installation uses Docker Compose. It requires:

- Docker with the Compose plugin;
- a local folder that contains your music library.

For a native installation, use Python 3.12 or later. ExifTool is required for
metadata extraction. FFmpeg, FFprobe, and the optional `analysis` dependencies are
required when audio analysis is enabled.

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

DJ Digger supports only the current catalog schema (v6). If the workspace contains a
catalog created by an earlier release, keep it as a backup and move it out of the
workspace before running the current version. DJ Digger will create a fresh v6 catalog;
it does not migrate legacy catalogs.

### Native Python installation

Create and activate a virtual environment, then install the project:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[analysis]'
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

### Main commands

Catalog commands require `--config`. The standalone `copy` command instead takes an
explicit read-only library root and output directory.

| Command | Purpose |
| --- | --- |
| `scan` | Scan configured sources and update file presence. |
| `metadata` | Extract or refresh embedded metadata. |
| `analyze` | Analyze eligible audio files. |
| `export` | Publish catalog and analysis files. |
| `refresh` | Run scan, metadata, analysis, and export in order. |
| `status` | Report catalog, source, and export status. |
| `doctor` | Check paths, dependencies, and the current database schema. |
| `snapshot` | Create a validated export snapshot. |
| `copy` | Copy and renumber a playlist or explicit tracks into a portable set directory. |

Catalog commands print compact JSON diagnostics. Exit code `0` means success, `1`
means failure, and `2` means that the command completed only partially. `copy` reports
its own file progress: `0` means success, `1` a runtime/filesystem failure, and `2`
invalid command usage.

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

Audio analysis is designed for libraries containing many tracks:

- each track is analyzed by a fresh Python child process, so a native Essentia crash
  cannot stop the remaining queue;
- child processes only read audio and return versioned JSON; the parent process alone
  schedules work, updates SQLite, and renders Rich progress;
- decoded audio stays in single precision (`float32`);
- spectral facts are accumulated one FFT frame at a time instead of retaining a
  whole-track spectrum matrix;
- each completed track is committed to SQLite immediately;
- only `--workers` tracks can be analyzed concurrently;
- successful results are reused when the input file and analysis identity are unchanged.

BPM detection uses Essentia's `PercivalBpmEstimator` to estimate the track's global
tempo. DJ Digger then feeds that tempo into `BpmHistogram` with constant-tempo
tracking over an onset novelty curve, producing the beat grid used by intro/outro
windows and structural sections.

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

An analysis run is recorded as `running` before extraction starts. If the process is
stopped externally, every track committed before the interruption remains reusable. On
the next invocation, DJ Digger automatically finalizes the abandoned run as `partial` or
`failed`, then processes only remaining eligible work.

Only one analysis command may use a catalog at a time. A second concurrent invocation
fails immediately instead of modifying or duplicating the active run.

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

DJ Digger supports only the consolidated v6 schema. Catalogs created with versions v1–v5
are not upgraded. Preserve the old database as a backup, move it out of the configured
workspace location, and rerun DJ Digger to create a fresh catalog.

### Why does `doctor` report missing programs?

Metadata extraction requires `exiftool`. Analysis also requires `ffmpeg`, `ffprobe`,
and Essentia. The Docker image installs these dependencies. For a native setup, they
must be installed on the host.

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

## Architecture

DJ Digger uses a layered Python architecture under `src/dj_digger/`:

| Layer | Location | Responsibility |
| --- | --- | --- |
| Command line | `cli.py` | Defines Typer commands, JSON diagnostics, and exit codes. |
| Orchestration | `application.py` | Coordinates scans, metadata, analysis, exports, snapshots, and health checks. |
| Configuration | `config.py` | Loads and validates workspace, source, and DSP settings. |
| Scanning | `scanning/` | Discovers supported files and records source scan lifecycles. |
| Metadata | `metadata/` | Extracts and normalizes embedded tags with ExifTool. |
| Catalog | `catalog/` | Owns SQLite access, current-schema initialization, models, and repositories. |
| Analysis | `analysis/` | Runs audio decoding, DSP extraction, segmentation, semantics, and persistence. |
| Exports | `exports/` | Validates and atomically publishes catalog, analysis, audit, and snapshot files. |
| LLM curation | `skills/electronic-dj-set-curator/` | Turns eligible exports into a narrative DJ set with validated transitions and alternatives. |

`WorkspaceApplication` is the main coordination boundary. It opens the SQLite
database, validates or initializes its schema, registers configured sources, and
calls the service for each CLI operation. The catalog is the durable source of truth;
export files are generated views and can be recreated.

The main pipeline is:

1. `scan` observes configured source folders and reconciles successful observations.
2. `metadata` selects new or changed tracks and stores normalized embedded tags.
3. `analyze` selects eligible tracks and stores versioned technical and structural
   results.
4. `export` validates and publishes the current facets with atomic file replacement.
5. `snapshot` packages validated exports for transfer or archival.

The analysis identity includes its schema version, analyzer version, and DSP
configuration hash. This makes stale analysis detectable when code or analysis
settings change. JSON Schemas in `schemas/` define the public export contracts. The
single schema in `src/dj_digger/catalog/sql/` initializes fresh catalogs; generated
exports are never treated as primary storage.

The LLM curator is a downstream consumer, not part of the catalog runtime. This
separation keeps availability and technical facts deterministic while allowing the
LLM to reason about musical narrative, energy progression, alternatives, and
improvisation. Its outputs conform to `schemas/dj-set.schema.json`; they do not modify
the SQLite catalog or the source music files.
