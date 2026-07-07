from __future__ import annotations

import argparse
import hashlib


def verify_pow(prefix: str, nonce: str, difficulty: int) -> bool:
    digest = hashlib.sha256((prefix + nonce).encode("ascii")).digest()
    whole_bytes, remaining_bits = divmod(difficulty, 8)
    if any(digest[index] != 0 for index in range(whole_bytes)):
        return False
    if remaining_bits == 0:
        return True
    return digest[whole_bytes] >> (8 - remaining_bits) == 0


def solve_pow(prefix: str, difficulty: int) -> str:
    counter = 0
    while True:
        nonce = f"{counter:x}"
        if verify_pow(prefix, nonce, difficulty):
            return nonce
        counter += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Solve the Rubikscube server proof-of-work challenge.")
    parser.add_argument("prefix", help="Hex prefix from `POW prefix=<hex> difficulty=<bits>`.")
    parser.add_argument("difficulty", type=int, help="Difficulty bits from the POW line.")
    args = parser.parse_args()
    print(solve_pow(args.prefix, args.difficulty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
