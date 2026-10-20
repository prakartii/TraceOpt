# Presenting TraceOpt

A guide for showing the project to someone who has not seen it before
(about 10 minutes). Everything shown comes from `scripts/demo.sh` and
`results/demo-report.html`; no number needs to be typed in by hand.

## Before the presentation

In PowerShell:

```powershell
wsl -d Ubuntu
```

Then in WSL:

```bash
cd /mnt/c/Users/<you>/Desktop/projects/TraceOpt
scripts/build_backend.sh                 # only if not built yet (~4 min)
scripts/demo.sh --no-pause > /dev/null   # warm-up run: checks everything works
```

Also open `results/demo-report.html` in a browser (double-click it in
Explorer). It is the backup if the terminal run has problems, and the
easier thing to scroll through when answering questions.

## The run

Start `scripts/demo.sh`. It stops after every step; press Enter to go on.

| Screen | What it shows | What to say |
|---|---|---|
| Title | What a zkVM is, why cost comes in power-of-two steps | "Proving cost depends on cycles, but rounded up to a power of two. Compilers don't know that." |
| Pipeline | C → LLVM → versions → predict → decide → RISC Zero | "TraceOpt sits between the compiler and the zkVM, and predicts without running the zkVM." |
| Step 1 | The C program, input n, expected answer | "This is the input program. The answer we expect comes from an independent Python version." |
| Step 2 | Unroll picture; the four versions; answer checks | "Unrolling trades code size for fewer loop checks. Every version gives the same answer on the test inputs." |
| Step 3 | Executed operations, predicted cycles, bar chart | "Blue is the work the run needs, orange is padding the prover still has to prove. The original just misses 131,072, so it pays for 262,144." |
| Step 4 | Decision with a reason per version | "2x might fit, but a 10% prediction error would undo it, so it is rejected. 8x makes the code too big. 4x is a safe win." |
| Step 5 | zkVM answer, predicted vs measured | "The zkVM gives the right answer, and the measured size really halves: 262,144 → 131,072." |
| xorshift | Same steps, original kept | "Here unrolling saves cycles, but not reliably a bucket. The rejected 8x version was predicted to halve, and the measurement shows it would not have." |
| Evaluation | 16 cases | "12 cases had nothing to gain, 1 win was taken, 3 were missed, and TraceOpt never made things worse." |
| Closing | Limits | Read the limits out: small kernels, one optimization, executor cycle counts rather than full proofs, tests rather than proofs of equivalence. |

## Likely questions

- **Why not just measure every version in the zkVM?** For these small
  kernels you could. The point is predicting without running: in a real
  program there are too many optimization choices to execute each one.
- **How good is the model?** Leave-one-kernel-out error is 1.5–18% (worst
  for the memory-heavy `strided_rw`). The decision rule only accepts wins
  that survive a 10% error, which is why it missed 3 wins and took no false
  ones.
- **Why not real proving time?** Proving the larger runs did not fit in the
  development machine's memory. Proving work follows the padded cycle count,
  which the executor reports exactly.
- **Is the unrolled code proven equivalent?** No. It is LLVM's own
  transformation, checked by running it on test inputs in the interpreter
  and in the zkVM.

## If something goes wrong

- `RISC Zero host not built`: run `scripts/build_backend.sh` once.
- `LLVM tools not on PATH`: use `scripts/demo.sh`, which sets the path, not
  `python3 scripts/demo.py` directly.
- No time or WSL trouble: `scripts/demo.sh --no-measure` shows the
  predictions only, or present from `results/demo-report.html`.
