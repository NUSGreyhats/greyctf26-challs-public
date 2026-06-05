from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

sys.dont_write_bytecode = True

warnings.filterwarnings("ignore", message="Failed to initialize NumPy*", category=UserWarning)
import torch

from common import DEFAULT_PAYLOAD, PAYLOAD_LEN, PUBLIC_FILES, PUBLIC_KEYS, payload_to_flag


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


def run_py(args: list[str], cwd: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, check=False, env=env)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def run_checker(flag: str) -> tuple[int, str, str]:
    return run_py([sys.executable, str(DIST_DIR / "check.py"), flag], DIST_DIR)


def audit_public_bundle(expected_payload: str) -> None:
    files = {path.name for path in DIST_DIR.iterdir() if path.is_file()}
    dirs = [path.name for path in DIST_DIR.iterdir() if path.is_dir()]
    if files != set(PUBLIC_FILES) or dirs:
        raise SystemExit(f"unexpected dist contents: files={sorted(files)} dirs={dirs}")
    raw = torch.load(DIST_DIR / "model.pt", map_location="cpu")
    if set(raw) != PUBLIC_KEYS:
        raise SystemExit(f"unexpected public checkpoint keys: {sorted(raw)}")
    size = (DIST_DIR / "model.pt").stat().st_size
    if size > 2_000_000:
        raise SystemExit(f"public model.pt is too large: {size} bytes")
    forbidden = [
        b"metadata.json",
        b"expected_payload",
        b"char_masks",
        b"pair_tables",
        b"triple_tables",
        b"target_residue",
        b"cell.write.weight",
        b"cell.unpack.weight",
        b"hidden.project.weight",
        b"readout.project.weight",
        b"gate.update.weight",
        b"memory.recurrent.weight",
        b"b.i",
        b"b.v",
        b"b.s",
        expected_payload.encode(),
        payload_to_flag(expected_payload).encode(),
    ]
    paths = [p for p in DIST_DIR.rglob("*") if p.is_file()]
    for path in paths:
        data = path.read_bytes()
        for token in forbidden:
            if token in data:
                raise SystemExit(f"{path} leaks forbidden token {token!r}")
    int_keys = [key for key, value in raw.items() if not value.is_floating_point() and key != "config.meta"]
    if int_keys:
        raise SystemExit(f"public checkpoint exposes non-config integer tensors: {int_keys}")


def audit_folder_independence() -> None:
    bad_tokens = {
        ROOT / "dist": ("from chall", "import chall", "../chall", "from solve", "import solve", "../solve"),
        ROOT / "solve": ("from chall", "import chall", "../chall", "sys.path.insert", "sys.path.append"),
    }
    for folder, tokens in bad_tokens.items():
        for path in folder.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in tokens:
                if token in text:
                    raise SystemExit(f"{path} contains cross-folder import token {token!r}")


def mutate(payload: str, pos: int, repl: str) -> str:
    if payload[pos] == repl:
        repl = "b" if repl != "b" else "c"
    return payload[:pos] + repl + payload[pos + 1 :]


def main() -> None:
    metadata = json.loads((ROOT / "chall" / "metadata.json").read_text(encoding="utf-8"))
    expected_payload = metadata["payload"]
    expected_flag = payload_to_flag(expected_payload)
    audit_public_bundle(expected_payload)
    audit_folder_independence()

    cases = [
        (expected_flag, True),
        (payload_to_flag(mutate(expected_payload, 0, "z")), False),
        (payload_to_flag(mutate(expected_payload, PAYLOAD_LEN // 2, "a")), False),
        (payload_to_flag(mutate(expected_payload, PAYLOAD_LEN - 1, "0")), False),
        (payload_to_flag("a" * PAYLOAD_LEN), False),
        (payload_to_flag((DEFAULT_PAYLOAD[::-1])[:PAYLOAD_LEN]), False),
        (f"grey{{{expected_payload[:-1]}}}", False),
        (f"grey{{{expected_payload}a}}", False),
    ]
    for flag, should_accept in cases:
        rc, stdout, stderr = run_checker(flag)
        accepted = rc == 0 and stdout == "accepted" and stderr == ""
        rejected = rc != 0 and stdout == "rejected" and stderr == ""
        if should_accept and not accepted:
            raise SystemExit(f"checker rejected expected flag: rc={rc} stdout={stdout!r} stderr={stderr!r}")
        if not should_accept and not rejected:
            raise SystemExit(f"checker accepted/reported badly for {flag!r}: rc={rc} stdout={stdout!r} stderr={stderr!r}")

    rc, stdout, stderr = run_py([sys.executable, str(ROOT / "solve" / "solve.py"), "--report"], ROOT)
    if rc != 0:
        raise SystemExit(stdout or stderr or "solve.py failed")
    if expected_flag not in stdout or "Z3 uniqueness: proved" not in stdout:
        raise SystemExit(f"solver report missing expected proof:\n{stdout}\n{stderr}")

    rc, stdout, stderr = run_py(
        [sys.executable, str(ROOT / "chall" / "redteam_suite.py"), "--fast", "--expected-payload", expected_payload],
        ROOT,
    )
    if rc != 0:
        raise SystemExit(stdout or stderr or "redteam fast failed")
    print(f"verified unique payload: {expected_flag}")


if __name__ == "__main__":
    main()
