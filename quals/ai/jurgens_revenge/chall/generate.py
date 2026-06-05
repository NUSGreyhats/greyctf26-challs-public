from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from common import (
    DEFAULT_PAYLOAD,
    DEFAULT_SEED,
    build_model_parameters,
    clean_dist,
    save_public_model,
    validate_payload,
    write_alphabet_file,
    write_private_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
CHALL_DIR = ROOT / "chall"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the jurgens_revenge public bundle.")
    parser.add_argument("--payload", default=DEFAULT_PAYLOAD)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_payload(args.payload)
    clean_dist(DIST_DIR)
    CHALL_DIR.mkdir(parents=True, exist_ok=True)
    model = build_model_parameters(args.payload, args.seed)
    save_public_model(model, DIST_DIR / "model.pt")
    write_alphabet_file(DIST_DIR / "alphabet.json")
    write_private_metadata(CHALL_DIR / "metadata.json", args.payload, args.seed)
    print(f"generated {DIST_DIR / 'model.pt'}")


if __name__ == "__main__":
    main()
