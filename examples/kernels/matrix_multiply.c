// Custom-kernel example: 8x8 matrix multiply with 2D arrays.
// Case: nested loops (three deep) and 2D arrays; every version is checked.
// Try: scripts/live.sh examples/kernels/matrix_multiply.c 50
#include <stdint.h>

static uint32_t A[8][8], B[8][8], C[8][8];

uint32_t traceopt_kernel(uint32_t n) {
  for (int i = 0; i < 8; i++)
    for (int j = 0; j < 8; j++) {
      A[i][j] = i + j + n;
      B[i][j] = i * j + n;
      C[i][j] = 0;
    }
  for (int i = 0; i < 8; i++)
    for (int j = 0; j < 8; j++)
      for (int k = 0; k < 8; k++)
        C[i][j] += A[i][k] * B[k][j];
  uint32_t trace = 0;
  for (int i = 0; i < 8; i++) trace += C[i][i];
  return trace;
}
