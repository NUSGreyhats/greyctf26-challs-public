import random
from itertools import cycle

FLAG = "grey{d4t4_4n4ly71c5_15_m4th_15_cRyp70_l0l_s1xs3v3n67676767}"

class PRNG:
    r = 0
    x = 0
    ct = 0
    
    def __init__(self, r, x):
        self.r = r
        self.x = x
        
        for i in range(1000):
            self.step()
            
    def step(self):
        self.x = self.r * self.x * (1-self.x)
        self.ct += 1
        
    def generate(self):
        while self.ct <= 3000:
            self.step()
            byte = int(self.x * 256)
            yield byte


RR = 3.676 + random.random() * 0.000767676767

RR = float("%.15f"%RR)

start = random.random()

SECRET = random.randbytes(16)
print(RR)

p = PRNG(RR, start)

xor = lambda x, y : bytes(a^b for a, b in zip(x, y))

def encrypt(pt):
    ct = xor(xor(p.generate(), pt), cycle(SECRET))
    return ct

try:
    while True:
        
            msg = bytes.fromhex(input("Enter message (in hex): "))

            if (msg == SECRET):
                print("stop hacking!!!!!!!!1")
                print(FLAG)
                break
                
            t = encrypt(msg)

            if (len(t) == 0):
                break

            print(t.hex())
    
except Exception as e:
    pass
