#!/usr/bin/env python3
"""Author-side packaging audit.

Checks that the real flag is not present in files meant for participants or in
reference-solve files.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_FLAG = (ROOT / "chall" / "flag.txt").read_text(encoding="utf-8").strip()

bad = []
for folder in [ROOT / "dist", ROOT / "solve"]:
    for path in folder.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            if REAL_FLAG.encode() in data:
                bad.append(path)

if bad:
    for path in bad:
        print(f"real flag leak: {path.relative_to(ROOT)}")
    raise SystemExit(1)

print("ok: real flag not found in dist/ or solve/")
