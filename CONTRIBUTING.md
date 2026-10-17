# Contributing to TraceOpt

## Workflow

- Branch from `main`, keep changes small, and open a pull request. Another
  team member reviews before merging.
- Never force-push to `main` or rewrite published history.
- Never commit secrets, `.env` files, or large build outputs (`results/raw/`
  is ignored; curated JSON goes in `results/`).

## Commit messages

Use a short prefix that names the kind of change:

| Prefix | Use |
|---|---|
| `feat(<area>)` | new behaviour (`analyzer`, `cli`, `cost-model`, `optimizer`, `backend`) |
| `fix(<area>)` | bug fix |
| `test(<area>)` | tests only |
| `bench` | benchmark kernels or curated results |
| `docs` | documentation |
| `build`, `ci`, `chore` | packaging, workflows, housekeeping |

## Before pushing

```bash
python -m unittest discover -s tests   # must print OK
```

CI runs the same command on Python 3.10 and 3.12. Changes to the RISC Zero
backend or benchmarks should also pass `scripts/smoke_test.sh` inside WSL.

## Results and claims

- Numbers in documentation must come from a committed results file or a
  documented command. Record unavailable metrics as unavailable.
- Label work as Implemented, Experimental, In progress, or Planned, and
  update the README status table when that changes.
- Differential testing checks outputs; it is not a proof of equivalence, so
  do not describe it as one.
