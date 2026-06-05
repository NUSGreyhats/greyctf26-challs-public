import random

NFUNCS = 100
NFLOWS = 100

msg = ""

FNAMES = []
for i in range(NFUNCS):
    fname = "".join(random.sample("abcdefghijklmnopqrstuvwxyz", 5))
    FNAMES.append(fname)
MIS = []

res = lambda x, As, y, i : ["", f"{FNAMES[(i+1) % len(FNAMES)]}(d);"][i+1 < NFUNCS] + "break;" if x >= NFLOWS - 1 else \
    f"tmp = {As[x+1]};" + f"*d {random.sample("+-*^", 1)[0]}= {(2*random.getrandbits(64)+1) % 2**64}u;"

for fi in range(NFUNCS):
    fname = FNAMES[fi]
    As = [random.getrandbits(32) for _ in range(NFLOWS)]
    order = list(range(NFLOWS))
    y = random.randrange(1, NFLOWS)
    random.shuffle(order)
    mi = f"""
void {fname}(unsigned long long*  d) {{
    unsigned int tmp = {As[0]};
    while (1) {{
        if (tmp == {As[order[0]]}) {{{res(order[0], As,y,fi)}}}"""
    for i in range(1, NFLOWS):
        mi += f"\n        else if (tmp == {As[order[i]]}) {{{res(order[i], As,y,fi)}}}"
    mi += f"""
    }}
}}
"""
    msg = mi + msg

msg = """
#include <cstdio>
""" + msg
msg += f"""
int main() {{
    unsigned long long d, e;
    printf(">> ");
    scanf("%llu", &d);
    e = d;
    {FNAMES[0]}(&d);
    if (d == 0x67696d65666c6167) {{
        printf(\"grey{{%llu}}\\n\", e);
    }} else {{
        printf(\"X\\n\");
    }}
}}
"""
open("src.cpp","w").write(msg)

# g++ src.cpp -o src.exe -O0