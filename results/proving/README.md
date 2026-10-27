# Real proofs: original vs TraceOpt's choice

Each file is one run of `scripts/prove_compare.sh`: the original (no
unrolling) and the version TraceOpt chose were proved alternately, 3 times
each, with RISC Zero 3.0.6 on the CPU prover (WSL, about 7.6 GB of RAM).
Every proof was verified, and every answer matched the native build.

Composite receipts (one STARK proof per segment; every run here is one
segment):

| Program and inputs | Chosen | Proved size | Proving time (median) | Peak memory | Proof size |
|---|---|---|---|---|---|
| `strided_rw 5` | 4x | 262,144 → 131,072 (−50%) | 51.0 s → 30.9 s (−39.4%) | 2,347 → 1,186 MiB (−49.5%) | 255,656 → 243,944 B (−4.6%) |
| `demos/fib.c 20000` | 8x | 262,144 → 65,536 (−75%) | 56.3 s → 15.7 s (−72.1%) | 2,349 → 598 MiB (−74.5%) | 255,656 → 220,904 B (−13.6%) |
| `demos/array_sum.c 12000` | 8x | 262,144 → 131,072 (−50%) | 58.4 s → 28.6 s (−51.1%) | 2,349 → 1,182 MiB (−49.7%) | 255,656 → 243,944 B (−4.6%) |
| `demos/counter.c 1000 3` | 8x | 65,536 → 32,768 (−50%) | 12.9 s → 7.2 s (−44.5%) | 597 → 304 MiB (−49.0%) | 220,904 → 209,256 B (−5.3%) |

What this shows:

- Proving time and memory follow the proved (padded) size, which is what
  TraceOpt predicts: halving the size roughly halved memory and cut time by
  39–51%; quartering it cut both by about three quarters.
- The proof itself gets slightly smaller, because a STARK proof grows with
  the logarithm of the trace length.
- Proving times vary between runs by up to about 75% on this laptop (e.g.
  35.8 s to 62.9 s for the same proof; the individual times are in each
  file), which is why the two versions alternate. In every pair, the chosen
  version was proved faster.
