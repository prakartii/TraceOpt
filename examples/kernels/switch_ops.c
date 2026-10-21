// Custom-kernel example: a different operation each round, chosen by switch.
// Case: a switch statement inside a loop; the cost model splits the cases
// evenly unless the value is known.
// Try: scripts/live.sh examples/kernels/switch_ops.c 1000
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 0; i < n; i++) {
    switch (i % 5) {
      case 0: s += i; break;
      case 1: s ^= i; break;
      case 2: s *= 3; break;
      case 3: s -= 7; break;
      default: s = (s << 1) | (s >> 31);
    }
  }
  return s;
}
