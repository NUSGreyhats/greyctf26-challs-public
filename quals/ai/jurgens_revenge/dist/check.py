from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from model import RevengeModel


ROOT = Path(__file__).resolve().parent
ALPHABET_INFO = json.loads((ROOT / "alphabet.json").read_text(encoding="utf-8"))
PAYLOAD_LEN = int(ALPHABET_INFO["payload_length"])
FLAG_RE = re.compile(rf"grey\{{([a-z0-9_]{{{PAYLOAD_LEN}}})\}}\Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="jurgens_revenge checker")
    parser.add_argument("candidate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    match = FLAG_RE.fullmatch(args.candidate)
    if match is None:
        print("rejected")
        return 1
    model = RevengeModel.from_paths(ROOT / "model.pt", ROOT / "alphabet.json")
    try:
        accepted = model.run_payload(match.group(1))["accepted"]
    except Exception:
        accepted = False
    print("accepted" if accepted else "rejected")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
