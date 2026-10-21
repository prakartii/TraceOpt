// Custom-kernel example: divides by n.
// Case: undefined behavior. With n = 0 the C program divides by zero, so
// there is no correct answer to compare against and stage 2 stops with an
// explanation. Any other n works normally.
// Try: scripts/live.sh examples/kernels/divide_by_n.c 0
//      scripts/live.sh examples/kernels/divide_by_n.c 7
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 0; i < 100; i++) s += 1000000u / n + i;
  return s;
}
