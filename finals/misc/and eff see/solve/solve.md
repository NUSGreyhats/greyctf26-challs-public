# Stage 1 Solve — NTAG213 Snack Card

> Constraint: solvers read the card with an **NFC phone app** (or a USB NFC
> reader). No Proxmark / Flipper required. The only "tool" you truly need is
> something that can send an NTAG **password auth** (`PWD_AUTH`) — most NFC
> phone apps can.

## TL;DR

1. Read the card. Most pages dump fine; a range of pages is locked.
2. The open pages contain the card **UID** and a note: `xor uid halves!!`.
3. Password = `UID[0:4] XOR UID[3:7]` (a 4-byte value).
4. Authenticate with that password, read the locked pages — the flag is there in
   plaintext.

The card UID is unique per card, so the password differs per card. The example
below uses UID `04 A1 B2 C3 D4 E5 F6`; substitute your own card's UID.

---

## Step 1 — Extract what's readable

Tap the card with an NFC app. Good free options:

- **NXP TagInfo** (Android/iOS) — identifies the chip and dumps readable pages.
- **NFC Tools** (Android/iOS) — read + raw records.
- **MIFARE++ Ultralight** (Android) — can also send a **password** (needed in
  Step 4).

You'll see the tag identified as **NTAG213** (an NFC Forum Type 2 tag — flat
4-byte pages, *no* sector keys or Crypto1). A dump of the open pages looks like:

```
Page 0-1 : 04 A1 B2 C3  D4 E5 F6 ..   <- UID = 04 A1 B2 C3 D4 E5 F6
Page 4   : 78 6F 72 20   "xor "
Page 5   : 75 69 64 20   "uid "
Page 6   : 68 61 6C 76   "halv"
Page 7   : 65 73 21 21   "es!!"
Page 8+  : --  --  --    (read fails / returns 00 -- locked)
```

So you have two readable facts: the **UID** and the note **`xor uid halves!!`**.

## Step 2 — Spot the protection

Pages 8 onward won't read. That's NTAG213 **password protection**: the config
sets `AUTH0 = 0x08` (protect from page 8) with read+write protection, so reads of
those pages need a 32-bit password (`PWD_AUTH`, command `0x1B`).

Brute force is hopeless — 2³² passwords at NFC speed is years. The note tells you
the password is *derived*, not guessed.

## Step 3 — Recover the password

The note `xor uid halves!!` means: split the 7-byte UID into two overlapping
4-byte halves and XOR them.

```
UID         = 04 A1 B2 C3 D4 E5 F6
front (0:4) = 04 A1 B2 C3
back  (3:7) =       C3 D4 E5 F6
```

### Without tools (by hand)

XOR the two 4-byte halves byte-by-byte:

```
04 ^ C3 = C7
A1 ^ D4 = 75
B2 ^ E5 = 57
C3 ^ F6 = 35
---------------
PWD = C7 75 57 35
```

(Each byte: write both in binary or use any hex calculator; XOR is "bits differ →
1".) Password = **`C7755735`**.

### With tools (script)

```python
uid = bytes.fromhex("04A1B2C3D4E5F6")          # your card's UID
pwd = bytes(uid[i] ^ uid[i + 3] for i in range(4))
print("PWD =", pwd.hex().upper())              # -> C7755735
```

Or paste the UID into CyberChef and XOR the two halves.

## Step 4 — Unlock and read the flag

### Without tools (phone app, manual)

Use an app that accepts a password, e.g. **MIFARE++ Ultralight**:

1. Read the tag.
2. Enter the password `C7755735` in the app's password / `PWD_AUTH` field.
3. Re-read — pages 8+ now return data. Read them as ASCII.
4. Convert the hex pages to text by hand (or paste into CyberChef → "From Hex"):

```
67 72 65 79 7B 30 68 5F ...  ->  grey{0h_...
```

### With tools (automated, USB NFC reader)

With a cheap USB reader (ACR122U / PN532) and Python `nfcpy`:

```python
import nfc

def derive(uid):
    return bytes(uid[i] ^ uid[i + 3] for i in range(4))

def on_connect(tag):
    uid = bytes(tag.identifier)             # 7-byte UID
    pwd = derive(uid)
    tag.transceive(b"\x1B" + pwd)           # PWD_AUTH -> returns PACK
    data = b""
    for p in range(8, 28, 4):               # READ (0x30) returns 4 pages each
        data += tag.transceive(bytes([0x30, p]))[:16]
    print(data.rstrip(b"\x00").decode())

nfc.ContactlessFrontend("usb").connect(rdwr={"on-connect": on_connect})
```

(Same idea works from an Android app with a raw-command feature: send
`1B C7 75 57 35`, then `30 08`, `30 0C` … and decode the responses.)

## Flag

```
grey{0h_i_s33_y0u_4re_qu1te_g00d_at_th1s_nfc_th1n9_HuH}
```

---

## Notes for solvers

- The password is **per-card** — it depends on that card's UID. Re-derive it for
  each card; there is no single universal password.
- You cannot read the protected pages from an offline dump alone — the locked
  pages aren't in it. You need live access to the card to authenticate. Any
  NFC-capable phone with a password-aware app is enough; no Proxmark/Flipper.
- `hf mfu pwdgen` and Flipper's built-in NTAG unlock try *known* derivation
  algorithms — this one is custom, so those auto-attempts won't crack it. The
  on-card hint is the intended route.
