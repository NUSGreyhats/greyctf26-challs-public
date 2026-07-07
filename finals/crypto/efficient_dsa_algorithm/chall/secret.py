from hashlib import sha256


FLAG = b"grey{LFSR_i5_n0t_4_C5PRNG_at_aL1!!!}"
SECRET_D = int.from_bytes(sha256(b"simple-lfsr-ecdsa-private-key").digest(), "big")
SECRET_LFSR_STATE = 0xC0FFEE42
SECRET_LFSR_MASK = 0x80000057
