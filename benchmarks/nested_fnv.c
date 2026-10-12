// Nested loops: FNV-1a-style mixing over an n x 16 iteration space.
// The multiply chain is loop-carried, so LLVM cannot fold it to a closed
// form. The inner loop has a constant trip count of 16.
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t h = 2166136261u;
  for (uint32_t i = 0; i < n; i++) {
    for (uint32_t j = 0; j < 16; j++) {
      h = (h ^ (i + j)) * 16777619u;
    }
  }
  return h;
}
