class word:
    def __init__(self, n:int, s):
        self.len = n
        if type(s) == list:
            self.data = s.copy()
            return
        assert all(i in "abcdefghijklmnopqrstuvwxyz{|}" for i in s) and len(s) == n
        self.data = [0] * self.len
        for i in range(len(s)):
            self.data[i] = ord(s[i]) - ord('a')
    
    def __add__(self, w):
        assert w.len <= self.len
        res = word(self.len, self.data)
        for i in range(w.len - 1, -1, -1):
            res.data[i] = res.data[i] + w.data[i]
            if res.data[i] >= 29:
                res.data[i] -= 29
                if i:
                    res.data[i-1] += 1
        return res

    def __mul__(self, w):
        res = word(self.len, "a"*self.len)
        for i in range(w.len):
            tmp = word(self.len, self.data[i:] + [0]*i)
            for _ in range(w.data[-i-1]):
                res += tmp
        return res
    
    def __xor__(self, w):
        assert w.len == self.len
        res = word(self.len, self.data)
        for i in range(w.len - 1, -1, -1):
            res.data[i] = (res.data[i] ^ w.data[i]) % 29
        return res
    
    def __eq__(self, w):
        return w.len == self.len and all(self.data[i] == w.data[i] for i in range(self.len))
    
    def __str__(self):
        return ''.join(chr(ord('a') + i) for i in self.data)
    
    # added this function in word to simplify calculations
    def str2num(self):
        x = 0
        for p,i in enumerate(self.data[::-1]):
            x += 29**p * i
        return x
    

def caexor(s:str) -> word:
    assert len(s) % 2 == 0, "Input string must be even length!"
    assert len(s) >= 24, "Input string is too short!"
    h = word(16, "greyctfisawesome")
    c = word(16, "cryptoisverycool")
    f = word(16, "{|}helloworld{|}")
    for i in range(0, len(s), 2):
        h += c
        h *= f
        h ^= word(16, 'a'*14 + s[i:i+2])
    return h

h = word(16, "greyctfisawesome").str2num()
c = word(16, "cryptoisverycool").str2num()
f = word(16, "{|}helloworld{|}").str2num()
TARGET = word(16, "gimmeflagthankuu").str2num()
MOD = 29**16

from sage.all import Matrix, identity_matrix, vector

n = 11
solved = False
while not solved:
    n += 1

    rem = f * c * (1-pow(f, n, MOD)) * pow(1-f, -1, MOD) % MOD
    M = Matrix.column([f**(n - i - 1) for i in range(n)] + [-(TARGET - h*f**n - rem), MOD])
    M = M.augment(identity_matrix(n+1).stack(vector([0] * (n+1))))
    Q = Matrix.diagonal([2**128] + [2**4] * n + [2**8])
    M *= Q
    M = M.BKZ() # BKZ produces more accuracy over LLL on closest vector
    M /= Q
    print(M, 29**2)

    vals = []
    for r in M:
        if r[0] != 0 or abs(r[-1]) != 1:
            continue
        r *= r[-1]
        vals.append(r[1:-1])
    if not vals:
        continue

    for val in vals:
        cnt, tmp_num = 0, word(16, "greyctfisawesome").str2num()
        sstr = ""
        for i, v in enumerate(val):
            tmp_num = (tmp_num + c) * f % MOD
            want = (tmp_num + v) % MOD
            for j in range(29**2):
                j0, j1 = j % 29, j // 29
                w0, w1 = tmp_num % 29, (tmp_num // 29) % 29
                test = ((tmp_num // 29**2) * 29**2 + ((w1 ^ j1) % 29)*29 + ((w0 ^ j0) % 29) ) % MOD
                if test == want:
                    cnt += 1
                    break
            tmp_num = want
            sstr += chr(ord('a') + j1) + chr(ord('a') + j0)
        if cnt == len(val):
            print(sstr, caexor(sstr))
            solved = True
    print("==============================")
    print(f'{n = }')

"""
amdaaeppduhcdcatdzhjajag gimmeflagthankuu
cjpfbkajavhtbncidaanbvab gimmeflagthankuu <-- works
"""