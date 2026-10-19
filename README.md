# TraceOpt

[![tests](https://github.com/prakartii/TraceOpt/actions/workflows/tests.yml/badge.svg)](https://github.com/prakartii/TraceOpt/actions/workflows/tests.yml)

**TraceOpt: A Proving-Cost-Aware Compiler Optimization Framework for Zero-Knowledge Virtual Machines**

> Invention-disclosure title: *Method and System for Proving-Cost-Aware
> Compilation for Zero-Knowledge Virtual Machine Targets*

TraceOpt is a research prototype. It asks whether a compiler can make better
optimization decisions for zero-knowledge virtual machines (zkVMs) by
estimating the **cost of proving** a program's execution, instead of relying
only on conventional goals such as native speed or code size.

> **Status: research prototype, working end to end (Phases 0–5).**
> `traceopt optimize` compiles a C kernel with Clang, generates loop-unroll
> variants with LLVM, predicts each one's padded proving size with a model
> calibrated on RISC Zero measurements, picks one (or keeps the baseline),
> and can measure the result in the RISC Zero executor. On a first
> evaluation of 16 unseen cases it halved the padded size once, kept the
> baseline 15 times, and never chose a variant that measured worse; it also
> missed 3 available wins. See [Results](#results) and
> [Project progress](#project-progress).

## Contents

- [The problem](#the-problem)
- [Approach](#approach)
- [How TraceOpt works](#how-traceopt-works)
- [Project progress](#project-progress)
- [Findings so far](#findings-so-far)
- [Results](#results)
- [Benchmarks](#benchmarks)
- [Cost model](#cost-model-initial-proposal)
- [Installation](#installation)
- [Usage](#usage)
- [Testing](#testing)
- [Documentation](#documentation)
- [Repository structure](#repository-structure)
- [Limitations](#limitations)

# The problem

A zkVM runs a program and produces a cryptographic proof that the run was
correct. Generating that proof usually costs far more than running the program,
and the cost depends on properties of the execution trace, such as the number
of cycles and memory paging, rather than on native wall-clock time.

Conventional compiler heuristics optimize for native hardware. Loop unrolling is
an example: it removes loop-control instructions, which can reduce zkVM cycles,
but it also enlarges the code. In RISC Zero, touching additional memory pages
carries a significant per-page cycle cost, so an optimization that helps on a
CPU can be neutral or harmful inside a zkVM.

TraceOpt explores using a calibrated, target-specific proving-cost estimate to
decide **whether and how** to apply an optimization.

## Approach

For the first prototype, the scope is deliberately narrow:

- **One backend:** [RISC Zero](https://dev.risczero.com/) 3.0.6. SP1 is the
  fallback; Phase 0 found no blocker that requires it.
- **One optimization:** loop unrolling, using LLVM's existing `loop-unroll` pass.
  TraceOpt chooses the unroll factor; it does not implement its own unroller.
- **One cost model:** a linear model over a small set of IR features, calibrated
  against measured RISC Zero cycle counts, combined with a model of RISC Zero's
  segment padding.

Design choices and their reasons are recorded in
[docs/design-decisions.md](docs/design-decisions.md).

## How TraceOpt works

```
Source (C) → LLVM IR → Program Analysis → Candidate Optimizations
          → Proving-Cost Estimation → Optimization Selection
          → Target Compilation (RISC Zero guest) → Evaluation Report
```

| Stage | Module | Status |
|---|---|---|
| Source → LLVM IR (Clang 21) | `traceopt/toolchain.py` | Implemented |
| Program analysis (loops, trip counts, instruction classes, footprint) | `traceopt/ir.py`, `loops.py`, `features.py`, `footprint.py` | Implemented; matches LLVM LoopInfo on all benchmarks |
| Dynamic count estimation | `traceopt/frequency.py`, `evaluate.py` | Implemented; exact vs. an IR interpreter except data-dependent branches |
| Candidate generation (`opt` loop-unroll factors) | `traceopt/toolchain.py` | Implemented |
| Proving-cost estimation | `traceopt/model.py`, `segments.py`, `calibrate.py` | Implemented; calibrated, 8.3% mean held-out cycle error |
| Optimization selection | `traceopt/decision.py`, `optimize.py` | Implemented, with differential testing and an uncertainty margin |
| Target compilation into a RISC Zero guest | `backend/risc0/`, `traceopt/backend.py` | Implemented (Clang and GCC routes verified) |
| Evaluation and reports (JSON) | `scripts/evaluate.py`, `traceopt/report.py` | Implemented; first evaluation done |

Module responsibilities are described in
[docs/architecture.md](docs/architecture.md).

## Project progress

The work is split into seven phases over about eight weeks. Full task lists
are in the [development roadmap](docs/development-roadmap.md), and work is
tracked as [GitHub issues](https://github.com/prakartii/TraceOpt/issues)
labelled by phase. The percentages below are rough estimates against the
roadmap checklists, not measurements.

| Phase | Goal | Status | Estimate |
|---|---|---|---|
| 0. Feasibility | Toolchain works; a C kernel runs in a RISC Zero guest | Done except proving memory vs. segment size | ~95% |
| 1. IR analysis and baseline | Analyzer, benchmarks, reproducible baseline | Done: validated on Clang 21 IR against LLVM LoopInfo and an IR interpreter | 100% |
| 2. Cost model | Calibrated model with reported error | Done: 64 measured variants, held-out error reported | 100% |
| 3. Cost-aware optimization | Pick an unroll factor or keep the baseline | Done: `traceopt optimize` with differential tests and an uncertainty margin | 100% |
| 4. Backend integration and reporting | Automated build → run → report | Done: `--measure`, guest-only builds (17 s per variant) | ~90% |
| 5. Evaluation | Baseline vs. `-O2` vs. TraceOpt | First evaluation done (16 cases); larger benchmark set pending | ~70% |
| 6. Finalization and demo | Clean setup check, demo, write-up | Demo script done; clean-install check pending | ~40% |

**Overall: roughly 85%.** The full pipeline works; what remains is
broadening the evaluation and polishing.

**Next steps:**
1. Verify the setup on a clean WSL install ([#26](https://github.com/prakartii/TraceOpt/issues/26)).
2. Measure proving time and memory against segment size ([#3](https://github.com/prakartii/TraceOpt/issues/3)); needs care with the ~7.6 GB memory limit.
3. Improve the model where it fails: memory-heavy loops (strided_rw) and
   multi-segment paging (docs/experiments.md §5).
4. Add benchmarks so the model is calibrated and evaluated on more than four
   kernels.

## Findings so far

All measured in the RISC Zero 3.0.6 executor. Commands and full tables are in
[docs/feasibility.md](docs/feasibility.md) §4.

- **Total cycles are padded to powers of two.** Each segment's size is
  rounded up to 2^k, so cutting user cycles lowers proving work only when it
  crosses a boundary. For example, xorshift at n = 1000 has 12,100 user
  cycles and 18,635 paging cycles, and is padded to 65,536.
- **The segment model matches every measured configuration.**
  `traceopt/segments.py` reproduces the segment count and padded total of all
  9 measured runs, including runs with smaller segment limits
  (`tests/test_segments.py`).
- **Loop overhead is visible and exactly linear.** The xorshift kernel costs
  `95 + 8n` cycles: 8 cycles per iteration, two of which are loop control.
  This is the overhead unrolling targets.
- **Paging depends on memory footprint, not access count.** `strided_rw`
  pays 61,154 paging cycles whether it makes 0 or 1000 passes over its 64 KiB
  array; xorshift pays 18,635. The memory feature in the cost model should be
  distinct pages touched, not memory accesses.
- **Compilers can delete the loop entirely.** rustc/LLVM replaced a
  sum-of-squares loop with its closed form, so its cycle count did not grow
  with n. Benchmarks are designed with loop-carried dependences to avoid this.
- **Segment size changes paging cost.** The same run pays 18,635 paging
  cycles with one segment and 31,825 with four (limit 2^18), so variants must
  be compared at the same segment limit.
- **Proving memory is the hardware limit.** A 2^15-cycle proof took 7.0 s and
  peaked at 303 MB. A 2^20-cycle segment was killed after using 7.5 GB, the
  memory available to WSL on the development machine.

## Results

All numbers below come from committed result files; the commands that
regenerate them are in [docs/cost-model.md](docs/cost-model.md) and
[docs/experiments.md](docs/experiments.md).

**Cost model** (`results/model-clang21.json`, fitted on 64 measured
variants: 4 benchmarks × unroll factors 1, 2, 4, 8 × n = 1, 10, 100, 1000):

| Held-out benchmark | Mean error of predicted kernel cycles |
|---|---|
| branchy | 1.5% |
| nested_fnv | 6.4% |
| xorshift | 7.1% |
| strided_rw | 18.3% |

Each benchmark is predicted by a model fitted without it. Exact instruction
counts from the IR interpreter give almost the same errors, so the remaining
error is in the IR-to-cycles mapping rather than the static analysis.

**Evaluation** (`results/evaluation-clang21.json`, 16 cases at inputs not
used for calibration, all outputs correct):

| Outcome | Cases |
|---|---|
| No unroll factor could lower the padded total; TraceOpt kept the baseline | 12 |
| A lower padded total was available and TraceOpt chose it (strided_rw, n = 5: −50%) | 1 |
| A lower padded total was available and TraceOpt missed it | 3 |
| TraceOpt's choice measured worse than the baseline | 0 |

Clang `-O2` lowered the padded total in one case (nested_fnv, n = 3000) and
matched the baseline in the other 15. The missed wins are analyzed in
[docs/experiments.md](docs/experiments.md#5-results): two are near a
power-of-two boundary, where the 10% safety margin declined to act, and one
is a model failure on a memory-heavy, multi-segment run.

These results cover four small kernels on one machine and one toolchain;
they show the approach working, not a general speedup.

## Benchmarks

Each kernel in `benchmarks/` exports `uint32_t traceopt_kernel(uint32_t n)`
and has a Python reference in `tests/reference.py`. Baseline numbers below
are from [results/baseline-gcc.json](results/baseline-gcc.json): compiled
with RISC Zero's GCC 13.2.0 at `-O2`, default segment limit, 1 segment each.
Every run matched its reference and was identical across repeats.

| Kernel | What it exercises | Code (bytes) | Kernel cycles, n = 1000 | Padded total, n = 1000 |
|---|---|---|---|---|
| `sum_squares` | simple arithmetic loop | 44 | 4,094 | 32,768 |
| `xorshift` | loop-carried bit operations | 64 | 8,095 | 65,536 |
| `nested_fnv` | nested loop (n × 16), hashing with multiply | 72 | 67,098 | 131,072 |
| `branchy` | data-dependent three-way branch | 124 | 14,814 | 65,536 |
| `strided_rw` | strided reads and writes over a 64 KiB array | 140 | 645,641 | 1,048,576 |

These are GCC baselines for the measurement backend. The planned Clang
`-O1` / `-O2` / `-O3` / TraceOpt comparison has not been run yet.

## Cost model (initial proposal)

```
C(F) = Σᵢ wᵢ·nᵢ(F) + w_M·M(F) + w_B·B(F) + w_L·L(F)
```

- `nᵢ(F)`: estimated dynamic counts of instruction classes
- `M(F)`: memory and code-footprint features related to paging
- `B(F)`: estimated dynamic branch count
- `L(F)`: lookup/precompile features (omitted for the first backend)

The weights will be fitted to measured cycle counts by non-negative least
squares (`traceopt/calibrate.py`), and the error reported on held-out
benchmarks. The predicted user and paging cycles then go through the segment
model to give a padded total, which is what candidates are compared on. This
is a modeling hypothesis, not a validated formula. Precise feature
definitions are in
[architecture.md §4](docs/architecture.md#4-cost-model-initial-proposal-not-validated).

TraceOpt keeps these quantities separate and never reports one as another:

- **Predicted cost**: the model's output.
- **Execution cycles and segment count**: measured by the RISC Zero executor.
- **Proving time**: measured wall-clock time of proof generation. It depends on
  the hardware and may be unavailable when memory is limited.
- **Native execution time**: not used as a proxy for proving cost.

### Decision rule

`traceopt/decision.py` keeps the baseline unless a candidate:

1. has every prediction it needs,
2. passed differential testing (same outputs as the baseline),
3. is at most 16× the baseline's code size (a loose safety limit; extra
   1 KiB code pages are charged as paging in the prediction), and
4. has a predicted padded total at least 5% below the baseline's.

Among the candidates that qualify, the lowest padded total wins; ties go to
fewer user cycles, then smaller code. Every candidate gets a row explaining
why it was or was not chosen.

## Installation

RISC Zero's installer supports x86-64 Linux and arm64 macOS, so on Windows
the project is developed inside WSL 2 (Ubuntu). The commands below were
verified on Ubuntu 26.04 in WSL.

### Verified toolchain

| Tool | Version |
|---|---|
| rzup | 0.5.0 |
| cargo-risczero, r0vm, `risc0-zkvm` | 3.0.6 |
| RISC Zero guest Rust | 1.97.0 |
| RISC Zero C/C++ toolchain | 2024.1.5 (GCC 13.2.0, `riscv32-unknown-elf`) |
| Host Rust | 1.99.0 |
| Python | 3.10+ (CI: 3.10 and 3.12) |
| LLVM/Clang | not installed yet |

### Backend (WSL)

```bash
# Toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
curl -L https://risczero.com/install | bash
~/.risc0/bin/rzup install

# Build (first build takes ~15 minutes; uses 4 jobs to stay within memory)
scripts/build_backend.sh
```

LLVM, needed for the Clang route (not yet tested end to end):

```bash
sudo apt-get update && sudo apt-get install -y clang llvm lld
```

### Python tools (any OS)

Standard library only, no dependencies:

```bash
pip install .            # installs the `traceopt` command
# or run without installing:
python -m traceopt --help
```

## Usage

### Run a benchmark in the zkVM (WSL)

```bash
# Build the guest with one benchmark, run it for each n, check against the reference
scripts/check_kernel.sh nested_fnv 1 100

# Run the most recently built kernel directly: host <execute|prove> <probe|kernel> [n]
~/.cache/traceopt-target/release/host execute kernel 1000

# Cap the segment size (2^18 cycles)
TRACEOPT_SEGMENT_PO2=18 ~/.cache/traceopt-target/release/host execute kernel 100000
```

The host prints JSON with the kernel's output, the cycles spent inside the
kernel, and the session statistics (segments and total, user, paging, and
reserved cycles). `prove` works for small inputs; for larger inputs, cap the
segment size with `TRACEOPT_SEGMENT_PO2` (see
[docs/feasibility.md](docs/feasibility.md) §5).

### TraceOpt commands

```bash
# Choose an unroll factor for a C kernel (needs LLVM on PATH and a fitted model)
source scripts/llvm_env.sh
traceopt optimize benchmarks/xorshift.c --model results/model-clang21.json --arg 0=1000

# Features of an LLVM IR function (JSON). --arg sets loop-bound parameters.
traceopt analyze tests/fixtures/clang21/xorshift.ll --arg 0=1000

# Exact counts from the IR interpreter, next to the static estimate
traceopt profile tests/fixtures/clang21/branchy.ll --arg 0=100

# Predicted segments and padded total for user and per-segment paging cycles
traceopt segments 12100 18635            # → 1 segment, padded total 65536
traceopt segments 804100 7956 --po2 18   # → 4 segments

# Cost-aware choice among candidates
traceopt decide examples/candidates.json [--min-improvement 0.05] [--po2 20]
```

`candidates.json` format (see `examples/candidates.json`):

```json
{
  "baseline":   {"name": "unroll1", "predicted_user_cycles": 30000, "paging_per_segment": 18635, "code_bytes": 140},
  "candidates": [{"name": "unroll2", "predicted_user_cycles": 9000, "paging_per_segment": 18635, "code_bytes": 200}]
}
```

Use `null` for a prediction that is unavailable; that candidate is then
never selected.

## Testing

Unit tests (69 tests, standard library only; run from the repository root).
CI runs them on every push:

```bash
python -m unittest discover -s tests
```

They cover the IR parser, loops and trip counts (cross-checked against
simulation over more than 1,000 cases), instruction classes, frequency
estimates, the CLI, the segment model (against measured data), calibration,
and the decision logic.

zkVM checks (inside WSL, after building):

```bash
scripts/smoke_test.sh                     # probe and kernel guests vs. reference
scripts/check_kernel.sh nested_fnv 1 100  # one benchmark in the zkVM
python3 scripts/run_baseline.py --out results/baseline-gcc.json
```

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Pipeline, modules, cost-model features, predicted vs. measured quantities |
| [docs/feasibility.md](docs/feasibility.md) | Phase 0 environment, commands, measurements, and blockers |
| [docs/design-decisions.md](docs/design-decisions.md) | Why RISC Zero, C kernels via FFI, Python over textual IR, LLVM's unroller |
| [docs/development-roadmap.md](docs/development-roadmap.md) | Phases 0–6, tasks, dependencies, risks, work split |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Workflow, commit conventions, rules for reporting results |

## Repository structure

```
TraceOpt/
├── .github/workflows/      CI: unit tests on Python 3.10 and 3.12
├── .gitattributes
├── .gitignore
├── CONTRIBUTING.md
├── README.md
├── pyproject.toml          package metadata and `traceopt` command
├── backend/risc0/          RISC Zero workspace
│   ├── host/               runs guests, prints JSON measurements
│   └── methods/
│       ├── guest/          Rust-only probe guest
│       └── kernel/         Rust guest that links a C kernel via FFI
├── benchmarks/             C kernels exporting traceopt_kernel(uint32_t)
├── docs/
│   ├── architecture.md
│   ├── design-decisions.md
│   ├── development-roadmap.md
│   └── feasibility.md      Phase 0 measurements and blockers
├── results/                curated measurement outputs (JSON)
│   └── baseline-gcc.json   GCC baseline for all five benchmarks
├── scripts/
│   ├── build_backend.sh    builds the backend in WSL
│   ├── check_kernel.sh     runs one benchmark and checks its output
│   ├── run_baseline.py     measures all benchmarks, writes JSON
│   └── smoke_test.sh       end-to-end backend checks
├── tests/                  unit tests, IR fixtures, kernel references
└── traceopt/               Python package
    ├── ir.py               textual LLVM IR parser
    ├── loops.py            dominators, natural loops, trip counts
    ├── features.py         instruction classes and static counts
    ├── frequency.py        block frequencies, dynamic counts
    ├── segments.py         RISC Zero segment and padding model
    ├── calibrate.py        least-squares fit, held-out error
    ├── decision.py         cost-aware candidate selection
    └── cli.py              `traceopt analyze | segments | decide`
```

## Limitations

- A single backend (RISC Zero) and a single transformation (loop unrolling).
- C benchmark kernels only. Rust guest code is not optimized by TraceOpt.
- The IR parser handles the subset of LLVM IR the benchmarks need and rejects
  `switch`, `invoke`, and other constructs it does not model.
- Correctness is checked by differential testing, not formal equivalence proofs.
- Proving time may be measurable only for small programs on the development
  machine (about 7.6 GB of RAM available to WSL).
- The cost model will be calibrated on a small benchmark set and may not
  generalize.
- `env::cycle_count()`, used to measure kernel cycles, is reported by the host
  and not constrained by the proof. It is a measurement aid, not a proven value.

**Future work** (not part of the current plan): other zkVMs such as SP1, more
transformations (inlining, strength reduction), and cost models that account
for precompiles.

## Contributors

- Prakarti Dubey

<!-- Add the other team members here. -->

## References

- RISC Zero, *Installation*: https://dev.risczero.com/api/zkvm/install
- RISC Zero, *Optimizing guest programs* (cycles and paging costs): https://dev.risczero.com/api/zkvm/optimization
- Succinct, *SP1 installation*: https://docs.succinct.xyz/docs/sp1/getting-started/install
- LLVM, *LLVM's Analysis and Transform Passes* (`loop-unroll`): https://llvm.org/docs/Passes.html
