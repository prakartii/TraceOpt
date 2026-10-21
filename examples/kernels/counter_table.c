// Custom-kernel example: a small table, partly initialized, updated n times.
// Case: TraceOpt finds wins in code it has never seen. At n = 500 the
// original just misses the 32,768-cycle bucket and unrolling 8x fits; at
// n = 1,000,000 unrolling cuts the proved size by 63%.
// Try: scripts/live.sh examples/kernels/counter_table.c 500
//      n = 50:   nothing can be gained
//      n = 1000: a win too close to the edge for the 10% margin (a missed
//                win); taken with --margin 5
#include <stdint.h>

static uint32_t T[8] = {3, 1};

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 0; i < n; i++) {
    T[i & 7] += i;
    s ^= T[(i * 3) & 7];
  }
  return s;
}
