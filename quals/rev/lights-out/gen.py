import random
import numpy as np
import galois

RANK = 256
FLAG = b'grey{addin_redstone_2_my_rEsumE}'
assert len(FLAG)*8 == RANK

random.seed(int(FLAG.hex(), 16))
GF2 = galois.GF(2)

run = 0
while True:
    print(f'trying... ({(run:=run+1)})')
    connections = [
        (btn, eqn)
        for eqn in range(RANK)
        for btn in random.sample(list(set(range(RANK)) - {eqn}), 17-1)
    ] + [(i, i) for i in range(RANK)]
    random.shuffle(connections)
    # verification
    m = [[0 for _ in range(RANK)] for _ in range(RANK)]
    for btn, eqn in connections:
        m[eqn][btn] = 1
    m = GF2(m)
    if np.linalg.matrix_rank(m) == RANK:
        break

v = GF2([
    int(b)
    for x in FLAG
    for b in f'{x:08b}'
])
b = m @ v
assert bytes.fromhex(hex(int(''.join(map(str, np.linalg.solve(m, b).tolist())), 2))[2:]) == FLAG
np.save('bulbs.npy', b)

# ==============================================================================================

import heapq

DIRS = {
    (-1, 0, 0): 'east',
    (1, 0, 0): 'west',
    (0, -1, 0): 'down', # flipped; on this board 0 is at the top
    (0, 1, 0): 'up',
    (0, 0, -1): 'south',
    (0, 0, 1): 'north'
}

STATE = []
BOARD = [[[None for _ in range(RANK)] for _ in range(RANK)] for _ in range(RANK)]
def dist(p1, p2): return sum(map(lambda x: abs(x[0]-x[1]), zip(p1, p2)))
def delta(p1, p2): return tuple(map(lambda x: x[1]-x[0], zip(p1, p2)))
def valid(p): return all(map(lambda x: 0 <= x[0] < x[1], zip(p, (RANK, RANK, RANK))))
def _get(p): return BOARD[p[0]][p[1]][p[2]]
def _set(p, x): BOARD[p[0]][p[1]][p[2]] = x
def apply(p, d): return tuple(map(lambda x: x[0]+x[1], zip(p, d)))
def empty(p): return _get(p) is None

for btn, eqn in connections:
    while not empty((0, (y:=random.randrange(0, RANK)), btn)):
        pass
    _set((0, y, btn), (-1, y, btn))
    STATE.append((y, btn, eqn))


SENTINEL = -1
# stage 1: ey=None
# stage 2: use ey as a guide
def route(sy, sz, ez, ey=None, ex=RANK-2):
    q = [(0, 0, random.random(), (0, sy, sz), SENTINEL)]
    V = {}
    while q:
        _, g, _, cur, prev = heapq.heappop(q)
        if cur in V: continue
        V[cur] = prev

        cx, cy, cz = cur
        if (cx, cz) == (ex, ez):
            _set((cx+1, cy, cz), cur)
            while (prev:=V[cur]) != SENTINEL:
                _set(cur, prev)
                cur = prev
            _set(cur, (cur[0]-1, cur[1], cur[2]))
            return cy

        for d in DIRS:
            nxt = apply(cur, d)
            nx, ny, nz = nxt
            if nx <= ex and valid(nxt) and empty(nxt) and nxt not in V:
                if ey is None:
                    weight = g + (ex-nx)*2 + abs(ez-nz)*2
                else:
                    _d = abs(ex-nx) + abs(ez-nz) + abs(ey-ny)
                    weight = _d + random.randint(0, int(_d * 2))
                heapq.heappush(q, (weight, g+1, random.random(), nxt, cur))
    assert False, 'No valid path!'

# stage 1: bare minimum connection
conn = []
STATE.sort(key=lambda s: abs(s[1]-s[2]))
for i, (y, z, target) in enumerate(STATE):
    _set((0, y, z), None)
    _y = route(y, z, target)
    conn.append(((0, y, z), (RANK-1, _y, target)))
    if i % 256 == 0: print(i)

print('stage 1 done!')

# stage 2: chaos generation
random.shuffle(conn)
for i, (s, e) in enumerate(conn):
    cur = e
    while cur != s:
        prev = _get(cur)
        _set(cur, None)
        cur = prev
    _set(cur, None)
    sx, sy, sz = s
    _, ey, ez = e
    route(sy, sz, ez, ey=ey)
    print(i)

print('stage 2 done!')

SERIALIZE = [None, 'north', 'south', 'east', 'west', 'up', 'down']
for x, a in enumerate(BOARD):
    for y, b in enumerate(a):
        for z, c in enumerate(b):
            # c stores where we reached current block from
            _set((x, y, z), SERIALIZE.index(
                DIRS[delta(c, (x, y, z))] if c is not None else c
            ))

np.save('cube.npy', np.array(BOARD))
