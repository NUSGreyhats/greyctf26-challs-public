import gc
import os
import struct
import time

import adafruit_pioasm
import board
import digitalio
import hardware.fpga
import rp2pio


ADDR_COUNT = 15
SAMPLES_PER_ADDR = 200
PIO_FREQ = 25_000_000
PIO_READ_TIMEOUT = 2.0

# PMOD J2 mapping from the badge docs:
# bit0=GP27, bit1=GP16 (not connected), bit2=GP23, bit3=GP25,
# bit4=GP26, bit5=GP22, bit6=GP28, bit7=GP24.
MISSING_MASK = 0x00
PRINTABLE = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_{}-!@#$%^&*()+[]=;:,.?/\\|"


PIO_SOURCE = """
.program fast_secure_memory_probe
loop:
pull block
set pins %d
nop [7]
set pins 31
in pins, 7
push block
jmp loop
"""


def setup_fpga():
    bitstream = "/tmp/main.bit" if "main.bit" in os.listdir("/tmp") else "/hardware/bitstreams/main.bit"
    if bitstream == "/tmp/main.bit" or "main.bit" in os.listdir("/hardware/bitstreams"):
        print("Uploading", bitstream)
        rst = hardware.fpga.upload_bitstream(bitstream)
        time.sleep(0.25)
        return rst
    else:
        print("No main.bit found; using current FPGA bitstream")
        return None


def open_output(pin, value):
    dio = digitalio.DigitalInOut(pin)
    dio.direction = digitalio.Direction.OUTPUT
    dio.value = value
    return dio


def open_input(pin):
    dio = digitalio.DigitalInOut(pin)
    dio.direction = digitalio.Direction.INPUT
    return dio


def deinit_all(items):
    for item in items:
        if item is not None:
            try:
                item.deinit()
            except Exception:
                pass


def make_state_machine(addr):
    program = adafruit_pioasm.assemble(PIO_SOURCE % (addr & 0x1F))
    return rp2pio.StateMachine(
        program,
        frequency=PIO_FREQ,
        init=adafruit_pioasm.assemble("set pindirs 31"),
        first_set_pin=board.GP8,
        set_pin_count=5,
        first_in_pin=board.GP22,
        in_pin_count=7,
        in_shift_right=True,
        auto_push=False,
        initial_set_pin_state=31,
        initial_set_pin_direction=0x1F,
    )


def sample_raw(addr, count):
    sm = make_state_machine(addr)
    try:
        sm.restart()
        tx = bytearray(count * 4)
        rx = bytearray(count * 4)
        sm.write_readinto(tx, rx, out_end=count * 4, in_end=count * 4)
        return [pio_word_to_raw(struct.unpack_from("<I", rx, i * 4)[0]) for i in range(count)]
    finally:
        sm.deinit()


ADDR_PINS = [board.GP8, board.GP9, board.GP10, board.GP11, board.GP12]
PMOD_PINS = [board.GP27, None, board.GP23, board.GP25, board.GP26, board.GP22, board.GP28, board.GP24]


def read_pmod_digital(inputs):
    raw = 0
    for bit, pin in enumerate(inputs):
        if pin is not None and pin.value:
            raw |= 1 << bit
    value = raw & 0x9F
    value |= ((raw >> 6) & 1) << 5
    value |= ((raw >> 5) & 1) << 6
    value |= ((raw >> 7) & 1) << 1
    value &= 0x7F
    return value


def run_digitalio_baseline():
    print("DIGITALIO_BASELINE_START")
    outputs = []
    inputs = []
    try:
        for pin in ADDR_PINS:
            outputs.append(open_output(pin, True))
        for pin in PMOD_PINS:
            inputs.append(None if pin is None else open_input(pin))

        for addr in (31, 0, 31):
            for bit, output in enumerate(outputs):
                output.value = bool(addr & (1 << bit))
            time.sleep(0.25)
            value = read_pmod_digital(inputs)
            known = value & ~MISSING_MASK
            print("digitalio addr", addr, "pmod=0x%02x" % value, "known=0x%02x" % known, "candidates=%s/%s" % (safe_chr(known), safe_chr(known | MISSING_MASK)))
    finally:
        deinit_all(inputs)
        deinit_all(outputs)
    print("DIGITALIO_BASELINE_DONE")


def pio_word_to_raw(word):
    return (word >> 25) & 0x7F


def raw_to_known_byte(raw):
    # raw bit positions for first_in_pin=GP22:
    # raw0=GP22, raw1=GP23, raw2=GP24, raw3=GP25,
    # raw4=GP26, raw5=GP27, raw6=GP28.
    value = 0
    value |= ((raw >> 5) & 1) << 0
    value |= ((raw >> 2) & 1) << 1
    value |= ((raw >> 1) & 1) << 2
    value |= ((raw >> 3) & 1) << 3
    value |= ((raw >> 4) & 1) << 4
    value |= ((raw >> 6) & 1) << 5
    value |= ((raw >> 0) & 1) << 6
    return value


def candidates_for_known(known):
    return (known & ~MISSING_MASK, (known & ~MISSING_MASK) | MISSING_MASK)


def score_candidate(c):
    ch = chr(c)
    if ch in "fun{}":
        return 5
    if ch in PRINTABLE:
        return 3
    if 32 <= c <= 126:
        return 1
    return -10


def best_from_hist(hist):
    if MISSING_MASK == 0:
        return max(hist.items(), key=lambda item: item[1])[0] if hist else ord("?")

    scored = []
    for known, hits in hist.items():
        for cand in candidates_for_known(known):
            scored.append((score_candidate(cand), hits, cand))
    scored.sort(reverse=True)
    return scored[0][2] if scored else ord("?")


def print_hist(addr, hist):
    rows = sorted(hist.items(), key=lambda item: item[1], reverse=True)[:8]
    parts = []
    for known, hits in rows:
        c0, c1 = candidates_for_known(known)
        parts.append("%s/%s:%d" % (safe_chr(c0), safe_chr(c1), hits))
    print("%02d %s" % (addr, " ".join(parts)))


def safe_chr(value):
    if 32 <= value <= 126:
        return chr(value)
    return "\\x%02x" % value


def solve():
    gc.collect()
    fpga_rst = setup_fpga()

    try:
        run_digitalio_baseline()

        print("Diagnostic address 31")
        diag = {}
        for raw in sample_raw(31, 100):
            known = raw_to_known_byte(raw)
            diag[known] = diag.get(known, 0) + 1
        print_hist(31, diag)

        recovered = []
        for addr in range(ADDR_COUNT):
            hist = {}
            for raw in sample_raw(addr, SAMPLES_PER_ADDR):
                known = raw_to_known_byte(raw)
                if known in (0, ord("?") & ~MISSING_MASK, ord("L") & ~MISSING_MASK):
                    continue
                hist[known] = hist.get(known, 0) + 1
            print_hist(addr, hist)
            recovered.append(chr(best_from_hist(hist)))

        print("BEST:", "".join(recovered))
        print("FAST_" + "SECMEM_DONE")
    finally:
        if fpga_rst is not None:
            try:
                fpga_rst.deinit()
            except Exception:
                pass


solve()
