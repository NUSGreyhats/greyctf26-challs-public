#!/usr/bin/env python3
"""
add_anti_analysis.py — inject IDA-confusing STT_FUNC metadata into an ELF
(or a C source file that is compiled first).

Technique
---------
IDA Pro 9.3's auto-analyser refuses to create a function when multiple
STT_FUNC symbols claim bodies that overlap at byte granularity. It drops
*all* of the colliding symbols, including the one that coincides with
e_entry. Additional STT_FUNC symbols that point at otherwise-unvisited
bytes are accepted as functions and decompiled even when those bytes are
data. See POC_DISASM_CONFUSION.md.

This tool applies the same technique in-place to a supplied binary:

  - Adds three overlapping STT_FUNC symbols with randomized names at the
    chosen address (default e_entry), at offsets 0 / +1 / +2.
  - Adds a randomized "phantom" STT_FUNC somewhere in the executable segment
    where IDA will find data bytes that happen to decode into plausible x86.

Usage
-----
  add_anti_analysis.py INPUT [-o OUTPUT] [--address HEX]
                             [--phantom-offset BYTES]
                             [--cc CC]

INPUT may be either an ELF or a C source file. For a C source file the
tool invokes `$CC input.c -o tmp_elf` first, then post-processes the
result. Default CC is `cc`.

Limitations
-----------
- ELF64 little-endian only (x86-64, aarch64, etc.).
- Target binary must have a section header table (true for almost all
  compilers' output, even stripped).
- If the binary has no .symtab / .strtab, they are created and the
  section header table is expanded.
"""

import argparse
import os
import secrets
import struct
import subprocess
import sys
import tempfile


# ------------------------------- ELF consts ---------------------------------

SHT_NULL       = 0
SHT_PROGBITS   = 1
SHT_SYMTAB     = 2
SHT_STRTAB     = 3
SHT_NOBITS     = 8

SHF_ALLOC      = 0x02
SHF_EXECINSTR  = 0x04

STB_LOCAL      = 0
STB_GLOBAL     = 1
STT_FUNC       = 2


def st_info(bind, typ):
    return (bind << 4) | (typ & 0xf)


# ----------------------------- ELF primitives -------------------------------

ELF64_EHDR = '<16sHHIQQQIHHHHHH'
ELF64_EHDR_SZ = struct.calcsize(ELF64_EHDR)   # 64
ELF64_SHDR = '<IIQQQQIIQQ'
ELF64_SHDR_SZ = struct.calcsize(ELF64_SHDR)   # 64
ELF64_SYM  = '<IBBHQQ'
ELF64_SYM_SZ = struct.calcsize(ELF64_SYM)     # 24


def parse_ehdr(data):
    e_ident = data[:16]
    if e_ident[:4] != b'\x7fELF':
        raise ValueError("not an ELF")
    if e_ident[4] != 2:
        raise ValueError("only ELF64 is supported")
    if e_ident[5] != 1:
        raise ValueError("only little-endian ELF is supported")
    (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff,
     e_flags, e_ehsize, e_phentsize, e_phnum, e_shentsize,
     e_shnum, e_shstrndx) = struct.unpack_from(ELF64_EHDR, data, 0)[1:]
    return dict(
        e_ident=e_ident,
        e_type=e_type, e_machine=e_machine, e_version=e_version,
        e_entry=e_entry, e_phoff=e_phoff, e_shoff=e_shoff,
        e_flags=e_flags, e_ehsize=e_ehsize, e_phentsize=e_phentsize,
        e_phnum=e_phnum, e_shentsize=e_shentsize, e_shnum=e_shnum,
        e_shstrndx=e_shstrndx,
    )


def pack_ehdr(ehdr):
    return struct.pack(
        ELF64_EHDR,
        ehdr['e_ident'],
        ehdr['e_type'], ehdr['e_machine'], ehdr['e_version'],
        ehdr['e_entry'], ehdr['e_phoff'], ehdr['e_shoff'],
        ehdr['e_flags'], ehdr['e_ehsize'], ehdr['e_phentsize'],
        ehdr['e_phnum'], ehdr['e_shentsize'], ehdr['e_shnum'],
        ehdr['e_shstrndx'],
    )


