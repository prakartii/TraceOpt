// Custom-kernel example: a polynomial hash over 0..n-1 (a counted loop TraceOpt
// can analyze). Try: scripts/live.sh examples/kernels/poly_hash.c 12345
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t h = 7;
  for (uint32_t i = 0; i < n; i++) {
    h = h * 31 + (i ^ (h >> 7));
  }
  return h;
}
