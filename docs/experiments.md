# Experiments

Status: **first evaluation complete** (`results/evaluation-clang21.json`).
Every number here comes from a committed results file and the command that
produced it.

## 1. Questions

1. How accurately does the calibrated model predict RISC Zero cycles for
   unroll variants of benchmarks it was not fitted on?
2. Does choosing the unroll factor by predicted *padded* cost lower the
   measured padded total compared with a baseline and with LLVM's default
   heuristics, and how often does it correctly keep the baseline?

## 2. Builds compared

| Build | How it is produced |
|---|---|
| Baseline | Clang 21 `-O1 -fno-unroll-loops` |
| Conventional | Clang 21 `-O2` (LLVM's default unrolling heuristics) |
| TraceOpt | Baseline IR + the unroll factor chosen by `traceopt optimize` (or the baseline unchanged) |

All builds are compiled for rv32im / ILP32 with `llc -O2`, linked into the
same kernel guest, and executed in the RISC Zero 3.0.6 executor with the
default segment limit (2^20). Outputs are checked against
`tests/reference.py`.

`-O3` produces the same kernel code as `-O2` for all four benchmarks
(checked by object size), so it is not listed separately.

## 3. Metrics

- **Padded total cycles** (`total_cycles`): the primary metric. Proving work
  follows it.
- User, paging, and kernel cycles; segment count; kernel code size.
- **Prediction error**: relative error of predicted user cycles and whether
  the predicted padded total equals the measured one.
- Proving time is not reported: proving segments larger than 2^15 cycles
  exceeded the memory available on the development machine
  (docs/feasibility.md §4.6).

Execution is deterministic; repeated runs gave identical statistics in every
case measured so far (results/baseline-gcc.json), so each configuration is
run once.

## 4. Threats to validity

- **Small benchmark set.** Four kernels with simple loops. Results may not
  transfer to larger programs, calls, or irregular control flow.
- **Calibration and evaluation overlap.** The model is fitted on the same
  four kernels it is evaluated on. Leave-one-benchmark-out errors are
  reported to show how it does on an unseen kernel, and evaluation inputs
  (n) differ from the calibration inputs.
- **Kernel cycles are host-reported.** `env::cycle_count()` is not
  constrained by the proof; it is used only as a measurement aid. Padded
  totals and user and paging cycles come from the executor's session
  statistics.
- **One machine, one toolchain.** Clang/LLVM 21.1.8 and RISC Zero 3.0.6 in
  WSL 2. Cycle counts do not depend on the host machine; proving time would.
- **Paging model simplifications.** Whole globals are assumed touched, and
  code growth is charged in whole pages (docs/cost-model.md §4).
- **Heuristic branch probabilities.** branchy's data-dependent branches are
  split evenly by the analyzer; its predictions carry that error.
- **Differential testing is not equivalence.** Variants are checked on a set
  of inputs in the IR interpreter and against the reference in the zkVM; this
  does not prove them equivalent for all inputs.

## 5. Results

Model: `results/model-clang21.json` (docs/cost-model.md). Policy: 5% minimum
improvement, 16x code-growth limit, 10% uncertainty band on user cycles.
Inputs n = 5, 50, 300, 3000 — none of them used for calibration (1, 10, 100,
1000). Every build's output matched the reference.

```bash
source scripts/llvm_env.sh
python3 scripts/evaluate.py --model results/model-clang21.json \
    --out results/evaluation-clang21.json
```

### Measured padded total cycles

"Best variant" is the lowest padded total among the measured unroll
variants (factors 1, 2, 4, 8), i.e. the best TraceOpt's candidate set could
reach.

| Benchmark | n | Baseline | -O2 | TraceOpt (choice) | Best variant |
|---|---|---|---|---|---|
| xorshift | 5 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| xorshift | 50 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| xorshift | 300 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| xorshift | 3000 | 65536 | 65536 | 65536 (unroll1) | 65536 |
| nested_fnv | 5 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| nested_fnv | 50 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| nested_fnv | 300 | 65536 | 65536 | 65536 (unroll1) | 65536 |
| nested_fnv | 3000 | 524288 | **262144** | 524288 (unroll1) | 262144 |
| branchy | 5 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| branchy | 50 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| branchy | 300 | 32768 | 32768 | 32768 (unroll1) | 32768 |
| branchy | 3000 | 131072 | 131072 | 131072 (unroll1) | 65536 |
| strided_rw | 5 | 262144 | 262144 | **131072 (unroll4)** | 131072 |
| strided_rw | 50 | 262144 | 262144 | 262144 (unroll1) | 262144 |
| strided_rw | 300 | 524288 | 524288 | 524288 (unroll1) | 524288 |
| strided_rw | 3000 | 2621440 | 2621440 | 2621440 (unroll1) | 2097152 |

### Summary

| Outcome | Cases |
|---|---|
| No variant could lower the padded total; TraceOpt kept the baseline | 12 |
| A win was available and TraceOpt took it | 1 (strided_rw n=5: −50%) |
| A win was available and TraceOpt missed it | 3 |
| TraceOpt's choice measured worse than the baseline | **0** |
| Predicted padded total of TraceOpt's choice equal to the measured one | 15 of 16 |

-O2 lowered the padded total in one case (nested_fnv n=3000), where it fully
unrolls the 16-iteration inner loop; in the other 15 its padded total equals
the baseline's. TraceOpt beat -O2 once (strided_rw n=5) and lost to it once
(nested_fnv n=3000).

### Why the three wins were missed

- **nested_fnv, n=3000** and **branchy, n=3000**: decisions near a
  power-of-two boundary. The baseline predictions were accurate (1.0% and
  0.3% error), but the 10% uncertainty band could not rule out that the
  baseline already fits the smaller padded size (nested_fnv) or that the
  candidates do not (branchy). The band was introduced after
  `traceopt optimize --measure` selected xorshift n=1000 unroll8 for a
  predicted halving that did not happen when measured; it trades missed wins
  for no false ones.
- **strided_rw, n=3000**: a model failure. User cycles were under-predicted
  by 35% (strided_rw's update loop, as in calibration), and the run spans 3
  segments, whose paging (159756 cycles) the single-segment paging model
  does not capture.

### Conclusions so far

- For these kernels, most unroll decisions do not change proving work at
  all: in 12 of 16 cases no unroll factor lowered the padded total, although
  unrolling lowered the cycle count in every calibration case with n ≥ 10
  (at n = 1 it was sometimes slower, e.g. xorshift 102 → 112 cycles).
- When TraceOpt changed the code, the predicted halving was real. It never
  selected a variant that measured worse than the baseline.
- The limiting factor is prediction accuracy near boundaries and for
  memory-heavy and multi-segment runs, not the decision logic.
