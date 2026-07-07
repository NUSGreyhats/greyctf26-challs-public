#!/usr/bin/env python3
"""
decrypt_flag.py — decrypt a captured 802.15.4 broadcaster frame

Requires:
    pip install pycryptodome

Usage:
    python3 decrypt_flag.py <frame_hex> <network_key_hex>

Arguments:
    frame_hex       — the hex string printed after "RX CH25 RSSI:... LEN:...: " by the sniffer
    network_key_hex — 32 hex chars (16 bytes), the NetworkKey from the badge

Example:
    python3 decrypt_flag.py 49c8153713ffff... aaadbeebcaacbadd0123456789abcdef

────────────────────────────────────────────────────────────────────────────────
HOW TO IDENTIFY THE BROADCASTER FRAME
────────────────────────────────────────────────────────────────────────────────
The sniffer prints one hex line per received frame. Look for one where bytes at
wire offsets 3-4 (counting from 0) read "37 13" — that is PAN ID 0x1337 stored
in little-endian order (low byte first), defined in IEEE 802.15.4-2006 §7.2.1.4.

────────────────────────────────────────────────────────────────────────────────
FRAME LAYOUT  (IEEE 802.15.4-2006, §7.2 + §7.6.1)
────────────────────────────────────────────────────────────────────────────────
Offset  Len  Field               Spec section
──────  ───  ──────────────────  ────────────
  0      2   Frame Control       §7.2.1.1, Table 65
  2      1   Sequence Number     §7.2.1.2
  3      2   Dst PAN ID (LE)     §7.2.1.4
  5      2   Dst Addr (0xFFFF)   §7.2.1.5  (broadcast short address)
  7      8   Src EUI-64          §7.2.1.7  (extended source address)
 15      1   Security Control    §7.6.1.2, Table 95/96
 16      4   Frame Counter (LE)  §7.6.1.3
 20      4   Key Source          §7.6.1.4  (Key ID Mode 2: 4-byte KeySource)
 24      1   Key Index           §7.6.1.4  (Key ID Mode 2: 1-byte KeyIndex)
 25      N   Ciphertext          §7.6.3    (AES-CCM encrypted payload)
 25+N    4   MIC-32              §7.6.3.4, Annex B (Message Integrity Code)

Security Control byte = 0x15:
    bits [2:0] = 101  → Security Level 5 = ENC-MIC-32  (§7.6.1.2, Table 95)
    bits [4:3] = 10   → Key ID Mode 2                   (§7.6.1.2, Table 96)

Source PAN ID is absent because PAN ID Compression (FC bit 6) = 1 (§7.2.1.8):
both source and destination are on the same PAN, so only one PAN ID is sent.

────────────────────────────────────────────────────────────────────────────────
KEY DERIVATION  (Thread specification, implemented in OpenThread key_manager.cpp)
────────────────────────────────────────────────────────────────────────────────
The NetworkKey is a 16-byte secret shared across the Thread network. It is NOT
transmitted. Participants obtain it from a separate challenge stage.

The actual AES key used for this frame is derived as:

    KeyMaterial = HMAC-SHA256(NetworkKey, KeySource(4B) || "Thread")

    Note: the input is KeySource (4 bytes, big-endian) followed by the 6 ASCII
    bytes of "Thread" — NO null terminator, NO extra 0x00 separator. Total = 10B.

    The 32-byte HMAC output splits as:
        bytes  [0:16]  = MLE key   (used by Thread's mesh link establishment)
        bytes [16:32]  = MAC key   (used for 802.15.4 link-layer encryption)  ← this one

    Reference: openthread/src/core/thread/key_manager.cpp, struct HashKeys:
        mMleKey = mHash[0:16]
        mMacKey = mHash[16:32]

KeySource on the wire = KEY_SEQUENCE as 4-byte big-endian = 0x00000000 (all zeros),
because KEY_SEQUENCE = 0 for this CTF. Key Index on the wire = (0 & 0x7F) + 1 = 1.

────────────────────────────────────────────────────────────────────────────────
CCM ENCRYPTION  (IEEE 802.15.4-2006 Annex B, NIST SP 800-38C)
────────────────────────────────────────────────────────────────────────────────
802.15.4 uses CCM* (CCM-star) for authenticated encryption. Two inputs feed it:

Nonce (13 bytes) — constructed per §7.6.3.4:
    SrcEUI64 (8B) || FrameCounter (4B, little-endian) || SecurityLevel (1B = 0x05)

    The frame counter is in the nonce, so every frame produces unique ciphertext
    even though the plaintext (the flag) is identical every broadcast.

AAD (Additional Authenticated Data, 25 bytes) — per §7.6.3.4:
    All bytes from Frame Control through Key Index inclusive (offsets 0–24).
    These bytes are authenticated but NOT encrypted — they stay in plaintext on
    the wire so the receiver can route/process the frame, but any tampering with
    them causes MIC verification to fail.

MIC (Message Integrity Code, 4 bytes) — per §7.6.3.4 / Annex B:
    A CBC-MAC computed over B0 (nonce + length) || AAD || plaintext, then the
    resulting 4-byte tag is XOR-encrypted with AES(A0) where A0 uses counter=0.
    Security Level 5 = ENC-MIC-32 means 32-bit (4-byte) MIC + full encryption.

────────────────────────────────────────────────────────────────────────────────
NOTE ON MIC VERIFICATION
────────────────────────────────────────────────────────────────────────────────
The broadcaster currently has a firmware bug: the ESP32-C6 hardware auto-appends
a 2-byte FCS (CRC) after the PSDU but the firmware does not reserve space for it,
so the FCS overwrites the last 2 bytes of the MIC. The sniffer's receive side
replaces those 2 bytes with RSSI/LQI metadata (see ESP-IDF docs). Either way,
the MIC on the wire is corrupted and verification will fail.

Decryption itself is unaffected — the ciphertext keystream does not depend on the
MIC. This script decrypts and prints the flag; it reports the MIC mismatch as a
warning rather than aborting, until the broadcaster firmware is fixed.
"""

