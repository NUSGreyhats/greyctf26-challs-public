#!/usr/bin/env python3
from __future__ import annotations

import shutil
import struct
import subprocess
import tarfile
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


DEATH_TIMERS = [
    "5:36",
    "7:02",
    "9:40",
    "12:40",
    "18:14",
    "21:21",
    "23:09",
    "24:17",
    "26:09",
]

GAME_DURATION = "26:23.925"
PRE_SECONDS = 20.0
POST_SECONDS = 20.0


def parse_timer(timer: str) -> float:
    minutes, seconds = timer.split(":", 1)
    return int(minutes) * 60 + float(seconds)


def mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes:02d}:{seconds - minutes * 60:05.2f}"


def signed8(value: int) -> int:
    return value - 256 if value >= 128 else value


def decode_report(report: bytes) -> tuple[int, int, int]:
    if len(report) >= 7 and report[1] == 0:
        button = report[0]
        dx = struct.unpack("<h", report[2:4])[0]
        dy = struct.unpack("<h", report[4:6])[0]
        return button, dx, dy
    if len(report) >= 4:
        return report[0], signed8(report[1]), signed8(report[2])
    raise ValueError("short HID report")


def extract_pcap(archive: Path) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    with tarfile.open(archive) as tar:
        tar.extractall(tmp.name, filter="data")
    return tmp


def parse_mouse(pcap: Path) -> list[dict]:
    if not shutil.which("tshark"):
        raise SystemExit("tshark is required to extract USB HID reports from the PCAPNG.")

    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-Y",
        "usbhid.data",
        "-T",
        "fields",
        "-e",
        "frame.number",
        "-e",
        "frame.time_relative",
        "-e",
        "usbhid.data",
    ]
    raw = subprocess.check_output(cmd, text=True)

    rows = []
    x = y = 0
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or not parts[2]:
            continue

        try:
            button, dx, dy = decode_report(bytes.fromhex(parts[2].replace(":", "")))
        except (ValueError, struct.error):
            continue

        prev_x, prev_y = x, y
        x += dx
        y += dy
        rows.append(
            {
                "frame": int(parts[0]),
                "time": float(parts[1]),
                "right": bool(button & 0x02),
                "dx": dx,
                "dy": dy,
                "prev_x": prev_x,
                "prev_y": prev_y,
                "x": x,
                "y": y,
            }
        )

    return rows


def render(rows: list[dict], start_s: float, end_s: float, out_png: Path) -> bool:
    clicked = [
        row
        for row in rows
        if start_s <= row["time"] <= end_s and row["right"] and (row["dx"] or row["dy"])
    ]
    if not clicked:
        return False

    points = [(row["prev_x"], row["prev_y"]) for row in clicked] + [(row["x"], row["y"]) for row in clicked]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)

    pad = 50
    scale = min(1800 / max(1, max_x - min_x), 900 / max(1, max_y - min_y), 10)
    scale = max(scale, 0.35)
    width = max(280, int((max_x - min_x) * scale + pad * 2))
    height = max(220, int((max_y - min_y) * scale + pad * 2))

    def tr(point: tuple[int, int]) -> tuple[int, int]:
        return (
            int((point[0] - min_x) * scale + pad),
            int((point[1] - min_y) * scale + pad),
        )

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    for row in clicked:
        draw.line(
            [tr((row["prev_x"], row["prev_y"])), tr((row["x"], row["y"]))],
            fill=(0, 0, 0),
            width=max(2, int(scale * 1.2)),
        )

    img.save(out_png)
    return True


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    archive = "grey_yuumi.tar.gz"
    tmp = extract_pcap(archive)
    pcap = Path(tmp.name) / "grey_yuumi.pcapng"

    mouse = parse_mouse(pcap)
    if not mouse:
        raise SystemExit("No USB HID mouse reports found.")

    pcap_duration = mouse[-1]["time"] - mouse[0]["time"]
    game_duration = parse_timer(GAME_DURATION)
    for idx, timer in enumerate(DEATH_TIMERS, 1):
        game_time = parse_timer(timer)
        pcap_time = mouse[0]["time"] + (game_time / game_duration) * pcap_duration
        start = max(mouse[0]["time"], pcap_time - PRE_SECONDS)
        end = min(mouse[-1]["time"], pcap_time + POST_SECONDS)
        out_png = Path(f"{idx:02d}_{timer.replace(':', 'm')}s.png")
        rendered = render(mouse, start, end, out_png)
        print(
            f"{idx:02d}: game {timer} -> pcap {mmss(pcap_time)} "
            f"window {start:.3f}..{end:.3f} rendered={rendered} file={out_png}"
        )


if __name__ == "__main__":
    main()
