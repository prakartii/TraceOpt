#!/usr/bin/env bash
# TraceOpt demonstration (inside WSL, after the setup in README.md).
#
#   scripts/demo.sh                 narrated walk-through, pauses between steps
#   scripts/demo.sh --no-pause      runs straight through
#   scripts/demo.sh --no-measure    predictions only, no RISC Zero runs
#
# Puts LLVM on PATH and runs scripts/demo.py, which explains every step: the
# C program and its input, the unrolled versions, their predicted cost and
# power-of-two padding, the decision, and the measured zkVM result. Any
# other option is passed on to demo.py (see `scripts/demo.py --help`).
#
# Needs the backend built once (scripts/build_backend.sh) for the zkVM runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
cd "$ROOT"
exec python3 scripts/demo.py "$@"
