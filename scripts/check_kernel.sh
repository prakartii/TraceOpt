#!/usr/bin/env bash
# Build the kernel guest with one benchmark and check its zkVM output against
# tests/reference.py for each n. Prints kernel and user cycles for each run.
#
# Usage (inside WSL): scripts/check_kernel.sh <benchmark> <n>...
#   e.g. scripts/check_kernel.sh xorshift 0 1 1000
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <benchmark> <n>..." >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="$1"; shift
SRC="$ROOT/benchmarks/$NAME.c"
[[ -f "$SRC" ]] || { echo "no such benchmark: $SRC" >&2; exit 2; }

export TRACEOPT_KERNEL_SRC="$SRC"
"$ROOT/scripts/build_backend.sh" >/dev/null
HOST="${CARGO_TARGET_DIR:-$HOME/.cache/traceopt-target}/release/host"

fail=0
for n in "$@"; do
  report="$("$HOST" execute kernel "$n")"
  read -r got kcycles ucycles < <(python3 -c '
import json, sys
r = json.load(sys.stdin)
print(r["result"]["output"], r["result"]["kernel_cycles"], r["stats"]["user_cycles"])' <<<"$report")
  want="$(python3 "$ROOT/tests/reference.py" "$NAME" "$n")"
  if [[ "$got" == "$want" ]]; then
    echo "PASS $NAME n=$n output=$got kernel_cycles=$kcycles user_cycles=$ucycles"
  else
    echo "FAIL $NAME n=$n got=$got want=$want"
    fail=1
  fi
done
exit "$fail"
