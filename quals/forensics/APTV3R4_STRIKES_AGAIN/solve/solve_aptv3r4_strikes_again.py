#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:
    from Cryptodome.Cipher import AES, ARC4
    from Cryptodome.Hash import MD4, SHA256
    from Cryptodome.Protocol.KDF import PBKDF2
except ImportError:
    try:
        from Crypto.Cipher import AES, ARC4
        from Crypto.Hash import MD4, SHA256
        from Crypto.Protocol.KDF import PBKDF2
    except ImportError as exc:
        raise SystemExit(
            "missing crypto dependency; install one of:\n"
            "  py -m pip install pycryptodomex\n"
            "  python3 -m pip install pycryptodomex"
        ) from exc


TOKEN_RE = re.compile(rb"token=([A-Za-z0-9]{67})")
ANY_TOKEN_RE = re.compile(rb"\b[A-Za-z0-9]{67}\b")
HEX_KEY_RE = re.compile(rb"\b[0-9a-fA-F]{64}\b")
FLAG_RE = re.compile(rb"grey\{[^}\r\n]+\}")

SMB2_FLAGS_SERVER_TO_REDIR = 0x00000001
SMB2_NEGOTIATE = 0
SMB2_SESSION_SETUP = 1
SMB2_TREE_CONNECT = 3
SMB2_CREATE = 5
SMB2_READ = 8

NTLMSSP_NEGOTIATE_UNICODE = 0x00000001


@dataclass
class TcpSegment:
    seq: int
    payload: bytes


@dataclass
class SmbMessage:
    flow: tuple[str, int, str, int]
    index: int
    raw: bytes


@dataclass
class Smb2Header:
    command: int
    status: int
    flags: int
    message_id: int
    tree_id: int
    session_id: int

    @property
    def from_server(self) -> bool:
        return bool(self.flags & SMB2_FLAGS_SERVER_TO_REDIR)


@dataclass
class TransformHeader:
    signature: bytes
    nonce: bytes
    original_size: int
    algorithm: int
    session_id: int

    @property
    def aad(self) -> bytes:
        return (
            self.nonce
            + struct.pack("<LHHQ", self.original_size, 0, self.algorithm, self.session_id)
        )


def default_challenge_dir() -> Path:
    candidates = [
        Path.cwd(),
        Path.cwd() / "APTV3R4_STRIKES_AGAIN",
        Path.home()
        / "Downloads"
        / "greyctf26-challs"
        / "quals"
        / "forensics"
        / "APTV3R4_STRIKES_AGAIN",
    ]
    for candidate in candidates:
        if (candidate / "dist" / "artifact.pcap").is_file():
            return candidate
    return Path.cwd()


def read_pcap_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) < 24:
        raise ValueError(f"{path} is too small to be a pcap")
    return data


def extract_token(pcap_data: bytes) -> str:
    tokens = []
    tokens.extend(match.group(1) for match in TOKEN_RE.finditer(pcap_data))
    if not tokens:
        tokens.extend(ANY_TOKEN_RE.findall(pcap_data))

    unique = []
    for token in tokens:
        if token not in unique:
            unique.append(token)

    if not unique:
        raise ValueError("could not find a 67 character vault token in the pcap")
    if len(unique) > 1:
        print(f"[!] multiple token-like strings found; using {unique[0].decode()}")
    return unique[0].decode("ascii")


def extract_base_url(pcap_data: bytes, token: str) -> str | None:
    token_b = token.encode("ascii")
    http_re = re.compile(
        rb"(?:GET|POST)\s+(/api/vault[^\s]*)\s+HTTP/1\.[01]\r\n"
        rb"(?:(?!\r\n\r\n).)*?Host:\s*([^\r\n]+)",
        re.DOTALL | re.IGNORECASE,
    )
    for match in http_re.finditer(pcap_data):
        if token_b in match.group(1):
            host = match.group(2).decode("ascii", "replace")
            return "http://" + host
    return None


