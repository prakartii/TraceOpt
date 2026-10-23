int m[16][16];

int total(int n) {
  int s = 0;
  for (int k = 0; k < n; k++)
    for (int i = 0; i < 16; i++)
      s = s + m[i][k & 15] * i;
  return s;
}
