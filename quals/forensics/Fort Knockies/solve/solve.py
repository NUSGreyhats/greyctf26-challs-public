#!/usr/bin/env python3
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


PASSWORD = "pycachePATH"
FLAG_ENC = Path(__file__).with_name("flag.enc")


def b64d(value: str) -> bytes:
    return base64.b64decode(value)


def decrypt_fkenc0(path: Path, password: str) -> bytes:
    blob = json.loads(path.read_text(encoding="utf-8"))
    if blob.get("version") != "FKENC0":
        raise ValueError("expected an FKENC0 encrypted file")

    key = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=32,
        salt=b64d(blob["salt_b64"]),
        iterations=int(blob["iterations"]),
    ).derive(password.encode("utf-8"))

    decryptor = Cipher(algorithms.AES(key), modes.CBC(b64d(blob["iv_b64"]))).decryptor()
    padded = decryptor.update(b64d(blob["ciphertext_b64"])) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def main() -> None:
    print(decrypt_fkenc0(FLAG_ENC, PASSWORD).decode("utf-8").strip())


if __name__ == "__main__":
    main()
