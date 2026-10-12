# Phase 0 Feasibility Note

Status: **in progress.** Each result below was observed on the machine
described in §1. Items not yet tested are listed in §6.

## 1. Environment

| Item | Value |
|---|---|
| Host | Windows 11, Intel i7-13700H, 15.7 GB RAM |
| Build/run environment | WSL 2, Ubuntu 26.04, x86-64, 20 cores, ~7.6 GB RAM (default WSL limit), 2 GB swap |
| Host Rust | rustc 1.99.0, cargo 1.99.0 |
| RISC Zero | rzup 0.5.0; cargo-risczero 3.0.6; r0vm 3.0.6; guest Rust toolchain 1.97.0; C++ toolchain 2024.1.5 (GCC) |
| Crates | `risc0-zkvm = "=3.0.6"`, `risc0-build = "=3.0.6"` |
| LLVM/Clang | **not installed yet** (Ubuntu candidate: 21.1.6; needs `sudo`) |

RISC Zero's installer supports x86-64 Linux and arm64 macOS only, so all
toolchain work runs in WSL.

## 2. Installation (verified)

```bash
# inside WSL Ubuntu
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
curl -L https://risczero.com/install | bash
~/.risc0/bin/rzup install        # installs cargo-risczero, r0vm, rust, cpp
```

## 3. Building the backend (verified)

```bash
cd backend/risc0
export CARGO_TARGET_DIR=$HOME/.cache/traceopt-target   # keep build output off /mnt/c
cargo build --release -j 4
```

- First build: **14 min 14 s**, largest single process 2.6 GB RSS,
  minimum available memory during the build 4.4 GB.
- An earlier build with Cargo's default parallelism (20 jobs) was killed and
  WSL failed with `Wsl/Service/E_UNEXPECTED`, requiring `wsl --shutdown`.
  The cause was not captured. Memory exhaustion is the likely explanation
  (see §5), but this is not confirmed for that run. Use `-j 4`.

## 4. Results

### 4.1 Minimal RISC Zero guest runs (verified)

`host execute probe <n>` runs a Rust-only guest computing Σ i² (mod 2³²).

| n | output | user cycles | paging cycles | total cycles | segments |
|---|---|---|---|---|---|
| 0 | 0 | 3749 | 17487 | 32768 | 1 |
| 10 | 285 | 3766 | 17487 | 32768 | 1 |
| 1000 | 332833500 | 3766 | 17487 | 32768 | 1 |
| 100000 | 216474736 | 3766 | 17487 | 32768 | 1 |

Outputs match a Python reference. **User cycles do not grow with n**: the
disassembly of `probe::main` has no loop, only a multiply sequence including
the constant `0x55555556` (division by 3), i.e. LLVM replaced the loop with
the closed form n(n−1)(2n−1)/6.

**Consequence for benchmarks:** loops that LLVM can fold into a closed form
are useless for measuring unrolling. Benchmarks need loop-carried
dependences or memory traffic (e.g. `benchmarks/xorshift.c`).

### 4.2 A C kernel can be linked into a guest — GCC route (verified)

`host execute kernel <n>`: a Rust guest calls `traceopt_kernel()` from
`benchmarks/xorshift.c` via FFI. The C file is compiled by RISC Zero's GCC
toolchain through the `cc` crate (risc0-build sets `CC` and
`CFLAGS_riscv32im_risc0_zkvm_elf="-march=rv32im -nostdlib"`). The guest
measures the kernel with `env::cycle_count()` before and after the call.

| n | output | kernel cycles | user cycles | total cycles | segments |
|---|---|---|---|---|---|
| 0 | 2463534242 | 94 | 4099 | 32768 | 1 |
| 1 | 723471715 | 103 | 4108 | 32768 | 1 |
| 10 | 2653896249 | 175 | 4180 | 32768 | 1 |
| 1000 | 3298996588 | 8095 | 12100 | 65536 | 1 |
| 100000 | 196514455 | 800095 | 804100 | 1048576 | 1 |

