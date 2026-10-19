# TraceOpt Development Roadmap

Team: 3 people. Duration: about 8 weeks. Phase lengths are estimates, and
phases overlap where dependencies allow. The priority is a **thin end-to-end
slice by the end of week 3**: one benchmark, two candidates, a placeholder
cost, a decision, and a measured cycle count. Everything after that improves
accuracy and coverage.

Status values: Not started / In progress / Done / Blocked.

| Phase | Weeks | Status |
|---|---|---|
| 0. Repository audit and feasibility | 1 | Done except proving memory vs. segment size (#3) |
| 1. IR analysis and baseline | 1–3 | Done (analyzer validated on Clang 21 IR against LLVM LoopInfo and an IR interpreter) |
| 2. Initial proving-cost model | 3–4 | Done (docs/cost-model.md) |
| 3. First cost-aware optimization | 4–5 | Done (`traceopt optimize`) |
| 4. Backend integration and reporting | 5–6 | Done (`optimize --measure`, guest-only builds) |
| 5. Evaluation and testing | 6–7 | First evaluation done (docs/experiments.md); broader benchmark set open |
| 6. Finalization and demonstration | 8 | In progress (demo script done; clean-install check open, #26) |

## Phase 0 — Repository audit and feasibility (week 1)

**Goal:** Confirm the architecture can be built with the chosen toolchain.

Tasks:
- [x] Audit the repository (one initial commit, README only).
- [x] Choose RISC Zero as the primary backend, with SP1 as the fallback.
- [x] Install Rust and the RISC Zero toolchain (3.0.6) in WSL Ubuntu.
- [x] Install LLVM/Clang in WSL Ubuntu (21.1.8, unpacked without `sudo`).
- [x] Build and run a minimal RISC Zero guest; record its cycle count.
- [x] Link a C kernel into a RISC Zero guest (GCC route).
- [x] Link a Clang/LLVM-IR-compiled C kernel into a RISC Zero guest.
- [x] Measure peak memory of a small proof (2^15 segment: 303 MB).
- [ ] Measure proving memory with capped segment sizes (a 2^20 segment was OOM-killed).
- [x] Record accessible metrics: segments and total/user/paging/reserved cycles,
      plus in-guest kernel cycles. Proving time is available for small segments.
      Code size is measured from the linked guest ELF.

**Deliverable:** `docs/feasibility.md` with commands, outputs, and blockers.
**Completion criterion:** A simple program runs through the toolchain, or a
blocker is documented with an agreed alternative.

## Phase 1 — IR analysis and baseline (weeks 1–3)

**Goal:** A reliable starting point.

Tasks:
- Decide on the analyzer implementation (Python over textual IR vs. C++ on the LLVM API).
- Extract the feature vector defined in `architecture.md` §4.
- Write 5–6 benchmark kernels: arithmetic, simple loop, nested loop,
  branch-heavy, memory-intensive, and (if feasible) a hash-like kernel.
- Script the baseline build and run, and record cycle counts.
- Unit tests for feature extraction on small hand-written `.ll` files.

**Deliverable:** Analyzer prototype and reproducible baseline numbers.
**Completion criterion:** The analyzer emits JSON features for every benchmark,
and rerunning the baseline script reproduces the same cycle counts.

## Phase 2 — Initial proving-cost model (weeks 3–4)

**Goal:** A simple, explainable model.

Tasks:
- Generate calibration variants (benchmarks × unroll factors × input sizes).
- Fit the linear weights by least squares (NumPy only, unless a clear need appears).
- Report prediction error on held-out benchmarks.
- Document what the model ignores and where it fails.

**Deliverable:** Cost model plus a documented calibration script.
**Completion criterion:** The model predicts cost for every supported benchmark,
and its error against measured cycles is reported.

## Phase 3 — First cost-aware optimization (weeks 4–5)

**Goal:** One working optimization decision.

Tasks:
- Generate candidates with LLVM `loop-unroll` at factors {1, 2, 4, 8}.
- Score the candidates; apply the decision rule (margin and code-size limit).
- Keep the baseline when no candidate wins or the analysis is inconclusive.
- Differential tests: every variant's outputs match the baseline's.

**Deliverable:** End-to-end optimization prototype (`traceopt optimize`).
**Completion criterion:** Given an input, the tool compares candidates, selects
one or keeps the baseline, and prints its reasoning.

## Phase 4 — Backend integration and reporting (weeks 5–6)

**Goal:** Connect decisions to real RISC Zero runs.

Tasks:
- Automate build → execute (→ prove when memory allows) for the selected variant.
- JSON reports holding config, toolchain versions, predictions, and measurements.
- Explicit handling of build failures and unavailable metrics.

**Deliverable:** A repeatable evaluation pipeline.
**Completion criterion:** Every supported benchmark runs through the baseline
and TraceOpt workflows with comparable outputs.

## Phase 5 — Evaluation and testing (weeks 6–7)

**Goal:** Determine whether the prototype provides measurable value.

Tasks:
- Compare: baseline (`-O1`, no unrolling), conventional (`-O2`/`-O3`
  heuristic unrolling), and TraceOpt.
- Repeated runs for timing metrics, with variance reported.
- Tabulate prediction error, wins, neutral cases, and regressions.
- Write up threats to validity.

**Deliverable:** Evaluation tables, scripts, raw results, and analysis in `docs/experiments.md`.
**Completion criterion:** Every reported number can be regenerated by a
documented command.

## Phase 6 — Finalization and demonstration (week 8)

**Goal:** A complete, understandable project.

Tasks:
- Verify the setup instructions on a clean WSL environment.
- Polish error messages and tests.
- Prepare a demo on one representative benchmark.
- Final limitations and future-work section.

**Completion criterion:** Another developer can follow the README, run the
workflow, and understand the scope.

## Dependencies

- Phases 1–5 depend on the Phase 0 integration result (C kernel in a RISC Zero guest).
- Phase 2 needs Phase 1 features **and** the baseline measurements.
- Phase 3 can start on the decision logic with a stub model while Phase 2 is calibrated.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| C kernel cannot be linked into a guest | Blocks the whole pipeline | Try RISC Zero's C/C++ toolchain, then Rust-emitted IR, then SP1 |
| Proving does not fit in ~7.6 GB of WSL memory | No proving-time metric | Use cycles/segments as the primary metric; test small segment sizes; then consider raising the WSL limit |
| LLVM version mismatch between Clang and the guest toolchain | Link or ABI errors | Pin versions and record them in `feasibility.md` |
| Unrolling rarely changes cycle cost meaningfully | Weak results | Report it honestly; it remains a valid finding |
| Small calibration set | Overfit model | Hold out benchmarks and report error |

## Suggested work split (3 people)

- **A — Analysis:** IR analyzer, features, unit tests.
- **B — Backend:** RISC Zero toolchain, guest harness, measurement scripts.
- **C — Model and evaluation:** calibration, decision engine, reports, experiments.

All three review each other's pull requests.
