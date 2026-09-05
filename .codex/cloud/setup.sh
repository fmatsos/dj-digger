#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

# Keep the default in one place.  An override is accepted only as a plain
# semantic version so it cannot turn this command into an arbitrary install.
uv_version=${DJ_DIGGER_UV_VERSION:-0.11.19}
case "$uv_version" in
  [0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "invalid DJ_DIGGER_UV_VERSION: $uv_version" >&2; exit 2 ;;
esac

if [ "$(id -u)" -eq 0 ]; then
  apt_cmd=apt-get
else
  command -v sudo >/dev/null 2>&1 || {
    echo "setup requires root or sudo for system packages" >&2
    exit 1
  }
  apt_cmd="sudo apt-get"
fi

$apt_cmd update
DEBIAN_FRONTEND=noninteractive $apt_cmd install -y --no-install-recommends \
  ffmpeg libimage-exiftool-perl libchromaprint-tools unzip curl ca-certificates python3-pip

cd /workspace/dj-digger

python3 -m pip install "uv==$uv_version"
uv --version
uv sync --frozen --group dev
exec .codex/cloud/check.sh --quick
