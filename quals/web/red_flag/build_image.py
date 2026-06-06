#!/usr/bin/env python3
"""Build Red Flag images and package the player-facing dist tarball.

The Dockerfile performs the challenge's two build-time hardening steps:

1. Go source uses utils.RevealString for compile-time string obfuscation.
2. add_anti_analysis.py injects overlapping STT_FUNC symbols into the
   stripped binary for function-discovery confusion.

This script keeps those build helpers out of the distributed image while
verifying that the final binary still contains evidence of the function
obfuscation pass.
"""

import argparse
import gzip
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time


HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE = os.path.join(HERE, "service")
DIST = os.path.join(HERE, "dist")
DIST_IMAGE = "red_flag:latest"
SERVICE_IMAGE = "red_flag:service"
TEST_CONTAINER = "red_flag_build_test"
TEST_PORT = "18080"
FAKE_FLAG = "grey{fake_flag}\n"
REAL_FLAG_MARKER = "grey{f0und_th3_r34l_fl4g_1n_th3_s34_0f_r3d_fl4g5_251f7d0d033afee8}"
SENSITIVE_DEFAULTS = (
    "crm_jwt_s3cr3t_k3y_2026",
    "CRM-ADMIN-2024-XKEY",
    "bfhgbvfbkx@gmail.com",
)


def run(cmd, **kw):
    print(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True, **kw)


def output(cmd, **kw):
    return subprocess.check_output(cmd, shell=True, text=True, **kw)


def copy_service_tree(dst):
    ignore = shutil.ignore_patterns(
        "data",
        "uploads",
        "__pycache__",
        "*.pyc",
    )
    shutil.copytree(SERVICE, dst, ignore=ignore)


def build_image(context, tag):
    run(f"docker build -t {tag} .", cwd=context)


def save_dist_image():
    os.makedirs(DIST, exist_ok=True)
    run(f"docker save {DIST_IMAGE} | gzip > {DIST}/red_flag_image.tar.gz")
    start_sh = os.path.join(DIST, "start.sh")
    if os.path.exists(start_sh):
        os.chmod(start_sh, 0o755)


def image_file_list(image):
    return output(
        "docker run --rm --entrypoint sh "
        f"{image} -c 'find / -xdev -type f 2>/dev/null | sort'"
    ).splitlines()


def copy_crm_from_image(image, dst):
    cid = output(f"docker create --entrypoint sh {image} -c true").strip()
    try:
        run(f"docker cp {cid}:/crm {dst}")
    finally:
        run(f"docker rm -f {cid} >/dev/null 2>&1 || true")


def verify_dist_image(check_bundle):
    files = image_file_list(DIST_IMAGE)
    forbidden_names = {"build_image.py", "add_anti_analysis.py"}
    present = sorted(
        path for path in files if os.path.basename(path) in forbidden_names
    )
    if present:
        raise SystemExit(
            "dist image contains build-only script(s): " + ", ".join(present)
        )

    with tempfile.TemporaryDirectory(prefix="red_flag_verify_") as tmp:
        crm = os.path.join(tmp, "crm")
        copy_crm_from_image(DIST_IMAGE, crm)
        symbols = output(f"readelf --wide -Ws {crm}")
        if re.search(r"\baa_(start|main|hidden|phantom)", symbols):
            raise SystemExit("dist image binary still contains aa_* symbols")
        injected = re.findall(
            r"\bFUNC\b\s+GLOBAL\s+DEFAULT\s+\d+\s+(_[0-9a-f]{20})\b",
            symbols,
        )
        if len(injected) < 4:
            raise SystemExit("dist image binary has no randomized injected FUNC symbols")

    for value in SENSITIVE_DEFAULTS:
        found = output(
            "docker run --rm --entrypoint sh "
            f"{DIST_IMAGE} -c \"grep -a -q '{value}' /crm && echo yes || true\""
        ).strip()
        if found:
            raise SystemExit(
                f"dist image binary contains unobfuscated default: {value}"
            )

    if not check_bundle:
        return

    with gzip.open(os.path.join(DIST, "red_flag_image.tar.gz"), "rb") as f:
        tar_data = f.read()
    if REAL_FLAG_MARKER.encode() in tar_data:
        raise SystemExit("dist image tarball contains the real flag")


def run_solve_test(image):
    run(f"docker rm -f {TEST_CONTAINER} >/dev/null 2>&1 || true")
    run(
        f"docker run --rm -d --name {TEST_CONTAINER} "
        f"-e FLAG='{FAKE_FLAG.strip()}' "
        f"-p 127.0.0.1:{TEST_PORT}:8080 {image} >/dev/null"
    )
    time.sleep(2)
    try:
        result = subprocess.run(
            [
                "python3",
                os.path.join(HERE, "solve", "solve.py"),
                f"http://127.0.0.1:{TEST_PORT}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if "FLAG: grey{" not in result.stdout:
            sys.exit("solve.py did not retrieve a flag")
    finally:
        run(f"docker rm -f {TEST_CONTAINER} >/dev/null 2>&1 || true")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--no-bundle",
        action="store_true",
        help="skip writing dist/red_flag_image.tar.gz",
    )
    ap.add_argument(
        "--service",
        action="store_true",
        help=f"also build the real-flag service image as {SERVICE_IMAGE}",
    )
    ap.add_argument(
        "--test",
        action="store_true",
        help="run solve.py against the built image",
    )
    args = ap.parse_args()

    os.chdir(HERE)

    with tempfile.TemporaryDirectory(prefix="red_flag_dist_") as tmp:
        context = os.path.join(tmp, "service")
        copy_service_tree(context)
        build_image(context, DIST_IMAGE)

    if not args.no_bundle:
        save_dist_image()
    verify_dist_image(check_bundle=not args.no_bundle)

    if args.service:
        build_image(SERVICE, SERVICE_IMAGE)

    if args.test:
        run_solve_test(SERVICE_IMAGE if args.service else DIST_IMAGE)

    print("\nPlayer bundle:", DIST)
    for name in sorted(os.listdir(DIST)):
        path = os.path.join(DIST, name)
        if os.path.isfile(path):
            print(f"  {name}  ({os.path.getsize(path):,} bytes)")
    print(
        "\nVerified: build scripts are absent from dist image; "
        "randomized injected FUNC symbols exist in /crm; "
        "sensitive defaults are not plaintext."
    )


if __name__ == "__main__":
    main()
