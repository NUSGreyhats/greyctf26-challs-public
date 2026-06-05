#!/usr/bin/env python3
import json
import sys
from pathlib import Path

try:
    from sage.all import GF, Matrix, vector
except ImportError as exc:
    raise ImportError(
        "This solver requires SageMath. Run it with: sage -python solve/solve.py"
    ) from None


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
sys.dont_write_bytecode = True
sys.path.insert(0, str(DIST_DIR))

from challenge import BLOCK_SIZE, xor_bytes


BITS_PER_BLOCK = BLOCK_SIZE * 8
F2 = GF(2)


def block_to_bits(block):
    """Return an MSB-first list of bits for a 16-byte block."""
    bits = []
    for byte in block:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits


def bits_to_block(bits):
    """Convert an MSB-first bit vector back into bytes."""
    output = bytearray(BLOCK_SIZE)
    for bit_index, bit in enumerate(bits):
        if int(bit):
            byte_index = bit_index // 8
            bit_in_byte = 7 - (bit_index % 8)
            output[byte_index] |= 1 << bit_in_byte
    return bytes(output)


def parse_output(path=DIST_DIR / "output.txt"):
    data = json.loads(path.read_text(encoding="utf-8"))
    zero_pt = bytes.fromhex(data["zero"]["pt"])
    zero_ct = bytes.fromhex(data["zero"]["ct"])

    if zero_pt != bytes(BLOCK_SIZE):
        raise ValueError("output.txt has an unexpected zero plaintext block")

    basis_pairs = []
    for pair in data["basis_pairs"]:
        basis_pairs.append((bytes.fromhex(pair["pt"]), bytes.fromhex(pair["ct"])))

    flag_ct = bytes.fromhex(data["flag_ct"])
    return zero_ct, basis_pairs, flag_ct


def basis_index(block):
    bits = block_to_bits(block)
    if sum(bits) != 1:
        raise ValueError("basis plaintext is not a one-bit block")
    return bits.index(1)


def build_matrix(zero_ct, basis_pairs):
    if len(basis_pairs) != BITS_PER_BLOCK:
        raise ValueError("expected exactly 128 basis plaintext/ciphertext pairs")

    columns = [None] * BITS_PER_BLOCK
    for plaintext, ciphertext in basis_pairs:
        index = basis_index(plaintext)
        # E(P) = A(P) xor B, and B = E(0), so E(e_i) xor E(0) = A(e_i).
        columns[index] = block_to_bits(xor_bytes(ciphertext, zero_ct))

    if any(column is None for column in columns):
        raise ValueError("basis pairs do not cover all 128 input bits")

    # Sage stores matrices as rows. Row r, column c says whether input bit c
    # contributes to output bit r under the linear map A.
    rows = []
    for output_bit in range(BITS_PER_BLOCK):
        row = []
        for input_bit in range(BITS_PER_BLOCK):
            row.append(columns[input_bit][output_bit])
        rows.append(row)

    matrix = Matrix(F2, rows)
    rank = matrix.rank()
    if rank != BITS_PER_BLOCK:
        raise ValueError(f"linear map is not invertible; rank is {rank}")
    return matrix


def decrypt_block(ciphertext, zero_ct, matrix):
    # Remove the affine offset B first, then ask Sage to solve A(P) = target.
    target_bits = block_to_bits(xor_bytes(ciphertext, zero_ct))
    target = vector(F2, target_bits)
    plaintext_bits = matrix.solve_right(target)
    return bits_to_block(plaintext_bits)


def pkcs7_unpad(data, block_size=BLOCK_SIZE):
    if not data or len(data) % block_size != 0:
        raise ValueError("invalid padded data length")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError("invalid PKCS#7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-pad_len]


def main():
    zero_ct, basis_pairs, flag_ct = parse_output()
    matrix = build_matrix(zero_ct, basis_pairs)

    plaintext_blocks = []
    for offset in range(0, len(flag_ct), BLOCK_SIZE):
        block = flag_ct[offset:offset + BLOCK_SIZE]
        plaintext_blocks.append(decrypt_block(block, zero_ct, matrix))

    flag = pkcs7_unpad(b"".join(plaintext_blocks))
    print(flag.decode())


if __name__ == "__main__":
    main()
