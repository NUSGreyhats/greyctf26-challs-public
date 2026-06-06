#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Decrypt flag.enc using keyfile.txt.")
    parser.add_argument("-i", "--input", default="flag.enc", help="Encrypted flag file")
    parser.add_argument("-k", "--keyfile", default="keyfile.txt", help="OpenSSL passphrase file")
    parser.add_argument("-o", "--output", default="decrypted_flag.txt", help="Output plaintext file")
    args = parser.parse_args()

    if shutil.which("openssl") is None:
        print("error: openssl was not found in PATH", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    keyfile_path = Path(args.keyfile)
    output_path = Path(args.output)

    if not input_path.is_file():
        print(f"error: missing input file: {input_path}", file=sys.stderr)
        return 1
    if not keyfile_path.is_file():
        print(f"error: missing key file: {keyfile_path}", file=sys.stderr)
        return 1

    cmd = [
        "openssl",
        "enc",
        "-d",
        "-aes-256-cbc",
        "-pbkdf2",
        "-salt",
        "-in",
        str(input_path),
        "-out",
        str(output_path),
        "-pass",
        f"file:{keyfile_path}",
    ]

    subprocess.run(cmd, check=True)
    print(output_path.read_text(errors="replace").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
