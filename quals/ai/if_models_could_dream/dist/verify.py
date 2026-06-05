#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import sys


EXPECTED_SHA256 = "8c62565158110278305836e6129182063a23919327416496c3dc9f2b2d945a16"


def main() -> int:
    candidate = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    actual = hashlib.sha256(candidate.encode()).hexdigest()
    print("correct" if hmac.compare_digest(actual, EXPECTED_SHA256) else "incorrect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
