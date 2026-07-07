from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit an enshittification-detector prediction JSON.")
    parser.add_argument("--url", required=True, help="challenge server base URL, e.g. http://localhost:5000")
    parser.add_argument("--payload", required=True, type=Path)
    args = parser.parse_args()

    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    response = requests.post(args.url.rstrip("/") + "/submit", json=payload, timeout=20)
    print(response.text.strip())


if __name__ == "__main__":
    main()
