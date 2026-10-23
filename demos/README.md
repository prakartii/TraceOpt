# Demo programs

Short C functions, one per kind of outcome. Run from the repository root in
WSL:

```bash
scripts/live.sh demos/fib.c 20000
```

Each command below was run end to end; the zkVM answer matched the native
answer every time. Results are with the default 10% margin and the cost model
calibrated before the generated entry function (6eba567), so a case close to
a bucket edge may change after the model is recalibrated.

| Command (`scripts/live.sh ...`) | Outcome | Measured proved size |
|---|---|---|
| `demos/fib.c 20000` | unrolled 8x chosen | 262,144 → 65,536 (75% less) |
| `demos/fib.c 1000000` | unrolled 8x chosen | 6,291,456 → 1,572,864 (75% less) |
| `demos/array_sum.c 12000` | unrolled 8x chosen | 262,144 → 131,072 (50% less) |
| `demos/array_sum.c 300000` | unrolled 8x chosen | 3,145,728 → 2,097,152 (33% less) |
| `demos/counter.c 1000 3` | unrolled 8x chosen (two inputs) | 65,536 → 32,768 (50% less) |
| `demos/mix.c 1000` | original kept: nothing to gain | 32,768 |
| `demos/formula.c 1000` | original kept: LLVM replaced the loop by a formula | 32,768 |
| `demos/steps.c 27` | original kept: loop count depends on the data | 32,768 |
| `demos/matrix.c 5000` | original kept: 2x rejected as too risky (a missed win) | 1,048,576 |
| `demos/array_sum.c 100000` | original kept: 2x saves less than 5% | 1,064,960 |

In some runs a version that was not chosen has a wrong predicted size (stage
8 shows "✘ off"), e.g. `fib.c 1000000` and `array_sum.c 300000`; the chosen
version was right in every case.
