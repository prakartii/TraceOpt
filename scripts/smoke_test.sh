#!/usr/bin/env bash
# Differential smoke test: run each guest in the RISC Zero executor and check
# its output against tests/reference.py. Execute mode only (no proving).
#
# Usage (inside WSL, after building backend/risc0):
#   scripts/smoke_test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${CARGO_TARGET_DIR:-$HOME/.cache/traceopt-target}/release/host"
REF="$ROOT/tests/reference.py"

if [[ ! -x "$HOST" ]]; then
  echo "host binary not found at $HOST; build backend/risc0 first" >&2
  exit 1
fi

fail=0
check() {
  local guest="$1" kernel="$2" n="$3"
  local got want
  got="$("$HOST" execute "$guest" "$n" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["output"])')"
  want="$(python3 "$REF" "$kernel" "$n")"
  if [[ "$got" == "$want" ]]; then
    echo "PASS $guest n=$n output=$got"
  else
    echo "FAIL $guest n=$n got=$got want=$want"
    fail=1
  fi
}

for n in 0 1 10 1000; do
  check probe sum_squares "$n"
  check kernel xorshift "$n"
done

exit "$fail"
