#!/usr/bin/env python3
"""Submit the bundled sample JPEG to a running dbench_jumbf service."""
from __future__ import annotations

import argparse
import socket
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_IMAGE = HERE / "sample_c2pa.jpg"


def recv_until(sock: socket.socket, marker: bytes) -> bytes:
    data = bytearray()
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a JPEG to the validator service")
    parser.add_argument("host", nargs="?", default="localhost")
    parser.add_argument("port", nargs="?", type=int, default=32167)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()

    image = args.image.read_bytes()

    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.settimeout(5)
        output = bytearray()
        output.extend(recv_until(sock, b"jpeg size> "))
        sock.sendall(str(len(image)).encode() + b"\n")
        output.extend(recv_until(sock, b"jpeg hex> "))
        sock.sendall(image.hex().encode() + b"\n")
        output.extend(recv_until(sock, b"done\n"))
        sock.sendall(b"0\n")
        output.extend(recv_until(sock, b"goodbye\n"))

    print(output.decode("utf-8", errors="replace"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
