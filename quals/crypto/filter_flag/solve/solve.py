#!/usr/bin/env python3
from pwn import *

def solve():
    # r = process(['python3', '../challenge/server.py'])
    r = remote('127.0.0.1', 37167)

    r.recvuntil(b"Encrypted flag: ")
    enc_flag_hex = r.recvline().strip().decode()
    enc_flag = bytes.fromhex(enc_flag_hex)

    # Split the encrypted flag into its 4 respective 16-byte blocks
    c1 = enc_flag[0:16]
    c2 = enc_flag[16:32]
    c3 = enc_flag[32:48]
    c4 = enc_flag[48:64]
    c5 = enc_flag[64:80]

    print(len(enc_flag))
    log.info("Step 1: Recovering the first three blocks...")
    # We replace the last block with C1. The ciphertext is no longer exactly the original,
    # bypassing the oracle's exact-match filter. The first 3 blocks remain mathematically intact.
    payload1 = c1 + c2 + c3 + c4 + c1
    r.sendlineafter(b"decrypt: ", payload1.hex().encode())

    r.recvuntil(b"Decrypted: ")
    resp1 = r.recvline().strip().decode()
    log.success(f"Response 1: {resp1}")

    log.info("Step 2: Recovering the last block using the Commutative State trick...")
    # In PCBC mode, the state passed to block i+1 depends on the XOR sum of all previous
    # ciphertexts and plaintexts. Therefore, the SET of previous blocks matters, but their ORDER does not!
    # By swapping C1 and C2, we destroy the decryption of blocks 1 and 2, but the PCBC state 
    # restores perfectly by block 3, allowing block 4 to decrypt perfectly!
    payload2 = c2 + c1 + c3 + c4 + c5
    r.sendlineafter(b"decrypt: ", payload2.hex().encode())

    r.recvuntil(b"Decrypted: ")
    resp2 = r.recvline().strip().decode()
    log.success(f"Response 2: {resp2}")

    # Extract the clean pieces from the responses
    part1 = resp1.replace("?", "")
    part2 = resp2.replace("?", "")

    # part1 contains Blocks 1, 2, and 3.
    # part2 contains Blocks 3 and 4.
    # We stitch the first 48 bytes of part1 with the last 16 bytes of part2.
    final_flag = part1[:64] + part2[-16:]

    log.info(f"Recovered Flag: {final_flag}")
    r.close()

if __name__ == "__main__":
    solve()