#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = subprocess.run([sys.executable, str(ROOT / "solve" / "solve.py")], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    candidate = result.stdout.strip().splitlines()[-1]
    checked = subprocess.run([sys.executable, str(ROOT / "dist" / "verify.py"), candidate], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if checked.stdout.strip() != "correct":
        raise SystemExit("reference solve output failed verifier")
    print("reference solve: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
