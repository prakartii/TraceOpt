#!/usr/bin/env bash
# TraceOpt demonstration (inside WSL, after the setup in README.md).
#
#   scripts/demo.sh [model.json]      (default: results/model-clang21.json)
#
# 1. Analyze a kernel's LLVM IR and compare the static estimate with exact
#    counts from the IR interpreter.
# 2. Ask TraceOpt for an unroll factor in two situations:
#    - strided_rw, n = 5: unrolling crosses a power-of-two padding boundary,
#      so the proving work halves;
#    - xorshift, n = 1000: unrolling saves cycles but not padded size, so
#      the baseline is kept.
# 3. Link the chosen kernel into the RISC Zero guest, execute it, and print
#    the predicted and measured cycles side by side.
#
# Needs the backend built once (scripts/build_backend.sh); step 3 then
# rebuilds only the guest (seconds).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${1:-$ROOT/results/model-clang21.json}"
WORK="${TRACEOPT_DEMO_WORK:-$HOME/.cache/traceopt-demo}"
TARGET="${CARGO_TARGET_DIR:-$HOME/.cache/traceopt-target}"
KERNEL_BIN="$TARGET/riscv-guest/methods/kernel/riscv32im-risc0-zkvm-elf/release/kernel.bin"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
cd "$ROOT"
mkdir -p "$WORK"

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "1. Static estimate vs exact counts (branchy, n = 100)"
python3 -m traceopt profile tests/fixtures/clang21/branchy.ll --arg 0=100 \
  > "$WORK/profile.json"
python3 - "$WORK/profile.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
print(f"{'class':12} {'exact':>8} {'estimated':>10}")
for c in ("alu", "mul", "cmp", "cond_branch", "jump"):
    print(f"{c:12} {r['dynamic_counts'][c]:>8} {r['estimated_dynamic_counts'][c]:>10.1f}")
EOF

run_case() {
  local bench="$1" n="$2" out="$WORK/$1-$2"
  step "2. traceopt optimize $bench, n = $n"
  python3 -m traceopt optimize "benchmarks/$bench.c" --model "$MODEL" --arg "0=$n" \
    --work "$out" > "$out.json"
  python3 - "$out.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
print(f"{'candidate':10} {'pred. user':>11} {'pred. padded':>13} {'code B':>7}  note")
for c in r["candidates"]:
    print(f"{c['name']:10} {c['predicted_user_cycles'] or '-':>11} "
          f"{c['padded_total'] or '-':>13} {c['code_bytes']:>7}  {c['note']}")
print(f"\nselected: {r['selected']} ({r['reason']})")
EOF

  step "3. Measure the selected kernel in the RISC Zero executor"
  local obj
  obj=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["selected_object"])' \
        "$out.json")
  TRACEOPT_GUEST_ONLY=1 TRACEOPT_KERNEL_OBJ="$obj" scripts/build_backend.sh > /dev/null 2>&1
  TRACEOPT_KERNEL_ELF="$KERNEL_BIN" "$TARGET/release/host" execute kernel "$n" \
    > "$out.measured.json"
  python3 - "$out.json" "$out.measured.json" "$bench" "$n" <<'EOF'
import json, sys
sys.path.insert(0, "tests")
from reference import KERNELS
pred = json.load(open(sys.argv[1]))
meas = json.load(open(sys.argv[2]))
row = next(c for c in pred["candidates"] if c["name"] == pred["selected"])
s = meas["stats"]
ok = meas["result"]["output"] == KERNELS[sys.argv[3]](int(sys.argv[4]))
print(f"{'':14} {'predicted':>10} {'measured':>10}")
print(f"{'user cycles':14} {row['predicted_user_cycles']:>10} {s['user_cycles']:>10}")
print(f"{'padded total':14} {row['padded_total']:>10} {s['total_cycles']:>10}")
print(f"output matches reference: {ok}")
EOF
}

run_case strided_rw 5
run_case xorshift 1000
