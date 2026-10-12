// Memory-intensive kernel: fills a 64 KiB static array, then performs n
// passes of strided read-modify-write (1 KiB stride, 64 accesses per pass).
// Intended to touch many distinct memory pages in the zkVM.
#include <stdint.h>

#define WORDS 16384u /* 64 KiB of uint32_t */
#define STRIDE 256u  /* 1 KiB */

static uint32_t buf[WORDS];

uint32_t traceopt_kernel(uint32_t n) {
  for (uint32_t i = 0; i < WORDS; i++) {
    buf[i] = i * 2654435761u;
  }
  uint32_t acc = 0;
  for (uint32_t r = 0; r < n; r++) {
    for (uint32_t i = 0; i < WORDS; i += STRIDE) {
      uint32_t k = (i + r) & (WORDS - 1);
      acc = (acc ^ buf[k]) + r;
      buf[k] = acc;
    }
  }
  return acc;
}
