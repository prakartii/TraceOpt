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
