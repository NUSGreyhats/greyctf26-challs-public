from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
CHALL_DIR = ROOT / "chall"
if str(DIST_DIR) not in sys.path:
    sys.path.insert(0, str(DIST_DIR))
