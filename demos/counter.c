int count[8];

int tally(int n, int step) {
  for (int i = 0; i < n; i++)
    count[(i * step) & 7] += i;
  return count[0] + count[3];
}
