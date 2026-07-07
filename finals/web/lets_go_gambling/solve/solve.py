import argparse
import re
import socket
import time
from pathlib import Path

from eth_account import Account
from solcx import compile_standard, install_solc, set_solc_version
from web3 import Web3


def eth_attr(obj, *names):
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(names[0])


def raw(signed):
    if hasattr(signed, "raw_transaction"):
        return signed.raw_transaction
    return signed.rawTransaction


def talk(host, port, data):
    s = socket.create_connection((host, port), timeout=10)
    s.settimeout(180)
    out = s.recv(4096)
    s.sendall(data)
    while True:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        out += chunk
    s.close()
    return out.decode(errors="replace")


def selector(sig):
    return Web3.keccak(text=sig)[:4]


def call_uint(w3, to, data):
    return int.from_bytes(w3.eth.call({"to": to, "data": data}), "big")


def call_bool(w3, to, data):
    return call_uint(w3, to, data) == 1


def call_addr(w3, to, data):
    return Web3.to_checksum_address(w3.eth.call({"to": to, "data": data})[-20:].hex())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host", nargs="?", default="127.0.0.1")
    ap.add_argument("--launcher-port", type=int, default=33267)
    ap.add_argument("--rpc-port", type=int, default=33367)
    ap.add_argument("--attempts", type=int, default=400)
    args = ap.parse_args()

    launch = talk(args.host, args.launcher_port, b"1\n")
    print(launch)
    uuid = re.search(r"uuid:\s*([0-9a-f-]+)", launch).group(1)
    pk = re.search(r"private key:\s*(0x[0-9a-f]+)", launch).group(1)
    setup = Web3.to_checksum_address(re.search(r"setup contract:\s*(0x[0-9a-fA-F]+)", launch).group(1))
    rpc = f"http://{args.host}:{args.rpc_port}/{uuid}"
    w3 = Web3(Web3.HTTPProvider(rpc))
    acct = Account.from_key(pk)

    install_solc("0.8.35")
    set_solc_version("0.8.35")
    src = (Path(__file__).resolve().parent / "Solve.sol").read_text()
    out = compile_standard({
        "language": "Solidity",
        "sources": {"Solve.sol": {"content": src}},
        "settings": {"outputSelection": {"*": {"*": ["evm.bytecode.object"]}}},
    })
    bytecode = out["contracts"]["Solve.sol"]["Solve"]["evm"]["bytecode"]["object"]
    constructor = setup[2:].lower().rjust(64, "0")
    nonce = eth_attr(w3.eth, "get_transaction_count", "getTransactionCount")(acct.address)
    tx = {
        "value": 10 * 10**18,
        "data": "0x" + bytecode + constructor,
        "gas": 900000,
        "gasPrice": 0,
        "nonce": nonce,
        "chainId": 1337,
    }
    h = eth_attr(w3.eth, "send_raw_transaction", "sendRawTransaction")(raw(acct.sign_transaction(tx)))
    rcpt = eth_attr(w3.eth, "wait_for_transaction_receipt", "waitForTransactionReceipt")(h, timeout=120)
    assert rcpt.status == 1
    solve = rcpt.contractAddress
    target = call_addr(w3, setup, selector("TARGET()"))
    print("rpc", rpc)
    print("solve", solve)
    print("target", target)

    nonce += 1
    step = selector("step()")
    for i in range(args.attempts):
        tx = {"to": solve, "data": step, "gas": 120000, "gasPrice": 0, "nonce": nonce + i, "chainId": 1337}
        eth_attr(w3.eth, "send_raw_transaction", "sendRawTransaction")(raw(acct.sign_transaction(tx)))
    print("broadcasted", args.attempts, "attempts")

    solved_sig = selector("isSolved()")
    legendary_sig = selector("legendary()")
    stock3_sig = selector("stock(uint256)") + (3).to_bytes(32, "big")
    for i in range(240):
        solved = call_bool(w3, setup, solved_sig)
        legendary = call_uint(w3, target, legendary_sig)
        stock3 = call_uint(w3, target, stock3_sig)
        if i % 5 == 0 or solved:
            print(f"poll={i} legendary={legendary} stock3={stock3} solved={solved}")
        if solved:
            break
        time.sleep(1)
    assert call_bool(w3, setup, solved_sig)
    print(talk(args.host, args.launcher_port, b"3\n" + uuid.encode() + b"\n"))


if __name__ == "__main__":
    main()
