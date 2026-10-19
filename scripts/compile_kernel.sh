#!/usr/bin/env bash
# Compile a C kernel through LLVM IR into a RISC-V object for the guest.
#
# Usage (inside WSL): scripts/compile_kernel.sh <kernel.c> <outdir> [unroll_factor]
#
# Writes to <outdir>:
#   base.ll    clang -O1 -fno-unroll-loops, with the unroll-disable loop
#              metadata neutralized so that opt can still unroll it
#   uK.ll      base.ll after `opt -passes=loop-unroll -unroll-count=K`
#              (K = 1 means no unrolling: uK.ll is a copy of base.ll)
#   uK.o       llc output for rv32im / ILP32, to link via TRACEOPT_KERNEL_OBJ
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <kernel.c> <outdir> [unroll_factor]" >&2
  exit 2
fi
SRC="$1"; OUT="$2"; K="${3:-1}"
[[ "$K" =~ ^[1-9][0-9]*$ ]] || { echo "unroll factor must be a positive integer" >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=llvm_env.sh
source "$ROOT/scripts/llvm_env.sh"
mkdir -p "$OUT"

TARGET=(--target=riscv32-unknown-elf -march=rv32im -mabi=ilp32)

# -fno-unroll-loops stops Clang's own pipeline from unrolling, but it also
# tags each loop with llvm.loop.unroll.disable, which opt would honor. The
# rename leaves an unknown (ignored) loop property instead.
clang "${TARGET[@]}" -O1 -fno-unroll-loops -S -emit-llvm "$SRC" -o "$OUT/base.tmp.ll"
sed 's/llvm\.loop\.unroll\.disable/traceopt.unroll.cleared/' "$OUT/base.tmp.ll" > "$OUT/base.ll"
rm "$OUT/base.tmp.ll"

if [[ "$K" == 1 ]]; then
  cp "$OUT/base.ll" "$OUT/u1.ll"
else
  opt -S -passes=loop-unroll -unroll-count="$K" -unroll-runtime \
      "$OUT/base.ll" -o "$OUT/u$K.ll"
fi

llc -O2 -mattr=+m -target-abi=ilp32 -filetype=obj "$OUT/u$K.ll" -o "$OUT/u$K.o"
echo "$OUT/u$K.o"
