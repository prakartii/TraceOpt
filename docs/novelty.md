# What is new in TraceOpt, and what is not

This document separates the project's contribution from the existing
techniques it builds on, so that each claim can be checked. Every number
cited comes from a committed results file.

## The question

Compilers decide optimizations with cost models of a CPU: latency, code
size, cache behavior. In a zero-knowledge virtual machine, the cost that
matters is proving, and it behaves differently:

1. **It moves in steps.** RISC Zero pads every segment to a power of two
   (32,768, 65,536, … up to 2^20 cycles in our runs), so proving work changes only
   when a run crosses one of those sizes. A 20% cycle saving can change
   nothing, and a 2% saving can halve the cost.
2. **It counts things a CPU model ignores.** Each 1 KiB memory page the
   program touches costs paging cycles (about 670 cycles per page in our
   measurements), and every segment has a fixed reserved overhead.
3. **Measuring it is expensive.** Proving a program to find out its cost
   takes far longer, and far more memory, than compiling it.

TraceOpt asks: **can a compiler choose an optimization by predicted proving
cost, before running the zkVM, and do so safely?**

## Contributions

1. **Proving cost as the compiler's objective, including padding.** TraceOpt
   ranks optimization candidates by their predicted *padded* proving size:
   predicted cycles plus paging plus reserved cycles, split into segments
   and rounded up the way RISC Zero's executor does
   (`traceopt/segments.py`). Because of the steps, the useful question is
   not "is this version faster" but "does it cross a boundary".
2. **Prediction from LLVM IR, without executing the zkVM.** Loop trip counts
   are derived from the IR and the input (`traceopt/loops.py`,
   `evaluate.py`), dynamic instruction counts follow from them
   (`frequency.py`), and a linear model calibrated on 64 measured RISC Zero
   runs turns them into cycles (`calibrate.py`, `model.py`). Held-out error
   (each kernel predicted by a model fitted without it): 1.5–18% mean
   (`results/fit-clang21.json`).
3. **A decision rule that accounts for prediction error near the steps.**
   Near a power-of-two boundary a small prediction error flips the outcome,
   so a candidate is accepted only if its saving survives a 10% error in the
   unfavorable direction, after paying for any extra code pages
   (`traceopt/decision.py`). In the evaluation this produced 0 regressions,
   at the cost of 3 missed wins (`results/evaluation-clang21.json`).
4. **End-to-end validation against the real zkVM.** Every decision is
   checked by executing the chosen and original programs in RISC Zero 3.0.6,
   comparing predicted and measured padded size and the program's answer
   against independent references (`scripts/evaluate.py`,
   `scripts/live.py`).

The evidence for the claims: in 16 evaluation cases, TraceOpt's predicted
padded size was exactly right for its choice in 15; it halved proving work in
the one case where that was available and safe (strided_rw, n = 5:
262,144 → 131,072 cycles); and Clang's own `-O2` heuristics lowered the
padded size in only 1 of the 16 cases.

## What is not new

- **Loop unrolling.** TraceOpt uses LLVM's own `loop-unroll` pass; it only
  chooses the factor.
- **Compiler cost models** in general, and linear models fitted to
  measurements: both are standard techniques.
- **RISC Zero's padding and paging behavior.** It is a property of RISC
  Zero, read from its executor source and confirmed by measurement; TraceOpt
  models it but did not discover it.
- **Differential testing.** Checking versions on sample inputs is a standard
  testing method, and it is not a proof of equivalence.

## Limits of the claims

- Four benchmark kernels and one optimization. The results may not transfer
  to large programs, function calls, or other optimizations.
- Costs are measured as padded cycles in RISC Zero's executor. Full proofs
  of the larger runs did not fit in the development machine's memory, so
  proving time itself is not reported (issue #3).
- Multi-segment runs are predicted less accurately (paging is modeled for
  one segment).
- No systematic literature survey has been done. Before these points are
  stated as novel in a paper, they should be checked against current work on
  zkVM-aware compilation and guest-program optimization.

## In one sentence

TraceOpt shows that, for RISC Zero, a compiler can predict from LLVM IR
whether an optimization changes the *padded* proving cost and choose it
only when the saving survives the model's error, and it validates every
choice against the real zkVM.