def parse_shdrs(data, ehdr):
    out = []
    for i in range(ehdr['e_shnum']):
        off = ehdr['e_shoff'] + i * ehdr['e_shentsize']
        (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
         sh_link, sh_info, sh_addralign, sh_entsize) = \
            struct.unpack_from(ELF64_SHDR, data, off)
        out.append(dict(
            sh_name=sh_name, sh_type=sh_type, sh_flags=sh_flags,
            sh_addr=sh_addr, sh_offset=sh_offset, sh_size=sh_size,
            sh_link=sh_link, sh_info=sh_info,
            sh_addralign=sh_addralign, sh_entsize=sh_entsize,
        ))
    return out


def pack_shdr(sh):
    return struct.pack(
        ELF64_SHDR,
        sh['sh_name'], sh['sh_type'], sh['sh_flags'], sh['sh_addr'],
        sh['sh_offset'], sh['sh_size'], sh['sh_link'], sh['sh_info'],
        sh['sh_addralign'], sh['sh_entsize'],
    )


def cstr_at(buf, off):
    end = buf.find(b'\x00', off)
    if end < 0:
        return buf[off:]
    return buf[off:end]


def find_section(shdrs, shstrtab, name):
    wanted = name.encode() if isinstance(name, str) else name
    for i, sh in enumerate(shdrs):
        if cstr_at(shstrtab, sh['sh_name']) == wanted:
            return i, sh
    return None, None


def pick_text_shndx(shdrs, ehdr):
    """Return index of the section containing e_entry, preferring one that
    is SHF_ALLOC|SHF_EXECINSTR."""
    entry = ehdr['e_entry']
    for i, sh in enumerate(shdrs):
        if sh['sh_addr'] <= entry < sh['sh_addr'] + sh['sh_size']:
            return i
    # fallback: first exec+alloc section
    for i, sh in enumerate(shdrs):
        if (sh['sh_flags'] & SHF_EXECINSTR) and (sh['sh_flags'] & SHF_ALLOC):
            return i
    raise ValueError("could not find a section containing e_entry")


