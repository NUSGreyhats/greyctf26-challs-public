#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


EXPECTED = {
    "verify.py",
    "requirements.txt",
    "start_seed.txt",
    "model/config.json",
    "model/policy.pt",
    "model/encoder.pt",
    "model/rssm.pt",
    "model/decoder.pt",
    "model/reward_head.pt",
    "model/continue_head.pt",
    "model/value_head.pt",
    "logs/train_summary.txt",
}

FORBIDDEN_NAMES = {
    "ORGANIZER_NOTES.md",
    "AUDIT.md",
    "SCRATCHPAD.md",
    "make_challenge.py",
    "make_release.py",
    "solve.py",
    "visual_solve.py",
    "run_all.py",
}

FORBIDDEN_BYTES = [b"grey{", b"d3LulU", b"Som3T1me5", b"gooD_s0LUlu"]


def main() -> int:
    if not DIST.exists():
        subprocess.run([sys.executable, str(ROOT / "chall" / "make_challenge.py")], cwd=ROOT, check=True)
    found = {str(path.relative_to(DIST)) for path in DIST.rglob("*") if path.is_file()}
    missing = EXPECTED - found
    extra = found - EXPECTED
    if missing or extra:
        raise SystemExit(f"dist file mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    leaked_names = [str(path.relative_to(DIST)) for path in DIST.rglob("*") if path.name in FORBIDDEN_NAMES]
    if leaked_names:
        raise SystemExit(f"dist contains organizer files: {leaked_names}")
    for forbidden in ("clean_env.py", "dream_rollout.py", "eval_model.py"):
        if (DIST / forbidden).exists():
            raise SystemExit(f"dist contains removed helper: {forbidden}")
    for path in DIST.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            for marker in FORBIDDEN_BYTES:
                if marker in data:
                    raise SystemExit(f"dist plaintext leak in {path}")
    print("dist bundle: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
