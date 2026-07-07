import gc
import struct
import time

import adafruit_pioasm
import board
import hardware.fpga
import rp2pio


PIO_FREQ = 25_000_000
PIO_SOURCE = """
.program fast_secure_memory_probe
loop:
pull
set pins %d
push
jmp loop
"""


def make_state_machine(addr):
    program = adafruit_pioasm.assemble(PIO_SOURCE % (addr & 0x1F))
    return rp2pio.StateMachine(
        program,
        frequency=PIO_FREQ,
        init=adafruit_pioasm.assemble("set pindirs 31"),
        first_set_pin=board.GP8,
        set_pin_count=5,
        in_shift_right=True,
        auto_push=False,
        initial_set_pin_state=31,
        initial_set_pin_direction=0x1F,
    )


gc.collect()
bitstream = "/challs/fast_secure_memory/main.bit"
fpga_rst = None
print("Uploading", bitstream)
fpga_rst = hardware.fpga.upload_bitstream(bitstream)
time.sleep(0.25)


### Initialise Programmable IO
addr=31
sm = make_state_machine(addr)
sm.restart()
tx = bytearray(1 * 4)
rx = bytearray(1 * 4)
sm.write_readinto(tx, rx, out_end=len(tx), in_end=len(rx))
    
if fpga_rst is not None:fpga_rst.deinit()



