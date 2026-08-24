#!/usr/bin/env bash

set -Eeuo pipefail

# ==============================================================================
# DJ / Music library audit exporter
#
# Usage:
#   ./export-music-audit.sh /path/to/djing /path/to/music [output-directory]
#
# Example:
#   ./export-music-audit.sh ./djing ./music .
#
# Requirements:
#   - bash
#   - python3
#   - exiftool
#   - find
#   - sort
#   - tar
#   - realpath
#   - wc
#
# Optional:
#   - tree
#
# READ ONLY regarding source media libraries.
# ==============================================================================

DJING_ROOT="${1:-}"
MUSIC_ROOT="${2:-}"
OUTPUT_BASE="${3:-./music-library-audit}"

AUDIO_EXTENSIONS=(
    mp3
    flac
    wav
    aiff
    aif
    m4a
    aac
    ogg
    opus
)

if [[ -z "$DJING_ROOT" || -z "$MUSIC_ROOT" ]]; then
    echo "Usage:"
    echo "  $0 /path/to/djing /path/to/music [output-directory]"
    exit 1
fi

for command in python3 exiftool find sort tar realpath wc; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "ERROR: required command not found: $command" >&2
        exit 1
    fi
done

DJING_ROOT="$(realpath -- "$DJING_ROOT")"
MUSIC_ROOT="$(realpath -- "$MUSIC_ROOT")"
OUTPUT_BASE="$(realpath -m -- "$OUTPUT_BASE")"

if [[ ! -d "$DJING_ROOT" ]]; then
    echo "ERROR: djing directory does not exist: $DJING_ROOT" >&2
    exit 1
fi

if [[ ! -d "$MUSIC_ROOT" ]]; then
    echo "ERROR: music directory does not exist: $MUSIC_ROOT" >&2
    exit 1
fi

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
OUTPUT_DIR="${OUTPUT_BASE%/}/music-library-audit-${TIMESTAMP}"
ARCHIVE="${OUTPUT_DIR}.tar.gz"

mkdir -p "$OUTPUT_DIR"

LOG_FILE="${OUTPUT_DIR}/audit.log"
touch "$LOG_FILE"

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log() {
    printf '[%s] %s\n' "$(timestamp)" "$*" | tee -a "$LOG_FILE"
}

log_detail() {
    printf '[%s] %s\n' "$(timestamp)" "$*" >> "$LOG_FILE"
}

on_error() {
    local exit_code=$?
    local line_number="${1:-unknown}"

    trap - ERR
    set +e

    echo
    echo "============================================================"
    echo "ERROR"
    echo "============================================================"
    echo
    echo "The audit failed at line ${line_number}."
    echo "Exit code: ${exit_code}"
    echo

    if [[ -f "$LOG_FILE" ]]; then
        echo "Last 40 log lines:"
        echo
        tail -n 40 "$LOG_FILE"
        echo
        echo "Complete log:"
        echo "  $LOG_FILE"
    else
        echo "Log file unavailable:"
        echo "  $LOG_FILE"
    fi

    exit "$exit_code"
}

trap 'on_error $LINENO' ERR

log "============================================================"
log "Music library audit"
log "============================================================"
log ""
log "DJ library : $DJING_ROOT"
log "Music      : $MUSIC_ROOT"
log "Output     : $OUTPUT_DIR"
log "Log        : $LOG_FILE"
log ""

generate_inventory() {
    local root="$1"
    local prefix="$2"

    log "[$prefix] Generating audio file inventory..."

    ROOT="$root" PREFIX="$prefix" OUTPUT_DIR="$OUTPUT_DIR" \
    python3 <<'PY' 2>>"$LOG_FILE"
import csv
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

root = Path(os.environ["ROOT"]).resolve()
prefix = os.environ["PREFIX"]
output_dir = Path(os.environ["OUTPUT_DIR"])

extensions = {
    ".mp3", ".flac", ".wav", ".aiff", ".aif",
    ".m4a", ".aac", ".ogg", ".opus",
}

files_output = output_dir / f"{prefix}-files.tsv"
stats_output = output_dir / f"{prefix}-directory-stats.tsv"
summary_output = output_dir / f"{prefix}-summary.txt"

level1 = Counter()
level2 = Counter()
extensions_stats = Counter()
total_files = 0
total_bytes = 0

def clean(value):
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")

with files_output.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["path", "filename", "extension", "size_bytes", "mtime"])

    for path in sorted(root.rglob("*")):
        try:
            if not path.is_file():
                continue
            extension = path.suffix.lower()
            if extension not in extensions:
                continue
            stat = path.stat()
        except OSError as error:
            print(f"WARNING: unable to inspect {path}: {error}", file=sys.stderr)
            continue

        relative = path.relative_to(root)
        writer.writerow([
            clean(relative),
            clean(path.name),
            extension,
            stat.st_size,
            datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        ])

        total_files += 1
        total_bytes += stat.st_size
        extensions_stats[extension] += 1

        parts = relative.parts[:-1]
        if len(parts) >= 1:
            level1[parts[0]] += 1
        if len(parts) >= 2:
            level2["/".join(parts[:2])] += 1

