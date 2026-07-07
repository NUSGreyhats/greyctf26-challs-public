import gc
import struct
import time

import adafruit_pioasm
import board
import hardware.fpga
import rp2pio


ADDR_COUNT = 15
SAMPLES_PER_ADDR = 50
PIO_FREQ = 25_000_000
PIO_IN_BITS = 7


PIO_SOURCE = """
.program fast_secure_memory_probe
loop:
pull
in pins, 7
push block
jmp loop
"""


def make_state_machine(addr):
    program = adafruit_pioasm.assemble(PIO_SOURCE)
    return rp2pio.StateMachine(
        program,
        frequency=PIO_FREQ,
        init=adafruit_pioasm.assemble("set pindirs 31"),
        first_set_pin=board.GP8,
        first_in_pin=board.GP22,
        in_pin_count=PIO_IN_BITS,
        in_shift_right=True,
        auto_push=False,
        initial_set_pin_state=31,
        initial_set_pin_direction=0x1F,
    )


# Current bitstream mirrors value[1] onto PMOD J2 bit 7, so the PIO window can
# stay on the connected GP22..GP28 pins and recover ASCII bit 1 from GP24.
# raw0=GP22, raw1=GP23, raw2=GP24, raw3=GP25,
# raw4=GP26, raw5=GP27, raw6=GP28.
PMOD_RAW_BITS = (5, 2, 1, 3, 4, 6, 0)
def raw_to_byte(raw):
    value = 0
    for pmod_bit, raw_bit in enumerate(PMOD_RAW_BITS):
        value |= ((raw >> raw_bit) & 1) << pmod_bit
    return value

'''
gc.collect()
bitstream = "/challs/fast_secure_memory/main.bit"
fpga_rst = None
print("Uploading", bitstream)
fpga_rst = hardware.fpga.upload_bitstream(bitstream)
time.sleep(0.25)
'''


### Initialise Programmable IO

print("PIO Init")
addr=31
sm = make_state_machine(addr)
sm.restart()
tx = bytearray(SAMPLES_PER_ADDR * 4) # Length of this determines how many times ran
rx = bytearray(SAMPLES_PER_ADDR * 4)
sm.write_readinto(tx, rx, out_end=len(tx), in_end=len(rx))

print("PIO Finish")
i = 0
raw_mask = (1 << PIO_IN_BITS) - 1
word = struct.unpack_from("<I", rx, i * 4)[0]
raw = (word >> (32 - PIO_IN_BITS)) & raw_mask
value = raw_to_byte(raw)
print(value, chr(value))

sm.deinit()

if fpga_rst is not None:fpga_rst.deinit()



