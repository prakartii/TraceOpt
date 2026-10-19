# Experiments

Status: **methodology fixed; results pending.** Every number added here must
come from a committed results file and the command that produced it.

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

Pending.
