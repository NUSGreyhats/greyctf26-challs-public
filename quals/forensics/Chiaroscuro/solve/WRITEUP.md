# Chiaroscuro — Writeup

**Category:** Forensics / Steganography
**Author:** Hexerberg
**Flag:** `grey{p41n73d_47_p1_0v3r_7w0}`

## Challenge

> I recently went to art school to brush up my skills before I apply to join the world-renowned greyhats publicity team. I picked up an unusual technique there: painting onto sound. I tried it on this piano piece. To the untrained ear, nothing is amiss.

Solvers are handed a single `painted_audio.wav` — a piano piece from *Clair Obscur: Expedition 33* — and told something is hidden inside.

## Recon: the obvious paths are dead ends

The natural first moves all turn up empty, which is the point:

- **Listen.** Clean piano. No clicks, no buzz, no static, no DTMF.
- **Spectrogram.** Nothing drawn, no hidden tones, no Morse along a frequency band.
- **LSB / amplitude steg.** stegoVeritas, Audacity bit-depth analysis, sonic-visualizer — silent.
- **`strings` / `binwalk`.** The PCM body is unremarkable; no appended payloads.

This is intentional. The title is **Chiaroscuro** for a reason: the secret lives in something that *isn't* visible.

## The hint lives in metadata

`exiftool` (or `ffprobe`) on the file reveals a comment field:

```
$ exiftool output.wav
...
Comment : Le clair se décale vers l'obscur. Seul le prélude fut repeint.
```

3 things to notice:

1. **"Le clair... l'obscur"** — the game's title (and the challenge name) are embedded directly in the sentence.
2. **"se décale"** — the French verb *décaler* means *to shift*. More specifically, *décalage de phase* is the standard French term for **phase shift**.
3. **"Seul le prélude fut repeint"** - Only the prelude was painted over, a hint that only the first chunk was modified 

The hint is announcing, in the most flavorful way possible: this is **phase-coding steganography** and of only the first chunk.

## Phase coding, briefly

Any audio sample can be decomposed into a sum of sinusoids — that's what the FFT gives you. Each frequency bin carries two pieces of information: a **magnitude** (how loud the sinusoid is) and a **phase** (when it crests).

Spectrograms only render magnitude. Human ears are also relatively insensitive to absolute phase. That makes phase a perfect hiding place: invisible to the spectrogram, inaudible to a listener.

Phase coding works like this:

1. Take the first chunk of audio — a power-of-2 number of samples.
2. FFT it into magnitudes and phases.
3. **Overwrite** specific phase values in the lower half of the spectrum with `±π/2`:
   - `+π/2` encodes a `0` bit
   - `−π/2` encodes a `1` bit
4. Mirror those phases (negated, reversed) into the upper half so the IFFT produces a real signal.
5. IFFT, write back, leave the rest of the audio bit-exact.

This is what the description means by "painting onto sound." And the flag itself — `p41n73d_47_p1_0v3r_7w0`, *painted at pi over two* — tells you exactly where the brush touched.

## Solution

A decoder needs two parameters: `chunk_size` (power of 2) and `msg_len` (number of hidden bits). Both are recoverable from the file itself, because the encoder leaves a clear fingerprint: a contiguous run of bins whose phase is suspiciously close to `±π/2`. However, due to random noise also having points that are close to `±π/2`, this can lead to an overestimation of the length of the message, and thus an erroneous decoding of the flag.

We thus employ a strategy of walking backwards, to find the largest continuous region with phases near `±π/2`, that ends in `mid - 1`

```python
    for chunk_size in [128, 256, 512, 1024, 2048, 4096]:
        phases = np.angle(np.fft.fft(audio[:chunk_size]))
        mid = chunk_size // 2

        # walk backwards from mid-1, stop at first non-suspicious bin, due to natural noise having phase +- pi / 2
        msg_len = 0
        for i in range(mid - 1, -1, -1):
            if abs(abs(phases[i]) - np.pi / 2) < 0.05:
                msg_len += 1
            else:
                break

        if msg_len >= 6 * 8: # at least the number of bits needed to represent grey{} 
            print(f"chunk_size={chunk_size}, msg_len={msg_len}")
            return chunk_size, msg_len
    return None, None
```

For this challenge that resolves to `chunk_size = 512`, `msg_len = 224` — which is exactly `28 × 8`, the length of the flag in bits.

Only the first chunk of audio was modified, thus leaving the audio without any noticeable beeps or buzzing, as the other chunks of audio are the exact same.

Decoding is a handful of lines:

```python
def decode(wav_path):
    chunk_size, msg_len = bruteforce_chunk_len(wav_path)
    with wave.open(wav_path, 'rb') as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    phases = np.angle(np.fft.fft(audio[:chunk_size]))
    mid = chunk_size // 2
    bits = ''.join('1' if p < 0 else '0' for p in phases[mid - msg_len:mid])
    return ''.join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))


print(decode("../dist/painted_audio.wav"))
# grey{p41n73d_47_p1_0v3r_7w0}
```

## Flag

```
grey{p41n73d_47_p1_0v3r_7w0}
```

## Closing notes

The track is "Alicia" from *Clair Obscur: Expedition 33* — fitting, given the game's central conceit of a Paintress who paints things into and out of existence. The title, the metadata hint, the technique, and the flag all converge on the same idea: **what's hidden isn't gone, it's just shifted out of sight.**