// Simple loop with a loop-carried dependence: n rounds of xorshift32.
// Unlike sum_squares, LLVM cannot replace this loop with a closed form,
// so its cycle count scales with n.
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t x = 2463534242u;
  for (uint32_t i = 0; i < n; i++) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
  }
  return x;
}
