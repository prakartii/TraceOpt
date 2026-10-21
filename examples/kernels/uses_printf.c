// Custom-kernel example: calls printf.
// Case: an invalid kernel. Kernels run inside the zkVM without an operating
// system, so library functions are not available; TraceOpt stops with a
// one-line explanation instead of crashing.
// Try: scripts/live.sh examples/kernels/uses_printf.c 5
#include <stdint.h>
#include <stdio.h>

uint32_t traceopt_kernel(uint32_t n) {
  printf("n = %u\n", n);
  return n;
}
