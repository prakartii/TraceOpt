# TraceOpt

**TraceOpt: A Proving-Cost-Aware Compiler Optimization Framework for Zero-Knowledge Virtual Machines**

> Invention-disclosure title: *Method and System for Proving-Cost-Aware
> Compilation for Zero-Knowledge Virtual Machine Targets*

TraceOpt is a research prototype. It asks whether a compiler can make better
optimization decisions for zero-knowledge virtual machines (zkVMs) by
estimating the **cost of proving** a program's execution, instead of relying
only on conventional goals such as native speed or code size.

> **Status: early development (Phases 0–1).** The RISC Zero measurement
> backend works. Analyzer, segment model, calibration, and decision components
> exist but have not yet run end to end on real Clang IR. TraceOpt does not yet
> optimize anything. See [Current status](#current-status).

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

- **One backend:** [RISC Zero](https://dev.risczero.com/) (SP1 is the fallback if Phase 0 finds a blocker).
- **One optimization:** loop unrolling, using LLVM's existing `loop-unroll` pass.
  TraceOpt chooses the unroll factor; it does not implement its own unroller.
- **One cost model:** a linear model over a small set of IR features, calibrated
  against measured RISC Zero cycle counts.

## How TraceOpt works

```
Source (C) → LLVM IR → Program Analysis → Candidate Optimizations
          → Proving-Cost Estimation → Optimization Selection
          → Target Compilation (RISC Zero guest) → Evaluation Report
```

| Stage | Status |
|---|---|
| Source → LLVM IR (`clang`) | Planned |
| Program analysis (feature extraction) | Implemented on hand-written IR; not yet run on Clang output |
| Candidate generation (`opt` loop-unroll factors) | Planned (needs LLVM) |
| Proving-cost estimation | Segment padding model implemented and checked against measurements; per-instruction weights not yet calibrated |
| Optimization selection | Decision logic implemented and unit-tested; not yet connected to real predictions |
| Target compilation into a RISC Zero guest | C via GCC works (Phase 0); Clang/IR route not yet tested |
| Evaluation report (JSON) | Planned |

Linking a Clang-compiled C kernel into a RISC Zero guest is an assumption that
has **not yet been verified**. Phase 0 tests it and records the result in
`docs/feasibility.md`. Module responsibilities are described in
[docs/architecture.md](docs/architecture.md).

## Cost model (initial proposal)

```
C(F) = Σᵢ wᵢ·nᵢ(F) + w_M·M(F) + w_B·B(F) + w_L·L(F)
```

- `nᵢ(F)`: estimated dynamic counts of instruction classes
- `M(F)`: memory and code-footprint features related to paging
- `B(F)`: estimated dynamic branch count
- `L(F)`: lookup/precompile features (omitted for the first backend)

The weights are fitted to measured cycle counts. This is a modeling hypothesis,
not a validated formula. Precise feature definitions are in
[architecture.md §4](docs/architecture.md#4-cost-model-initial-proposal-not-validated).

TraceOpt keeps these quantities separate and never reports one as another:

- **Predicted cost**: the model's output.
- **Execution cycles and segment count**: measured by the RISC Zero executor.
- **Proving time**: measured wall-clock time of proof generation. It depends on
  the hardware and may be unavailable when memory is limited.
- **Native execution time**: not used as a proxy for proving cost.

## Current status

**Implemented (tested):**
- *Backend:* a RISC Zero host that runs a guest in the executor or the prover
  and prints JSON with segments and total/user/paging/reserved cycles. A guest
  calls a C benchmark kernel through FFI and reports the cycles spent inside
  it. C is currently compiled with RISC Zero's GCC toolchain.
- *Benchmarks:* five C kernels (`sum_squares`, `xorshift`, `nested_fnv`,
  `branchy`, `strided_rw`) with Python references, verified natively and in
  the zkVM, and a baseline runner that records cycles, code size, and
  toolchain versions.
- *Analyzer* (`traceopt/`): textual LLVM IR parser, dominators and natural
  loops, trip counts, instruction classes, and the `traceopt analyze` CLI.
  Tested on hand-written IR only.
- *Segment model:* predicts RISC Zero's segment count and padded total cycles.
  It matches all 9 measured configurations.

**Experimental (implemented, not yet validated on real data):**
- Dynamic instruction-count estimation (`traceopt/frequency.py`).
- Least-squares calibration (`traceopt/calibrate.py`) and the cost-aware
  decision engine (`traceopt/decision.py`). Both are unit-tested on
  synthetic inputs.

Measured results are in [docs/feasibility.md](docs/feasibility.md).

**Blocked / in progress:**
- Compiling kernels through Clang → LLVM IR → `opt` → RISC-V object and
  linking them into the guest. LLVM is not installed yet, and this blocks
  running the analyzer on real IR, generating unroll candidates, and
  calibrating the model.
- Proving with capped segment sizes: a single 2^20-cycle segment exceeded the
  ~7.6 GB of memory available to WSL.

**Planned:** everything in the pipeline table above. See the
[development roadmap](docs/development-roadmap.md).

**Known limitations of the planned prototype:**
- A single backend (RISC Zero) and a single transformation (loop unrolling).
- C benchmark kernels only. Rust guest code is not optimized by TraceOpt.
- Correctness is checked by differential testing, not formal equivalence proofs.
- Proving time may be measurable only for small programs on the development
  machine (about 7.6 GB of RAM available to WSL).
- The cost model is calibrated on a small benchmark set and may not generalize.

## Installation and usage

RISC Zero's installer supports x86-64 Linux and arm64 macOS, so on Windows
the project is developed inside WSL 2 (Ubuntu). The commands below were
verified on Ubuntu 26.04 in WSL with RISC Zero 3.0.6.

```bash
# Toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
curl -L https://risczero.com/install | bash
~/.risc0/bin/rzup install

# Build (first build takes ~15 minutes)
scripts/build_backend.sh

# Run a guest in the executor: host <execute|prove> <probe|kernel> [n]
~/.cache/traceopt-target/release/host execute kernel 1000
```

Proving (`prove`) works for small inputs. For larger inputs, set
`TRACEOPT_SEGMENT_PO2` (for example `18`) to cap memory. See
[docs/feasibility.md](docs/feasibility.md) §5.

The TraceOpt optimizer itself has no usage instructions yet because it does
not exist yet.

## Benchmarking and evaluation (planned)

Each benchmark kernel will be built three ways:

1. **Baseline:** `-O1` without loop unrolling.
2. **Conventional:** `-O2`/`-O3` with LLVM's default unrolling heuristics.
3. **TraceOpt:** baseline plus the unroll factor TraceOpt selects, or the
   baseline unchanged if no candidate is predicted to help.

Metrics collected where available: RISC Zero cycles and segments, proving time
(repeated runs), code size, compile time, peak memory, and cost-model prediction
error. Each run checks that its outputs match the baseline's. Unavailable
metrics are recorded as unavailable, not estimated. No results have been
collected yet.

## Testing

Unit tests (Python 3.10+, standard library only; run from the repository root):

```bash
python -m unittest discover -s tests
```

They cover the IR parser, loops and trip counts (cross-checked against
simulation), instruction classes, frequency estimates, the CLI, the segment
model (against measured data), calibration, and decision logic.

zkVM checks (inside WSL, after building):

```bash
scripts/smoke_test.sh                     # probe and kernel guests vs. reference
scripts/check_kernel.sh nested_fnv 1 100  # one benchmark in the zkVM
python3 scripts/run_baseline.py --out results/baseline-gcc.json
```

## Repository structure

```
TraceOpt/
├── .gitattributes
├── .gitignore
├── README.md
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
├── scripts/
│   ├── build_backend.sh
│   ├── check_kernel.sh
│   ├── run_baseline.py
│   └── smoke_test.sh
├── tests/                  unit tests, IR fixtures, kernel references
└── traceopt/               Python package
    ├── ir.py               textual LLVM IR parser
    ├── loops.py            dominators, natural loops, trip counts
    ├── features.py         instruction classes and static counts
    ├── frequency.py        block frequencies, dynamic counts
    ├── segments.py         RISC Zero segment and padding model
    ├── calibrate.py        least-squares fit, held-out error
    ├── decision.py         cost-aware candidate selection
    └── cli.py              `python -m traceopt analyze`
```

## Limitations and future work

Beyond the limitations listed above: support for additional zkVMs (for example
SP1), more transformations (such as inlining and strength reduction), and
cost models that account for target-specific precompiles are possible future
work. None of these is part of the current plan.

## Contributors

- Prakarti Dubey

<!-- Add the other team members here. -->

## References

- RISC Zero, *Installation*: https://dev.risczero.com/api/zkvm/install
- RISC Zero, *Optimizing guest programs* (cycles and paging costs): https://dev.risczero.com/api/zkvm/optimization
- Succinct, *SP1 installation*: https://docs.succinct.xyz/docs/sp1/getting-started/install
- LLVM, *LLVM's Analysis and Transform Passes* (`loop-unroll`): https://llvm.org/docs/Passes.html
