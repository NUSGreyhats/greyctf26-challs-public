#!/usr/local/bin/python

import os
import queue
import select
import socket
import socketserver
import textwrap
import threading
import time

import server as challenge


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "5000"))
MAX_CLIENTS = int(os.environ.get("MAX_CLIENTS", "512"))
LISTEN_BACKLOG = int(os.environ.get("LISTEN_BACKLOG", str(MAX_CLIENTS)))
JOB_QUEUE_SIZE = int(os.environ.get("JOB_QUEUE_SIZE", "256"))
WORKERS = int(os.environ.get("MAX_TROUPE_EXECUTIONS", "3"))
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "35"))
QUEUE_RESULT_TIMEOUT = int(os.environ.get("QUEUE_RESULT_TIMEOUT", "75"))
QUEUE_POLL_INTERVAL = float(os.environ.get("QUEUE_POLL_INTERVAL", "0.5"))

BUSY_MESSAGE = (
    b"[BUSY] Terminal connection limit reached. Please retry in a few seconds.\n"
)
QUEUE_FULL_MESSAGE = (
    b"[BUSY] Transmission queue is full. The terminal is under heavy load; "
    b"please retry in a few seconds.\n"
)


class Job:
    def __init__(self, program):
        self.program = program
        self.cancelled = threading.Event()
        self.result = queue.Queue(maxsize=1)
        self.created_at = time.monotonic()


client_slots = threading.BoundedSemaphore(MAX_CLIENTS)
job_queue = queue.Queue(maxsize=JOB_QUEUE_SIZE)


def encode(text):
    return text.encode("utf-8", errors="replace")


def send_text(sock, text):
    sock.sendall(encode(text))


def read_line(rfile):
    line = rfile.readline(challenge.MAX_CODE_LENGTH + 1024)
    if not line:
        return None
    return line.decode("utf-8", errors="replace").rstrip("\r\n")


def read_player_code(rfile):
    lines = []
    total_len = 0

    while True:
        line = read_line(rfile)
        if line is None:
            break
        if line.strip() == "EOF":
            break
        lines.append(line)
        total_len += len(line) + 1
        if total_len > challenge.MAX_CODE_LENGTH:
            break

    return "\n".join(lines)


def boxed_message(title, message):
    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  {title:<58.58s}  ║",
        "╠══════════════════════════════════════════════════════════════╣",
    ]
    for line in textwrap.wrap(message, width=58) or [""]:
        lines.append(f"║  {line:<58s}  ║")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines) + "\n"


def boxed_system_message(message):
    return boxed_message("[SYSTEM]", message)


def transmission_prompt():
    return """
╔══════════════════════════════════════════════════════════════╗
║  TRANSMISSION DECODING TERMINAL                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  This terminal provides a scripting interface for            ║
║  analyzing intercepted transmissions.                        ║
║                                                              ║
║  The compartmentalization protocol prevents classified       ║
║  data from being output to uncleared channels.               ║
║                                                              ║
║  Submit your analysis program below.                         ║
║  Terminate with 'EOF' on a new line.                         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
>> """


def queue_status(position):
    wave = max(0, (position - 1) // max(1, WORKERS))
    estimated_wait = wave * challenge.TIMEOUT
    return boxed_message(
        "[QUEUED]",
        (
            f"Submission accepted. Queue position: {position}. "
            f"Estimated wait: about {estimated_wait}-{estimated_wait + challenge.TIMEOUT} seconds. "
            "Keep this connection open; reconnecting sends a new submission to the back of the queue."
        ),
    )


def client_disconnected(sock):
    try:
        readable, _, _ = select.select([sock], [], [], 0)
        if not readable:
            return False
        return sock.recv(1, socket.MSG_PEEK) == b""
    except (BlockingIOError, InterruptedError):
        return False
    except (ConnectionResetError, OSError):
        return True


def wait_for_job_result(sock, job):
    deadline = time.monotonic() + QUEUE_RESULT_TIMEOUT

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            job.cancelled.set()
            return boxed_message(
                "[QUEUE TIMEOUT]",
                (
                    "Your submission waited too long before execution. "
                    "It may not have started running. Please retry shortly."
                ),
            )

        if client_disconnected(sock):
            job.cancelled.set()
            return None

        try:
            return job.result.get(timeout=min(QUEUE_POLL_INTERVAL, remaining))
        except queue.Empty:
            pass


def run_job(job):
    if job.cancelled.is_set():
        return

    stdout, stderr, returncode = challenge.run_troupe(job.program)
    output = challenge.format_output_text(stdout, stderr, returncode)
    output += "\n[SYSTEM] Transmission channel closed. Reconnect to submit another program.\n"

    try:
        job.result.put_nowait(output)
    except queue.Full:
        pass


def worker():
    while True:
        job = job_queue.get()
        try:
            run_job(job)
        finally:
            job_queue.task_done()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if not client_slots.acquire(blocking=False):
            self.request.sendall(BUSY_MESSAGE)
            return

        try:
            self.request.settimeout(SESSION_TIMEOUT)
            rfile = self.request.makefile("rb", buffering=0)

            send_text(self.request, challenge.BANNER)
            send_text(self.request, challenge.MAIN_MENU)

            choice = read_line(rfile)
            if choice != "4":
                send_text(
                    self.request,
                    boxed_system_message(
                        "Only Transmission is available on this remote terminal."
                    ),
                )
                return

            send_text(self.request, transmission_prompt())
            player_code = read_player_code(rfile)

            error = challenge.validate_player_code_error(player_code)
            if error is not None:
                send_text(self.request, boxed_system_message(error))
                return

            program = challenge.build_program(player_code)
            if program is None:
                send_text(self.request, boxed_system_message("Terminal program malformed."))
                return

            job = Job(program)
            position = job_queue.qsize() + 1
            try:
                job_queue.put_nowait(job)
            except queue.Full:
                self.request.sendall(QUEUE_FULL_MESSAGE)
                return

            send_text(self.request, queue_status(position))
            result = wait_for_job_result(self.request, job)
            if result is None:
                return

            send_text(self.request, result)

        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        finally:
            client_slots.release()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = LISTEN_BACKLOG


def main():
    for _ in range(WORKERS):
        threading.Thread(target=worker, daemon=True).start()

    with Server((HOST, PORT), Handler) as tcp_server:
        tcp_server.serve_forever()


if __name__ == "__main__":
    main()