with stats_output.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["level", "path", "tracks"])
    for path, count in level1.most_common():
        writer.writerow([1, clean(path), count])
    for path, count in level2.most_common():
        writer.writerow([2, clean(path), count])

with summary_output.open("w", encoding="utf-8") as handle:
    handle.write(f"Root: {root}\n")
    handle.write(f"Audio files: {total_files}\n")
    handle.write(f"Total bytes: {total_bytes}\n")
    handle.write(f"Total GiB: {total_bytes / 1024**3:.2f}\n")
    handle.write("\nFiles by extension:\n")
    for extension, count in extensions_stats.most_common():
        handle.write(f"{extension}\t{count}\n")
PY

    log "[$prefix] Audio inventory complete."
}

generate_directories() {
    local root="$1"
    local prefix="$2"

    log "[$prefix] Generating directory trees..."

    (
        cd "$root"
        find . -mindepth 1 -type d -printf '%P\n' 2>>"$LOG_FILE" | sort
    ) > "$OUTPUT_DIR/${prefix}-directories.txt"

    if command -v tree >/dev/null 2>&1; then
        (
            cd "$root"
            tree -d -L 3 --noreport 2>>"$LOG_FILE"
        ) > "$OUTPUT_DIR/${prefix}-tree-depth-3.txt"
    else
        (
            cd "$root"
            find . -mindepth 1 -maxdepth 3 -type d -printf '%P\n' 2>>"$LOG_FILE" | sort
        ) > "$OUTPUT_DIR/${prefix}-tree-depth-3.txt"
    fi

    log "[$prefix] Directory trees complete."
}

