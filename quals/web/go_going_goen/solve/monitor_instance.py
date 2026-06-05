#!/usr/bin/env python3
"""Watch a challenge instance and announce only when it changes state.

Run from a machine that can actually reach the instance (e.g. your laptop
on the CTF network). Prints a timestamped line on every up<->down
transition and rings the terminal bell, so you can leave it running and
get told when instancing drops it.

Usage:
    python monitor_instance.py --base-url 'http://challs.nusgreyhats.org:34167/?token=tt_...'
    python monitor_instance.py --base-url <url> --interval 10
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import httpx

from exploit_common import resolve_base_and_token


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--interval", type=float, default=15.0, help="seconds between checks")
    p.add_argument("--path", default="/healthz", help="endpoint to poll")
    p.add_argument("--timeout", type=float, default=10.0, help="per-check timeout")
    return p.parse_args()


def check(client: httpx.Client, path: str) -> tuple[bool, str]:
    try:
        r = client.get(path)
        return (r.status_code < 500, f"{r.status_code}")
    except httpx.HTTPError as exc:
        return (False, exc.__class__.__name__)


def main() -> int:
    args = parse_args()
    base, _ = resolve_base_and_token(args.base_url)  # tolerate a ?token=... URL
    state: bool | None = None  # None = unknown, True = up, False = down
    print(f"[*] watching {base}{args.path} every {args.interval:g}s (Ctrl-C to stop)")
    with httpx.Client(base_url=base, timeout=args.timeout, follow_redirects=True) as client:
        while True:
            up, detail = check(client, args.path)
            if up != state:
                stamp = datetime.now().strftime("%H:%M:%S")
                label = "UP" if up else "DOWN"
                bell = "\a" if state is not None else ""  # no bell on first reading
                print(f"{bell}[{stamp}] {label}  ({detail})", flush=True)
                state = up
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[*] stopped")
