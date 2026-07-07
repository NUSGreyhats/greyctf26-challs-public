#!/usr/bin/env python3
"""
decrypt.py — decrypt a captured 802.15.4 broadcaster frame

Requires:
    pip install pycryptodome

Usage:
    python3 decrypt.py <frame_hex> <??_key_hex>

Arguments:
    frame_hex  — the hex string printed by the sniffer
    ??_key_hex — 16 bytes the ?? from the badge

────────────────────────────────────────────────────────────────────────────────
HOW TO IDENTIFY THE BROADCASTER FRAME
────────────────────────────────────────────────────────────────────────────────
Look for PAN ID in little-endian order defined in IEEE 802.15.4-2006 §7.2.1.4.
https://people.ece.ubc.ca/edc/7860/data/802.15.4-2006.pdf <- USE THIS SPECIFICATION

────────────────────────────────────────────────────────────────────────────────
FRAME LAYOUT  (IEEE 802.15.4-2006, §7.)
────────────────────────────────────────────────────────────────────────────────
Offset  Len  Field               Spec section
──────  ───  ──────────────────  ────────────
  0      2   Frame Control       
  2      1   ?     
  3      2   ?     
  5      2   ?   
  7      8   ?      
 15      1   Security Control    
 20      4   ?        
 24      1   ?          
 25      N   ?                  
 25+N    4   ?                   

Security Control byte = ?: 

Source PAN ID is absent because of PAN ID Compression

────────────────────────────────────────────────────────────────────────────────
KEY DERIVATION  
https://github.com/openthread/openthread/blob/main/src/core/thread/key_manager.cpp
Look at ComputeKeys()
────────────────────────────────────────────────────────────────────────────────
The ? is a 16-byte secret shared across the Thread network.

The actual AES key used for this frame is derived as:

    KeyMaterial = HMAC-SHA256(?, ? || ?)

────────────────────────────────────────────────────────────────────────────────
CCM ENCRYPTION  (IEEE 802.15.4-2006 Annex B, NIST SP 800-38C)
────────────────────────────────────────────────────────────────────────────────
802.15.4 uses CCM* (CCM-star) for authenticated encryption. Two inputs feed it:

Nonce (13 bytes)
    ? || ? || ?

AAD (Additional Authenticated Data) 

MIC (Message Integrity Code, 4 bytes) Annex B:
    A CBC-MAC computed over B0 (nonce + length) || AAD || plaintext, then the
    resulting tag is XOR-encrypted with AES(A0) where A0 uses counter=0.

"""

import sys
import hmac
import hashlib
import struct
from Crypto.Cipher import AES

# https://people.ece.ubc.ca/edc/7860/data/802.15.4-2006.pdf <- Use this datasheet please
# ── key derivation ─────────────────────────────────────────────────────────────

def derive_mac_key(k: bytes, s: bytes) -> bytes:
    """
    Thread MAC key derivation.

    KeyMaterial = HMAC-SHA256(?, ? || ?)
    """
    hmac_input  = b"???" # TODO
    key_material = hmac.new(k, hmac_input, hashlib.sha256).digest()
    return key_material[?:?]                     # MAC key = ?


# ── frame parser ───────────────────────────────────────────────────────────────

