#!/bin/sh
set -eu

cd /workspace/dj-digger

uv sync --frozen --group dev
exec .codex/cloud/check.sh --quick
