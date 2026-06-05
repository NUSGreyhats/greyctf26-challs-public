#!/usr/bin/env python3
import json
import sys
import time
import base64
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:34467").rstrip("/")


def make_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def get_json(opener, path, headers=None):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=headers or {})
    with opener.open(req) as resp:
        return json.loads(resp.read().decode()), resp.info()


def decode_stamp(stamp, trace_id):
    encoded = base64.b64decode(stamp)
    parts = str(trace_id or "").split("-")
    seed = parts[1] if len(parts) >= 3 else ""
    index = int(parts[2]) - 1 if len(parts) >= 3 and parts[2].isdigit() else -1
    key_base = sum(ord(ch) for ch in seed) + max(0, index) * 17
    decoded = bytes(
        value ^ ((key_base + offset * 13) & 0xFF)
        for offset, value in enumerate(encoded)
    )
    return decoded.decode("utf-8")


def main():
    opener = make_opener()
    bootstrap, _ = get_json(opener, "/api/bootstrap")
    target = bootstrap["fastPhaseScore"] + 40

    samples = [
        (0, 0),
        (120, 260),
        (240, 620),
        (360, 1180),
        (480, 1880),
        (560, target),
    ]

    for tick, score in samples:
        query = urllib.parse.urlencode({"tick": tick, "score": score, "state": "running"})
        get_json(opener, f"/api/run?{query}")
        time.sleep(1.1)

    fragments = []
    for lane in (0, 1, 0, 1, 0, 1):
        query = urllib.parse.urlencode({"score": target, "lane": lane})
        ghost, _ = get_json(opener, f"/api/ghost?{query}")
        stamp = ghost.get("stamp")
        trace_id = ghost.get("traceId")
        if stamp and trace_id:
            fragments.append(decode_stamp(stamp, trace_id))

    flag = "".join(fragments)
    print(flag)


if __name__ == "__main__":
    main()