def parse_frame(raw: bytes) -> dict:
    """
    Parse a raw 802.15.4 Data frame (starting at Frame Control).

    Works by advancing an offset pointer through each field in wire order,
    using the addressing mode bits from the Frame Control to decide which
    optional fields are present — exactly as described in IEEE 802.15.4-2006 §7.2.
    """
    # The ESP-IDF 802.15.4 driver appends 2 bytes of RSSI/LQI metadata
    # in place of the hardware FCS at the end of every received frame.
    # Strip them before parsing so MIC slicing is correct.
    raw = raw[:-2]

    off = 0 # offsets to get the payload

    # ── Frame Control (§7.2.1.1, Table 65) ───────────────────────────────────
    # 2 bytes, little-endian. Bit fields tell us the frame type and which
    # address/security fields follow.
    fc_word       = struct.unpack_from('<H', raw, off)[0]; off += 2
    security_en   = (fc_word >>  3) & 0x1   # bit 3: Auxiliary Security Header present
    pan_compress  = (fc_word >>  6) & 0x1   # bit 6: Source PAN ID omitted
    dst_addr_mode = (fc_word >> 10) & 0x3   # bit 10-11: Destination Addressing Mode
    src_addr_mode = (fc_word >> 14) & 0x3   # bit 15:14: Source Addressing Mode

    seq = raw[off]; off += 1

    dst_pan = struct.unpack_from('<H', raw, off)[0]; off += 2

    if   dst_addr_mode == 2: off += 2
    elif dst_addr_mode == 3: off += 8

    if not pan_compress and src_addr_mode != 0:
        off += 2

    # ── TODO §7.2.1.7 ─────────────────────────────────────────────
    # This feeds into the CCM nonce, you need it
    src_eui64 = raw[off: off + ?]; off += ?

    if not security_en:
        raise ValueError("Security Enabled bit not set — frame is unencrypted")

    # Security Control (§7.6.1.2, Table 95/96): 1 byte
    #   bits [2:0] = Security Level (5 = ENC-MIC-32)
    #   bits [4:3] = Key ID Mode    (2 = KeySource(4B) + KeyIndex(1B))
    sec_ctrl    = raw[off]; off += 1
    sec_level   = sec_ctrl & 0x07
    key_id_mode = (sec_ctrl >> 3) & 0x03

    # Used in the CCM nonce TODO
    frame_ctr_raw = raw[off: off + ?]; off += ?
    frame_ctr     = struct.unpack('<I', frame_ctr_raw)[0]

    # Used Somewhere TODO
    key_source = raw[off: off + ?]; off += ?

    key_index  = raw[off]; off += ?

    # ── AAD boundary ─────────────────────────────────────────────────────────
    # Per §7.6.3.4: AAD = all bytes from Frame Control through end of Aux
    # Security Header (Key Index inclusive) = offsets [0 : off] = 25 bytes.
    # These are authenticated (MIC covers them) but not encrypted.
    aad = raw[:off]

    # ── Ciphertext and MIC ────────────────────────────────────────────────────
    # Everything after the header: ciphertext (N bytes) then MIC (4 bytes).
    # We slice from the forward offset rather than from the end, so any
    # trailing bytes (e.g. if the capture has extra metadata) don't corrupt
    # the MIC slice.
    payload    = raw[off:]           # ciphertext + MIC
    ciphertext = payload[:-4]        # all but last 4
    mic        = payload[-4:]        # last 4 bytes = MIC-32

    # ── Nonce (§7.6.3.4) ─────────────────────────────────────────────────────
    # 13 bytes TODO
    nonce = bytes(?) + ? + bytes([?])

    return {
        'dst_pan':     dst_pan,
        'src_eui64':   src_eui64,
        'frame_ctr':   frame_ctr,
        'sec_level':   sec_level,
        'key_id_mode': key_id_mode,
        'key_source':  key_source,
        'key_index':   key_index,
        'nonce':       nonce,
        'aad':         aad,
        'ciphertext':  ciphertext,
        'mic':         mic,
    }


# ── main decrypt routine ───────────────────────────────────────────────────────

def decrypt(frame_hex: str, n_key_hex: str) -> bytes:
    raw     = bytes.fromhex(frame_hex.replace(' ', '').replace(':', ''))
    k = bytes.fromhex(n_key_hex.replace(' ', '').replace(':', ''))

    if len(k) != 16:
        print(f"[-] ??_key_hex must be exactly 16 bytes (32 hex chars), got {len(k)}")
        sys.exit(1)

    try:
        info = parse_frame(raw)
    except (ValueError, struct.error) as e:
        print(f"[-] frame parse error: {e}")
        sys.exit(1)

    mac_key = derive_mac_key(k, info['key_source'])

    # Print every derived value so participants can verify each step
    print()
    print("── parsed frame ──────────────────────────────────")
    print(f"  dest PAN ID    : 0x{info['dst_pan']:04X}")
    print(f"  src EUI-64     : {info['src_eui64'].hex(' ')}")
    print(f"  frame counter  : {info['frame_ctr']}")
    print(f"  security level : {info['sec_level']} ")
    print(f"  key ID mode    : {info['key_id_mode']} ")
    print(f"  key source     : {info['key_source'].hex()}  (KeySequence = {int.from_bytes(info['key_source'], 'big')})")
    print(f"  key index      : {info['key_index']}")
    print()
    print("── key derivation ────────────────────────────────")
    print(f"  HMAC-SHA256(?, ? || ?)[16:32]")
    print(f"  mac key        : {mac_key.hex()}")
    print()
    print("── CCM inputs ────────────────────────────────────")
    print(f"  nonce (13B)    : {info['nonce'].hex()}")
    print(f"  AAD   ({len(info['aad']):2d}B)    : {info['aad'].hex()}")
    print(f"  ciphertext     : {info['ciphertext'].hex()}")
    print(f"  MIC   ( 4B)    : {info['mic'].hex()}")

    cipher = AES.new(mac_key, AES.MODE_CCM, nonce=info['nonce'], mac_len=4)
    cipher.update(info['aad'])

    # Maybe do something here if youre having trouble 
    try:
        plaintext = cipher.decrypt_and_verify(info['ciphertext'], info['mic'])
    except ValueError:
        print()
        print("── result ────────────────────────────────────────")
        print("  MIC verification failed.")
        print("  Check your key derivation, nonce construction, and AAD.")
        sys.exit(1)

    print()
    print("── result ────────────────────────────────────────")
    print("  MIC verified ✓")
    print()
    print("=" * 50)
    print(f"  {plaintext.decode('utf-8', errors='replace')}")
    print("=" * 50)
    print()
    return plaintext


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    decrypt(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()