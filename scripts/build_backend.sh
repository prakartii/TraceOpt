#!/usr/bin/env bash
# Build the RISC Zero backend (host + guests) inside WSL/Linux.
#
# - Limits parallelism: a default 20-job build exhausted WSL's ~7.6 GB and
#   crashed the VM (see docs/feasibility.md). Override with JOBS=<n>.
# - TRACEOPT_GUEST_ONLY=1 rebuilds only the guests (see the host's
#   TRACEOPT_KERNEL_ELF), which is much faster when only the kernel changed.
# - Keeps build output off /mnt/c, which is much slower than the Linux FS.
#   Override with CARGO_TARGET_DIR.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/.cache/traceopt-target}"
export PATH="$HOME/.risc0/bin:$HOME/.cargo/bin:$PATH"

cd "$ROOT/backend/risc0"
if [[ "${TRACEOPT_GUEST_ONLY:-0}" == 1 ]]; then
  # Rebuild only the guests; run the existing host with
  # TRACEOPT_KERNEL_ELF=$CARGO_TARGET_DIR/riscv-guest/methods/kernel/riscv32im-risc0-zkvm-elf/release/kernel.bin
  cargo build --release -j "${JOBS:-4}" -p methods "$@"
else
  cargo build --release -j "${JOBS:-4}" "$@"
fi
echo "host binary: $CARGO_TARGET_DIR/release/host"
