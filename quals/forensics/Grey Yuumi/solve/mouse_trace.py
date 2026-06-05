#!/usr/bin/env python3
import argparse
import csv
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def s8(value):
    return value - 256 if value >= 128 else value


def decode_report(report, layout):
    if layout == "auto":
        if len(report) >= 7 and report[1] == 0:
            layout = "int16"
        elif len(report) >= 4:
            layout = "int8"
        else:
            raise ValueError(f"short HID report: {report.hex()}")

    if layout == "int16":
        return {
            "button": report[0],
            "dx": struct.unpack("<h", report[2:4])[0],
            "dy": struct.unpack("<h", report[4:6])[0],
            "wheel": struct.unpack("<b", report[6:7])[0],
        }

    if layout == "int8":
        return {
            "button": report[0],
            "dx": s8(report[1]),
            "dy": s8(report[2]),
            "wheel": s8(report[3]),
        }

    raise ValueError(f"unknown layout: {layout}")


def tshark_reports(pcap):
    if not shutil.which("tshark"):
        raise SystemExit("tshark is required. Install Wireshark/tshark and try again.")

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
        "usb.device_address",
        "-e",
        "usb.endpoint_address",
        "-e",
        "usbhid.data",
    ]
    raw = subprocess.check_output(cmd, text=True)

    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not parts[4]:
            continue
        yield {
            "frame": int(parts[0]),
            "time": float(parts[1]),
            "device": parts[2],
            "endpoint": parts[3],
            "report": bytes.fromhex(parts[4].replace(":", "")),
        }


def parse_mouse(pcap, layout):
    x = y = 0
    rows = []

    for item in tshark_reports(pcap):
        try:
            decoded = decode_report(item["report"], layout)
        except (ValueError, struct.error):
            continue

        prev_x, prev_y = x, y
        x += decoded["dx"]
        y += decoded["dy"]
        rows.append(
            {
                **item,
                **decoded,
                "prev_x": prev_x,
                "prev_y": prev_y,
                "x": x,
                "y": y,
                "left": bool(decoded["button"] & 0x01),
                "right": bool(decoded["button"] & 0x02),
                "middle": bool(decoded["button"] & 0x04),
            }
        )

    return rows


def click_intervals(rows):
    intervals = []
    start = None
    previous = None

    for row in rows:
        if row["right"] and start is None:
            start = row
        if not row["right"] and start is not None:
            intervals.append((start, previous))
            start = None
        previous = row

    if start is not None:
        intervals.append((start, previous))

    return intervals


def render(rows, out_path, clicked_only=False):
    if not rows:
        raise SystemExit("No mouse HID reports found.")

    points = [(row["x"], row["y"]) for row in rows]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)

    pad = 40
    scale = min(1800 / max(1, max_x - min_x), 1200 / max(1, max_y - min_y), 6)
    scale = max(scale, 0.25)
    width = max(240, int((max_x - min_x) * scale + pad * 2))
    height = max(240, int((max_y - min_y) * scale + pad * 2))

    def tr(point):
        return (
            int((point[0] - min_x) * scale + pad),
            int((point[1] - min_y) * scale + pad),
        )

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    for row in rows:
        start = (row["prev_x"], row["prev_y"])
        end = (row["x"], row["y"])
        if not row["dx"] and not row["dy"]:
            continue
        if not clicked_only:
            draw.line([tr(start), tr(end)], fill=(225, 225, 225), width=1)
        if row["right"]:
            draw.line([tr(start), tr(end)], fill=(0, 0, 0), width=max(2, int(scale * 1.3)))

    for start, end in click_intervals(rows):
        sx, sy = tr((start["x"], start["y"]))
        ex, ey = tr((end["x"], end["y"]))
        draw.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], fill=(220, 40, 40))
        draw.ellipse([ex - 4, ey - 4, ex + 4, ey + 4], outline=(40, 120, 220), width=2)

    img.save(out_path)


def write_csv(rows, out_path):
    fields = [
        "frame",
        "time",
        "device",
        "endpoint",
        "button",
        "left",
        "right",
        "middle",
        "dx",
        "dy",
        "wheel",
        "prev_x",
        "prev_y",
        "x",
        "y",
        "report",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "report": row["report"].hex()})


def main():
    parser = argparse.ArgumentParser(description="Render right-click mouse traces from a USB HID pcapng.")
    parser.add_argument("pcap", type=Path, help="input .pcapng captured with Wireshark/USBPcap")
    parser.add_argument("-o", "--out", type=Path, default=Path("mouse_trace.png"), help="output PNG")
    parser.add_argument("--csv", type=Path, help="optional decoded CSV output")
    parser.add_argument(
        "--layout",
        choices=["auto", "int16", "int8"],
        default="auto",
        help="HID report layout: auto, int16 button,x16,y16,wheel, or int8 button,x8,y8,wheel",
    )
    parser.add_argument("--clicked-only", action="store_true", help="hide non-right-click movement in the PNG")
    parser.add_argument("--max-intervals", type=int, default=40, help="maximum right-click intervals to print")
    args = parser.parse_args()

    rows = parse_mouse(args.pcap, args.layout)
    intervals = click_intervals(rows)

    render(rows, args.out, clicked_only=args.clicked_only)
    if args.csv:
        write_csv(rows, args.csv)

    print(f"reports: {len(rows)}")
    if rows:
        print(f"time: {rows[0]['time']:.6f}s to {rows[-1]['time']:.6f}s")
        print(f"final relative position: ({rows[-1]['x']}, {rows[-1]['y']})")
    print(f"right-click intervals: {len(intervals)}")
    for i, (start, end) in enumerate(intervals[: args.max_intervals], 1):
        print(
            f"{i:02d}: {start['time']:.6f}s -> {end['time']:.6f}s "
            f"frames {start['frame']} -> {end['frame']} "
            f"xy ({start['x']},{start['y']}) -> ({end['x']},{end['y']})"
        )
    if len(intervals) > args.max_intervals:
        print(f"... skipped {len(intervals) - args.max_intervals} more intervals")
    print(f"wrote: {args.out}")
    if args.csv:
        print(f"wrote: {args.csv}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(e.output, file=sys.stderr)
        raise
