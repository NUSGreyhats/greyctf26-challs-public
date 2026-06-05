#!/usr/bin/env python3
BLOCK_SIZE = 16
N_ROUNDS = 10

RCON = [
    0x01, 0x02, 0x04, 0x08, 0x10,
    0x20, 0x40, 0x80, 0x1B, 0x36,
]


def xor_bytes(left, right):
    return bytes(a ^ b for a, b in zip(left, right))


def pkcs7_pad(data, block_size=BLOCK_SIZE):
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def _xtime(value):
    value <<= 1
    if value & 0x100:
        value ^= 0x11B
    return value & 0xFF


def _mul2(value):
    return _xtime(value)


def _mul3(value):
    return _xtime(value) ^ value


def _bytes_to_state(block):
    return [[block[4 * col + row] for col in range(4)] for row in range(4)]


def _state_to_bytes(state):
    return bytes(state[row][col] for col in range(4) for row in range(4))


def _add_material(state, material):
    for col in range(4):
        for row in range(4):
            state[row][col] ^= material[4 * col + row]


def _shift_rows(state):
    for row in range(1, 4):
        state[row] = state[row][row:] + state[row][:row]


def _mix_single_column(column):
    a0, a1, a2, a3 = column
    return [
        _mul2(a0) ^ _mul3(a1) ^ a2 ^ a3,
        a0 ^ _mul2(a1) ^ _mul3(a2) ^ a3,
        a0 ^ a1 ^ _mul2(a2) ^ _mul3(a3),
        _mul3(a0) ^ a1 ^ a2 ^ _mul2(a3),
    ]


def _mix_columns(state):
    for col in range(4):
        mixed = _mix_single_column([state[row][col] for row in range(4)])
        for row in range(4):
            state[row][col] = mixed[row]


def _rot_word(word):
    return word[1:] + word[:1]


def _make_schedule(secret):
    if len(secret) != BLOCK_SIZE:
        raise ValueError("secret must be exactly one AES block")

    words = [list(secret[4 * i:4 * i + 4]) for i in range(4)]
    for index in range(4, 4 * (N_ROUNDS + 1)):
        temp = words[index - 1].copy()
        if index % 4 == 0:
            # In this variant, the SubWord step is also the identity map.
            temp = _rot_word(temp)
            temp[0] ^= RCON[index // 4 - 1]
        words.append([words[index - 4][i] ^ temp[i] for i in range(4)])

    schedule = []
    for round_index in range(N_ROUNDS + 1):
        chunk = []
        for word in words[4 * round_index:4 * round_index + 4]:
            chunk.extend(word)
        schedule.append(bytes(chunk))
    return schedule


def encrypt_block(block, secret):
    if len(block) != BLOCK_SIZE:
        raise ValueError("block must be exactly one AES block")

    schedule = _make_schedule(secret)
    state = _bytes_to_state(block)

    _add_material(state, schedule[0])
    for round_index in range(1, N_ROUNDS):
        # AES normally applies SubBytes here. AE-no-S replaces it with identity.
        _shift_rows(state)
        _mix_columns(state)
        _add_material(state, schedule[round_index])

    _shift_rows(state)
    _add_material(state, schedule[N_ROUNDS])
    return _state_to_bytes(state)


def encrypt_padded(data, secret):
    padded = pkcs7_pad(data)
    blocks = []
    for offset in range(0, len(padded), BLOCK_SIZE):
        blocks.append(encrypt_block(padded[offset:offset + BLOCK_SIZE], secret))
    return b"".join(blocks)