def download_zip_url(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "aptv3r4-solver/1.0"})
    temp_path = out_path.with_suffix(out_path.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=30) as response, temp_path.open("wb") as fh:
            first_chunk = True
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                if first_chunk:
                    first_chunk = False
                    if not chunk.startswith(b"PK"):
                        preview = chunk[:80].decode("utf-8", "replace").replace("\n", "\\n")
                        raise ValueError(f"response was not a zip archive: {preview!r}")
                fh.write(chunk)
        temp_path.replace(out_path)
        if not zipfile.is_zipfile(out_path):
            out_path.unlink(missing_ok=True)
            raise ValueError("downloaded file is not a valid zip archive")
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return out_path


def download_memdump(base_url: str, token: str, out_path: Path) -> Path:
    query = urllib.parse.urlencode({"download": "mem_dump.dmp", "token": token})
    root_url = base_url.rstrip("/") + "/?" + query
    api_url = base_url.rstrip("/") + "/api/vault?" + query
    errors = []

    for label, url in (("website", root_url), ("frontend redirect target", api_url)):
        print(f"[*] downloading memdump archive from {url}")
        try:
            return download_zip_url(url, out_path)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            print(f"[!] {label} download failed: {exc}")

    raise ValueError("; ".join(errors))


def choose_memdump_source(args: argparse.Namespace, challenge_dir: Path, token: str, base_url: str | None) -> tuple[str, Path]:
    if args.memdump:
        return "raw", args.memdump
    if args.memdump_zip:
        return "zip", args.memdump_zip

    local_zip = challenge_dir / "backend" / "vault_files" / "mem_dump.zip"
    local_raw = challenge_dir / "backend" / "vault_files" / "mem_dump.dmp"
    download_error: Exception | None = None
    if base_url:
        try:
            return "zip", download_memdump(base_url, token, args.outdir / "mem_dump.zip")
        except Exception as exc:
            download_error = exc
            print(f"[!] remote download failed: {exc}")
            if args.force_download:
                raise

    if local_zip.is_file() and not args.force_download:
        print(f"[*] falling back to local memdump archive: {local_zip}")
        return "zip", local_zip
    if local_raw.is_file() and not args.force_download:
        print(f"[*] falling back to local memdump: {local_raw}")
        return "raw", local_raw

    if not base_url:
        raise ValueError("no base URL found in pcap; pass --base-url or --memdump-zip")
    if download_error:
        raise ValueError("remote download failed and no local memdump fallback exists") from download_error
    raise ValueError("no local memdump fallback exists")


def scan_stream_for_flag_enc(stream, out_path: Path) -> bytes:
    begin = b"BEGIN_REAL_ARTIFACT_flag.enc"
    end = b"END_REAL_ARTIFACT"
    keep = 2 * 1024 * 1024
    tail = b""
    collecting = False
    collected = bytearray()
    candidates: set[bytes] = set()

    while True:
        chunk = stream.read(8 * 1024 * 1024)
        if not chunk:
            break

        if collecting:
            end_at = chunk.find(end)
            if end_at >= 0:
                collected.extend(chunk[:end_at])
                artifact = normalize_openssl_blob(bytes(collected))
                out_path.write_bytes(artifact)
                return artifact
            collected.extend(chunk)
            if len(collected) > 2 * 1024 * 1024:
                raise ValueError("flag.enc marker started but did not end within 2 MiB")
            continue

        data = tail + chunk
        search_from = 0
        while True:
            start = data.find(begin, search_from)
            if start < 0:
                break
            after = data[start + len(begin) :]
            end_at = after.find(end)
            if end_at >= 0:
                segment = after[:end_at]
                salted_at = segment.find(b"Salted__")
                if salted_at >= 0:
                    artifact = normalize_openssl_blob(segment[salted_at:])
                    out_path.write_bytes(artifact)
                    return artifact
                search_from = start + 1
                continue

            salted_at = after.find(b"Salted__")
            if salted_at >= 0:
                collected.extend(after[salted_at:])
                collecting = True
                tail = b""
            break

        pos = 0
        while True:
            hit = data.find(b"Salted__", pos)
            if hit < 0:
                break
            if hit + 64 <= len(data):
                candidates.add(data[hit : hit + 64])
            pos = hit + 1

        tail = data[-keep:]

    if candidates:
        artifact = next(iter(candidates))
        out_path.write_bytes(artifact)
        print("[!] real-artifact marker not found; wrote one OpenSSL Salted__ candidate")
        return artifact
    raise ValueError("could not carve flag.enc from the memory dump")


