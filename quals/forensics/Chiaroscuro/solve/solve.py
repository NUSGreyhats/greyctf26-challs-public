import numpy as np
import wave

def bruteforce_chunk_len(file_name):
    with wave.open(file_name, 'rb') as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

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

def decode(wav_path):
    chunk_size, msg_len = bruteforce_chunk_len(wav_path)
    with wave.open(wav_path, 'rb') as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    phases = np.angle(np.fft.fft(audio[:chunk_size]))
    mid = chunk_size // 2
    bits = ''.join('1' if p < 0 else '0' for p in phases[mid - msg_len:mid])
    return ''.join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))


print(decode("../dist/painted_audio.wav"))