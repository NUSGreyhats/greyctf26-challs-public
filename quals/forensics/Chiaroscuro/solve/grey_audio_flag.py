import numpy as np
import wave

def encode(input_wav, output_wav, message, chunk_size=None):
    with wave.open(input_wav, 'rb') as w:
        params = w.getparams()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).copy()

    bits = ''.join(format(ord(c), '08b') for c in message)
    msg_len = len(bits)
    print(msg_len)

    min_size = 2 ** int(np.ceil(np.log2(2 * msg_len)))
    if chunk_size is None:
        chunk_size = min_size
    else:
        if chunk_size & (chunk_size - 1) != 0 or chunk_size <= 0:
            raise ValueError(f"chunk_size must be a power of 2, got {chunk_size}")
        if chunk_size < 2 * msg_len:
            raise ValueError(
                f"chunk_size={chunk_size} too small for {msg_len}-bit message; "
                f"need at least {min_size}"
            )

    if len(audio) < chunk_size:
        raise ValueError(f"audio is shorter than one chunk ({len(audio)} < {chunk_size})")

    # only touch the first chunk; everything after that stays bit-exact original
    first = audio[:chunk_size].astype(np.float64)
    rest  = audio[chunk_size:]

    spectrum = np.fft.fft(first)
    mags   = np.abs(spectrum)
    phases = np.angle(spectrum)
    # After computing mags and phases, before placing phases:

    mid = chunk_size // 2
    msg_phases = np.array([-np.pi/2 if b == '1' else np.pi/2 for b in bits])

    THRESHOLD = 1000  # tune as needed

    mags[mid - msg_len:mid] = np.maximum(mags[mid - msg_len:mid], THRESHOLD)
    mags[mid + 1:mid + 1 + msg_len] = np.maximum(mags[mid + 1:mid + 1 + msg_len], THRESHOLD)

    phases[mid - msg_len:mid] = msg_phases
    phases[mid + 1:mid + 1 + msg_len] = -msg_phases[::-1]

    new_first = np.fft.ifft(mags * np.exp(1j * phases)).real
    new_first = np.clip(new_first, -32768, 32767).astype(np.int16) # we only overwrite the first chunk  

    out = np.concatenate([new_first, rest])

    with wave.open(output_wav, 'wb') as w:
        w.setparams(params)
        w.writeframes(out.tobytes())

    print(f"encoded {msg_len} bits, chunk_size={chunk_size}")
    return chunk_size, msg_len


def decode(wav_path, chunk_size, msg_len):
    with wave.open(wav_path, 'rb') as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

    phases = np.angle(np.fft.fft(audio[:chunk_size]))
    mid = chunk_size // 2
    bits = ''.join('1' if p < 0 else '0' for p in phases[mid - msg_len:mid])
    return ''.join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))


if __name__ == '__main__':
    flag = 'grey{p41n73d_47_p1_0v3r_7w0}'
    chunk_size, msg_len = encode('modified_alicia.wav', 'output.wav', flag)
    # print('recovered:', decode("output_metadata_modified.wav", 512, 224))