def normalize_openssl_blob(blob: bytes) -> bytes:
    while len(blob) >= 32 and (len(blob) - 16) % 16 and blob[-1:] in b"\r\n\t \x00":
        blob = blob[:-1]
    return blob


def carve_flag_enc(source_kind: str, source_path: Path, out_path: Path) -> bytes:
    print(f"[*] carving flag.enc from {source_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if source_kind == "raw":
        with source_path.open("rb") as stream:
            return scan_stream_for_flag_enc(stream, out_path)

    with zipfile.ZipFile(source_path) as zf:
        members = [info for info in zf.infolist() if not info.is_dir()]
        dmp_members = [info for info in members if info.filename.lower().endswith(".dmp")]
        target = dmp_members[0] if dmp_members else members[0]
        with zf.open(target) as stream:
            return scan_stream_for_flag_enc(stream, out_path)


def iter_pcap_tcp_payloads(path: Path) -> dict[tuple[str, int, str, int], list[TcpSegment]]:
    flows: dict[tuple[str, int, str, int], list[TcpSegment]] = {}
    with path.open("rb") as fh:
        global_header = fh.read(24)
        if len(global_header) != 24:
            raise ValueError("truncated pcap global header")
        magic = global_header[:4]
        if magic in (b"\xd4\xc3\xb2\xa1", b"M<\xb2\xa1"):
            endian = "<"
        elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2<M"):
            endian = ">"
        else:
            raise ValueError("unsupported pcap magic")

        while True:
            packet_header = fh.read(16)
            if not packet_header:
                break
            if len(packet_header) != 16:
                raise ValueError("truncated pcap packet header")
            _ts_sec, _ts_frac, incl_len, _orig_len = struct.unpack(endian + "IIII", packet_header)
            packet = fh.read(incl_len)
            if len(packet) != incl_len or len(packet) < 14:
                continue
            if packet[12:14] != b"\x08\x00":
                continue

            ip = packet[14:]
            if len(ip) < 20:
                continue
            version = ip[0] >> 4
            ihl = (ip[0] & 0x0F) * 4
            if version != 4 or len(ip) < ihl + 20 or ip[9] != 6:
                continue

            src_ip = ".".join(str(b) for b in ip[12:16])
            dst_ip = ".".join(str(b) for b in ip[16:20])
            tcp = ip[ihl:]
            if len(tcp) < 20:
                continue
            src_port, dst_port, seq, _ack, off_flags = struct.unpack("!HHIIH", tcp[:14])
            tcp_header_len = ((off_flags >> 12) & 0x0F) * 4
            payload = tcp[tcp_header_len:]
            if not payload or (src_port != 445 and dst_port != 445):
                continue

            # Linux TCP keepalive/probe captures can appear as tiny all-zero payloads.
            if len(payload) <= 6 and set(payload) == {0}:
                continue

            flow = (src_ip, src_port, dst_ip, dst_port)
            flows.setdefault(flow, []).append(TcpSegment(seq, payload))
    return flows


def reassemble_tcp(segments: list[TcpSegment]) -> bytes:
    out = bytearray()
    cur_seq: int | None = None
    for segment in sorted(segments, key=lambda seg: (seg.seq, -len(seg.payload))):
        seq = segment.seq
        payload = segment.payload
        if cur_seq is None:
            cur_seq = seq
        if seq + len(payload) <= cur_seq:
            continue
        if seq < cur_seq:
            payload = payload[cur_seq - seq :]
            seq = cur_seq
        if seq > cur_seq:
            out.extend(b"\x00" * (seq - cur_seq))
            cur_seq = seq
        out.extend(payload)
        cur_seq += len(payload)
    return bytes(out)


def parse_smb_messages(pcap_path: Path) -> list[SmbMessage]:
    messages = []
    for flow, segments in iter_pcap_tcp_payloads(pcap_path).items():
        stream = reassemble_tcp(segments)
        offset = 0
        index = 0
        while offset + 4 <= len(stream):
            if stream[offset] != 0:
                break
            length = int.from_bytes(stream[offset + 1 : offset + 4], "big")
            if length <= 0 or offset + 4 + length > len(stream):
                break
            raw = stream[offset + 4 : offset + 4 + length]
            messages.append(SmbMessage(flow, index, raw))
            index += 1
            offset += 4 + length
    return messages


def parse_smb2_header(raw: bytes) -> Smb2Header:
    if len(raw) < 64 or raw[:4] != b"\xfeSMB":
        raise ValueError("not an SMB2 packet")
    return Smb2Header(
        command=struct.unpack_from("<H", raw, 12)[0],
        status=struct.unpack_from("<L", raw, 8)[0],
        flags=struct.unpack_from("<L", raw, 16)[0],
        message_id=struct.unpack_from("<Q", raw, 24)[0],
        tree_id=struct.unpack_from("<L", raw, 36)[0],
        session_id=struct.unpack_from("<Q", raw, 40)[0],
    )


def parse_transform_header(raw: bytes) -> TransformHeader:
    if len(raw) < 52 or raw[:4] != b"\xfdSMB":
        raise ValueError("not an SMB3 transform packet")
    return TransformHeader(
        signature=raw[4:20],
        nonce=raw[20:36],
        original_size=struct.unpack_from("<L", raw, 36)[0],
        algorithm=struct.unpack_from("<H", raw, 42)[0],
        session_id=struct.unpack_from("<Q", raw, 44)[0],
    )


def ntlm_token(raw: bytes) -> bytes | None:
    pos = raw.find(b"NTLMSSP\x00")
    if pos < 0:
        return None
    return raw[pos:]


def security_buffer(data: bytes, offset: int) -> bytes:
    length, _max_length, buffer_offset = struct.unpack_from("<HHI", data, offset)
    return data[buffer_offset : buffer_offset + length]


def parse_ntlm_type2(data: bytes) -> tuple[int, bytes]:
    if data[:8] != b"NTLMSSP\x00" or struct.unpack_from("<L", data, 8)[0] != 2:
        raise ValueError("not an NTLM type 2 challenge")
    flags = struct.unpack_from("<L", data, 20)[0]
    challenge = data[24:32]
    return flags, challenge


def parse_ntlm_type3(data: bytes) -> dict[str, bytes | str | int]:
    if data[:8] != b"NTLMSSP\x00" or struct.unpack_from("<L", data, 8)[0] != 3:
        raise ValueError("not an NTLM type 3 authenticate message")
    flags = struct.unpack_from("<L", data, 60)[0]
    encoding = "utf-16le" if flags & NTLMSSP_NEGOTIATE_UNICODE else "cp437"
    return {
        "flags": flags,
        "lm": security_buffer(data, 12),
        "nt": security_buffer(data, 20),
        "domain": security_buffer(data, 28).decode(encoding, "replace"),
        "user": security_buffer(data, 36).decode(encoding, "replace"),
        "host": security_buffer(data, 44).decode(encoding, "replace"),
        "session_key": security_buffer(data, 52),
    }


def nt_hash(password: str) -> bytes:
    digest = MD4.new()
    digest.update(password.encode("utf-16le"))
    return digest.digest()


def ntowfv2(user: str, password: str, domain: str) -> bytes:
    return hmac.new(
        nt_hash(password),
        user.upper().encode("utf-16le") + domain.encode("utf-16le"),
        hashlib.md5,
    ).digest()


def kdf_counter_mode(key: bytes, label: bytes, context: bytes, bits: int = 128) -> bytes:
    result = b""
    blocks = max(1, (bits + 255) // 256)
    for counter in range(1, blocks + 1):
        data = struct.pack(">L", counter) + label + b"\x00" + context + struct.pack(">L", bits)
        result += hmac.new(key, data, hashlib.sha256).digest()
    return result[: bits // 8]


def derive_smb_keys(
    messages: list[SmbMessage],
    password: str,
) -> tuple[bytes, bytes, tuple[str, int, str, int], tuple[str, int, str, int]]:
    items: dict[str, bytes] = {}
    client_flow = None
    server_flow = None

    for message in messages:
        if message.raw[:4] != b"\xfeSMB":
            continue
        header = parse_smb2_header(message.raw)
        if header.command == SMB2_NEGOTIATE and header.message_id == 1:
            items["neg_resp" if header.from_server else "neg_req"] = message.raw
        elif header.command == SMB2_SESSION_SETUP:
            token = ntlm_token(message.raw)
            if token:
                token_type = struct.unpack_from("<L", token, 8)[0]
                if token_type in (1, 2, 3):
                    items[f"ss{token_type}"] = message.raw
                    items[f"type{token_type}"] = token
                    if token_type == 1:
                        client_flow = message.flow
                    elif token_type == 2:
                        server_flow = message.flow

    needed = ["neg_req", "neg_resp", "ss1", "ss2", "ss3", "type2", "type3"]
    missing = [name for name in needed if name not in items]
    if missing:
        raise ValueError(f"missing SMB/NTLM metadata in pcap: {', '.join(missing)}")
    if client_flow is None or server_flow is None:
        raise ValueError("could not identify SMB client/server flows")

    preauth = b"\x00" * 64
    for name in ("neg_req", "neg_resp", "ss1", "ss2", "ss3"):
        preauth = hashlib.sha512(preauth + items[name]).digest()

    _type2_flags, server_challenge = parse_ntlm_type2(items["type2"])
    type3 = parse_ntlm_type3(items["type3"])
    nt_response = type3["nt"]
    if not isinstance(nt_response, bytes):
        raise TypeError("unexpected NTLM response type")
    response_key_nt = ntowfv2(str(type3["user"]), password, str(type3["domain"]))
    nt_proof = nt_response[:16]
    expected_proof = hmac.new(response_key_nt, server_challenge + nt_response[16:], hashlib.md5).digest()
    if expected_proof != nt_proof:
        raise ValueError("SMB password did not validate against the captured NTLMv2 response")

    session_base_key = hmac.new(response_key_nt, nt_proof, hashlib.md5).digest()
    encrypted_session_key = type3["session_key"]
    if not isinstance(encrypted_session_key, bytes):
        raise TypeError("unexpected encrypted session key type")
    exported_session_key = (
        ARC4.new(session_base_key).decrypt(encrypted_session_key)
        if encrypted_session_key
        else session_base_key
    )

    c2s_key = kdf_counter_mode(exported_session_key, b"SMBC2SCipherKey\x00", preauth)
    s2c_key = kdf_counter_mode(exported_session_key, b"SMBS2CCipherKey\x00", preauth)
    print(
        f"[*] SMB auth: {type3['domain']}\\{type3['user']} from {type3['host']}; "
        f"session {exported_session_key.hex()}"
    )
    return c2s_key, s2c_key, client_flow, server_flow


def decrypt_transform(raw: bytes, key: bytes) -> tuple[bytes, str]:
    header = parse_transform_header(raw)
    ciphertext = raw[52:]
    aad = header.aad

    # The challenge capture authenticates as AES-GCM/12-byte nonce even though
    # the transform algorithm field says 0x0001. Try the advertised CCM first,
    # then the observed GCM form.
    attempts = [("AES-CCM", AES.MODE_CCM, 11), ("AES-GCM", AES.MODE_GCM, 12)]
    if header.algorithm == 2:
        attempts.reverse()

    for name, mode, nonce_len in attempts:
        cipher = AES.new(key, mode, nonce=header.nonce[:nonce_len])
        cipher.update(aad)
        try:
            plaintext = cipher.decrypt_and_verify(ciphertext, header.signature)
            if len(plaintext) == header.original_size and plaintext.startswith(b"\xfeSMB"):
                return plaintext, name
        except ValueError:
            continue
    raise ValueError("could not decrypt SMB3 transform packet")


def parse_read_response_buffer(plaintext: bytes) -> bytes | None:
    header = parse_smb2_header(plaintext)
    if header.command != SMB2_READ or not header.from_server or header.status != 0:
        return None
    if len(plaintext) < 80:
        return None
    data_offset = plaintext[66]
    data_length = struct.unpack_from("<L", plaintext, 68)[0]
    if data_offset == 0 or data_offset + data_length > len(plaintext):
        return None
    return plaintext[data_offset : data_offset + data_length]


def extract_keyfile_from_smb(pcap_path: Path, password: str, out_path: Path) -> bytes:
    print(f"[*] decrypting SMB3 traffic from {pcap_path}")
    messages = parse_smb_messages(pcap_path)
    c2s_key, s2c_key, client_flow, server_flow = derive_smb_keys(messages, password)
    recovered = []

    for message in messages:
        if message.raw[:4] != b"\xfdSMB":
            continue
        if message.flow == client_flow:
            key = c2s_key
        elif message.flow == server_flow:
            key = s2c_key
        else:
            continue
        plaintext, _mode = decrypt_transform(message.raw, key)
        read_buffer = parse_read_response_buffer(plaintext)
        if read_buffer:
            recovered.append(read_buffer)

    for chunk in recovered:
        match = HEX_KEY_RE.search(chunk)
        if match:
            keyfile = match.group(0) + b"\n"
            out_path.write_bytes(keyfile)
            return keyfile

    joined = b"".join(recovered)
    match = HEX_KEY_RE.search(joined)
    if match:
        keyfile = match.group(0) + b"\n"
        out_path.write_bytes(keyfile)
        return keyfile
    raise ValueError("could not recover keyfile contents from decrypted SMB READ responses")


def decrypt_openssl_enc(flag_enc: bytes, passphrase: bytes) -> bytes:
    if not flag_enc.startswith(b"Salted__") or len(flag_enc) < 32:
        raise ValueError("flag.enc is not an OpenSSL salted enc file")
    salt = flag_enc[8:16]
    ciphertext = flag_enc[16:]
    key_iv = PBKDF2(passphrase.rstrip(b"\r\n"), salt, dkLen=48, count=10000, hmac_hash_module=SHA256)
    plaintext = AES.new(key_iv[:32], AES.MODE_CBC, key_iv[32:]).decrypt(ciphertext)
    pad = plaintext[-1]
    if pad < 1 or pad > 16 or plaintext[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad padding while decrypting flag.enc")
    return plaintext[:-pad]


def solve(args: argparse.Namespace) -> str:
    challenge_dir = args.challenge_dir
    pcap_path = args.pcap or challenge_dir / "dist" / "artifact.pcap"
    if not pcap_path.is_file():
        raise FileNotFoundError(f"missing pcap: {pcap_path}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    pcap_data = read_pcap_bytes(pcap_path)
    token = extract_token(pcap_data)
    base_url = args.base_url or extract_base_url(pcap_data, token)
    print(f"[*] vault token: {token}")
    if base_url:
        print(f"[*] vault URL: {base_url}")

    source_kind, source_path = choose_memdump_source(args, challenge_dir, token, base_url)
    flag_enc_path = args.outdir / "flag.enc"
    flag_enc = carve_flag_enc(source_kind, source_path, flag_enc_path)
    print(f"[*] carved {len(flag_enc)} bytes to {flag_enc_path}")

    keyfile_path = args.outdir / "keyfile.txt"
    keyfile = extract_keyfile_from_smb(pcap_path, args.smb_password, keyfile_path)
    print(f"[*] recovered keyfile to {keyfile_path}: {keyfile.decode().strip()}")

    plaintext = decrypt_openssl_enc(flag_enc, keyfile)
    decrypted_path = args.outdir / "decrypted_flag.txt"
    decrypted_path.write_bytes(plaintext)
    flag_match = FLAG_RE.search(plaintext)
    flag = flag_match.group(0).decode("ascii") if flag_match else plaintext.decode("utf-8", "replace").strip()
    print(f"[*] decrypted flag written to {decrypted_path}")
    return flag


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solve GreyCTF APTV3R4_STRIKES_AGAIN.")
    parser.add_argument(
        "--challenge-dir",
        type=Path,
        default=default_challenge_dir(),
        help="challenge root containing dist/artifact.pcap",
    )
    parser.add_argument("--pcap", type=Path, help="pcap path; defaults to CHALLENGE_DIR/dist/artifact.pcap")
    parser.add_argument("--base-url", help="vault base URL; defaults to Host observed in the pcap")
    parser.add_argument("--memdump", type=Path, help="local raw mem_dump.dmp")
    parser.add_argument("--memdump-zip", type=Path, help="local mem_dump.zip")
    parser.add_argument("--force-download", action="store_true", help="download even if a local mem_dump.zip exists")
    parser.add_argument("--smb-password", default="mypassword", help="SMB password from the challenge prompt")
    parser.add_argument("--outdir", type=Path, default=Path("solve_out"), help="directory for recovered artifacts")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        flag = solve(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(flag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