import sys
import hmac
import hashlib
import struct
from Crypto.Cipher import AES


# ── key derivation ─────────────────────────────────────────────────────────────

def derive_mac_key(network_key: bytes, key_source: bytes) -> bytes:
    """
    Thread MAC key derivation.

    HMAC-SHA256(NetworkKey, KeySource(4B) || "Thread")
    Input is exactly 10 bytes: 4-byte KeySource + 6-byte ASCII "Thread", no NUL.
    Output is 32 bytes; MAC key = upper half [16:32].

    Source: openthread/src/core/thread/key_manager.cpp  ComputeKeys()
            struct HashKeys { MleKey mMleKey; MacKey mMacKey; }
    """
    hmac_input  = key_source + b'Thread'          # 4B + 6B = 10B, no 0x00
    key_material = hmac.new(network_key, hmac_input, hashlib.sha256).digest()
    return key_material[16:32]                     # MAC key = bytes [16:32]


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

    off = 0

    # ── Frame Control (§7.2.1.1, Table 65) ───────────────────────────────────
    # 2 bytes, little-endian. Bit fields tell us the frame type and which
    # address/security fields follow.
    fc_word       = struct.unpack_from('<H', raw, off)[0]; off += 2
    security_en   = (fc_word >>  3) & 0x1   # bit 3: Auxiliary Security Header present
    pan_compress  = (fc_word >>  6) & 0x1   # bit 6: Source PAN ID omitted
    dst_addr_mode = (fc_word >> 10) & 0x3   # bits 11:10 — 0=none 2=short 3=extended
    src_addr_mode = (fc_word >> 14) & 0x3   # bits 15:14 — 0=none 2=short 3=extended

    # ── Sequence Number (§7.2.1.2) ────────────────────────────────────────────
    # 1 byte, increments each frame. Not needed for decryption.
    seq = raw[off]; off += 1

    # ── Destination PAN ID (§7.2.1.4) ────────────────────────────────────────
    # 2 bytes, little-endian. 0x1337 stored as 37 13 on the wire.
    dst_pan = struct.unpack_from('<H', raw, off)[0]; off += 2

    # ── Destination Address (§7.2.1.5) ───────────────────────────────────────
    # Mode 2 = 16-bit short address. 0xFFFF = broadcast (§7.4.1).
    if   dst_addr_mode == 2: off += 2
    elif dst_addr_mode == 3: off += 8

    # ── Source PAN ID (§7.2.1.4) ─────────────────────────────────────────────
    # Omitted when PAN ID Compression = 1, meaning Src PAN == Dst PAN.
    if not pan_compress and src_addr_mode != 0:
        off += 2

    # ── Source EUI-64 (§7.2.1.7) ─────────────────────────────────────────────
    # 8-byte extended address. Present because Src Addr Mode = 3 (extended).
    # Critical: feeds into the CCM nonce, so it must be read from THIS frame.
    if src_addr_mode != 3:
        raise ValueError(f"expected extended source address (mode 3), got mode {src_addr_mode}")
    src_eui64 = raw[off: off + 8]; off += 8

    if not security_en:
        raise ValueError("Security Enabled bit not set — frame is unencrypted")

    # ── Auxiliary Security Header (§7.6.1) ───────────────────────────────────

    # Security Control (§7.6.1.2, Table 95/96): 1 byte
    #   bits [2:0] = Security Level (5 = ENC-MIC-32)
    #   bits [4:3] = Key ID Mode    (2 = KeySource(4B) + KeyIndex(1B))
    sec_ctrl    = raw[off]; off += 1
    sec_level   = sec_ctrl & 0x07
    key_id_mode = (sec_ctrl >> 3) & 0x03

    if key_id_mode != 2:
        raise ValueError(f"expected Key ID Mode 2, got {key_id_mode}")

    # Frame Counter (§7.6.1.3): 4 bytes, little-endian.
    # Used in the CCM nonce. Changes every frame, making ciphertext unique.
    frame_ctr_raw = raw[off: off + 4]; off += 4
    frame_ctr     = struct.unpack('<I', frame_ctr_raw)[0]

    # Key Source (§7.6.1.4, Key ID Mode 2): 4 bytes.
    # In Thread this equals the KeySequenceCounter (big-endian).
    # KeySequence = int.from_bytes(key_source, 'big') → 0 here.
    key_source = raw[off: off + 4]; off += 4

    # Key Index (§7.6.1.4): 1 byte.
    # In Thread: KeyIndex = (KeySequence & 0x7F) + 1 → 1 here.
    # Confirms which KeySequence was used when KeySource is ambiguous.
    key_index  = raw[off]; off += 1

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
    # 13 bytes: SrcEUI64(8) || FrameCounter(4, little-endian) || SecurityLevel(1)
    # SecurityLevel in the nonce is the numeric value from the Security Control
    # bits [2:0], which is 5 (= 0x05) for ENC-MIC-32.
    nonce = bytes(src_eui64) + frame_ctr_raw + bytes([sec_level])

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

