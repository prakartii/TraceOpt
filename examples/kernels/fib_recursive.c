// Custom-kernel example: recursive Fibonacci of (n mod 20).
// Case: recursion (a function calling itself); the answer checker follows
// the calls, and the zkVM answer is compared with the native build.
// Try: scripts/live.sh examples/kernels/fib_recursive.c 15
#include <stdint.h>

static uint32_t fib(uint32_t k) { return k < 2 ? k : fib(k - 1) + fib(k - 2); }

uint32_t traceopt_kernel(uint32_t n) { return fib(n % 20); }
