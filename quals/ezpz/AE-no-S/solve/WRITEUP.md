# AE-no-S Writeup

## Challenge Overview

The challenge publishes an AES-like block cipher in `dist/challenge.py` and a transcript in `dist/output.txt`. The transcript gives:

- the encryption of the all-zero block
- encryptions of all 128 one-bit basis blocks
- the encrypted PKCS#7-padded flag

The goal is to recover the flag without the secret.

## Why Removing SubBytes Breaks AES

AES is built from several round operations. AddRoundKey is XOR, ShiftRows is a byte permutation, and MixColumns is linear arithmetic over bytes. SubBytes is the nonlinear step.

If SubBytes is removed, every remaining operation is linear over GF(2), except for the secret-dependent XOR constants introduced by AddRoundKey.

## Why The Cipher Becomes Affine

For a fixed secret, the modified cipher has the form:

```text
E(P) = A(P) xor B
```

`A` is a fixed linear map on 128-bit blocks. `B` is a fixed offset caused by the secret material.

## The All-Zero Block Reveals The Offset

For the zero block:

```text
E(0) = A(0) xor B = B
```

So the published zero-block ciphertext is exactly the affine offset.

## Basis Plaintexts Reveal The Linear Map

Let `e_i` be a block with only bit `i` set. The transcript includes `E(e_i)` for every input bit.

Since `B = E(0)`:

```text
A(e_i) = E(e_i) xor E(0)
```

These 128 values are the columns of the 128x128 binary matrix for `A`.

## Decrypting The Flag

For each encrypted flag block `C`, remove the offset:

```text
target = C xor E(0)
```

Then solve the linear system:

```text
A(P) = target
```

The sample solver asks SageMath to solve this system over GF(2), recovers each padded plaintext block, and removes PKCS#7 padding.

## Implementation Details

The solver treats a 16-byte block as a 128-bit vector. Bit index 0 is the most significant bit of the block, matching how the public transcript represents each one-bit basis plaintext.

The solver parses every basis plaintext/ciphertext pair. For a one-bit plaintext `e_i`, it stores:

```text
column_i = E(e_i) xor E(0)
```

Those columns describe where each input basis bit goes under the linear part `A`.

SageMath expects a matrix as rows, so the solver transposes those columns into a 128x128 matrix over `GF(2)`. Each row corresponds to one output bit. A coefficient is set when that input bit's column contributes to the row's output bit.

For each encrypted flag block, the solver removes the affine offset and creates a Sage vector:

```text
target = C xor E(0)
```

Then it uses:

```python
plaintext_bits = matrix.solve_right(target)
```

Sage handles the Gaussian elimination internally. The solver still checks that the matrix has rank 128 before decrypting. The solved bits are mapped back into 16-byte plaintext blocks, concatenated, and checked with PKCS#7 unpadding. Padding validation is important because an incorrect matrix, bit order, or ciphertext parse should fail instead of silently producing garbage.

## Commands

From the challenge root:

```sh
pyenv activate cs5242
sage -python solve/solve.py
```

To regenerate the public artifacts locally:

```sh
pyenv activate cs5242
python3 chall/generate.py
sage -python solve/solve.py
```

## Expected Flag

```text
grey{iT5_4LL_l1N3R_aLGyBeR?_a1WaY5_HaZ_B1n...}
```
