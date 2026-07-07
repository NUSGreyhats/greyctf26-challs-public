MEM = [None for _ in range(3000)]
REG = {
    'A': 0,
    'B': 0,
    'F': 3000,
    'G': 3000,
    'I': 13,   # instruction pointer (rip)
    'X': 0,
    'Y': 0,
    'ZERO': 0, # guaranteed to not change
}
def execute(op, x=0, y=0, z=0):
    if   op == 0: # push
        REG['F'] -= 1; MEM[REG['F']] = REG[x]
    elif op == 1:
        REG[x] = MEM[REG['F']]; REG['F'] += 1
    elif op == 2:
        REG[x] = REG[y] + z
    elif op == 3:
        REG[x] = MEM[REG[y] + z]
    elif op == 4:   
        MEM[REG[x] + y] = REG[z]
    elif op == 5:
        REG[x] = (REG[y] == REG[z])
    elif op == 6:
        if REG[x] is False:
            print('Wrong!')
            exit()
    elif op == 7:
        print('Correct!')
        exit()
    elif op == 8: # call
        execute(0, 'I')
        execute(2, 'I', 'ZERO', y)

# get user input (the python way)
inp = input("Enter VM input: ")
if len(inp) != 25:
    print('Invalid length!')
    exit()
key = '____aadeghhimnorrstttvy{}'
# load input and key into memory
for i in range(25):
    MEM[1000+i] = inp[i]
    MEM[2000+i] = key[i]

# have fun with the checker!
def run():
    while True:
        instruction = MEM[REG['I']]
        REG['I'] += 1
        execute(*instruction)

_code = [
    (0, 'G'),
    (2, 'G', 'F'),
    (2, 'F', 'F', -2),
    (3, 'A', 'X', 1000),
    (4, 'G', -1, 'A'),
    (3, 'A', 'Y', 2000),
    (4, 'G', -2, 'A'),
    (3, 'A', 'G', -1),
    (3, 'B', 'G', -2),
    (5, 'A', 'A', 'B'),
    (2, 'F', 'G'),
    (1, 'G'),
    (1, 'I'),

# vm entrypoint (our "main")
    (2, 'X', 'ZERO'),
    (2, 'Y', 'ZERO', 8),
    (8, 0), # points to the start of this list
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 15),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 7),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 22),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 23), # notice a pattern?
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 21),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 12),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 0),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 11),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 17),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 1),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 13),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 14),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 18),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 2),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 19),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 9),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 4),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 20),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 3),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 10),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 5),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 16),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 6),
    (8, 0),
    (6, 'A'),
    (2, 'X', 'X', 1),
    (2, 'Y', 'ZERO', 24),
    (8, 0),
    (6, 'A'),
    (7,)
]
MEM[:len(_code)] = _code

# program entrypoint (like main())
if __name__ == '__main__':
    run()
