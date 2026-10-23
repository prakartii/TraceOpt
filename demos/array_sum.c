int a[64];

int sum(int n) {
  int s = 0;
  for (int i = 0; i < n; i++)
    s = s + a[i & 63] + i;
  return s;
}
