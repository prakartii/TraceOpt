# How to run everything

All commands run from the repository folder inside WSL, unless marked
"any OS". Run one at a time: proofs use a lot of memory, so close other
heavy programs first.

## Start

In PowerShell:

```powershell
wsl -d Ubuntu
```

Then:

```bash
cd /mnt/c/Users/prakarti/Desktop/projects/TraceOpt
scripts/build_backend.sh      # only after pulling host changes (about 4 minutes)
```

## 1. Live mode: TraceOpt on any program (10–20 seconds)

```bash
scripts/live.sh demos/fib.c 20000      # 8 stages, ends with the verdict
scripts/live.sh                        # asks for a program and inputs
cat demos/fib.c                        # show the program first
```

Other demo programs and what each shows: `demos/README.md`.

## 2. Blockchain demo: prover and verifier (30–60 seconds)

```bash
scripts/chain_demo.sh demos/counter.c 1000 3          # about 30 s
scripts/chain_demo.sh demos/fib.c 20000 --pause       # about 1 min, Enter between steps
```

Six steps: TraceOpt's choice, the prover making and saving real proofs, what
is sent to the chain, the chain verifying them in milliseconds, the chain
rejecting three forged proofs, and the prover's bill. What to say at each
step: `docs/presenting.md`.

## 3. Real proofs: original vs TraceOpt vs plain Clang (4–11 minutes)

```bash
scripts/prove_compare.sh demos/counter.c 1000 3 --repeat 1   # under a minute
scripts/prove_compare.sh demos/fib.c 20000                   # about 4 min
scripts/prove_compare.sh demos/fib.c 20000 --conventional O2 O3   # about 11 min
```

## 4. The staircase chart (about 20 minutes to measure, instant to draw)

```bash
scripts/prove_staircase.sh demos/fib.c --n 1000 2000 8000 --execute-only   # seconds
scripts/prove_staircase.sh demos/fib.c --n 100 1000 1500 2000 4000 6000 7000 8000 \
    12000 16000 17000 18000 20000 24000 --versions 1 8
python3 scripts/plot_staircase.py results/proving/staircase-fib.json --highlight 18000
```

The measured charts are already in `results/proving/`, so this is only
needed to measure again.

## 5. The results page (any OS, instant)

```bash
python3 scripts/make_proving_report.py
```

Then open `results/proving/proving-report.html` in a browser (on Windows:
double-click it in Explorer, in `results\proving\`). It shows the summary
cards, the staircase charts, original vs TraceOpt vs Clang for each program,
the blockchain view, the fixed-size compressed proof, and the limits. The
older report of the cycle-count evaluation is `results/demo-report.html`.

## 6. Tests

```bash
source scripts/llvm_env.sh
PYTHONPATH=.:tests python3 -m unittest discover -s tests
```

## If something goes wrong

- `RISC Zero host not built` or `unknown mode "verify"`: run
  `scripts/build_backend.sh`.
- A run hangs for more than a minute before proving: press Ctrl+C, run
  `pkill -x cargo`, and start again.
- Proving is much slower than the times above: the machine is short of
  memory; close other programs and run one command at a time.