count_inventory_records() {
    local file="$1"

    python3 - "$file" <<'PY'
import csv
import sys

with open(sys.argv[1], "r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    print(sum(1 for _ in reader))
PY
}

inspect_metadata_csv() {
    local file="$1"

    python3 - "$file" <<'PY'
import csv
import sys

path = sys.argv[1]
count = 0
source_files = set()
duplicate_source_files = 0

try:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "SourceFile" not in reader.fieldnames:
            print("INVALID")
            sys.exit(2)

        for row in reader:
            count += 1
            source = row.get("SourceFile", "")
            if source in source_files:
                duplicate_source_files += 1
            source_files.add(source)
except (OSError, csv.Error, UnicodeError) as error:
    print(f"ERROR:{error}", file=sys.stderr)
    sys.exit(2)

print(f"{count}\t{len(source_files)}\t{duplicate_source_files}")
PY
}

generate_metadata() {
    local root="$1"
    local prefix="$2"
    local inventory_file="$OUTPUT_DIR/${prefix}-files.tsv"
    local metadata_file="$OUTPUT_DIR/${prefix}-metadata.csv"

    log "[$prefix] Extracting audio metadata with ExifTool..."

    local ext_args=()
    for extension in "${AUDIO_EXTENSIONS[@]}"; do
        ext_args+=("-ext" "$extension")
    done

    local exif_status=0

    if (
        trap - ERR
        cd "$root" || exit 98
        exiftool \
            -r \
            -csv \
            "${ext_args[@]}" \
            -FileName \
            -Directory \
            -FileType \
            -FileSize# \
            -Duration \
            -AudioBitrate \
            -SampleRate \
            -Title \
            -Artist \
            -AlbumArtist \
            -Album \
            -Track \
            -DiscNumber \
            -Genre \
            -Date \
            -Year \
            -Composer \
            -Comment \
            -BPM \
            -InitialKey \
            -Grouping \
            . \
            2>>"$LOG_FILE"
    ) > "$metadata_file"; then
        exif_status=0
    else
        exif_status=$?
    fi

    if [[ ! -s "$metadata_file" ]]; then
        log "[$prefix] ERROR: ExifTool generated an empty metadata CSV."
        return 1
    fi

    local expected_records
    expected_records="$(count_inventory_records "$inventory_file")"

    local inspection
    if ! inspection="$(inspect_metadata_csv "$metadata_file")"; then
        log "[$prefix] ERROR: metadata CSV cannot be parsed."
        return 1
    fi

    local actual_records
    local unique_sources
    local duplicate_sources

    IFS=$'\t' read -r actual_records unique_sources duplicate_sources <<< "$inspection"

    log_detail "[$prefix] ExifTool exit status: $exif_status"
    log_detail "[$prefix] Expected audio files: $expected_records"
    log_detail "[$prefix] CSV logical records: $actual_records"
    log_detail "[$prefix] Unique SourceFile values: $unique_sources"
    log_detail "[$prefix] Duplicate SourceFile values: $duplicate_sources"

    if [[ "$actual_records" -ne "$expected_records" ]]; then
        log "[$prefix] ERROR: metadata export incomplete: expected ${expected_records} records, got ${actual_records}."
        return 1
    fi

    if [[ "$unique_sources" -ne "$expected_records" ]]; then
        log "[$prefix] ERROR: SourceFile mismatch: expected ${expected_records} unique files, got ${unique_sources}."
        return 1
    fi

    if [[ "$duplicate_sources" -ne 0 ]]; then
        log "[$prefix] ERROR: metadata CSV contains ${duplicate_sources} duplicate SourceFile record(s)."
        return 1
    fi

    if [[ "$exif_status" -ne 0 ]]; then
        log "[$prefix] WARNING: ExifTool returned status ${exif_status}, but the metadata export is complete."
        log "[$prefix] WARNING: ${actual_records}/${expected_records} audio files successfully exported; continuing."
        log "[$prefix] WARNING: ExifTool diagnostics are preserved in audit.log."
    else
        log "[$prefix] ExifTool completed successfully."
    fi

    log "[$prefix] Metadata validation: ${actual_records}/${expected_records} records OK."
}

generate_dj_metadata_inventory() {
    log "[dj] Searching Traktor / Serato / playlist metadata..."

    local output="$OUTPUT_DIR/dj-metadata-files.tsv"
    printf 'root\tpath\tsize_bytes\tmtime\n' > "$output"

    scan_root() {
        local root="$1"
        local label="$2"
        [[ -d "$root" ]] || return 0

        (
            cd "$root"
            find . -type f \
                \( \
                    -iname '*.nml' \
                    -o -iname '*.tsi' \
                    -o -iname '*.m3u' \
                    -o -iname '*.m3u8' \
                    -o -iname '*.pls' \
                    -o -iname '*.cue' \
                    -o -iname '*.xml' \
                    -o -iname '*.db' \
                    -o -iname '*.sqlite' \
                    -o -iname '*.sqlite3' \
                    -o -iname '*.crate' \
                    -o -iname '*.scrate' \
                    -o -iname '*.session' \
                    -o -iname 'collection.nml' \
                    -o -iname 'database' \
                    -o -iname 'database V2' \
                    -o -ipath '*/_Serato_/*' \
                \) \
                -printf "${label}\t%P\t%s\t%TY-%Tm-%Td %TH:%TM:%TS\n" \
                2>>"$LOG_FILE"
        )
    }

    {
        scan_root "$DJING_ROOT" "djing"
        scan_root "$MUSIC_ROOT" "music"
    } | sort >> "$output"

    local count
    count="$(python3 - "$output" <<'PY'
import csv
import sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    print(sum(1 for _ in csv.DictReader(handle, delimiter="\t")))
PY
)"

    log "[dj] Found $count DJ metadata file(s)."
}

generate_serato_inventory() {
    log "[serato] Searching for _Serato_ directories..."

    local output="$OUTPUT_DIR/serato-directories.txt"

    {
        find "$DJING_ROOT" -type d -iname '_Serato_' -print 2>>"$LOG_FILE"
        find "$MUSIC_ROOT" -type d -iname '_Serato_' -print 2>>"$LOG_FILE"
    } | sort -u > "$output"

    local count
    count="$(wc -l < "$output")"

    log "[serato] Found $count _Serato_ directorie(s)."
}

