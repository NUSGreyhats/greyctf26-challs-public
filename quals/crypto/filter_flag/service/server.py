#!/usr/bin/env python3
import os
import signal
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "120"))

t = str(int(time.time())).encode()
k = b"noflagsharing!!!"
i = b"noflagsharing!!!"
c = AES.new(k, AES.MODE_CBC, iv=i)
tag = (c.encrypt(pad(k + t, 16))).hex().encode()[6:]

# Exactly 80 bytes (5 blocks of 16 bytes)
FLAG = b"grey{" + tag + b"_W4h_uR_Q_gUd_4h}"
KEY = os.urandom(16)
IV = os.urandom(16)

def xor_bytes(b1, b2):
    return bytes(x ^ y for x, y in zip(b1, b2))

def encrypt_pcbc(key, iv, plaintext):
    """
    PCBC Encryption:
    C_i = E_k(P_i ^ P_{i-1} ^ C_{i-1})
    State passed to next block is (P_i ^ C_i)
    """
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = b""
    state = iv
    
    for i in range(0, len(plaintext), 16):
        p_block = plaintext[i:i+16]
        c_block = cipher.encrypt(xor_bytes(p_block, state))
        ciphertext += c_block
        state = xor_bytes(p_block, c_block)
        
    return ciphertext

def decrypt_pcbc(key, iv, ciphertext):
    """
    PCBC Decryption:
    P_i = D_k(C_i) ^ P_{i-1} ^ C_{i-1}
    State passed to next block is (P_i ^ C_i)
    """
    cipher = AES.new(key, AES.MODE_ECB)
    plaintext = b""
    state = iv
    
    for i in range(0, len(ciphertext), 16):
        c_block = ciphertext[i:i+16]
        p_block = xor_bytes(cipher.decrypt(c_block), state)
        plaintext += p_block
        state = xor_bytes(p_block, c_block)
        
    return plaintext

def is_printable(block):
    # Validates if a 16-byte block is fully printable ASCII (32-126)
    return all(32 <= b <= 126 for b in block)

def session_timeout(signum, frame):
    print("Session timed out.")
    raise SystemExit(0)

def main():
    if SESSION_TIMEOUT_SECONDS > 0:
        signal.signal(signal.SIGALRM, session_timeout)
        signal.alarm(SESSION_TIMEOUT_SECONDS)

    encrypted_flag = encrypt_pcbc(KEY, IV, FLAG)
    
    print(f"Encrypted flag: {encrypted_flag.hex()}")
    
    while True:
        try:
            user_input = input("\nEnter ciphertext (hex) to decrypt: ").strip()
            if not user_input:
                continue
            
            ciphertext = bytes.fromhex(user_input)
            
            # Constraint 1: Must be exactly the length of the flag (prevent truncation attacks)
            if len(ciphertext) != len(encrypted_flag):
                print(f"Error: Ciphertext must be exactly {len(encrypted_flag)} bytes.")
                continue
                
            # Constraint 2: Cannot decrypt the exact original flag
            if ciphertext == encrypted_flag:
                print("lol no")
                continue
                
            # Decrypt using our custom PCBC implementation
            plaintext = decrypt_pcbc(KEY, IV, ciphertext)
            
            # Constraint 3: Validity Filter (Prevent ECB-style Chosen Ciphertext Attacks)
            output_blocks = []
            for i in range(0, len(plaintext), 16):
                block = plaintext[i:i+16]
                if is_printable(block):
                    output_blocks.append(block.decode('ascii'))
                else:
                    output_blocks.append("????????????????")
                    
            print("Decrypted: " + "".join(output_blocks))
            
        except ValueError:
            print("Error: Invalid hex string.")
        except EOFError:
            break
        except Exception as e:
            print("An error occurred.")

if __name__ == "__main__":
    # Ensure stdout is unbuffered for xinetd/socat
    main()
