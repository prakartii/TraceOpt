#!/usr/bin/env bash
# Build the RISC Zero backend (host + guests) inside WSL/Linux.
#
# - Limits parallelism: a default 20-job build exhausted WSL's ~7.6 GB and
#   crashed the VM (see docs/feasibility.md). Override with JOBS=<n>.
# - Keeps build output off /mnt/c, which is much slower than the Linux FS.
#   Override with CARGO_TARGET_DIR.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/.cache/traceopt-target}"
export PATH="$HOME/.risc0/bin:$HOME/.cargo/bin:$PATH"

cd "$ROOT/backend/risc0"
cargo build --release -j "${JOBS:-4}" "$@"
echo "host binary: $CARGO_TARGET_DIR/release/host"