generate_traktor_inventory() {
    log "[traktor] Searching for Traktor files..."

    local output="$OUTPUT_DIR/traktor-files.tsv"
    printf 'root\tpath\tsize_bytes\tmtime\n' > "$output"

    scan_root() {
        local root="$1"
        local label="$2"
        [[ -d "$root" ]] || return 0

        (
            cd "$root"
            find . -type f \
                \( \
                    -iname '*.nml' \
                    -o -iname '*.tsi' \
                    -o -iname 'collection.nml' \
                \) \
                -printf "${label}\t%P\t%s\t%TY-%Tm-%Td %TH:%TM:%TS\n" \
                2>>"$LOG_FILE"
        )
    }

    {
        scan_root "$DJING_ROOT" "djing"
        scan_root "$MUSIC_ROOT" "music"
    } | sort >> "$output"

    local count
    count="$(python3 - "$output" <<'PY'
import csv
import sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    print(sum(1 for _ in csv.DictReader(handle, delimiter="\t")))
PY
)"

    log "[traktor] Found $count Traktor file(s)."
}

generate_readme() {
    log "[audit] Generating README..."

    cat > "$OUTPUT_DIR/README.txt" <<README_EOF
Music library audit export
==========================

Generated:
$(date --iso-8601=seconds)

Sources
-------

djing:
$DJING_ROOT

music:
$MUSIC_ROOT

Audio library exports
---------------------

djing-files.tsv
    Complete audio inventory of the historical DJ library.

djing-metadata.csv
    Embedded audio metadata extracted with ExifTool.

djing-directories.txt
    Complete directory list.

djing-tree-depth-3.txt
    Directory overview limited to 3 levels.

djing-directory-stats.tsv
    Track counts for directory levels 1 and 2.

djing-summary.txt
    Basic volume statistics.

music-files.tsv
music-metadata.csv
music-directories.txt
music-tree-depth-3.txt
music-directory-stats.tsv
music-summary.txt
    Equivalent exports for the Lidarr-managed music library.

DJ application exports
----------------------

dj-metadata-files.tsv
    Inventory of historical DJ application metadata.

    Includes:
    - Traktor NML
    - Traktor TSI
    - Serato crates
    - Serato smart crates
    - Serato history/session files
    - Serato databases
    - all files below _Serato_ directories
    - M3U / M3U8 playlists
    - PLS playlists
    - CUE files
    - XML files
    - SQLite databases

serato-directories.txt
    Detected _Serato_ directories.

traktor-files.tsv
    Dedicated Traktor NML / TSI inventory.

Diagnostics
-----------

audit.log
    Complete technical execution log.
    ExifTool stderr is preserved here.

    ExifTool metadata completeness is validated by parsing the generated CSV
    with Python's CSV parser. wc -l is intentionally not used for metadata CSV
    validation because valid CSV fields may contain embedded line breaks.

Safety
------

This audit is read-only regarding:

$DJING_ROOT
$MUSIC_ROOT

No media file is modified, moved, renamed, deleted or retagged.
README_EOF

    log "[audit] README complete."
}

log ""
log "Starting DJING analysis"
log ""

generate_inventory "$DJING_ROOT" "djing"
generate_directories "$DJING_ROOT" "djing"
generate_metadata "$DJING_ROOT" "djing"

log ""
log "Starting MUSIC analysis"
log ""

generate_inventory "$MUSIC_ROOT" "music"
generate_directories "$MUSIC_ROOT" "music"
generate_metadata "$MUSIC_ROOT" "music"

log ""
log "Starting DJ application metadata discovery"
log ""

generate_dj_metadata_inventory
generate_serato_inventory
generate_traktor_inventory
generate_readme

log ""
log "Creating archive..."

tar \
    -C "$(dirname "$OUTPUT_DIR")" \
    -czf "$ARCHIVE" \
    "$(basename "$OUTPUT_DIR")" \
    2>>"$LOG_FILE"

log ""
log "============================================================"
log "Done"
log "============================================================"
log ""
log "Directory:"
log "  $OUTPUT_DIR"
log ""
log "Archive to upload:"
log "  $ARCHIVE"
log ""
log "Technical log:"
log "  $LOG_FILE"
log ""
