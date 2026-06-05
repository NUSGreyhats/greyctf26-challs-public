LEN = 15 # may be different on remote
FLAG = 'grey{fake_flag}' # different on remote

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

TARGET = word(16, "gimmeflagthankuu")
s = str(input(">> "))
if not s.startswith('a') and all(i not in s for i in '{|}') and caexor(s) == TARGET:
    print("Good job!")
    if len(s) > LEN:
        print("Unfortunately, an even shorter preimage exists out there. lmao")
    else:
        print("Congratulations! Here's your flag:")
        print(FLAG)
else:
    print("Unfortunately...")
    print(f"caexor(s) == {caexor(s)}: {caexor(s) == TARGET}")
    print(f"not s.startswith('a'): {not s.startswith('a')}")
    print(f"all(i not in s for i in '{{|}}'): {all(i not in s for i in '{|}')}")
    print("Aw man :<")