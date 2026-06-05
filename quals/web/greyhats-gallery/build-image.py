#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVICE_DIR = ROOT / "service"
DIST_DIR = ROOT / "dist"
DIST_IMAGE = DIST_DIR / "greyhats_gallery_image.tar.gz"

BUILD_TAG = "greyhats_gallery:player-build"
SQUASHED_TAG = "greyhats_gallery:player-squashed"
PLAYER_TAG = "greyhats_gallery:latest"

DEFAULT_PLAYER_FLAG = "grey{fake_flag}"

IMAGE_CHANGES = [
    'ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'ENV NODE_VERSION=24.15.0',
    'ENV YARN_VERSION=1.22.22',
    'WORKDIR /app',
    'ENTRYPOINT ["/usr/local/bin/install-flag.sh"]',
    'CMD ["node","src/server.js"]',
    'EXPOSE 3000',
    'LABEL org.opencontainers.image.base.name=docker.io/library/node:lts-trixie-slim',
    'LABEL org.opencontainers.image.base.digest=sha256:c70f2d9b9dcd1f95d51b1f2d9c000637f203dbe2cbeaf06680780584518ca5c3',
    'LABEL org.opencontainers.image.base.revision=58635ae7aaeab55a5c036b59e8ca93d864119cbe',
]


def run(args, **kwargs):
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True, **kwargs)


def output(args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        return ""


def copy_service_context(destination, player_flag):
    shutil.copytree(
        SERVICE_DIR,
        destination,
        ignore=shutil.ignore_patterns("node_modules", "uploads", "storage", ".env"),
    )
    (destination / "flag.txt").write_text(player_flag.rstrip("\n") + "\n", encoding="utf-8")


def squash_image(source_tag, target_tag):
    container_id = output(["docker", "create", source_tag])
    if not container_id:
        raise RuntimeError(f"failed to create container from {source_tag}")

    try:
        export_proc = subprocess.Popen(
            ["docker", "export", container_id],
            stdout=subprocess.PIPE,
        )
        import_args = ["docker", "import", "--platform=linux/amd64"]
        for change in IMAGE_CHANGES:
            import_args.extend(["--change", change])
        import_args.extend(["-", target_tag])

        print("+ docker export", container_id, "|", " ".join(import_args), flush=True)
        import_proc = subprocess.Popen(import_args, stdin=export_proc.stdout)
        assert export_proc.stdout is not None
        export_proc.stdout.close()

        export_status = export_proc.wait()
        import_status = import_proc.wait()
        if export_status != 0 or import_status != 0:
            raise RuntimeError("failed to squash player image")
    finally:
        run(["docker", "rm", "-f", container_id], stdout=subprocess.DEVNULL)


def save_player_image(output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_proc = subprocess.Popen(["docker", "save", PLAYER_TAG], stdout=subprocess.PIPE)
    with output_path.open("wb") as fp:
        gzip_proc = subprocess.Popen(["gzip", "-n"], stdin=save_proc.stdout, stdout=fp)
        assert save_proc.stdout is not None
        save_proc.stdout.close()
        save_status = save_proc.wait()
        gzip_status = gzip_proc.wait()
    if save_status != 0 or gzip_status != 0:
        raise RuntimeError("failed to save player image")


def main():
    parser = argparse.ArgumentParser(
        description="Build the player dist image with a fake flag and stripped build history."
    )
    parser.add_argument(
        "--player-flag",
        default=os.environ.get("PLAYER_FLAG", DEFAULT_PLAYER_FLAG),
        help="fake flag embedded in the player image",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DIST_IMAGE,
        help="output docker-save tarball path",
    )
    args = parser.parse_args()

    previous_latest = output(["docker", "image", "inspect", PLAYER_TAG, "--format", "{{.Id}}"])

    with tempfile.TemporaryDirectory(prefix="greyhats-gallery-player-") as tmp:
        context = Path(tmp) / "service"
        copy_service_context(context, args.player_flag)
        run(["docker", "build", "--platform=linux/amd64", "-t", BUILD_TAG, str(context)])

    squash_image(BUILD_TAG, SQUASHED_TAG)
    run(["docker", "tag", SQUASHED_TAG, PLAYER_TAG])
    save_player_image(args.output)

    if previous_latest:
        run(["docker", "tag", previous_latest, PLAYER_TAG])

    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
