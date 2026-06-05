#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import sys


EXPECTED_SHA256 = "3263da4c5a5c8bab9cc722ebb46341a79fda7b17062d7295d1a37355a149ec52"


def read_candidate() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return sys.stdin.read().strip()


def main() -> int:
    candidate = read_candidate().encode()
    actual = hashlib.sha256(candidate).hexdigest()
    print("correct" if hmac.compare_digest(actual, EXPECTED_SHA256) else "incorrect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
