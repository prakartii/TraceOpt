// Simple loop: sum of i*i for i in [0, n), wrapping at 32 bits.
// Matches the Rust probe guest so the two can be compared.
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t acc = 0;
  for (uint32_t i = 0; i < n; i++) {
    acc += i * i;
  }
  return acc;
}
