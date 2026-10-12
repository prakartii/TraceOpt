# TraceOpt Architecture

This document describes the intended architecture of TraceOpt. Each component
carries a status label:

- **Implemented** — exists and is covered by tests.
- **In progress** — being developed now.
- **Planned** — designed, not yet written.
- **Experimental** — written, not yet validated.
- **Unverified** — a technical assumption that Phase 0 must confirm.

At the time of writing, **no component is implemented.** The status column is
updated in the same commit that changes a component's status.

## 1. Pipeline

```
 C kernel ──clang──▶ LLVM IR ──▶ IR Analyzer ──▶ Candidate Generator
                                   (features)     (unroll factors via opt)
                                                         │
                                                         ▼
 Report ◀── Evaluation ◀── zkVM Backend ◀── Decision ◀── Cost Model
 (JSON)     Harness        (RISC Zero)       Engine      (per candidate)
```

| Stage | Responsibility | Status |
|---|---|---|
| Source → LLVM IR | `clang -O1 -emit-llvm` on C benchmark kernels | Planned |
| IR Analyzer | Extract a fixed, documented feature vector per function | Planned |
| Candidate Generator | Produce variants with LLVM's `loop-unroll` pass at fixed factors | Planned |
| Cost Model | Predict RISC Zero cycle cost for each variant | Planned |
| Decision Engine | Pick a variant or keep the baseline; explain why | Planned |
| zkVM Backend Adapter | Compile the chosen IR for the guest and run it in RISC Zero | Planned, integration Unverified |
| Evaluation Harness | Run baseline / conventional / TraceOpt builds; collect metrics | Planned |
| Report Generator | Write JSON with config, predictions, and measurements | Planned |

## 2. Integration point (Unverified)

RISC Zero guest programs are written in Rust and compiled by rustc, which uses
LLVM internally. Inserting a custom pass into rustc's pipeline is not practical,
so TraceOpt plans to own the optimization of **C kernels** instead:

1. Compile the C kernel to LLVM IR with `clang`.
2. Analyze the IR and transform it with `opt` (TraceOpt chooses the parameters).
3. Lower the chosen IR to a RISC-V object for the guest target
   (`rv32im`, ILP32 ABI) with `llc` or `clang`.
4. Link that object into a minimal Rust guest that calls the kernel via FFI,
   so that the host, inputs, and harness code are identical across variants.

Steps 3–4 depend on the guest target's ABI, linker, and runtime expectations.
They are recorded as **Unverified** until `docs/feasibility.md` shows a working
build. If this route fails, alternatives to evaluate are: RISC Zero's C/C++
toolchain (`rzup install cpp`), or emitting IR from Rust guests and relinking.

## 3. Modules

### IR Analyzer and Feature Extractor — In progress
Input: a `.ll` file and a function name. Output: a JSON feature vector. Features
are defined in Section 4. Implemented in Python over textual IR (decision D3
in `design-decisions.md`):

