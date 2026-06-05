#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FORBIDDEN = [b"grey{", b"d3LulU", b"Som3T1me5", b"gooD_s0LUlu"]


def main() -> int:
    for path in DIST.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            for marker in FORBIDDEN:
                if marker in data:
                    raise SystemExit(f"leak marker in {path}")
    for model_file in (DIST / "model").glob("*.pt"):
        strings = subprocess.run(["strings", str(model_file)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        lowered = strings.stdout.lower()
        if "grey{" in lowered or "d3lulu" in lowered:
            raise SystemExit(f"strings recovered forbidden marker in {model_file}")
    print("static leakage: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
