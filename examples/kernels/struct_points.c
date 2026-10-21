// Custom-kernel example: an array of structs with fields of different sizes.
// Case: structs (padding between fields follows the RISC-V layout).
// Try: scripts/live.sh examples/kernels/struct_points.c 50
#include <stdint.h>

struct Point { uint8_t tag; uint32_t x; uint16_t y; };
static struct Point pts[16];

uint32_t traceopt_kernel(uint32_t n) {
  for (uint32_t i = 0; i < 16; i++) {
    pts[i].tag = (uint8_t)i;
    pts[i].x = i * n;
    pts[i].y = (uint16_t)(i + n);
  }
  uint32_t s = 0;
  for (uint32_t i = 0; i < 16; i++) s += (pts[i].x ^ pts[i].y) + pts[(i * 5) & 15].tag;
  return s;
}
