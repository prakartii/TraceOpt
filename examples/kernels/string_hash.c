// Custom-kernel example: FNV-1a hash over a constant string, n bytes long.
// Case: a constant string and byte loads (8-bit memory accesses).
// Try: scripts/live.sh examples/kernels/string_hash.c 1000
#include <stdint.h>

static const char msg[] = "zero knowledge";

uint32_t traceopt_kernel(uint32_t n) {
  uint32_t h = 2166136261u;
  for (uint32_t i = 0; i < n; i++) h = (h ^ (uint8_t)msg[i % 14]) * 16777619u;
  return h;
}
