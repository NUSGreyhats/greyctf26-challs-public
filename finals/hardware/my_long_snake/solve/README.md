# My Long Snake writeup

## Challenge summary

My Long Snake gives players a CircuitPython Snake challenge. Players provide a move file at:

/moves.txt

containing only U, D, L, and R. The badge replays the moves. To win, the snake must eat 40 apples without hitting the wall or itself.

Relevant constants from dist/snake_challenge.py:

SEED = 0x5A17C0DE
TARGET_APPLES = 40
MAX_MOVES = 4096
BOARD_W = 18
BOARD_H = 18
initial snake = [(9, 9), (8, 9), (7, 9)]
initial direction = right

## Reversing apple generation

Apple generation uses a deterministic xorshift32 PRNG:

x ^= (x << 13) & 0xFFFFFFFF
x ^= (x >> 17) & 0xFFFFFFFF
x ^= (x << 5) & 0xFFFFFFFF

Each apple candidate consumes two PRNG outputs:

x = 1 + (prng.next() % 16)
y = 1 + (prng.next() % 16)

If the candidate overlaps the snake body, it is rejected and another candidate is generated. This means apple positions cannot be fully listed upfront unless we also simulate the snake state.

The first apple is:

(9, 7)

## Solver idea

The simple reliable solve is to use a Hamiltonian-cycle-style path over the 16x16 playable area, then take safe shortcuts toward the current apple. The invariant is that the snake remains ordered along the
cycle, so it cannot trap itself.

A valid solution I found eats all 40 apples in:

780 moves

This is well below MAX_MOVES = 4096, so the challenge is definitely solvable.

## Solution moves

Put this into /moves.txt:

DDDDDDDLLLLLLLLUUUUUUUUURRRRRRRRDDDDDDDDDLLLLLLLLUUUUUUUUUUURRRRRRRRDDDDDDDDDDDLLLLLLLLUUUURDRRRDDDLLLLUUUUUUURRRRRRRRULLLLLDDDDDDDDLLLUUUUUUUUUUURRRDDDDDDDDRRDDDLLLLLUUUUUUURRRRRRRRRRDDRDDDDDLLLLLLLLLLLUUUUUU
UUUUUUUUURRRRRRRRRRDDDDDDDDDDDDDDDLLLLLLLLLLUUUUURRRRRRRRRDDDDDLLLLLLLLLUUUUUUUUURRRRRRRRRRRRDDDLLLLLLLLLDDDDDDLLLUUUUUUUUUUURRRRRRRRRRRRRRDDDDDDDDDDDLLLLLLLLLLLLLLUUUUUUUUUUUUUUURRRRRRRRRRRDDDDDDDLDDLLLDDLLLL
LLLUUUUUUURRRRRRRRRRRRRDDDDDDDDDDDLLLLLLLLLLLLLURRRRRRRRRRRRRDLLLLLLLLLLLLLUUUUUUUUUUUUURRDDDDDDDDDDDDDLLUUUUUUUUUUUUUUURRRRRRRRRRDDDDDDDDDLLLLLLLLDDDRRRRRRRRRRDDDLLLLLLLLLLLLUUUUUUUUUUUUUUURRRRRRRRRRRDDDDDDDD
DLLLLLDDDDDDLLLLLLUUUUUUUUUUUUURRRDDDDRRRDDRRRDDDDDDDLLLLLLLLLUUUUUUUUUUUUUUURRRRRRRRRRRRDDDDDDDDDLLLLDDDDDRRRRRRDLLLLLLLLLLLLLLUUUUUUUUUUURRRRRRRRRRRRRD

The challenge then prints:

grey{i_have_a_long_snakey}

For KOTH, submit a shorter valid move sequence; this 780-move solve is a baseline.