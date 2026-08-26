#!/usr/bin/env bash
set -euo pipefail

PROGRAM="${0##*/}"
VERBOSE=0
LIBRARY=""
OUTPUT=""
PLAYLIST=""
declare -a TRACK_ARGS=()

usage() {
  cat <<USAGE
Usage:
  $PROGRAM --library PATH --output PATH (--playlist FILE | --track FILE [...]) [options]

Required:
  -l, --library PATH   Root of the read-only media library.
  -o, --output PATH    Destination directory (must be outside the library).

At least one is required:
  -p, --playlist FILE  M3U/M3U8 playlist. Relative entries are resolved from --library.
                       #EXTGRP:<name> entries create relative subdirectories in --output.
  -t, --track FILE     Individual track. May be repeated; relative paths use --library.
                       Individual tracks are always appended after playlist entries,
                       preserving the order of the -t/--track arguments. If a playlist
                       ends inside an #EXTGRP, appended tracks inherit that group.

Optional:
  -v, --verbose        Show copy details in addition to the progress bar.
  -h, --help           Show this help.
USAGE
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

need_value() {
  [[ $# -ge 2 && -n "${2:-}" ]] || die "Missing value for $1"
}

trim() {
  local value=$1
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

while (($#)); do
  case "$1" in
    -l|--library)
      need_value "$@"
      LIBRARY=$2
      shift 2
      ;;
    -o|--output)
      need_value "$@"
      OUTPUT=$2
      shift 2
      ;;
    -p|--playlist)
      need_value "$@"
      [[ -z "$PLAYLIST" ]] || die "Only one --playlist may be provided"
      PLAYLIST=$2
      shift 2
      ;;
    -t|--track)
      need_value "$@"
      TRACK_ARGS+=("$2")
      shift 2
      ;;
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      (($# == 0)) || die "Unexpected positional arguments: $*"
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      die "Unexpected positional argument: $1"
      ;;
  esac
done

[[ -n "$LIBRARY" ]] || die "--library is required"
[[ -n "$OUTPUT" ]] || die "--output is required"
[[ -n "$PLAYLIST" || ${#TRACK_ARGS[@]} -gt 0 ]] || die "At least one --playlist or --track is required"
command -v rsync >/dev/null 2>&1 || die "rsync is required"
command -v realpath >/dev/null 2>&1 || die "realpath is required"
command -v chown >/dev/null 2>&1 || die "chown is required"

[[ -d "$LIBRARY" ]] || die "Library does not exist or is not a directory: $LIBRARY"
LIBRARY=$(realpath "$LIBRARY")
OUTPUT=$(realpath -m "$OUTPUT")

case "$OUTPUT/" in
  "$LIBRARY/"*) die "--output must be outside --library to keep the library read-only" ;;
esac

if [[ -n "$PLAYLIST" ]]; then
  [[ -f "$PLAYLIST" ]] || die "Playlist not found: $PLAYLIST"
  PLAYLIST=$(realpath "$PLAYLIST")
  case "${PLAYLIST,,}" in
    *.m3u|*.m3u8) ;;
    *) die "Playlist must have a .m3u or .m3u8 extension: $PLAYLIST" ;;
  esac
fi

mkdir -p -- "$OUTPUT"

declare -a SOURCES=()
declare -a SOURCE_LABELS=()
declare -a TRACK_GROUPS=()
CURRENT_GROUP=""

validate_group() {
  local group=$1 component
  group=$(trim "$group")
  [[ -n "$group" ]] || die "Empty #EXTGRP is not allowed"
  [[ "$group" != /* ]] || die "Absolute #EXTGRP paths are not allowed: $group"
  [[ "$group" != *$'\n'* && "$group" != *$'\r'* ]] || die "Invalid #EXTGRP value"

  IFS='/' read -r -a parts <<< "$group"
  for component in "${parts[@]}"; do
    [[ -n "$component" && "$component" != "." && "$component" != ".." ]] \
      || die "Unsafe #EXTGRP path: $group"
  done

  printf '%s\n' "$group"
}

resolve_library_track() {
  local raw=$1 candidate canonical
  raw=${raw%$'\r'}
  raw=$(trim "$raw")
  [[ -n "$raw" ]] || return 1

  if [[ "$raw" == file://* ]]; then
    raw=${raw#file://}
  elif [[ "$raw" =~ ^[a-zA-Z][a-zA-Z0-9+.-]*:// ]]; then
    die "Remote playlist entries are not supported: $raw"
  fi

  if [[ "$raw" = /* ]]; then
    candidate=$raw
  else
    candidate="$LIBRARY/$raw"
  fi

  canonical=$(realpath -e "$candidate" 2>/dev/null) || die "Track not found: $raw"
  [[ -f "$canonical" ]] || die "Track is not a regular file: $raw"

  case "$canonical" in
    "$LIBRARY"/*) ;;
    *) die "Track is outside the library: $raw" ;;
  esac

  printf '%s\n' "$canonical"
}

add_track() {
  local raw=$1 group=${2:-} resolved
  resolved=$(resolve_library_track "$raw")
  SOURCES+=("$resolved")
  SOURCE_LABELS+=("${resolved#"$LIBRARY/"}")
  TRACK_GROUPS+=("$group")
}

if [[ -n "$PLAYLIST" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%$'\r'}
    line=${line#$'\xEF\xBB\xBF'}
    line=$(trim "$line")
    [[ -n "$line" ]] || continue

    if [[ "$line" == \#EXTGRP:* ]]; then
      CURRENT_GROUP=$(validate_group "${line#\#EXTGRP:}")
      continue
    fi

    [[ "$line" == \#* ]] && continue
    add_track "$line" "$CURRENT_GROUP"
  done < "$PLAYLIST"
fi

# Individual tracks are appended after the playlist. If the playlist ends in a
# group, they inherit that group; with no playlist they remain at output root.
for track in "${TRACK_ARGS[@]}"; do
  add_track "$track" "$CURRENT_GROUP"
done

TOTAL=${#SOURCES[@]}
(( TOTAL > 0 )) || die "No tracks found"
WIDTH=${#TOTAL}
if (( WIDTH < 2 )); then WIDTH=2; fi
BAR_WIDTH=32

render_progress() {
  local current=$1 filled empty percent bar
  percent=$(( current * 100 / TOTAL ))
  filled=$(( current * BAR_WIDTH / TOTAL ))
  empty=$(( BAR_WIDTH - filled ))
  printf -v bar '%*s' "$filled" ''
  bar=${bar// /#}
  printf '\r[%-*s] %3d%% (%d/%d)' "$BAR_WIDTH" "$bar" "$percent" "$current" "$TOTAL"
  if (( current == TOTAL )); then printf '\n'; fi
  return 0
}

playlist_name="playlist.m3u8"
if [[ -n "$PLAYLIST" ]]; then
  playlist_name=$(basename "$PLAYLIST")
fi
playlist_out="$OUTPUT/$playlist_name"
playlist_stem=${playlist_name%.*}
txt_out="$OUTPUT/$playlist_stem.txt"

tmp_playlist=$(mktemp "$OUTPUT/.playlist.XXXXXX")
tmp_txt=$(mktemp "$OUTPUT/.playlist.XXXXXX")
cleanup_tmp() { rm -f -- "$tmp_playlist" "$tmp_txt"; }
trap cleanup_tmp EXIT
printf '#EXTM3U\n' > "$tmp_playlist"
printf 'ORDER\tGROUP\tFILE\tSOURCE\n' > "$tmp_txt"

last_written_group='__UNSET__'
render_progress 0
for ((i=0; i<TOTAL; i++)); do
  source=${SOURCES[$i]}
  source_label=${SOURCE_LABELS[$i]}
  group=${TRACK_GROUPS[$i]}
  basename=${source##*/}
  printf -v number "%0${WIDTH}d" $((i + 1))
  target_name="$number - $basename"

  target_dir="$OUTPUT"
  target_rel="$target_name"
  if [[ -n "$group" ]]; then
    target_dir="$OUTPUT/$group"
    target_rel="$group/$target_name"
  fi
  mkdir -p -- "$target_dir"
  target="$target_dir/$target_name"

  if (( VERBOSE )); then
    printf '\nCOPY %s/%s\n  group: %s\n  from:  %s\n  to:    %s\n' \
      "$number" "$TOTAL" "${group:-(root)}" "$source_label" "$target_rel"
    rsync -a --protect-args --itemize-changes -- "$source" "$target"
  else
    rsync -a --protect-args --quiet -- "$source" "$target"
  fi

  if [[ "$group" != "$last_written_group" ]]; then
    if [[ -n "$group" ]]; then
      printf '#EXTGRP:%s\n' "$group" >> "$tmp_playlist"
    fi
    last_written_group=$group
  fi
  printf '%s\n' "$target_rel" >> "$tmp_playlist"
  printf '%s\t%s\t%s\t%s\n' "$number" "$group" "$target_name" "$source_label" >> "$tmp_txt"
  render_progress $((i + 1))
done

mv -f -- "$tmp_playlist" "$playlist_out"
mv -f -- "$tmp_txt" "$txt_out"
trap - EXIT

if (( VERBOSE )); then
  printf '\nOWNERSHIP share:share -> %s\n' "$OUTPUT"
fi
chown -R share:share "$OUTPUT" || die "Failed to set ownership share:share on: $OUTPUT"

if (( VERBOSE )); then
  printf '\nPlaylist: %s\nText list: %s\n' "$playlist_out" "$txt_out"
fi
