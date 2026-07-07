with open('vm.bin', 'rb') as f:
    MEM = list(f.read()[:0x100].ljust(0x100, b'\0'))
FLAG = 'grey{fake_flag_for_testing_abcd}'
MEM[0x90:0xB0] = list(FLAG.encode())

r = [0 for _ in range(8)]
_zero = 0
_bp = 5
_sp = 6
_ip = 7

def add(a, b):
    return (a+b) % 0x100

def execute(op, x, y, z):
    _y = 0 if y is None else y
    _z = 0 if z is None else z
    # print(f'{op:02x} {x:02x} {_y:02x} {_z:02x} | {r[_sp]:02x} {r[_bp]:02x} {r[_ip]//4}')

    if   op == 0xF0:
        r[x] = add(r[y], z)
    elif op == 0xF1:
        r[x] = MEM[add(r[y], z)]
    elif op == 0xF2:
        MEM[add(r[x], y)] = r[z]

    elif op == 0xF3:
        execute(0xF2, _sp, -1, x)
        execute(0xF0, _sp, _sp, -1)
    elif op == 0xF4:
        execute(0xF0, _sp, _sp, 1)
        execute(0xF1, x, _sp, -1)

    elif op == 0xF5:
        # print(r[x], r[y])
        if r[x] != r[y]:
            execute(0xF0, _ip, _ip, z)

    elif op == 0xF6:
        inp = input('>>> ').encode()
        ptr = r[x]
        for c in inp:
            if 0x20 <= c < 0x7F:
                print(f'<<< {c:02x} [{chr(c)}]')
                MEM[ptr] = c
                ptr = add(ptr, 1)
        MEM[ptr] = 0

    elif op == 0xF7:
        print(r[x])
        exit()

    elif op == 0xF8:
        execute(0xF3, _ip, None, None)
        execute(0xF0, _ip, _ip, x)

    else:
        print('=== ILLEGAL INSTRUCTION ===')
        exit()

# have fun with the checker!
def run():
    while True:
        instruction = []
        for i in range(4):
            instruction.append(MEM[r[_ip]])
            r[_ip] = add(r[_ip], 1)
        execute(*instruction)

# program entrypoint (like main())
if __name__ == '__main__':
    run()
