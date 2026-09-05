#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
cd "$root"
mode=${1:---quick}
if [ "$mode" != --quick ] && [ "$mode" != --runtime ]; then
  echo "usage: $0 [--quick|--runtime]" >&2
  exit 2
fi

environment_version=$(tr -d '[:space:]' < "$root/.codex/cloud/ENVIRONMENT_VERSION")
if [ -n "${DJ_DIGGER_CODEX_ENV_VERSION:-}" ] &&
   [ "$DJ_DIGGER_CODEX_ENV_VERSION" != "$environment_version" ]; then
  echo "environment version mismatch: expected $environment_version, got $DJ_DIGGER_CODEX_ENV_VERSION" >&2
  exit 1
fi

python_version=$(uv run python -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')
case "$python_version" in
  3.12.*) ;;
  *) echo "Python 3.12.x required (found $python_version)" >&2; exit 1 ;;
esac

uv_version=${DJ_DIGGER_UV_VERSION:-0.11.19}
case "$(uv --version)" in
  "uv $uv_version "*) ;;
  *) echo "uv $uv_version required (found $(uv --version))" >&2; exit 1 ;;
esac

for command in ffmpeg ffprobe exiftool; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "missing required command: $command" >&2
    exit 1
  }
done
if ! ffmpeg -hide_banner -muxers 2>/dev/null | grep -q 'chromaprint'; then
  echo "ffmpeg is missing the chromaprint muxer" >&2
  exit 1
fi
uv run python -c 'import essentia'
uv run dj-digger --help >/dev/null

if [ "$mode" = --runtime ]; then
  if [ -f "$root/.codex/cloud/runtime-smoke.py" ]; then
    uv run python "$root/.codex/cloud/runtime-smoke.py"
  elif [ -x "$root/.codex/cloud/runtime-smoke.sh" ]; then
    "$root/.codex/cloud/runtime-smoke.sh"
  else
    # Bounded public-entry-point smoke while the dedicated runtime smoke is absent.
    uv run pytest tests/test_cli.py -q
  fi
fi

echo "Codex environment check passed ($environment_version)"
