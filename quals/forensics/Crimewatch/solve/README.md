# Crimewatch — Writeup

**Category:** Forensics / Android  
**Author:** x44ylan  
**Flag:** `grey{tobacco_and_vaporisers_control_actdf269}`

## 1. Identify And Decrypt The Android Image

The two anonymous files are Android emulator qcow2 images:

```text
a: userdata qcow2
b: encryption-key qcow2
```

Android file-based encryption is enabled, so the userdata image is not directly readable as a normal ext4 filesystem. Because the device had no lockscreen PIN, the emulator encryption-key image is enough to decrypt it.

One working route is `fbe-decrypt`:

```bash
git clone https://github.com/SlugFiller/fbe-decrypt /tmp/fbe-decrypt
cd crimewatch
cp a userdata-qemu.img.qcow2
cp b encryptionkey.img.qcow2
node /tmp/fbe-decrypt/fbe-decrypt.mjs
```

This produces `userdata-decrypted.img`, which can be inspected with `debugfs`.

Useful roots:

```text
/data/com.grey.telechat/
/data/com.android.providers.media.module/
/system_ce/0/
/system/usagestats/
/media/0/
```

## 2. Buyer Evidence

The live TeleChat database is:

```text
/data/com.grey.telechat/files/telechat.db
```

The `chats` and `messages` tables contain many normal personal/service chats. The most recent buyer-related chat is the lowercase `jiawei` thread:

```text
display_name = jiawei
username     = @jiawei_pickup
message      = im here already
reply        = ok. mango, same as reserved
```

The buyer answer is:

```text
jiawei
```

## 3. Deleted Supplier Evidence

The supplier chat has been removed from the live TeleChat chat list, but deleted/cache residue survives at:

```text
/data/com.grey.telechat/files/telechat.db-wal
/data/com.grey.telechat/files/cache/updates/pts_000091.bin
/system_ce/0/notification_history/notification_history.xml
/system_ce/0/people/people.xml
```

These artifacts tie the deleted supplier thread together:

```text
title       = Vanta Supply
username    = @vanta_supply
preview     = same SG673... import pic attached
media_ref   = cache/media/tc_4392470850.dat
```

The supplier answer is:

```text
@vanta_supply
```

The deleted supplier material only gives a partial plate clue, so the cache image is still required.

## 4. Import Vehicle Plate

The referenced deleted/cache image is:

```text
/data/com.grey.telechat/cache/media/tc_4392470850.dat
```

There is also a shared-media copy:

```text
/media/0/Pictures/TeleChat/IMG_20260514_164900.png
```

The image visibly shows the full import vehicle plate:

```text
SG67301K
```

## 5. Pickup Coordinates

The pickup image is:

```text
/media/0/Pictures/TeleChat/spot.jpg
```

The image has no GPS EXIF, and MediaStore does not store the answer coordinates. The intended solve is light OSINT from the visible scene. The location is Singapore Zoo.

Rounded to 2 decimal places for both latitude and longitude, the coordinate answer is:

```text
1.40,103.79
```

## 6. Decrypt The Flag

The reconstructed answers are:

```text
supplier    = @vanta_supply
plate       = SG67301K
buyer       = jiawei
coordinates = 1.40,103.79
```

Run:

```bash
python3 flag.py @vanta_supply SG67301K jiawei 1.40,103.79
```

Expected output:

```text
[+] grey{tobacco_and_vaporisers_control_actdf269}
```
