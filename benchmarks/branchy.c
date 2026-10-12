// Branch-heavy loop: a three-way data-dependent branch on an xorshift
// stream. Note: Clang may if-convert small arms into `select`; the emitted
// IR must be checked before treating this as a branch benchmark.
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t x = 2463534242u;
  uint32_t acc = 0;
  for (uint32_t i = 0; i < n; i++) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    if (x & 1) {
      acc += x >> 3;
    } else if (x & 2) {
      acc ^= x * 3u;
    } else {
      acc -= i;
    }
  }
  return acc;
}
