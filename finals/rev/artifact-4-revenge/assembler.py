import re

with open('vm.asm') as f:
    lines = f.read().strip().splitlines()

REGS = ['zer', 'rax', 'rcx', 'rdi', 'rsi', 'rbp', 'rsp', 'rip']
LABELS = {}
TEXT = []
ENDING = r'(?:;.*)?$'
INSNS = [x+ENDING for x in [
    r'^\s*mov\s+([a-z]{3}),\s*([a-z]{3})([-+](?:0x)?[0-9a-fA-F]{1,3})?\s*',
    r'^\s*ld\s+([a-z]{3}),\s*\[([a-z]{3})([-+](?:0x)?[0-9a-fA-F]{1,3})?\]\s*',
    r'^\s*st\s+([a-z]{3}),\s*\[([a-z]{3})([-+](?:0x)?[0-9a-fA-F]{1,3})?\]\s*',
    r'^\s*push\s+([a-z]{3})\s*',
    r'^\s*pop\s+([a-z]{3})\s*',
    r'^\s*bne\s+([a-z]{3}),\s*([a-z]{3}),\s*(\w+)\s*',
    r'^\s*gets\s+([a-z]{3})\s*',
    r'^\s*exit\s+([a-z]{3})\s*',
    r'^\s*call\s+([a-z_]+)\s*',
    r'^\s*mov\s+([a-z]{3}),\s*(FLAG|[-]?(?:0x)?[0-9a-fA-F]{1,3})\s*',
    r'^\s*ret\s*',
]]
_r = lambda x: REGS.index(x)
def _int(x):
    if x == 'FLAG':
        return 0x90
    elif '0x' in x:
        return int(x, 16)%0x100
    return int(x)%0x100
for line in map(lambda x: x.strip(), lines):
    if not line or line[0] == ';': # comment
        continue
    if line[-1] == ':': # label
        LABELS[line[:-1]] = len(TEXT)
        continue
    for op, insn in enumerate(INSNS):
        if (m:=re.fullmatch(insn, line)) is None:
            continue
        t = [x if x is not None else '0' for x in m.groups()] + ['0', '0']
        print(line, '|', m.groups(), t)
        if   op in (0, 1): # mov, ld
            res = (0xF0+op, _r(t[0]), _r(t[1]), _int(t[2]))
        elif op == 2: # st
            res = (0xF2, _r(t[1]), _int(t[2]), _r(t[0]))
        elif op in (3, 4, 6, 7): # push, pop, gets, exit
            res = (0xF0+op, _r(t[0]), 0, 0)
        elif op == 5: # bne
            res = (lambda a, b, c, d: (lambda _labels: (
                0xF5, a, b,
                (_labels[c] - d)*4 % 0x100
            )))(_r(t[0]), _r(t[1]), t[2], len(TEXT)+1)
        elif op == 8: # call
            res = (lambda a, b: (lambda _labels: (
                0xF8,
                (_labels[a] - b)*4 % 0x100,
                0, 0
            )))(t[0], len(TEXT)+1)
        elif op == 9: # mov const
            res = (0xF0, _r(t[0]), 0, _int(t[1]))
        elif op == 10: # ret
            res = (0xF4, _r('rip'), 0, 0)
        else:
            print('PARSING ERROR:', line)
            exit()
        assert not isinstance(res, tuple) or len(res) == 4
        TEXT.append(res)
        break
    else:
        print('PARSING ERROR:', line)
        exit()

print(TEXT)
out = b''.join(bytes(x if isinstance(x, tuple) else x(LABELS)) for x in TEXT)
print(out)
assert len(out) <= 0x90
if input('save? >>> ') == 'y':
    with open('dist/vm.bin', 'wb') as f:
        f.write(out)
