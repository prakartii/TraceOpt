# Prover and verifier (the blockchain view)

Each file is one run of `scripts/chain_demo.sh`: real RISC Zero receipts of
the original program and of TraceOpt's choice (one proof each), saved to
files and then checked by a separate `verify` step that never runs the
program, as a blockchain's verifier would.

| Program and inputs | Version | Proved size | Proving | Verifying | Receipt file | Answer from receipt |
|---|---|---|---|---|---|---|
| `demos/counter.c 1000 3` | original | 65,536 | 8.2 s | 14.7 ms | 221,242 B | correct |
| | TraceOpt (8x) | 32,768 | 4.4 s | 13.2 ms | 209,594 B | correct |
| `demos/fib.c 20000` | original | 262,144 | 59.9 s | 17.7 ms | 255,994 B | correct |
| | TraceOpt (8x) | 65,536 | 14.5 s | 16.2 ms | 221,242 B | correct |

In both runs the verifier rejected all three forged receipts:

- the chosen version's receipt with one bit changed ("proof is invalid");
- the original's receipt presented as the chosen version (its image ID, the
  fingerprint of the program's machine code, does not match);
- a receipt presented as an unknown program (image ID all zeros).

What this shows: verifying takes milliseconds and hardly changes, while
proving takes seconds to a minute and is where the cost is. TraceOpt cuts the
prover's side (here −46% and −76% proving time) and leaves the verifier's
side as it was.

Limits: these are composite receipts verified by the RISC Zero library on the
same laptop. A real chain such as Ethereum verifies a compressed Groth16
proof in a smart contract, which needs Docker and more memory than this
machine has; that step is not shown.
