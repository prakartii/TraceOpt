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


KERNELS = {"sum_squares": sum_squares, "xorshift": xorshift}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in KERNELS:
        print(f"usage: {sys.argv[0]} <{'|'.join(KERNELS)}> <n>", file=sys.stderr)
        return 2
    print(KERNELS[sys.argv[1]](int(sys.argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
