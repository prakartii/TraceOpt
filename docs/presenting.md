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

## The blockchain demo (prover and verifier)

Run `scripts/chain_demo.sh demos/fib.c 20000 --pause` (about 2 minutes;
`demos/counter.c 1000 3` takes about 30 seconds). Press Enter after each step.

| Step | What to say |
|---|---|
| 1 | "Same program as before. TraceOpt picks the 8x version." |
| 2 | "This is the prover, the expensive side. It proves both versions and saves each proof to a file. The original takes about a minute; TraceOpt's version about 15 seconds." |
| 3 | "This is what goes to the chain: the proof file, and the image ID, a fingerprint of the program. The answer is inside the proof." |
| 4 | "This is the chain. It checks each proof in milliseconds, without running the program, and reads the answer out of it. Both answers are correct." |
| 5 | "The chain cannot be fooled: one changed bit, the wrong program, or an unknown program are all rejected." |
| 6 | "So proving is where the cost is, and TraceOpt cuts it; the chain's cost stays tiny either way." |

## The staircase chart

Open `results/proving/proving-report.html` in a browser: it has the
staircase charts, bar charts of original vs TraceOpt vs plain Clang for
each program, and every measurement in one table. (The charts alone are
`results/proving/staircase-fib-time.svg` and `-memory.svg`.) Every dot is
a real RISC Zero proof of `demos/fib.c`.

- "Left to right the program runs more cycles, but proving time does not
  rise smoothly: it is flat on each step and jumps at a power of two."
- "Inside the 65,536 step the program ran 3.4 times as many cycles, from
  11,862 to 40,354, and proving still took 9 to 15 seconds."
- "The arrow is TraceOpt: at n = 18,000 the original needs the 262,144
  step, 54 s and 2.3 GB; the 8x version lands on 65,536, 13 s and 0.6 GB.
  That is the step TraceOpt predicts before running anything."
- If asked why two points at the same step differ in time: each dot is the
  median of 2 proofs, and the bars show the spread; the laptop's speed
  varies, memory does not.

## When the audience chooses the inputs

Run `scripts/live.sh` and let them type. It asks for a program (1–5, a
kernel name, or a path to a C file) and any n from 0 to 4,294,967,295, runs
all eight stages live, and asks again. Things worth knowing:

- **The expected answer is independent of TraceOpt.** Stage 2 compiles the C
  file natively with the host clang and runs it; for built-in kernels the
  Python reference is shown as well. Stage 8 compares the zkVM's answer with
  it.
- **They can write their own kernel.** Any C function with integer inputs
  that returns an integer, any name, no library calls and no `#include
  <stdio.h>`. Open an editor in WSL (`nano mine.c`), write it, then
  `scripts/live.sh mine.c 100` (one value per input: `mine.c 100 -7` for two).
  `examples/kernels/` has examples to start from. Loops, `switch`, recursion,
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

Inputs where TraceOpt **accepts** a smaller bucket (each run end to end with
the default 10% margin unless noted; the zkVM confirmed the saving and the
answer every time):

| Command (`scripts/live.sh ...`) | Chosen | Measured proved size |
|---|---|---|
| `strided_rw 5` | unrolled 4x | 262,144 → 131,072 (50% less) |
| `examples/kernels/counter_table.c 500` | unrolled 8x | 65,536 → 32,768 (50% less) |
| `nested_fnv 1500` | unrolled 8x | 262,144 → 131,072 (50% less) |
| `examples/kernels/string_hash.c 30000` | unrolled 2x | 524,288 → 262,144 (50% less) |
| `examples/kernels/counter_table.c 10000` | unrolled 8x | 262,144 → 131,072 (50% less) |
| `nested_fnv 30000` | unrolled 8x | 2,621,440 → 2,097,152 (20% less, several segments) |
| `examples/kernels/counter_table.c 1000000` | unrolled 8x | 14,680,064 → 5,373,952 (63% less) |
| `nested_fnv 1000000` | unrolled 8x | 87,031,808 → 56,754,176 (35% less) |
| `examples/kernels/string_hash.c 1000000` | unrolled 2x | 11,534,336 → 7,340,032 (36% less) |
| `strided_rw 3000 --margin 5` | unrolled 4x | 2,621,440 → 2,097,152 (20% less) |
| `nested_fnv 3000 --margin 5` | unrolled 8x | 524,288 → 262,144 (50% less) |
| `strided_rw 200 --margin 5` | unrolled 4x | 524,288 → 262,144 (50% less) |
| `xorshift 1000000 --margin 5` | unrolled 8x | 8,388,608 → 6,553,600 (22% less) |

