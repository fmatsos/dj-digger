#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
uv sync --frozen --group dev
exec "$root/.codex/cloud/check.sh" --quick