def find_phantom_spot(shdrs, text_shndx, base_addr, want_offset):
    """Choose a virtual address inside the text section for the phantom
    symbol. Prefer `base_addr + want_offset` if it's inside the section.
    Otherwise put it 64 bytes past base, clamped."""
    sh = shdrs[text_shndx]
    start = sh['sh_addr']
    end = start + sh['sh_size']
    candidate = base_addr + want_offset
    if start <= candidate < end:
        return candidate, min(64, end - candidate)
    candidate = base_addr + 0x40
    if start <= candidate < end:
        return candidate, min(32, end - candidate)
    return start + max(0, (end - start) // 2), min(32, end - (start + (end - start) // 2))


# ----------------------------- main transform -------------------------------

def random_symbol_name(prefix):
    return (prefix + secrets.token_hex(10)).encode()


def add_anti_analysis(data, target_addr=None, phantom_offset=0x40,
                      targets=None, symbol_prefix='_', verbose=False):
    """Return a new bytes object with the anti-analysis payload applied.

    `targets` is an optional iterable of addresses; one set of randomized
    overlapping STT_FUNC symbols + one phantom is injected per address. If
    omitted, falls back to `target_addr` or e_entry.
    """
    data = bytearray(data)
    ehdr = parse_ehdr(bytes(data))
    if ehdr['e_shoff'] == 0 or ehdr['e_shnum'] == 0:
        raise ValueError("ELF has no section header table; "
                         "cannot inject symbols")

    shdrs = parse_shdrs(bytes(data), ehdr)

    shstr_sh = shdrs[ehdr['e_shstrndx']]
    shstrtab = bytes(data[shstr_sh['sh_offset']:
                          shstr_sh['sh_offset'] + shstr_sh['sh_size']])

    symtab_idx, symtab_sh = find_section(shdrs, shstrtab, '.symtab')
    strtab_idx, strtab_sh = find_section(shdrs, shstrtab, '.strtab')

    text_shndx = pick_text_shndx(shdrs, ehdr)

    if targets is None:
        targets = [target_addr if target_addr is not None else ehdr['e_entry']]
    else:
        targets = list(targets)
        if not targets:
            raise ValueError("targets list is empty")

    # Build new .strtab. Start from existing content if present, otherwise
    # from a single null byte.
    if strtab_sh is not None:
        new_strtab = bytearray(
            data[strtab_sh['sh_offset']:strtab_sh['sh_offset']+strtab_sh['sh_size']]
        )
        if not new_strtab or new_strtab[0] != 0:
            new_strtab = bytearray(b'\x00') + new_strtab
    else:
        new_strtab = bytearray(b'\x00')

    def add_str(buf, s):
        if not s.endswith(b'\x00'):
            s = s + b'\x00'
        off = len(buf)
        buf += s
        return off

    # Build new .symtab. Start from existing entries if present, otherwise
    # from a single null symbol.
    if symtab_sh is not None:
        new_symtab = bytearray(
            data[symtab_sh['sh_offset']:symtab_sh['sh_offset']+symtab_sh['sh_size']]
        )
        existing_info = symtab_sh['sh_info']
    else:
        new_symtab = bytearray(b'\x00' * ELF64_SYM_SZ)
        existing_info = 1  # only the null symbol precedes global syms

    def pack_sym(name_off, info, shndx, value, size):
        return struct.pack(ELF64_SYM, name_off, info, 0, shndx, value, size)

    phantom_addrs = []
    for target in targets:
        name_start   = add_str(new_strtab, random_symbol_name(symbol_prefix))
        name_main    = add_str(new_strtab, random_symbol_name(symbol_prefix))
        name_hidden  = add_str(new_strtab, random_symbol_name(symbol_prefix))
        name_phantom = add_str(new_strtab, random_symbol_name(symbol_prefix))

        new_symtab += pack_sym(name_start,  st_info(STB_GLOBAL, STT_FUNC),
                               text_shndx, target,     0x0C)
        new_symtab += pack_sym(name_main,   st_info(STB_GLOBAL, STT_FUNC),
                               text_shndx, target + 1, 0x12)
        new_symtab += pack_sym(name_hidden, st_info(STB_GLOBAL, STT_FUNC),
                               text_shndx, target + 2, 0x11)

        phantom_addr, phantom_size = find_phantom_spot(
            shdrs, text_shndx, target, phantom_offset)
        new_symtab += pack_sym(name_phantom, st_info(STB_GLOBAL, STT_FUNC),
                               text_shndx, phantom_addr, phantom_size)
        phantom_addrs.append((phantom_addr, phantom_size))

    # Stash for verbose print (single-target preserves legacy behaviour).
    target = targets[0]
    phantom_addr, phantom_size = phantom_addrs[0]

    # If .symtab/.strtab didn't exist we also need to add their names to
    # shstrtab and create two new section header entries. Otherwise we
    # just update the existing ones to point at newly appended buffers.

    appended_sections = []   # list of (name_bytes, sh_template, payload)

    new_shstrtab = bytearray(shstrtab)
    if not new_shstrtab or new_shstrtab[0] != 0:
        new_shstrtab = bytearray(b'\x00') + new_shstrtab

    if symtab_idx is None:
        # Need to create .symtab and .strtab.
        nm_symtab = add_str(new_shstrtab, b'.symtab')
        nm_strtab = add_str(new_shstrtab, b'.strtab')
        appended_sections.append(('strtab', nm_strtab, None))
        appended_sections.append(('symtab', nm_symtab, None))
    else:
        nm_symtab = shdrs[symtab_idx]['sh_name']
        nm_strtab = shdrs[strtab_idx]['sh_name']

    # ----- Layout: keep everything up to ehdr['e_shoff'] intact, then
    #               append our new blobs, then write a fresh SHT.
    # Strategy: leave original file bytes (including the original section
    # contents) in place; append new_strtab, new_symtab, new_shstrtab,
    # and a new section header table at the end of the file.

    # Start writing new data just past the end of the original file, ignoring
    # where the original SHT used to live — we'll write a fresh SHT.
    # Use the larger of len(data) and (e_shoff + e_shnum*e_shentsize) in
    # case the SHT wasn't at the very end.
    tail_start = max(len(data),
                     ehdr['e_shoff'] + ehdr['e_shnum'] * ehdr['e_shentsize'])
    # truncate any trailing bytes past tail_start: none to truncate but
    # ensure our buffer has exactly that many bytes.
    if tail_start > len(data):
        data.extend(b'\x00' * (tail_start - len(data)))
    # Remove the original SHT bytes if they sit past any section data —
    # this is harmless either way because we always write new SHT at
    # the end.
    pos = tail_start

    def align_to(pos, align):
        pad = (-pos) & (align - 1)
        data.extend(b'\x00' * pad)
        return pos + pad

    # Append new_strtab
    pos = align_to(pos, 8)
    new_strtab_off = pos
    data.extend(new_strtab)
    pos = len(data)

    # Append new_symtab
    pos = align_to(pos, 8)
    new_symtab_off = pos
    data.extend(new_symtab)
    pos = len(data)

    # Append new shstrtab
    pos = align_to(pos, 8)
    new_shstrtab_off = pos
    data.extend(new_shstrtab)
    pos = len(data)

    # ----- Rebuild section header table.
    # Existing shdrs pointers remain valid; we patch in the updated entries
    # for .symtab, .strtab, shstrtab; optionally append two new entries.

    if strtab_idx is not None:
        shdrs[strtab_idx]['sh_type']    = SHT_STRTAB
        shdrs[strtab_idx]['sh_flags']   = 0
        shdrs[strtab_idx]['sh_addr']    = 0
        shdrs[strtab_idx]['sh_offset']  = new_strtab_off
        shdrs[strtab_idx]['sh_size']    = len(new_strtab)
        shdrs[strtab_idx]['sh_link']    = 0
        shdrs[strtab_idx]['sh_info']    = 0
        shdrs[strtab_idx]['sh_addralign'] = 1
        shdrs[strtab_idx]['sh_entsize'] = 0

    if symtab_idx is not None:
        shdrs[symtab_idx]['sh_type']    = SHT_SYMTAB
        shdrs[symtab_idx]['sh_flags']   = 0
        shdrs[symtab_idx]['sh_addr']    = 0
        shdrs[symtab_idx]['sh_offset']  = new_symtab_off
        shdrs[symtab_idx]['sh_size']    = len(new_symtab)
        shdrs[symtab_idx]['sh_link']    = strtab_idx
        shdrs[symtab_idx]['sh_info']    = existing_info
        shdrs[symtab_idx]['sh_addralign'] = 8
        shdrs[symtab_idx]['sh_entsize'] = ELF64_SYM_SZ

    # shstrtab: we updated it with two extra entries when creating
    # .symtab/.strtab. Redirect the existing shstrtab section header to the
    # new blob at new_shstrtab_off.
    shdrs[ehdr['e_shstrndx']]['sh_offset'] = new_shstrtab_off
    shdrs[ehdr['e_shstrndx']]['sh_size']   = len(new_shstrtab)

    # If we're creating new sections, append them to the shdr list.
    if symtab_idx is None:
        strtab_idx_new = len(shdrs)
        shdrs.append(dict(
            sh_name=nm_strtab, sh_type=SHT_STRTAB, sh_flags=0,
            sh_addr=0, sh_offset=new_strtab_off, sh_size=len(new_strtab),
            sh_link=0, sh_info=0, sh_addralign=1, sh_entsize=0,
        ))
        symtab_idx_new = len(shdrs)
        shdrs.append(dict(
            sh_name=nm_symtab, sh_type=SHT_SYMTAB, sh_flags=0,
            sh_addr=0, sh_offset=new_symtab_off, sh_size=len(new_symtab),
            sh_link=strtab_idx_new, sh_info=existing_info,
            sh_addralign=8, sh_entsize=ELF64_SYM_SZ,
        ))

    # Finally, write the new SHT at end of file.
    pos = align_to(len(data), 8)
    new_shoff = pos
    for sh in shdrs:
        data.extend(pack_shdr(sh))

    # Patch ELF header: new e_shoff, e_shnum.
    ehdr['e_shoff'] = new_shoff
    ehdr['e_shnum'] = len(shdrs)
    new_ehdr = pack_ehdr(ehdr)
    data[:ELF64_EHDR_SZ] = new_ehdr

    if verbose:
        sys.stderr.write(
            "[+] target=%#x  phantom=%#x (sz=%d)  text_shndx=%d  "
            "new_shoff=%#x  shnum=%d\n"
            % (target, phantom_addr, phantom_size, text_shndx,
               new_shoff, len(shdrs)))
        sys.stderr.write(
            "[+] appended %d bytes (strtab=%d sym=%d shstrtab=%d + SHT=%d)\n"
            % (len(data) - tail_start,
               len(new_strtab), len(new_symtab), len(new_shstrtab),
               len(shdrs) * ELF64_SHDR_SZ))

    return bytes(data)


# ------------------------------ C compile path ------------------------------

def compile_c(c_path, cc='cc', cflags=None):
    if cflags is None:
        cflags = ['-O1', '-no-pie']
    out = tempfile.NamedTemporaryFile(
        prefix='elf_', suffix='.elf', delete=False)
    out.close()
    cmd = [cc, c_path, '-o', out.name] + cflags
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        os.unlink(out.name)
        raise SystemExit("compilation failed: %s" % e)
    return out.name


def looks_like_elf(path):
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'\x7fELF'
    except OSError:
        return False


# -------------------------------- CLI ---------------------------------------

def parse_hex(x):
    return int(x, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('input', help='ELF binary or .c source file')
    ap.add_argument('-o', '--output', default=None,
                    help='output path (default: INPUT.aa)')
    ap.add_argument('--address', type=parse_hex, default=None,
                    help='target address for the overlapping symbols '
                         '(default: e_entry)')
    ap.add_argument('--targets', default=None,
                    help='comma-separated list of target addresses (hex). '
                         'Overrides --address. One overlap-set + phantom '
                         'is injected per address.')
    ap.add_argument('--targets-file', default=None,
                    help='file with one hex address per line (whitespace '
                         'and # comments tolerated)')
    ap.add_argument('--phantom-offset', type=parse_hex, default=0x40,
                    help='offset from target for the phantom symbol '
                         '(default: 0x40)')
    ap.add_argument('--symbol-prefix', default='_',
                    help='prefix for injected randomized symbol names '
                         '(default: _)')
    ap.add_argument('--cc', default=os.environ.get('CC', 'cc'),
                    help='C compiler (if input is .c)')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit("input does not exist: %s" % args.input)

    # Figure out whether this is a C file or an ELF.
    tmp_compiled = None
    if args.input.endswith(('.c', '.cc', '.cpp', '.cxx')) or \
       not looks_like_elf(args.input):
        if not looks_like_elf(args.input):
            # compile
            tmp_compiled = compile_c(args.input, cc=args.cc)
            src_for_patch = tmp_compiled
        else:
            src_for_patch = args.input
    else:
        src_for_patch = args.input

    with open(src_for_patch, 'rb') as f:
        data = f.read()

    targets = None
    if args.targets:
        targets = [parse_hex(x.strip()) for x in args.targets.split(',') if x.strip()]
    elif args.targets_file:
        with open(args.targets_file) as tf:
            targets = []
            for line in tf:
                line = line.split('#', 1)[0].strip()
                if line:
                    targets.append(parse_hex(line))

    patched = add_anti_analysis(data,
                                target_addr=args.address,
                                targets=targets,
                                phantom_offset=args.phantom_offset,
                                symbol_prefix=args.symbol_prefix,
                                verbose=args.verbose)

    out = args.output or (args.input + '.aa')
    with open(out, 'wb') as f:
        f.write(patched)
    # make executable if it was
    try:
        mode = os.stat(src_for_patch).st_mode
        os.chmod(out, mode | 0o111)
    except OSError:
        pass
    if tmp_compiled:
        os.unlink(tmp_compiled)
    sys.stderr.write("wrote %s (%d bytes)\n" % (out, len(patched)))


if __name__ == '__main__':
    main()
