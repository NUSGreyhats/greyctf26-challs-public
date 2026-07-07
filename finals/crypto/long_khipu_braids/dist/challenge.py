#!/usr/bin/env python3
"""
Long Khipu Braids public handout.

The SVG cords in CORD_PICTURES are lossless. Read crossings from the primary
cord downward. Each register contains one adjacent crossing: if the left/top
strand passes over its neighbor, record the positive sign; if it passes under,
record the negative sign. At each crossing, the strand drawn on top is the
over-strand; the other strand continues underneath it. The side knots are just
khipu-style register markers; ignore them when reading the crossings.

The braid parameters are public. The sealed cord opens only after the exchange
has been evaluated into its shared finite-field state.
"""

import hashlib
import operator

KIND = "Long-Khipu-Braids-v4.0"
N = 8
P = 10000019
Q = 17
T = 42
KDF_CONTEXT = b'Long-Khipu-Braids-v4.0'
STATE_DIMENSION = N * (N - 1) // 2

CORD_PICTURES = {'bob': [{'label': 'P_1', 'file': 'cords/bob_P_1.svg', 'crossings': 165}, {'label': 'P_2', 'file': 'cords/bob_P_2.svg', 'crossings': 161}, {'label': 'P_3', 'file': 'cords/bob_P_3.svg', 'crossings': 177}, {'label': 'P_4', 'file': 'cords/bob_P_4.svg', 'crossings': 165}, {'label': 'P_5', 'file': 'cords/bob_P_5.svg', 'crossings': 159}, {'label': 'P_6', 'file': 'cords/bob_P_6.svg', 'crossings': 151}, {'label': 'P_7', 'file': 'cords/bob_P_7.svg', 'crossings': 157}], 'alice': [{'label': 'E_1', 'file': 'cords/alice_E_1.svg', 'crossings': 177}, {'label': 'E_2', 'file': 'cords/alice_E_2.svg', 'crossings': 165}, {'label': 'E_3', 'file': 'cords/alice_E_3.svg', 'crossings': 177}, {'label': 'E_4', 'file': 'cords/alice_E_4.svg', 'crossings': 177}, {'label': 'E_5', 'file': 'cords/alice_E_5.svg', 'crossings': 177}, {'label': 'E_6', 'file': 'cords/alice_E_6.svg', 'crossings': 175}, {'label': 'E_7', 'file': 'cords/alice_E_7.svg', 'crossings': 169}]}

NONCE = bytes.fromhex("7f8216546ff62ce246731fe8fb2d3384")
CIPHERTEXT = bytes.fromhex("bf35c25852ca13f694e38bff3ff7c6597b99f5280995070401f71f5187ff0bc520459a8979d93b1012383c3d54140185ae8eea4feb53266421c018e1a434b4e739734be69d2a49b064fb6a6331")
TAG = bytes.fromhex("b369a66ed69d804c9ddad3cf2ecf316b")


def serialize_state(state):
    width = (P.bit_length() + 7) // 8
    if len(state) != STATE_DIMENSION or any(len(row) != STATE_DIMENSION for row in state):
        raise ValueError("wrong shared-state shape")
    return b"".join((int(x) % P).to_bytes(width, "big") for row in state for x in row)


def derive_key(shared_state):
    return hashlib.sha256(KDF_CONTEXT + serialize_state(shared_state)).digest()


def open_sealed_cord(shared_state):
    key = derive_key(shared_state)
    if hashlib.sha256(key + NONCE + CIPHERTEXT).digest()[:16] != TAG:
        raise ValueError("the cord stays shut")
    stream = hashlib.shake_256(key + NONCE).digest(len(CIPHERTEXT))
    return bytes(operator.xor(a, b) for a, b in zip(CIPHERTEXT, stream))
