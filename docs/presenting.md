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

## When the audience chooses the inputs

Run `scripts/live.sh` and let them type. It asks for a program (1–5, a
kernel name, or a path to a C file) and any n from 0 to 4,294,967,295, runs
all eight stages live, and asks again. Things worth knowing:

- **The expected answer is independent of TraceOpt.** Stage 2 compiles the C
  file natively with the host clang and runs it; for built-in kernels the
  Python reference is shown as well. Stage 8 compares the zkVM's answer with
  it.
- **They can write their own kernel.** Any C file with
  `uint32_t traceopt_kernel(uint32_t n)`, no library calls. Open an editor in
  WSL (`nano mine.c`), write it, then `scripts/live.sh mine.c 100`.
  `examples/kernels/` has two to start from. Loops, `switch`, recursion,
  2D arrays, structs, lookup tables and 64-bit math all work. Floating point
  runs, but its unrolled versions cannot be checked, so the original is kept.
  Anything unsupported gives a one-line "stopped: ..." message, never a
  crash.
- **Large n is fine.** n = 10,000,000 for xorshift runs 80 million cycles in
  79 segments in a few seconds. Above 2^31 predicted cycles the zkVM run is
  skipped, and stage 7 says so: TraceOpt's own prediction is what decides.
- **Loops whose count depends on data** (e.g. Collatz in
  `examples/kernels/collatz.c`): TraceOpt says it cannot predict the cost and
  keeps the original. The answer is still checked in the zkVM.
- **Undefined behavior** (e.g. dividing by n with n = 0): stage 2 reports the
  native crash and stops, because C defines no correct answer.
- Stage 4 takes 5–15 s on the memory-heavy kernel (every version runs in the
  Python IR interpreter); the rest takes a few seconds.

Good inputs to suggest if they ask for "an interesting one":

| Command | What it shows |
|---|---|
| `strided_rw 5` | unrolling 4x halves the proved size, confirmed by the zkVM |
| `xorshift 10000000` | multi-segment run; unrolling 8x saves about 22% |
| `xorshift 1000` | the tempting 8x is rejected as too risky |
| `nested_fnv 3000` | every version rejected as too close to a bucket edge; the evaluation shows one would have won (a missed win) |
| `examples/kernels/collatz.c 300` | data-dependent loop: no prediction, original kept |

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
- Run one live session at a time. Two sessions build the zkVM guest in the
  same directory, and the second waits for the first. If stage 7 hangs for
  more than a minute, a build left over from an interrupted run is holding
  the lock: press Ctrl+C, run `pkill -x cargo`, and start again.