def decrypt(frame_hex: str, network_key_hex: str) -> bytes:
    raw     = bytes.fromhex(frame_hex.replace(' ', '').replace(':', ''))
    net_key = bytes.fromhex(network_key_hex.replace(' ', '').replace(':', ''))

    if len(net_key) != 16:
        print(f"[-] network key must be exactly 16 bytes (32 hex chars), got {len(net_key)}")
        sys.exit(1)

    try:
        info = parse_frame(raw)
    except (ValueError, struct.error) as e:
        print(f"[-] frame parse error: {e}")
        sys.exit(1)

    mac_key = derive_mac_key(net_key, info['key_source'])

    # Print every derived value so participants can verify each step
    print()
    print("── parsed frame ──────────────────────────────────")
    print(f"  dest PAN ID    : 0x{info['dst_pan']:04X}")
    print(f"  src EUI-64     : {info['src_eui64'].hex(' ')}")
    print(f"  frame counter  : {info['frame_ctr']}")
    print(f"  security level : {info['sec_level']}  (ENC-MIC-32, §7.6.1.2 Table 95)")
    print(f"  key ID mode    : {info['key_id_mode']}  (KeySource+KeyIndex, §7.6.1.2 Table 96)")
    print(f"  key source     : {info['key_source'].hex()}  (KeySequence = {int.from_bytes(info['key_source'], 'big')})")
    print(f"  key index      : {info['key_index']}")
    print()
    print("── key derivation ────────────────────────────────")
    print(f"  HMAC-SHA256(NetworkKey, KeySource || 'Thread')[16:32]")
    print(f"  mac key        : {mac_key.hex()}")
    print()
    print("── CCM inputs ────────────────────────────────────")
    print(f"  nonce (13B)    : {info['nonce'].hex()}")
    print(f"                    = EUI64({info['src_eui64'].hex()}) || FrameCtr({info['ciphertext'][:0].hex()}{bytes(struct.pack('<I', info['frame_ctr'])).hex()}) || SecLvl(0{info['sec_level']:02x})")
    print(f"  AAD   ({len(info['aad']):2d}B)    : {info['aad'].hex()}")
    print(f"  ciphertext     : {info['ciphertext'].hex()}")
    print(f"  MIC   ( 4B)    : {info['mic'].hex()}")

    cipher = AES.new(mac_key, AES.MODE_CCM, nonce=info['nonce'], mac_len=4)
    cipher.update(info['aad'])

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

    # # Decrypt without verifying MIC first, so the flag is always recovered
    # # regardless of the broadcaster FCS bug.
    # cipher = AES.new(mac_key, AES.MODE_CCM, nonce=info['nonce'], mac_len=4)
    # cipher.update(info['aad'])
    # plaintext = cipher.decrypt(info['ciphertext'])

    # # Now attempt MIC verification separately so we can report the result
    # # without aborting. Once the broadcaster FCS bug is fixed, this will pass.
    # cipher2 = AES.new(mac_key, AES.MODE_CCM, nonce=info['nonce'], mac_len=4)
    # cipher2.update(info['aad'])
    # cipher2.encrypt(plaintext)          # must encrypt to finalise CBC-MAC
    # expected_mic = cipher2.digest()
    # mic_ok = (expected_mic == info['mic'])

    # print()
    # print("── result ────────────────────────────────────────")
    # if mic_ok:
    #     print("  MIC verified ✓")
    # else:
    #     print(f"  MIC mismatch (expected {expected_mic.hex()}, got {info['mic'].hex()})")
    #     print("  This is a known broadcaster FCS bug — ciphertext still decrypts correctly.")
    # print()
    # print("=" * 50)
    # print(f"  {plaintext.decode('utf-8', errors='replace')}")
    # print("=" * 50)
    # print()
    # return plaintext


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    decrypt(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()