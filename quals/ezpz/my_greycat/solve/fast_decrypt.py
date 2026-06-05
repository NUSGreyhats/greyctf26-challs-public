#!/usr/bin/env python3
"""
Fast decryptor for the uploaded ELF challenge binaries.

The original program computes each output byte with a slow loop:

    result = 1
    repeat ds[i] times:
        result = (result * cs[i]) % 257

This script replaces that loop with Python's fast modular exponentiation:

    pow(cs[i], ds[i], 257)

Unlike the first version, this one discovers the `cs`, `ds`, and `n` symbols
from the ELF symbol table, so it works on both provided binaries.
"""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from multiprocessing import Pool, cpu_count
from pathlib import Path


@dataclass(frozen=True)
class Section:
    name: str
    addr: int
    offset: int
    size: int
    entsize: int
    sh_type: int
    link: int


class ElfError(Exception):
    pass


def parse_elf64_symbols(blob: bytes) -> tuple[dict[str, int], list[Section]]:
    if blob[:4] != b"\x7fELF":
        raise ElfError("not an ELF file")
    if blob[4] != 2 or blob[5] != 1:
        raise ElfError("expected 64-bit little-endian ELF")

    # ELF64 little-endian header.
    e_shoff = struct.unpack_from("<Q", blob, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", blob, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", blob, 0x3C)[0]
    e_shstrndx = struct.unpack_from("<H", blob, 0x3E)[0]
    if e_shoff == 0 or e_shnum == 0:
        raise ElfError("ELF has no section headers")

    raw_sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh = struct.unpack_from("<IIQQQQIIQQ", blob, off)
        raw_sections.append(sh)

    shstr = raw_sections[e_shstrndx]
    shstr_data = blob[shstr[4] : shstr[4] + shstr[5]]

    def cstr(data: bytes, off: int) -> str:
        end = data.find(b"\0", off)
        if end < 0:
            end = len(data)
        return data[off:end].decode("utf-8", "replace")

    sections: list[Section] = []
    for sh in raw_sections:
        name = cstr(shstr_data, sh[0]) if sh[0] < len(shstr_data) else ""
        sections.append(
            Section(
                name=name,
                addr=sh[3],
                offset=sh[4],
                size=sh[5],
                entsize=sh[9],
                sh_type=sh[1],
                link=sh[6],
            )
        )

    # SHT_SYMTAB = 2, SHT_DYNSYM = 11. The useful challenge symbols are in .symtab.
    symbols: dict[str, int] = {}
    for sec in sections:
        if sec.sh_type not in (2, 11) or sec.entsize == 0:
            continue
        if sec.link >= len(sections):
            continue
        strtab = sections[sec.link]
        strings = blob[strtab.offset : strtab.offset + strtab.size]
        count = sec.size // sec.entsize
        for i in range(count):
            sym_off = sec.offset + i * sec.entsize
            st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
                "<IBBHQQ", blob, sym_off
            )
            if st_name >= len(strings):
                continue
            name = cstr(strings, st_name)
            if name:
                symbols[name] = st_value

    return symbols, sections


def va_to_file_offset(va: int, sections: list[Section]) -> int:
    for sec in sections:
        if sec.size and sec.addr <= va < sec.addr + sec.size:
            return sec.offset + (va - sec.addr)
    raise ElfError(f"could not map virtual address 0x{va:x} to a file offset")


def get_symbol_offset(name: str, symbols: dict[str, int], sections: list[Section]) -> int:
    if name not in symbols:
        raise ElfError(f"missing symbol {name!r}; binary may be stripped or changed")
    return va_to_file_offset(symbols[name], sections)


def _decrypt_range(args: tuple[bytes, int, int, int, int]) -> tuple[int, bytes]:
    blob, cs_off, ds_off, start, end = args
    out = bytearray(end - start)
    unpack = struct.unpack_from
    for j, i in enumerate(range(start, end)):
        c = unpack("<I", blob, cs_off + 4 * i)[0]
        d = unpack("<I", blob, ds_off + 4 * i)[0]
        out[j] = pow(c, d, 257) & 0xFF
    return start, bytes(out)


def decrypt(binary_path: Path, output_path: Path, jobs: int = 1, chunk_size: int = 200_000) -> None:
    blob = binary_path.read_bytes()
    symbols, sections = parse_elf64_symbols(blob)

    cs_off = get_symbol_offset("cs", symbols, sections)
    ds_off = get_symbol_offset("ds", symbols, sections)
    n_off = get_symbol_offset("n", symbols, sections)
    n = struct.unpack_from("<I", blob, n_off)[0]

    if cs_off + 4 * n > len(blob) or ds_off + 4 * n > len(blob):
        raise ElfError("cs/ds arrays do not fit in the file; symbol layout may have changed")

    print(f"[*] cs offset: 0x{cs_off:x}")
    print(f"[*] ds offset: 0x{ds_off:x}")
    print(f"[*] n/output size: {n:,} bytes")

    ranges = [
        (blob, cs_off, ds_off, start, min(start + chunk_size, n))
        for start in range(0, n, chunk_size)
    ]

    with output_path.open("wb") as f:
        f.truncate(n)
        if jobs <= 1:
            for task in ranges:
                start, chunk = _decrypt_range(task)
                f.seek(start)
                f.write(chunk)
        else:
            with Pool(processes=jobs) as pool:
                for start, chunk in pool.imap_unordered(_decrypt_range, ranges):
                    f.seek(start)
                    f.write(chunk)

    print(f"[+] wrote {output_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fast decryptor for the ELF challenge binaries")
    ap.add_argument("binary", nargs="?", default="main", help="path to the ELF binary")
    ap.add_argument("-o", "--output", default="data.bin", help="output file path")
    ap.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=max(1, cpu_count() - 1),
        help="worker processes; use 1 to avoid multiprocessing",
    )
    ap.add_argument("--chunk-size", type=int, default=200_000, help="items per worker chunk")
    args = ap.parse_args()

    decrypt(Path(args.binary), Path(args.output), jobs=args.jobs, chunk_size=args.chunk_size)


if __name__ == "__main__":
    main()
