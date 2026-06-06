# fort knockies - Writeup

**Category:** Forensics
**Author:** Dylan
**Flag:** `grey{jz_some_rookie_mistakesi9v2k}`

## Challenge

> hey i make a local password maanger check it out

Solvers receive a saved container image for a small local password-manager style web app. The final filesystem looks cleaned, but the saved image still preserves older layers. The solve is about reconstructing what the developer removed before shipping it.

## Image-layer artifacts

The final container contains the live app, but the useful material is in deleted paths from earlier layers:

- `/app/.env`
- `/app/.git/`
- `/var/lib/fortknockies/.staging/README`

The deletion markers confirm these paths were removed before the final image, but their earlier contents remain recoverable from the image layer data.

## Password reconstruction

The deleted `.env` is mostly routine configuration, but its final dangling line is:

```text
pycache
```

The deleted project history supplies the second half. One commit includes:

```python
part2 = "PATH"
```

These two fragments combine into the password:

```text
pycachePATH
```

## Hidden payload

The deleted staging file is named:

```text
/var/lib/fortknockies/.staging/README
```

Despite the name, it is not a README text file. Its file signature is:

```text
37 7a bc af 27 1c
```

That identifies it as a 7z archive. Extracting it gives two encrypted files:

- `sample-upload.enc`
- `flag.enc`

`sample-upload.enc` follows the live application's current `FKENC1` format and is only a decoy. `flag.enc` uses the older retired format.

## Legacy encryption format

The deleted project history also contains an old `scratch_crypto.py`. That file documents the legacy `FKENC0` import path used by `flag.enc`.

The `FKENC0` format uses:

- PBKDF2-HMAC-SHA1
- 64000 iterations
- AES-256-CBC
- PKCS7 padding

Using the reconstructed password:

```text
pycachePATH
```

`flag.enc` decrypts to the flag.

## Flag

```text
grey{jz_some_rookie_mistakesi9v2k}
```
