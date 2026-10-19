# Clang 21 IR fixtures

Real LLVM IR for each benchmark, emitted by Ubuntu clang 21.1.8 for
`riscv32-unknown-elf -march=rv32im -mabi=ilp32` at `-O1 -fno-unroll-loops`
(the unroll-disable loop metadata is renamed; see `scripts/compile_kernel.sh`).

Regenerate inside WSL:

```bash
for b in sum_squares xorshift nested_fnv branchy strided_rw; do
  scripts/compile_kernel.sh benchmarks/$b.c /tmp/ir/$b 1
  cp /tmp/ir/$b/base.ll tests/fixtures/clang21/$b.ll
done
```

Note: `sum_squares.ll` contains no loop. Clang replaced it with a closed form,
so it cannot be used to study unrolling under Clang.

`xorshift_u{2,4,8}.ll` and `{nested_fnv,branchy,strided_rw}_u4.ll` are the
base fixtures after LLVM's runtime unroller (all loops, including inner ones):

```bash
opt -S -passes=loop-unroll -unroll-count=K -unroll-runtime \
    tests/fixtures/clang21/NAME.ll -o tests/fixtures/clang21/NAME_uK.ll
```

Factor 2 handles the odd iteration with straight-line code; factors 4 and 8
add a remainder (epilogue) loop that runs `n mod K` times.
