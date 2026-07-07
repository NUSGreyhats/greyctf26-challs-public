import os

with open('vm.bin', 'rb') as f:
    MEM = list(f.read()[:0x100].ljust(0x100, b'\0'))
FLAG = os.environ.get('FLAG', 'grey{fake_flag_for_testing_abcd}')
MEM[0x90:0xB0] = list(FLAG.encode())

r = [0 for _ in range(8)]
def add(a, b): return (a+b) % 0x100

def execute(op, x, y=67, z=67):
    if   op == 0xF0:
        r[x] = add(r[y], z)
    elif op == 0xF1:
        r[x] = MEM[add(r[y], z)]
    elif op == 0xF2:
        MEM[add(r[x], y)] = r[z]
    elif op == 0xF3:
        execute(0xF2, 6, -1, x)
        execute(0xF0, 6, 6, -1)
    elif op == 0xF4:
        execute(0xF0, 6, 6, 1)
        execute(0xF1, x, 6, -1)
    elif op == 0xF5:
        if r[x] != r[y]:
            execute(0xF0, 7, 7, z)
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
        execute(0xF3, 7)
        execute(0xF0, 7, 7, x)
    else:
        print('=== ILLEGAL INSTRUCTION ===')
        exit()

# have fun with the checker!
def run():
    while True:
        instruction = []
        for i in range(4):
            instruction.append(MEM[r[7]])
            r[7] = add(r[7], 1)
        execute(*instruction)

# program entrypoint (like main())
if __name__ == '__main__':
    run()