The last four are wins only with `--margin 5`: with the default 10% margin
the same inputs are missed wins (below), which shows what the margin costs.

Other inputs, one per kind of case (all checked end to end; files are in
`examples/kernels/`):

| Command (`scripts/live.sh ...`) | Case | What it shows |
|---|---|---|
| `examples/kernels/counter_table.c 50` | nothing to gain | every version lands in the same bucket |
| `xorshift 1000` | nothing to gain | unrolling saves cycles, but not a bucket; the prediction says so correctly |
| `nested_fnv 3000` | missed win | 2x would have halved the size, but its saving is inside the 10% margin; the verdict says so (taken with `--margin 5`) |
| `examples/kernels/counter_table.c 1000` | missed win | the same, on custom code |
| `xorshift 10000000` | large input, missed win | 80 million cycles in 79 segments; 8x would save 22% but is inside the margin |
| `branchy 3000` | missed win | 2x would have halved the size; rejected as too risky |
| `examples/kernels/fib_recursive.c 15` | margin saves a wrong prediction | recursion: the machine code calls a function, so TraceOpt falls back to the IR model, which wrongly predicts a smaller bucket for every unrolled version; the margin rejects them and the zkVM confirms they would not have won |
| `xorshift 4294967295` | too large to run | the prediction (34 billion cycles) is above the limit, so the zkVM run is skipped |
| `sum_squares 1000` | no loop left | LLVM replaced the loop by a formula; nothing to unroll |
| `examples/kernels/collatz.c 300` | no prediction | data-dependent loop count: original kept rather than guess |
| `examples/kernels/matrix_multiply.c 50` | 2D arrays | three nested loops; every version checked |
| `examples/kernels/switch_ops.c 1000` | switch | a switch inside the loop |
| `examples/kernels/struct_points.c 50` | structs | fields of different sizes, laid out as on RISC-V |
| `examples/kernels/string_hash.c 1000` | strings | a constant string read byte by byte |
| `examples/kernels/float_sum.c 50` | unsupported feature | floating point: unrolled versions cannot be checked, so the original is kept |
| `examples/kernels/divide_by_n.c 0` | undefined behavior | division by zero: no correct answer exists, stage 2 explains and stops (n = 7 works) |
| `examples/kernels/uses_printf.c 5` | invalid kernel | library call: a one-line explanation instead of a crash |

## Likely questions

- **Why not just measure every version in the zkVM?** For these small
  kernels you could. The point is predicting without running: in a real
  program there are too many optimization choices to execute each one.
- **How good is the model?** Leave-one-kernel-out error is 1.5–18% (worst
  for the memory-heavy `strided_rw`). The decision rule only accepts wins
  that survive a 10% error, which is why it missed 3 wins and took no false
  ones.
- **Did you measure real proving time?** Yes, for runs with segments of up
  to 2^18 cycles (`scripts/prove_compare.sh`, results in
  `results/proving/`). Larger segments did not fit in the development
  machine's memory; for those, the padded cycle count the executor reports
  is the measure, and the small runs show proving time and memory follow it.
- **Where are these proofs used in blockchain?** Mainly zk-rollups: a
  server runs many transactions off-chain, proves they were run correctly,
  and posts one small proof that the chain (e.g. Ethereum) checks instead
  of re-running them. Also private payments and bridges between chains.
  `scripts/chain_demo.sh` shows the two sides: proving is slow and
  expensive, verifying takes milliseconds.
- **Who pays for proving?** Whoever runs the prover (a rollup operator, or a
  proving network that charges per proved cycle). That is the cost TraceOpt
  cuts; the chain's verification cost does not change.
- **Can you optimize the proof itself, not just the cycle count?** The
  final on-chain proof (Groth16) has the same size for every program, so no
  compiler can shrink it. What TraceOpt changes is the work to generate the
  proof: `scripts/prove_compare.sh` runs the real prover, and on
  `demos/fib.c 20000` proving took 72% less time and 75% less memory, and
  the per-segment proof was 13.6% smaller (`results/proving/`). Compressed
  into one succinct proof, both versions gave exactly 222,668 bytes, but
  the unrolled one was still proved 58% faster.
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
