import time

import hardware.fpga
import busio
import board


BITSTREAM = "/challs/watchdog/watchdog_koth_smoke.bit"
PAYLOAD = "/challs/watchdog/payload.wdog"
UART_READ_SIZE = 256
UART_RX_BUFFER_SIZE = 4096
UART_POLL_DELAY = 0.002

_uart_pending = bytearray()


def _print_uart_line(data):
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        print("[UART]: %r" % data)
        return

    if text.endswith("\r"):
        text = text[:-1]
    print("[UART]: " + text)


def print_uart(data, flush_partial=False):
    global _uart_pending

    if data:
        _uart_pending.extend(data)

    while True:
        newline = _uart_pending.find(b"\n")
        if newline < 0:
            break

        line = bytes(_uart_pending[:newline])
        _uart_pending = _uart_pending[newline + 1:]
        _print_uart_line(line)

    if flush_partial and _uart_pending:
        line = bytes(_uart_pending)
        _uart_pending = bytearray()
        _print_uart_line(line)


def read_until(uart, needle, timeout):
    deadline = time.monotonic() + timeout
    window = bytearray()
    while time.monotonic() < deadline:
        chunk = uart.read(UART_READ_SIZE)
        if chunk:
            window.extend(chunk)
            print_uart(chunk)
            if needle in window:
                print_uart(b"", flush_partial=True)
                return bytes(window)
        time.sleep(UART_POLL_DELAY)
    print_uart(b"", flush_partial=True)
    return bytes(window)

def read_until_newline(uart, timeout):
    deadline = time.monotonic() + timeout
    window = bytearray()

    while time.monotonic() < deadline:
        chunk = uart.read(UART_READ_SIZE)
        if chunk:
            window.extend(chunk)
            print_uart(chunk)

            if b"\n" in window:
                idx = window.index(b"\n") + 1
                return bytes(window[:idx])

        time.sleep(UART_POLL_DELAY)

    print_uart(b"", flush_partial=True)
    return bytes(window)

def read_for(uart, timeout):
    deadline = time.monotonic() + timeout
    data = bytearray()
    while time.monotonic() < deadline:
        chunk = uart.read(UART_READ_SIZE)
        if chunk:
            data.extend(chunk)
            print_uart(chunk)
        time.sleep(UART_POLL_DELAY)
    print_uart(b"", flush_partial=True)
    return bytes(data)


def print_forever(uart):
    print("WDOG_UPLOAD: UART_PRINT_FOREVER")

    while True:
        chunk = uart.read(UART_READ_SIZE)
        if chunk:
            print_uart(chunk)

        time.sleep(UART_POLL_DELAY)

def main():
    print("WDOG_UPLOAD: uploading", BITSTREAM)
    hardware.fpga.upload_bitstream(BITSTREAM)
    uart = busio.UART(
        board.GP8,
        board.GP9,
        baudrate=9600,
        timeout=0.1,
        receiver_buffer_size=UART_RX_BUFFER_SIZE,
    )
    try:
        boot_log = read_for(uart, 2.0)
        print("WDOG_UPLOAD: boot_log=%r" % boot_log)

        with open(PAYLOAD, "rb") as payload_file:
            payload = payload_file.read()
        print("WDOG_UPLOAD: sending_payload=%d bytes" % len(payload))
        for byte_value in payload:
            uart.write(bytes((byte_value,)))
            time.sleep(0.003)

        upload_log = read_until(uart, b"RUNNING\n", 10.0)
        print("WDOG_UPLOAD: upload_log=%r" % upload_log)
        if b"LOADED\n" not in upload_log or b"RUNNING\n" not in upload_log:
            raise AssertionError("payload upload did not reach LOADED/RUNNING")

        print("WDOG_UPLOAD: UART_UPLOAD_OK")
        print_forever(uart)
    finally:
        uart.deinit()


main()

