from __future__ import annotations

import hashlib
import secrets
import string
from dataclasses import dataclass

DEFAULT_POW_DIFFICULTY = 24
POW_PREFIX_BYTES = 16
NONCE_ALPHABET = string.ascii_letters + string.digits


@dataclass(frozen=True, slots=True)
class ProofOfWorkChallenge:
    prefix: str
    difficulty: int = DEFAULT_POW_DIFFICULTY


def make_challenge(difficulty: int = DEFAULT_POW_DIFFICULTY) -> ProofOfWorkChallenge:
    if difficulty < 0:
        raise ValueError("difficulty must be non-negative.")
    return ProofOfWorkChallenge(secrets.token_hex(POW_PREFIX_BYTES), difficulty)


def verify_nonce(prefix: str, nonce: str, difficulty: int = DEFAULT_POW_DIFFICULTY) -> bool:
    if difficulty < 0:
        return False
    digest = hashlib.sha256((prefix + nonce).encode("ascii", errors="ignore")).digest()
    whole_bytes, remaining_bits = divmod(difficulty, 8)
    if any(digest[index] != 0 for index in range(whole_bytes)):
        return False
    if remaining_bits == 0:
        return True
    return digest[whole_bytes] >> (8 - remaining_bits) == 0


def solve_challenge(prefix: str, difficulty: int = DEFAULT_POW_DIFFICULTY) -> str:
    counter = 0
    while True:
        nonce = f"{counter:x}"
        if verify_nonce(prefix, nonce, difficulty):
            return nonce
        counter += 1