| Part | File | Status |
|---|---|---|
| IR parser | `traceopt/ir.py` | Implemented (unit-tested on fixtures) |
| Dominators, loops, trip counts | `traceopt/loops.py` | Implemented (cross-checked against simulation) |
| Instruction classes, static counts | `traceopt/features.py` | Implemented |
| Block frequencies, dynamic counts | `traceopt/frequency.py` | Experimental |
| JSON CLI | — | Planned (issue #10) |

All tests so far use hand-written IR. Validation on real Clang output is
pending (issue #2).

### Candidate Optimization Generator — Planned
Produces a small, fixed set of variants: the baseline and loop unrolling with
factors {2, 4, 8} applied through LLVM's existing `loop-unroll` pass. TraceOpt
does not implement its own unroller; its contribution is the *decision*.
Legality is LLVM's responsibility. TraceOpt checks the result with differential
tests (Section 6).

### Proving-Cost Model — Planned
Maps a feature vector to a predicted cost. See Section 4.

### Optimization Decision Engine — Planned
Selects the candidate with the lowest predicted cost **only if** it beats the
baseline by a configurable margin (initially 5%) and stays within a code-size
limit. Otherwise it keeps the baseline. Every decision emits a short
justification listing the predicted costs of all candidates.

### zkVM Backend Adapter — Planned
Builds the guest with the selected kernel object and runs it in the RISC Zero
executor (cycle counts) and, when memory allows, the prover (proving time).
Only one backend is in scope. SP1 is the documented fallback.

### Benchmark and Evaluation Harness — Planned
Runs every benchmark through each build configuration with repeated runs, and
records toolchain versions and machine details.

### Report Generator — Planned
Writes one JSON report per run plus a short human-readable summary.

## 4. Cost model (initial proposal, not validated)

The proposed model is linear:

```
C(F) = Σᵢ wᵢ·nᵢ(F) + w_M·M(F) + w_B·B(F) + w_L·L(F)
```

Feature definitions (to be finalized in Phase 1; only features that can be
extracted reliably will be kept):

- **nᵢ(F)** — estimated *dynamic* count of IR instructions in class *i*
  (classes in `traceopt/features.py`: alu, mul, div, cmp, select, cast,
  address, load, store, cond_branch, jump, ret, phi, call, other).
  Implemented in `traceopt/frequency.py` *(Experimental)*:
  - Trip counts come from induction variables of rotated single-latch loops,
    with constant or parameter bounds (`traceopt/loops.py`).
  - Each block's frequency is its reach probability within its innermost
    loop iteration, multiplied by the enclosing trip counts.
  - Loop guards are assumed to enter the loop when its trip count is known to
    be at least 1. Other conditional branches are split 50/50.

  Limits: data-dependent branch probabilities are guesses, early exits
  (`break`) are not modeled, and an unknown trip count makes the estimate
  unavailable. IR counts are not machine instructions: in the xorshift loop,
  9 non-phi IR instructions cost 8 measured cycles per iteration, so the
  weights must absorb lowering effects.
- **M(F)** — memory-footprint features relevant to RISC Zero paging: code size
  of the lowered function in bytes and an estimate of distinct memory pages
  touched. RISC Zero's documentation states that each page-in/page-out costs on
  the order of a thousand cycles, so code growth from unrolling can raise cost.
- **B(F)** — estimated dynamic count of conditional branches.
- **L(F)** — lookup- or precompile-related features. No such feature has yet
  been identified that can be extracted reliably from the IR of our C kernels
  for RISC Zero, and accelerated precompiles (e.g. SHA-256) are out of scope
  for the first prototype. The term is therefore **omitted** initially and kept
  in the formula only to show where it would enter.

The weights *w* are fitted by least squares against measured RISC Zero cycle
counts from calibration programs (Phase 2). Prediction error is reported on
held-out benchmarks.

### From predicted cycles to proving work: segment padding (Implemented)

`C(F)` predicts *user* cycles (plus paging). Proving work, however, follows
the padded `total_cycles`, which `traceopt/segments.py` derives using the
rule in RISC Zero 3.0.6's executor (`risc0-circuit-rv32im` 4.0.5):

```
segment cycles = user + paging + 4113 (reserved)
split when segment cycles > 2^L − 25000      (L = segment limit po2, default 20)
non-final segments → 2^L;   final segment → next power of two
```

This reproduces the segment count and `total_cycles` of all 9 configurations
measured so far (`tests/test_segments.py`). Consequence for decisions: a
candidate that saves user cycles but does not cross a power-of-two boundary
does not change the padded total, so the decision engine compares the
padded totals, using the raw cycle prediction only to break ties.

### What the model predicts vs. what is measured

These quantities are related but **not interchangeable**, and reports keep them
in separate fields:

| Quantity | Source | Notes |
|---|---|---|
| Predicted cost `C(F)` | TraceOpt model | Unitless score calibrated to cycles |
| Execution cycles | RISC Zero executor | Includes paging overhead |
| Segment count | RISC Zero executor | Proving work grows in segment-sized steps |
| Proving time | Wall clock around the prover | Hardware-dependent; may be unavailable under memory limits |
| Native execution time | Host run | Not a proxy for proving cost |
| Code size | Object file size | Input to M(F) |

## 5. Configuration and reports — Planned

Configuration (unroll factors, improvement margin, code-size limit) will be a
small JSON file. Reports will be JSON with `config`, `toolchain`, `candidates`
(features and predicted cost), `decision`, and `measurements` (each metric is
a value or an explicit `"unavailable"` with a reason).

## 6. Correctness checking — Planned

TraceOpt does **not** claim formal semantic equivalence. Correctness is checked
by differential testing: each variant runs on the same inputs natively and in
the zkVM, and outputs must match the baseline exactly. A variant that fails
is reported and never selected.
