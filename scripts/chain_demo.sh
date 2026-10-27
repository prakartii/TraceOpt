#!/usr/bin/env bash
# Prover and verifier, the way a blockchain uses a proof (inside WSL);
# see scripts/chain_demo.py.
#
#   scripts/chain_demo.sh demos/counter.c 1000 3
#   scripts/chain_demo.sh demos/fib.c 20000 --pause
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
exec python3 "$ROOT/scripts/chain_demo.py" "$@"
