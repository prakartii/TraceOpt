# Source this file to put LLVM tools (clang, opt, llc, ld.lld) on PATH.
#   source scripts/llvm_env.sh
# Uses a system install (/usr/lib/llvm-<ver>) or the user install made by
# scripts/install_llvm_user.sh, preferring the user install.

TRACEOPT_LLVM_VERSION="${TRACEOPT_LLVM_VERSION:-21}"
_prefix="${TRACEOPT_LLVM_PREFIX:-$HOME/.local/llvm}"
if [ -x "$_prefix/usr/lib/llvm-$TRACEOPT_LLVM_VERSION/bin/clang" ]; then
  export PATH="$_prefix/usr/lib/llvm-$TRACEOPT_LLVM_VERSION/bin:$PATH"
  export LD_LIBRARY_PATH="$_prefix/usr/lib/x86_64-linux-gnu:$_prefix/usr/lib/llvm-$TRACEOPT_LLVM_VERSION/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
elif [ -x "/usr/lib/llvm-$TRACEOPT_LLVM_VERSION/bin/clang" ]; then
  export PATH="/usr/lib/llvm-$TRACEOPT_LLVM_VERSION/bin:$PATH"
else
  echo "llvm_env.sh: LLVM $TRACEOPT_LLVM_VERSION not found; run scripts/install_llvm_user.sh" >&2
fi
unset _prefix
