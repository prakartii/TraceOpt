# Design Decisions

Short records of decisions that shape the implementation. Each entry states
the context, the decision, and what would make us revisit it.

## D1. Primary backend: RISC Zero (Phase 0)

- **Context:** One backend for the prototype. SP1's documentation lists 16 GB+
  RAM for local proving; the development machine has ~7.6 GB available in WSL.
- **Decision:** RISC Zero 3.0.6, with SP1 as the fallback.
- **Revisit if:** the C/LLVM-IR route cannot be linked into a RISC Zero guest.

## D2. Integration point: C kernels linked into a Rust guest (Phase 0)

- **Context:** rustc does not offer a practical way to insert our own pass, but
  a guest can call a C function through FFI (verified with GCC, see
  `feasibility.md` §4.2).
- **Decision:** TraceOpt optimizes C kernels that export
  `uint32_t traceopt_kernel(uint32_t)`. The Rust guest, inputs, and host stay
  identical across variants, and the guest measures the cycles spent in the
  kernel.
- **Revisit if:** the Clang-compiled object cannot be linked (issue #2).

## D3. IR analyzer in Python over textual LLVM IR (Phase 1, issue #5)

- **Context:** The analyzer needs functions, basic blocks, the CFG, loops,
  constant trip counts, and per-class instruction counts for small,
  single-function kernels. The team works mostly in Python, and the cost model
  will be fitted in Python.
- **Options considered:**
  1. *C++ tool on the LLVM API.* Exact and complete, but needs LLVM development
     headers and a CMake build tied to one LLVM version. Slower to iterate on.
  2. *Python bindings (e.g. llvmlite).* Bundles its own LLVM build, which would
     need to match the version that produces our IR, and exposes only limited
     analyses.
  3. *Python over textual IR (`.ll`).* No build step or extra dependency, easy
     to unit-test with hand-written fixtures. Covers only the subset of IR our
     kernels use.
- **Decision:** Option 3, using only the standard library (`unittest` for
  tests). IR is produced by a pinned LLVM version (Ubuntu's LLVM 21) and
  normalized with `opt -S` before parsing.
- **Safeguards:**
  - The parser rejects constructs it does not understand instead of guessing.
  - Once LLVM is installed, loop detection is cross-checked against
    `opt -passes='print<loops>'` on every benchmark.
- **Revisit if:** the parser needs features beyond simple kernels (exceptions,
  `switch`-heavy code, complex metadata), or its loop results disagree with
  LLVM's.

## D4. Loop unrolling uses LLVM's existing pass (Phase 3)

- **Context:** TraceOpt's contribution is the cost-aware *decision*, not the
  transformation.
- **Decision:** Candidates are produced with `opt` and LLVM's `loop-unroll`
  pass at explicit factors. Legality is LLVM's responsibility. Correctness is
  checked by differential tests.

## D5. Baseline IR keeps loops unrollable (Phase 3)

- **Context:** `-fno-unroll-loops` stops Clang's pipeline from unrolling, but
  it also tags every loop with `llvm.loop.unroll.disable`, which `opt`
  honors, so no candidate could be generated from that IR. Without the flag,
  Clang's `-O1` pipeline may unroll on its own and the baseline would not be
  "factor 1".
- **Decision:** Compile with `-fno-unroll-loops`, then rename the metadata
  string to an unknown loop property (`traceopt.unroll.cleared`), which LLVM
  ignores. Candidates are generated with an explicit `-unroll-count` and a
  high `-unroll-threshold`, because without it `opt` silently lowers large
  counts (found when a requested factor 8 produced a different variant).
- **Consequence:** Factor 1 is exactly the baseline. Variants whose code is
  identical to a smaller factor's are reported as duplicates, not candidates.

## D6. An IR interpreter is the ground truth for the analyzer (Phase 1)

- **Context:** The static frequency estimates needed an independent check.
  Instrumented native builds would need a profiling runtime that is not
  installed, and comparing with zkVM cycles mixes in the model's error.
- **Decision:** `traceopt/interp.py` executes the IR subset the kernels use
  and counts block executions. Its return values are checked against the
  Python references, and the static estimates are compared with its counts
  block by block.
- **Consequence:** Estimates are exact for every kernel whose control flow
  depends only on n, unrolled or not; branchy's data-dependent branches are
  the known exception. The interpreter is slow (seconds for strided_rw at
  n = 1000), so it is used for validation and calibration, not in the
  zkVM measurement loop.

## D7. Code growth is costed as paging, not capped (Phase 3)

- **Context:** A fixed "at most 4x the baseline's code size" rule rejected a
  52 B → 216 B kernel that still fits in one 1 KiB page, so it cost nothing
  extra in the zkVM.
- **Decision:** A candidate whose code needs more 1 KiB pages than the
  baseline is charged the fitted per-page paging cost for each extra page.
  The relative limit remains as a loose safety bound (16x).
