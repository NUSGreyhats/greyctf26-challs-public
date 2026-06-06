from pwn import read

OP = {
    'print': ord(' '),
    'push': 67,
    'pop': 0x67,
    'swap': 0x35,
    'dup': 0x36,
    'rot': 0x37,
    'load': ord('L'),
    'store': ord('S'),
    'add': ord('+'),
    'sub': ord('-'),
    'mul': ord('*'),
    'and': ord('&'),
    'xor': ord('^'),
    'jmp': 5,
    'jz': 6,
    'jnz': 7,
}
assert len(set(OP.values())) == len(OP)
REV_OP = dict(zip(OP.values(), OP.keys()))
MULTI = ('push', 'jmp', 'jz', 'jnz')

def flat_map(f, xs):
    return [
        y
        for x in xs
        for y in f(x)
    ]
def is_int(x):
    try:
        int(x, 16)
        return True
    except:
        return False

RAW = read('../pool.bin')
opcode = True
operand = False
for i in range(len(RAW)//4):
    opts = list(RAW[i*4:(i+1)*4])
    opts = sorted(flat_map(
        lambda x: (
            ([REV_OP[x]] if opcode and x in REV_OP else [])
            + ([f'{x:02x}'] if operand else [])
        ),
        (tmp := opts + list(map(lambda x: (x+67)%256, opts)))
    ), key=lambda x: '}'+x if is_int(x) else x)
    assert opts, i
    opcode = any(x not in MULTI for x in opts)
    operand = any(x in MULTI for x in opts)
    print(*opts, sep='\t')