Outputs match a Python reference. Kernel cycles are exactly linear,
`95 + 8n` for n ≥ 1: 8 cycles per iteration (six xorshift operations plus
loop increment and branch). This is the overhead loop unrolling targets.

Note: `env::cycle_count()` is reported by the host and is not constrained by
the proof; it is a measurement aid, not a proven value.

### 4.3 Total cycles are padded to a power of two (verified)

`total_cycles = user + paging + reserved`, and it is always 2^k per segment
(32768, 65536, 1048576 above). Proving work therefore grows in **steps**:
reducing user cycles only lowers the padded size when it crosses a power-of-two
boundary. The cost model must account for this.

### 4.4 Segment size changes paging cost (verified)

xorshift, n = 100000, execute mode:

| `TRACEOPT_SEGMENT_PO2` | segments | paging cycles | user cycles | total cycles |
|---|---|---|---|---|
| default | 1 | 18635 | 804100 | 1048576 |
| 19 | 2 | 28183 | 804100 | 1048576 |
| 18 | 4 | 31825 | 804100 | 1048576 |

The segment limit must be held constant when comparing variants.

### 4.5 Paging depends on memory footprint, not access count (verified)

`benchmarks/strided_rw.c` (64 KiB array, GCC route), execute mode, one
segment:

| n | kernel cycles | user cycles | paging cycles | total cycles |
|---|---|---|---|---|
| 0 | 65636 | 69641 | 61154 | 262144 |
| 1000 | 645641 | 649646 | 61154 | 1048576 |

- Paging cycles are the same for 0 and 1000 passes over the array: within
  one segment, each touched page is paged in once (and paged out once if
  dirty). They exceed xorshift's 18635 by ~42.5K cycles because of the
  array's footprint.
- `kernel_cycles` (from `env::cycle_count()`) excludes paging: user cycles
  minus kernel cycles is 4005 for every kernel measured. Paging therefore has
  to be taken from the session statistics.
- Implication for the cost model: M(F) should be a footprint feature (distinct
  pages touched per segment), not a per-access count.

### 4.6 Proving (partially verified)

| Run | Result |
|---|---|
| probe, n = 1000 (1 segment, 2^15) | Proof generated and verified in **7.0 s**; peak RSS **303 MB** |
| kernel, n = 100000 (1 segment, 2^20) | **Killed by the kernel OOM killer** at 7.5 GB anon RSS |
| kernel, n = 100000, `TRACEOPT_SEGMENT_PO2=18` | Not yet run |

## 5. Blockers and constraints

1. **Prover memory.** Proving a 2^20-cycle segment does not fit in ~7.6 GB.
   After the OOM kill, WSL failed with `E_UNEXPECTED` within about two minutes
   and needed `wsl --shutdown`. Mitigations, in order of preference:
   cap segments (`TRACEOPT_SEGMENT_PO2`) and measure peak memory per po2;
   use cycle counts as the primary metric; raise the WSL memory limit only if
   proving time is required for larger segments.
2. **LLVM/Clang not installed.** Needs `sudo apt-get install clang llvm lld`
   in WSL. Blocks the IR route (§6).
3. **Closed-form folding.** See §4.1; affects benchmark design.

## 6. Not yet tested

- Clang route: `clang -emit-llvm` → `opt` (loop-unroll) → `llc` for
  `riscv32`/`rv32im`/ILP32 → link via `TRACEOPT_KERNEL_OBJ`. RISC Zero's build
  documents `CC_riscv32im_risc0_zkvm_elf` / `CFLAGS_riscv32im_risc0_zkvm_elf`
  as an override for the C compiler, but no Clang build has been run yet.
- Proving with capped segments, and peak memory per segment po2.
- Code-size measurement of the linked kernel.

## 7. Conclusion so far

The backend is viable for **execution-based measurements** (user, paging, and
total cycles; segments) under the current memory limit. Linking C into a
RISC Zero guest works with GCC. The decisive remaining test is the Clang/LLVM
IR route.
