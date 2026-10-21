// Entry function for kernels with the classic signature
// `uint32_t traceopt_kernel(uint32_t n)`, used when no TRACEOPT_ENTRY_OBJ is
// given (traceopt/signature.py generates the same function in LLVM IR for
// any other signature).
#include <stdint.h>

uint32_t traceopt_kernel(uint32_t n);
uint64_t traceopt_cycle_count(void);

void traceopt_entry(const uint32_t *words, uint64_t *out) {
  uint32_t n = words[0];
  uint64_t start = traceopt_cycle_count();
  uint32_t result = traceopt_kernel(n);
  uint64_t end = traceopt_cycle_count();
  out[0] = result;
  out[1] = end - start;
}
