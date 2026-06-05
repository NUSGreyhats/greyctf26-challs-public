#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

FORBIDDEN = [
    b"find_key_locked_door_prefix",
    b"--print-prefix",
    b"correct_history",
    b"locked-door-key-belief",
    b"good_history_features",
    b"carried_key",
    b"faced_locked_door",
    b"used_toggle",
    b"lamp",
    b"panel",
    b"corridor",
    b"treasure",
    b"fake_goal",
    b"door_echo",
    b"lava_reflection",
    b"reward_static",
    b"latent_3",
    b"highest imagined returns",
    b"histories involving locked doors",
]


def main() -> int:
    for path in DIST.rglob("*"):
        if not path.is_file() or path.name == "README.md":
            continue
        data = path.read_bytes().lower()
        for marker in FORBIDDEN:
            if marker.lower() in data:
                raise SystemExit(f"dist hint marker {marker!r} found in {path}")
    for path in (DIST / "model").glob("*.pt"):
        strings = subprocess.run(["strings", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        lowered = strings.stdout.lower()
        for marker in FORBIDDEN:
            if marker.decode().lower() in lowered:
                raise SystemExit(f"dist model hint marker {marker!r} found in {path}")
    print("dist hint scan: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
