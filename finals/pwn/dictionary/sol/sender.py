from pwn import *
from base64 import b64encode

p = remote("challs.nusgreyhats.org", 31467)

with open("./solve.py", "rb") as file:
    payload = b64encode(file.read())
    p.sendlineafter(b">", str(len(payload)).encode())
    p.sendlineafter(b">", payload)

p.interactive()
