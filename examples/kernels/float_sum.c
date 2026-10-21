// Custom-kernel example: adds 0.5 n times in floating point.
// Case: a feature TraceOpt's answer checker does not support. The zkVM still
// runs it and the answer is still compared, but the unrolled versions cannot
// be checked, so TraceOpt keeps the original rather than trust them.
// Try: scripts/live.sh examples/kernels/float_sum.c 50
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  float x = 0;
  for (uint32_t i = 0; i < n; i++) x += 0.5f;
  return (uint32_t)x;
}
