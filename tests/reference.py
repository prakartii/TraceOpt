"""Reference implementations of the benchmark kernels.

Used by differential tests: every kernel variant, natively or in the zkVM,
must produce the same 32-bit result as these functions.

Usage: python3 tests/reference.py <kernel> <n>
"""

import sys

MASK = 0xFFFFFFFF


def sum_squares(n: int) -> int:
    return sum(i * i for i in range(n)) & MASK


def xorshift(n: int) -> int:
    x = 2463534242
    for _ in range(n):
        x ^= (x << 13) & MASK
        x ^= x >> 17
        x ^= (x << 5) & MASK
    return x


def nested_fnv(n: int) -> int:
    h = 2166136261
    for i in range(n):
        for j in range(16):
            h = ((h ^ ((i + j) & MASK)) * 16777619) & MASK
    return h


def branchy(n: int) -> int:
    x = 2463534242
    acc = 0
    for i in range(n):
        x ^= (x << 13) & MASK
        x ^= x >> 17
        x ^= (x << 5) & MASK
        if x & 1:
            acc = (acc + (x >> 3)) & MASK
        elif x & 2:
            acc ^= (x * 3) & MASK
        else:
            acc = (acc - i) & MASK
    return acc


KERNELS = {
    "sum_squares": sum_squares,
    "xorshift": xorshift,
    "nested_fnv": nested_fnv,
    "branchy": branchy,
}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in KERNELS:
        print(f"usage: {sys.argv[0]} <{'|'.join(KERNELS)}> <n>", file=sys.stderr)
        return 2
    print(KERNELS[sys.argv[1]](int(sys.argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
