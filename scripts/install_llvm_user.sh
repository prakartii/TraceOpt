#!/usr/bin/env bash
# Install LLVM/Clang/LLD into a user directory without sudo, by downloading
# Ubuntu's packages and unpacking them (no package scripts are run).
#
# Usage (inside WSL): scripts/install_llvm_user.sh [version]   (default 21)
# Then: source scripts/llvm_env.sh
#
# With sudo available, `sudo apt-get install clang llvm lld` is simpler;
# scripts/llvm_env.sh finds either installation.
set -euo pipefail

VER="${1:-21}"
PREFIX="${TRACEOPT_LLVM_PREFIX:-$HOME/.local/llvm}"
DEBS="$HOME/.cache/llvm-debs"

# Packages needed for clang, opt, llc and ld.lld that are not already installed.
pkgs=$(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts \
         --no-breaks --no-replaces --no-enhances "clang-$VER" "llvm-$VER" "lld-$VER" \
       | grep '^\w' | sort -u \
       | while read -r p; do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done \
       | grep -v -e '^libobjc' -e '^libgc1$')

mkdir -p "$DEBS" "$PREFIX"
cd "$DEBS"
# shellcheck disable=SC2086
apt-get download $pkgs
for d in *.deb; do dpkg -x "$d" "$PREFIX"; done

echo "installed LLVM $VER into $PREFIX"
"$PREFIX/usr/lib/llvm-$VER/bin/clang" --version | head -1 || {
  echo "clang does not run; a shared library may be missing" >&2; exit 1; }
