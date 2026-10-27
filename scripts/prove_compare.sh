#!/usr/bin/env bash
# Prove the original and TraceOpt's choice in RISC Zero (inside WSL).
#
#   scripts/prove_compare.sh strided_rw 5
#   scripts/prove_compare.sh demos/fib.c 20000 --receipt succinct
#
# Puts LLVM on PATH and runs scripts/prove_compare.py (see its --help).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
exec python3 "$ROOT/scripts/prove_compare.py" "$@"
