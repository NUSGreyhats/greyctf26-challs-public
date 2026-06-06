#!/usr/bin/env python3
import base64
import json
import os
import queue
import threading
import concurrent.futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from statistics import median
from urllib.parse import urlparse

import mediapipe as mp
import numpy as np
from PIL import Image, ImageOps


HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8790"))
MODEL_PATH = os.environ.get("HAND_LANDMARK_MODEL", "/models/hand_landmarker.task")
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(2 * 1024 * 1024)))


BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode


def create_detector():
    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionRunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=0.35,
        min_hand_presence_confidence=0.35,
        min_tracking_confidence=0.35,
    )
    return HandLandmarker.create_from_options(options)


POOL_SIZE = int(os.environ.get("DETECTOR_POOL_SIZE", "8"))
DETECTOR_POOL = queue.Queue(maxsize=POOL_SIZE)
for _ in range(POOL_SIZE):
    DETECTOR_POOL.put(create_detector())


def json_response(handler, status, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def decode_data_url(value):
    if not isinstance(value, str):
        raise ValueError("image must be a data URL string")
    marker = "base64,"
    if marker not in value:
        raise ValueError("image must be base64 encoded")
    encoded = value.split(marker, 1)[1]
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("image base64 is invalid") from exc


def read_rgb_image(data):
    with Image.open(BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        return np.asarray(image.convert("RGB"))


def landmark_to_dict(point):
    return {
        "x": float(point.x),
        "y": float(point.y),
        "z": float(point.z),
    }


def anchor_from_landmarks(landmarks):
    xs = [float(point.x) for point in landmarks]
    ys = [float(point.y) for point in landmarks]
    return {
        "x": median(xs),
        "y": median(ys),
    }


def extract_landmarks(image_data):
    rgb = read_rgb_image(image_data)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    detector = DETECTOR_POOL.get()
    try:
        result = detector.detect(mp_image)
    finally:
        DETECTOR_POOL.put(detector)

    hands = []
    by_side = [None, None]
    for landmarks in result.hand_landmarks:
        anchor = anchor_from_landmarks(landmarks)
        side = 0 if anchor["x"] >= 0.5 else 1
        by_side[side] = anchor
        hands.append({
            "anchor": anchor,
            "landmarks": [landmark_to_dict(point) for point in landmarks],
        })

    payload = {
        "handCount": len(result.hand_landmarks),
        "hands": hands,
    }
    left_anchor, right_anchor = by_side
    if left_anchor and right_anchor:
        payload["leftY"] = left_anchor["y"]
        payload["rightY"] = right_anchor["y"]
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "hand-landmarks/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def do_GET(self):
        if urlparse(self.path).path != "/healthz":
            json_response(self, 404, {"ok": False, "error": "not found"})
            return
        json_response(self, 200, {"ok": True})

    def do_POST(self):
        if urlparse(self.path).path != "/landmarks":
            json_response(self, 404, {"ok": False, "error": "not found"})
            return

        content_length = int(self.headers.get("content-length") or "0")
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            json_response(self, 413, {"ok": False, "error": "invalid body size"})
            return

        try:
            body = self.rfile.read(content_length)
            request = json.loads(body.decode("utf-8"))
            image_data = decode_data_url(request.get("image"))
            response = extract_landmarks(image_data)
            response["ok"] = True
            response["challengeId"] = request.get("challengeId")
            json_response(self, 200, response)
        except Exception as exc:
            print(f"Exception: {exc}", flush=True)
            json_response(self, 400, {"ok": False, "error": str(exc)})


class ThreadPoolHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True, max_workers=32):
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def process_request(self, request, client_address):
        self.executor.submit(self.process_request_thread, request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
            self.shutdown_request(request)
        except Exception:
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def server_close(self):
        super().server_close()
        self.executor.shutdown(wait=False)


def main():
    max_workers = int(os.environ.get("MAX_WORKERS", "128"))
    server = ThreadPoolHTTPServer((HOST, PORT), Handler, max_workers=max_workers)
    print(f"hand landmark service listening on {HOST}:{PORT} with max {max_workers} workers", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
