#!/usr/bin/env bash
# Prove one program at many inputs (inside WSL); see scripts/prove_staircase.py.
#
#   scripts/prove_staircase.sh demos/fib.c --n 1000 2000 4000 --execute-only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
exec python3 "$ROOT/scripts/prove_staircase.py" "$@"
