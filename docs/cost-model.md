# Cost Model: Calibration Procedure and Limits

This document describes how TraceOpt's proving-cost model is built, how it is
fitted to measurements, and what it does not capture. Fitted values and
errors are in [Results](#results).

## 1. What is predicted

Proving work in RISC Zero follows the **padded total cycles** of a run: each
segment is rounded up to a power of two (docs/feasibility.md §4.3). TraceOpt
predicts it in three parts and combines them with the segment model:

| Quantity | Model | Source of coefficients |
|---|---|---|
| Kernel cycles | `intercept + Σ_f w_f · n_f` over dynamic instruction-class counts | least squares on measured variants |
| User cycles | kernel cycles + guest overhead | mean of measured `user − kernel` |
| Paging cycles | `paging_base + paging_per_page · pages` | least squares on measured paging |
| Padded total | `traceopt/segments.py` (segment splitting and padding) | RISC Zero source, checked on 9 runs |

`n_f` are the analyzer's static estimates of how often each IR instruction
class executes (`traceopt/frequency.py`); `pages` is the number of 1 KiB data
pages the kernel's globals occupy (`traceopt/footprint.py`), plus any extra
code pages a candidate needs compared with the baseline
(`traceopt/optimize.py`).

## 2. Calibration data

`scripts/run_variants.py` produces the data:

1. Each benchmark is compiled with Clang 21 at `-O1 -fno-unroll-loops`.
2. LLVM's `loop-unroll` pass makes variants with factors 1, 2, 4, and 8.
3. Each variant is linked into the kernel guest and executed for
   n ∈ {1, 10, 100, 1000}; outputs are checked against `tests/reference.py`.
4. Each record stores the measured cycles next to the analyzer's features for
   the same IR and n.

`sum_squares` is excluded: Clang folds its loop into a closed form.

```bash
source scripts/llvm_env.sh
python3 scripts/run_variants.py --work ~/.cache/traceopt-variants \
    --out results/variants-clang21.json
```

## 3. Fitting

`scripts/fit_model.py`:

1. Selects a linearly independent subset of the instruction classes, in a
   fixed preference order (`calibrate.independent_features`). For example,
   every `icmp` in these kernels feeds a conditional branch, so `cmp` and
   `cond_branch` cannot both be fitted.
2. Fits the kernel-cycle weights by least squares, constrained to be
   non-negative (an active-set heuristic, not an exact NNLS solver).
3. Reports the in-sample error and the **leave-one-benchmark-out** error:
   each benchmark is predicted by a model fitted without it.
4. With `--exact --ir DIR`, uses exact instruction counts from the IR
   interpreter instead of the static estimates. The difference between the
   two fits separates model error from frequency-estimation error.
5. With `--model-out`, writes the full `CostModel` used by
   `traceopt optimize`.

```bash
python3 scripts/fit_model.py results/variants-clang21.json \
    --out results/fit-clang21.json --model-out results/model-clang21.json
```

## 4. What the model ignores

- **IR is not machine code.** Weights are per IR instruction class; register
  allocation, instruction selection, and branch layout in `llc` are absorbed
  into the weights. A class with no instances in the data gets no weight.
- **Data-dependent branches** are split evenly by the analyzer (branchy);
  the fit sees estimated, not actual, counts unless `--exact` is used.
- **Paging** assumes each referenced global is touched in full and that
  paging is the same in every segment. Code-page growth is approximated in
  whole 1 KiB pages, ignoring where the code is placed.
- **Multi-segment runs** are predicted with the same per-segment paging in
  every segment.
- **Proving time** is not modeled directly; padded total cycles are the
  proxy, following how RISC Zero's prover scales with segment size.
- **Small data set**: four benchmarks, one machine, one toolchain version.

## Results

Pending: the first calibration run is in progress.
