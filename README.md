# TraceOpt

**TraceOpt: A Proving-Cost-Aware Compiler Optimization Framework for Zero-Knowledge Virtual Machines**

> Invention-disclosure title: *Method and System for Proving-Cost-Aware
> Compilation for Zero-Knowledge Virtual Machine Targets*

TraceOpt is a research prototype. It asks whether a compiler can make better
optimization decisions for zero-knowledge virtual machines (zkVMs) by
estimating the **cost of proving** a program's execution, instead of relying
only on conventional goals such as native speed or code size.

> **Status: early development (Phase 0).** No part of the optimization pipeline
> is implemented yet. This README describes the planned design and marks each
> stage's status. See [Current status](#current-status).

## The problem

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
| Program analysis (feature extraction) | Planned |
| Candidate generation (`opt` loop-unroll factors) | Planned |
| Proving-cost estimation | Planned |
| Optimization selection | Planned |
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

**Implemented (Phase 0 infrastructure, tested):**
- A RISC Zero host that runs a guest in the executor or the prover and prints
  JSON with segments and total/user/paging/reserved cycles.
- A guest that calls a C benchmark kernel through FFI and reports the cycles
  spent inside the kernel. The C file is compiled with RISC Zero's GCC
  toolchain.
- Two benchmark kernels (`sum_squares`, `xorshift`) with Python references
  and a differential smoke test.

None of the TraceOpt pipeline stages (analysis, cost model, decision) exist
yet. Measured results so far are in [docs/feasibility.md](docs/feasibility.md).

**In progress (Phase 0):**
- Compiling kernels through Clang → LLVM IR → `opt` → RISC-V object and
  linking them into the guest (LLVM is not installed yet).
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

```bash
scripts/smoke_test.sh   # inside WSL, after building
```

This runs both guests in the RISC Zero executor and compares their outputs
with the Python references in `tests/reference.py`. Unit tests for feature
extraction and decision logic are planned for Phases 1–3.

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
│   ├── development-roadmap.md
│   └── feasibility.md      Phase 0 measurements and blockers
├── scripts/
│   ├── build_backend.sh
│   └── smoke_test.sh
└── tests/
    └── reference.py        reference implementations of the kernels
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
