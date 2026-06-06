from pwn import read
RAW = read('../pool.bin')
VM = read('../vm.bin')

INST = ['push', '_', 'dup', 'dup', 'push', '2', 'store', 'push', '_', 'add', 'dup', 'jnz', 'f5', 'dup', 'dup', 'push', '2', 'load', 'swap', 'dup', 'dup', 'push', '80', 'and', 'xor', 'push', '1', 'load', 'rot', 'add', 'rot', 'add', 'dup', 'rot', 'dup', 'rot', 'dup', 'push', '2', 'load', 'swap', 'rot', 'dup', 'push', '2', 'load', 'rot', 'push', '2', 'store', 'push', '2', 'store', 'push', '_', 'add', 'dup', 'jnz', 'd3', 'and', 'dup', 'push', '_', 'add', 'dup', 'push', '2', 'load', 'rot', 'add', 'dup', 'rot', 'dup', 'rot', 'dup', 'rot', 'dup', 'rot', 'dup', 'push', '2', 'load', 'swap', 'rot', 'dup', 'push', '2', 'load', 'rot', 'push', '2', 'store', 'push', '2', 'store', 'push', '2', 'dup', 'rot', 'swap', 'load', 'rot', 'rot', 'dup', 'rot', 'swap', 'load', 'rot', 'add', 'swap', 'load', 'swap', 'dup', 'push', '_', 'add', 'push', '0', 'load', 'dup', 'jnz', '1', '_', 'rot', 'xor', 'print', 'jmp', 'bd']
assert len(INST) == 0x80

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
def find(x):
    if x in OP:
        return OP[x]
    try:
        return int(x, 16)
    except:
        pass
    assert x == '_', f'Invalid: {x}'
    return None

f, g = 0, 0 # checksums
brute_i = []
brute_xs = []
for i, x in enumerate(INST):
    y = find(x)
    if y is not None:
        assert (
            y in tuple(RAW[i*4:(i+1)*4])
            or (y-67)%256 in tuple(RAW[i*4:(i+1)*4])
        ), (i, x, y)
        f += y
        g += y*pow(131, 127-i, 256)
        f, g = f%256, g%256
    else:
        brute_i.append(i)
        brute_xs.append(tuple(
            y
            for x in RAW[i*4:(i+1)*4]
            for y in (x, (x+67)%256)
        ))
print(f, g, brute_i, brute_xs)

from itertools import product
TARGET_F, TARGET_G = 204, 118
found = []
for comb in product(*brute_xs):
    _f, _g = f, g
    for i, x in zip(brute_i, comb):
        _f += x
        _g += x*pow(131, 127-i, 256)
        _f, _g = _f%256, _g%256
    if _f == TARGET_F and _g == TARGET_G:
        print('found!', comb)
        found.append(comb)

from Crypto.Cipher import ARC4
for comb in found:
    _comb = iter(comb)
    key = bytes(
        y if (y:=find(x)) is not None else next(_comb)
        for x in INST
    )
    # i'm so sorry for the +1
    # sort of a design limitation of my rc4 implementation...
    # ending up spending quite a while debugging why the supposed correct key returns jibberish
    enc = VM[comb[-2]+1:]
    enc = enc[:enc.index(0)]
    print(ARC4.new(key).decrypt(enc))
