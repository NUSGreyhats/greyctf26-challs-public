# Solve - Gachapon NFC Checker

## Goal

Make a MIFARE Classic card that the `gachapon` firmware accepts as having enough
balance to trigger the servo.

This solve does not use `provision.ino`. Treat the checker firmware as the
target and derive the accepted card format from it.

## 1. Identify The Target

The provided binary is an ESP32-C3/RISC-V Arduino firmware:

```sh
file gachapon
```

Useful strings immediately show the validation flow:

```sh
strings -a gachapon | grep -E 'GREYGachaCard|Bad CRC|Balance|Insufficient|Card valid'
```

Relevant strings:

```text
GREYGachaCard
Bad CRC
Bad marker
Bad version
Balance:
Insufficient balance
Card valid. Moving servo.
```

The symbols are not stripped, so the interesting function names are also
visible:

```sh
nm -C gachapon | grep -E 'checkCardBalance|crc32|u32'
```

The checker reads a MIFARE Classic card using a PN532 reader. The only key in the
firmware is the default transport key:

```text
FF FF FF FF FF FF
```

## 2. Recover The Card Record Format

The checker authenticates and reads sector 4:

```text
block 16
block 17
```

Those two 16-byte blocks are concatenated into a 32-byte record.

The record layout is:

```text
offset  size  meaning
0       13    ASCII marker: GREYGachaCard
13      1     version: 01
14      4     balance in cents, uint32 little-endian
18      4     CRC32 over record bytes 0..17, uint32 little-endian
22      10    padding, ignored
```

The checker accepts the record only if:

```text
record[0:13] == "GREYGachaCard"
record[13]   == 0x01
stored_crc   == crc32(record[0:18])
balance      >= 670000
```

The CRC is standard CRC32/IEEE:

```text
poly    = 0xEDB88320
initial = 0xFFFFFFFF
final   = bitwise NOT
```

## 3. Build A Valid Record

The required balance is `670000` cents:

```text
670000 decimal = 0x000A3930
little-endian  = 30 39 0A 00
```

The CRC input is the 18-byte prefix:

```text
47 52 45 59 47 61 63 68 61 43 61 72 64 01 30 39 0A 00
G  R  E  Y  G  a  c  h  a  C  a  r  d  v  balance...
```

Using standard CRC32, the checksum is:

```text
crc32 = 0x7D620DBA
little-endian bytes = BA 0D 62 7D
```

So the full 32-byte accepted record is:

```text
47 52 45 59 47 61 63 68 61 43 61 72 64 01 30 39
0A 00 BA 0D 62 7D 00 00 00 00 00 00 00 00 00 00
```

Write the first 16 bytes to block 16:

```text
47 52 45 59 47 61 63 68 61 43 61 72 64 01 30 39
```

Write the next 16 bytes to block 17:

```text
0A 00 BA 0D 62 7D 00 00 00 00 00 00 00 00 00 00
```

## 4. Patch A Raw Dump

For a raw MIFARE Classic 1K dump, each block is 16 bytes.

```text
block 16 offset = 16 * 16 = 0x100
balance offset  = 0x10e
crc offset      = 0x112
```

A minimal patcher:

```python
#!/usr/bin/env python3
import binascii
import struct
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit(f"usage: {sys.argv[0]} input.bin output.bin")

dump = bytearray(Path(sys.argv[1]).read_bytes())
if len(dump) != 1024:
    raise SystemExit("expected a raw 1024-byte MIFARE Classic 1K dump")

record_offset = 16 * 16
marker = b"GREYGachaCard"
version = b"\x01"
balance = struct.pack("<I", 670000)

head = marker + version + balance
crc = struct.pack("<I", binascii.crc32(head) & 0xFFFFFFFF)
record = (head + crc).ljust(32, b"\x00")

dump[record_offset:record_offset + 32] = record
Path(sys.argv[2]).write_bytes(dump)
```

Run it:

```sh
python3 patch.py card.bin card-patched.bin
```

Then restore the patched dump to a writable MIFARE Classic-compatible card. With
Proxmark on a compatible magic card, that is typically:

```text
hf mf cload -f card-patched.bin
```

## 5. Present The Card

When the checker sees the patched card, the serial output should reach:

```text
Balance: 670000
Card valid. Moving servo.
```

At that point the servo moves, which is the challenge success condition.
