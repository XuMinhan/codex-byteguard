#!/usr/bin/env bash
set -euo pipefail
source_dir="${1:-$(cd "$(dirname "$0")" && pwd)}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/Library/Caches/CodexByteGuard-build}"
cd "$source_dir/codex-rs"
cargo build --locked -p codex-cli --bin codex --profile dev-small
mkdir -p "$source_dir/byteguard/Codex-ByteGuard/bin"
cp "$CARGO_TARGET_DIR/dev-small/codex" "$source_dir/byteguard/Codex-ByteGuard/bin/codex"
