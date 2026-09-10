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

The bounded MCP interface for curation is documented in
[docs/mcp.md](docs/mcp.md).

The implemented native curation workflow, including endpoint configuration, private
data disclosure, strict catalog grounding, human validation, and export variants, is
documented in [docs/curation.md](docs/curation.md).

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

4. Build the image and check the configuration. The fictional example below expects
   `demo-library/neon-archive` and `demo-library/lunar-radio` directories.

   ```bash
   export DJ_DIGGER_MUSIC_ROOT="$PWD/demo-library"
   docker compose build
   docker compose run --rm dj-digger doctor --config /config/local.toml
   ```

5. Build or refresh the complete catalog.

   ```bash
   docker compose run --rm dj-digger refresh --config /config/local.toml
   ```

The SQLite database is written to `workspace/dj-digger.sqlite`. Published files are
written to `workspace/exports/` with the example configuration.

DJ Digger maintains the SQLite catalog through ordered, timestamped migrations. Fresh
catalogs are initialized automatically, and supported existing catalogs are upgraded in place.
Unsupported legacy catalogs should be preserved as backups and moved out of the
configured workspace before creating a fresh catalog.

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
uvx dj-digger doctor --config config/demo.toml
uvx dj-digger refresh --config config/demo.toml
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
`duplicates`, and `export` commands through the current SQLite catalog. It never requires
or exposes the real media library. Docker and Docker Agent remain optional paths
for image distribution and orchestration; offline development uses the prepared
environment and local fixtures.

### Command guide

The [CLI usage guide](docs/cli-usage.md) documents every command, background jobs,
large-library analysis, duplicate handling, portable set copies, and LLM-assisted
curation. The supported portable-copy entry point is `dj-digger copy`; the historical
`references/copy-set.sh` script remains only as a migration aid.

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

DJ Digger initializes fresh catalogs and upgrades supported existing catalogs in
place. Unsupported legacy databases are not upgraded. Preserve an unsupported
database as a backup, move it out of the configured workspace location, and rerun
DJ Digger to create a fresh catalog.

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

See [Architecture](docs/ARCHITECTURE.md) for the current catalog data model,
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
