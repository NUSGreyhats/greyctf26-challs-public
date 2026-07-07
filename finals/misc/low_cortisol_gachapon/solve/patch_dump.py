#!/usr/bin/env python3
"""Patch a MIFARE Classic 1K dump for the gachapon checker.

The output remains a raw 1024-byte dump, suitable for flashing back to a
writable MIFARE Classic-compatible card with tools such as Proxmark.
"""
from __future__ import annotations

import argparse
import binascii
import struct
from pathlib import Path


DUMP_SIZE = 1024
BLOCK_SIZE = 16
RECORD_BLOCK = 16
RECORD_LEN = 32
RECORD_OFFSET = RECORD_BLOCK * BLOCK_SIZE

MARKER = b"GREYGachaCard"
VERSION = 0x01
WIN_BALANCE_CENTS = 670000


def build_record(balance_cents: int = WIN_BALANCE_CENTS) -> bytes:
    if not 0 <= balance_cents <= 0xFFFFFFFF:
        raise ValueError("balance must fit in uint32")

    head = MARKER + bytes([VERSION]) + struct.pack("<I", balance_cents)
    crc = binascii.crc32(head) & 0xFFFFFFFF
    return (head + struct.pack("<I", crc)).ljust(RECORD_LEN, b"\x00")


def patch_dump(raw: bytes, balance_cents: int = WIN_BALANCE_CENTS) -> bytes:
    if len(raw) != DUMP_SIZE:
        raise ValueError(f"expected raw {DUMP_SIZE}-byte MIFARE Classic 1K dump")

    patched = bytearray(raw)
    patched[RECORD_OFFSET : RECORD_OFFSET + RECORD_LEN] = build_record(balance_cents)
    return bytes(patched)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="input raw 1024-byte MIFARE Classic dump")
    parser.add_argument("output", help="output patched raw dump")
    parser.add_argument(
        "--balance-cents",
        type=int,
        default=WIN_BALANCE_CENTS,
        help=f"balance to write in cents, default: {WIN_BALANCE_CENTS}",
    )
    args = parser.parse_args()

    patched = patch_dump(Path(args.input).read_bytes(), args.balance_cents)
    Path(args.output).write_bytes(patched)

    record = patched[RECORD_OFFSET : RECORD_OFFSET + RECORD_LEN]
    balance = struct.unpack("<I", record[len(MARKER) + 1 : len(MARKER) + 5])[0]
    stored_crc = struct.unpack("<I", record[18:22])[0]

    print(f"wrote {args.output}")
    print(f"block 16: {record[:16].hex(' ')}")
    print(f"block 17: {record[16:].hex(' ')}")
    print(f"balance: {balance / 100:.2f} ({balance} cents)")
    print(f"crc32: {stored_crc:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
