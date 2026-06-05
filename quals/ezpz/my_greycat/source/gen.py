import random
import math

f = open("greyctf-trailer-modified.MOV","rb").read()
print(f"{len(f) = }")
cs = []
ds = []
es = []
n = 257
for i in range(len(f)):
    while True:
        d = random.randrange(1, 256**4) 
        try:
            e = pow(d, -1, n-1)
        except:
            continue
        # print(f"d = {d % (n-1)}")
        ds.append(d)
        d = d % n
        es.append(e)
        p = f[i]
        # c = p^e (mod n)
        # c^d = p (mod n)
        c = pow(p, e, n)
        cs.append(c)
        break

out = open("data.txt", "w")
import json
json.dump(cs, out)
out.write("\n")
json.dump(ds, out)
out.write("\n")
json.dump(es, out)
out.write("\n")
# out.write(cs)
# out.write(ds)
# out.write(es)
# print(f"{cs = }") # cs are the encrypted data 
# print(f"{ds = }") # ds are the exponents used for decryption which are large (can be shrunk mod (n-1))
# print(f"{es = }") # es are the exponents used for encryption which are small
print("finished")
# TODO: make the actual decrypter