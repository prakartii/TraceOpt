// Custom-kernel example: count Collatz steps for 1..n.
// The inner loop runs a data-dependent number of times, so TraceOpt cannot
// predict its cost and keeps the original. Keep n to a few thousand.
// Try: scripts/live.sh examples/kernels/collatz.c 300
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t total = 0;
  for (uint32_t i = 1; i <= n; i++) {
    uint32_t x = i;
    while (x != 1) {
      x = (x & 1) ? 3 * x + 1 : x / 2;
      total++;
    }
  }
  return total;
}
