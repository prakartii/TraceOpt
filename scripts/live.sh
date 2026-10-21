#!/usr/bin/env bash
# Run TraceOpt live on any input, stage by stage (inside WSL).
#
#   scripts/live.sh                     interactive: asks for program and inputs
#   scripts/live.sh xorshift 777        one built-in kernel and input
#   scripts/live.sh my_kernel.c 42      your own C kernel
#   scripts/live.sh my_kernel.c 42 -7   a function with two inputs
#
# Puts LLVM on PATH and runs scripts/live.py (see `scripts/live.py --help`).
# Needs the backend built once (scripts/build_backend.sh) for the zkVM runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
exec python3 "$ROOT/scripts/live.py" "$@"
