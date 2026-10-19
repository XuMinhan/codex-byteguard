#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "$0")" && pwd)"
export CODEX_MAX_REQUEST_BYTES="${CODEX_MAX_REQUEST_BYTES:-950000}"
export CODEX_BYTE_GUARD_STATUS_DIR="${CODEX_BYTE_GUARD_STATUS_DIR:-${CODEX_HOME:-$HOME/.codex}/byteguard/status}"
exec "$source_dir/byteguard/Codex-ByteGuard/bin/codex" "$@"
