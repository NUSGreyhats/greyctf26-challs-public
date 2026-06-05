#!/usr/bin/env python3
import os
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

FLAG = b"grey{REDACTED}"
KEY = os.urandom(16)
IV = os.urandom(16)

def xor_bytes(b1, b2):
    return bytes(x ^ y for x, y in zip(b1, b2))

def encrypt(key, iv, plaintext):
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = b""
    state = iv
    
    for i in range(0, len(plaintext), 16):
        p_block = plaintext[i:i+16]
        c_block = cipher.encrypt(xor_bytes(p_block, state))
        ciphertext += c_block
        state = xor_bytes(p_block, c_block)
        
    return ciphertext

def decrypt(key, iv, ciphertext):
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
    return all(32 <= b <= 126 for b in block)

def main():
    encrypted_flag = encrypt(KEY, IV, FLAG)
    
    print(f"Encrypted flag: {encrypted_flag.hex()}")
    
    while True:
        try:
            user_input = input("\nEnter ciphertext (hex) to decrypt: ").strip()
            if not user_input:
                continue
            
            ciphertext = bytes.fromhex(user_input)

            if len(ciphertext) != len(encrypted_flag):
                print(f"Error: Ciphertext must be exactly {len(encrypted_flag)} bytes.")
                continue

            if ciphertext == encrypted_flag:
                print("lol no")
                continue
                
            plaintext = decrypt(KEY, IV, ciphertext)

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
        except Exception as e:
            print("An error occurred.")

if __name__ == "__main__":
    main()