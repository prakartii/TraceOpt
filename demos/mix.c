int mix(int n) {
  int x = 1;
  for (int i = 0; i < n; i++)
    x = x * 3 ^ i;
  return x;
}
