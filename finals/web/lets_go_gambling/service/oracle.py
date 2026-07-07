import glob, json, os, secrets, time
import requests
from Crypto.Hash import keccak


def k(x):
    h = keccak.new(digest_bits=256)
    h.update(x)
    return h.hexdigest()


def rpc(p, m, a=None):
    return requests.post(f"http://127.0.0.1:{p}", json={"jsonrpc": "2.0", "id": 1, "method": m, "params": a or []}, timeout=3).json().get("result")


requested = "0x" + k(b"Requested(uint256)")
target = "0x" + k(b"TARGET()")[:8]
fulfill = "0x" + k(b"fulfill(uint256,bytes32)")[:8]
state = {}

while True:
    for path in glob.glob("/tmp/instances-by-uuid/*"):
        try:
            uuid = os.path.basename(path)
            if not os.path.exists(f"/tmp/{uuid}"):
                continue
            port = json.load(open(path))["port"]
            s = state.setdefault(uuid, {"block": 0})
            if "target" not in s:
                setup = json.load(open(f"/tmp/{uuid}"))["address"]
                s["target"] = "0x" + rpc(port, "eth_call", [{"to": setup, "data": target}, "latest"])[-40:]
                s["oracle"] = rpc(port, "eth_accounts")[0]
            latest = int(rpc(port, "eth_blockNumber"), 16)
            if latest >= s["block"]:
                logs = rpc(port, "eth_getLogs", [{"fromBlock": hex(s["block"]), "toBlock": hex(latest), "address": s["target"], "topics": [requested]}]) or []
                s["block"] = latest + 1
                for log in logs:
                    i = int(log["topics"][1], 16)
                    data = fulfill + f"{i:064x}{secrets.randbelow(100):064x}"
                    rpc(port, "eth_sendTransaction", [{"from": s["oracle"], "to": s["target"], "data": data, "gas": hex(500000), "gasPrice": "0x0"}])
                    rpc(port, "evm_mine")
        except Exception as e:
            print(e, flush=True)
    time.sleep(0.2)
