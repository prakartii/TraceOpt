// Custom-kernel example: a small table, partly initialized, updated n times.
// Case: TraceOpt finds a win in code it has never seen. At n = 1000 the
// original just misses the 32,768-cycle bucket and an unrolled version fits.
// Try: scripts/live.sh examples/kernels/counter_table.c 1000
//      (and n = 50 to see the same program where nothing can be gained)
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
