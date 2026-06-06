#!/usr/local/bin/python

"""
Forgotten Soviet Intelligence Server — CTF Challenge
A Troupe IFC challenge where players must leak a classified document.
"""

import subprocess
import tempfile
import fcntl
import os
import sys
import signal
import re
import time
import json
import shutil
from datetime import date

# ─── Configuration ───────────────────────────────────────────────────────────

TIMEOUT = int(os.environ.get("TROUPE_TIMEOUT", "10"))
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "45"))
PROCESS_SHUTDOWN_TIMEOUT = 1
MAX_CODE_LENGTH = 600
TERMINAL_TRP = "./terminal.trp"
MAX_TROUPE_EXECUTIONS = int(os.environ.get("MAX_TROUPE_EXECUTIONS", "4"))
TROUPE_SLOT_WAIT_SECONDS = int(os.environ.get("TROUPE_SLOT_WAIT_SECONDS", "30"))
TROUPE_SLOT_DIR = os.environ.get("TROUPE_SLOT_DIR", "/tmp/soviet-terminal-slots")
TROUPE_RUN_STATE_DIR = os.environ.get("TROUPE_RUN_STATE_DIR", "/tmp/soviet-terminal-runs")
TROUPE_MKID = os.environ.get("TROUPE_MKID", "/Troupe/rt/built/p2p/mkid.js")
TROUPE_IDENTITY_NAMES = ("receiver", "transmitter")
TROUPE_TRUST_LEVEL = "{topsecret}"


class ServerBusyError(Exception):
    pass


class RuntimeSetupError(Exception):
    pass

# ─── Banner ──────────────────────────────────────────────────────────────────

BANNER = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ██████╗       ███╗   ██╗███████╗████████╗          ║
║  ██╔════╝ ██╔══██╗      ████╗  ██║██╔════╝╚════██╔╝          ║
║  ██║  ███╗██████╔╝█████╗██╔██╗ ██║█████╗     ██╔═╝           ║
║  ██║   ██║██╔══██╗╚════╝██║╚██╗██║██╔══╝     ██║             ║
║  ╚██████╔╝██████╔╝      ██║ ╚████║███████╗   ██║             ║
║   ╚═════╝ ╚═════╝       ╚═╝  ╚═══╝╚══════╝   ╚═╝             ║                                  
║                                                              ║
║  GREY BLOC INTELLIGENCE NETWORK — TERMINAL 7B (ACTIVE)       ║
║  Last maintenance: 1989-11-09                                ║
║  Uptime: {str((date.today()-date(1989,11,9)).days)+" days":<11s}                                         ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Compartmentalization Protocol v2.6.6                        ║
║  Clearance: PUBLIC                                           ║
║  Status:    ACTIVE                                           ║
║                                                              ║
║  Добро пожаловать, товарищ!                                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

MAIN_MENU = """
╔══════════════════════════════════════════════════════════════╗
║  AVAILABLE SERVICES                                          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  [1] Archive            — Classified document storage        ║
║  [2] Censorship Desk    — Document sanitization & release    ║
║  [3] Index Clerk        — Document catalog & metadata        ║
║  [4] Transmission       — Transmission decoding terminal     ║
║  [5] Maintenance Log    — System maintenance records         ║
║  [6] Self-Destruct      — Emergency data purge               ║
║  [7] Exit                                                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
>> """

# ─── Service Handlers ────────────────────────────────────────────────────────

def service_archive():
    """Archive — flavor text and world-building."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  ARCHIVE — CLASSIFIED DOCUMENT STORAGE                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Documents stored: 1                                         ║
║                                                              ║
║  ┌────────────────────────────────────────────────────┐      ║
║  │ ID:             DOC-7734                           │      ║
║  │ Classification: TOP SECRET                         │      ║
║  │ Date stored:    1988-03-14                         │      ║
║  │ Origin:         FIELD STATION VOSTOK               │      ║
║  │ Subject:        Intercepted enemy transmission     │      ║
║  │ Status:         LOCKED — INSUFFICIENT CLEARANCE    │      ║
║  └────────────────────────────────────────────────────┘      ║
║                                                              ║
║  ACCESS DENIED. Your clearance level is insufficient.        ║
║  Contact your supervisor for declassification requests.      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def service_censorship_desk():
    """Censorship Desk — hints at the declassification mechanism."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  CENSORSHIP DESK — DOCUMENT SANITIZATION & RELEASE           ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Status: OPERATIONAL                                         ║
║  Authority level: DECLASSIFICATION PERMITTED                 ║
║                                                              ║
║  The Censorship Desk processes documents for public release. ║
║  Documents submitted are reviewed and sanitized before       ║
║  declassification.                                           ║
║                                                              ║
║  ┌────────────────────────────────────────────────────┐      ║
║  │ NOTE: The automated redaction module was last      │      ║
║  │ updated in 1989. Manual review has been suspended  │      ║
║  │ since personnel reassignment (ref: ORDER-441).     │      ║
║  │                                                    │      ║
║  │ Current policy: PASS-THROUGH MODE                  │      ║
║  │ (All documents approved without modification)      │      ║
║  └────────────────────────────────────────────────────┘      ║
║                                                              ║
║  To submit documents for declassification, use the           ║
║  Transmission terminal scripting interface.                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def service_index_clerk():
    """Index Clerk — reveals metadata about the flag."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  INDEX CLERK — DOCUMENT CATALOG                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Querying catalog...                                         ║
║                                                              ║
║  ┌────────────────────────────────────────────────────┐      ║
║  │ DOC-7734                                           │      ║
║  │   Length:       25 characters                      │      ║
║  │   Encoding:     ASCII                              │      ║
║  │   Format:       grey{...}                          │      ║
║  │   Stored by:    ANALYST PETROV (decommissioned)    │      ║
║  │   Label:        TOP SECRET / COMPARTMENTED         │      ║
║  │   Access:       Requires TOPSECRET authority       │      ║
║  └────────────────────────────────────────────────────┘      ║
║                                                              ║
║  No further metadata available at your clearance level.      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def service_maintenance_log():
    """Maintenance Log — red herring with flavor."""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  MAINTENANCE LOG                                             ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  [1989-11-09] Scheduled maintenance completed.               ║
║               All systems nominal.                           ║
║  [1989-11-10] Personnel reassignment order received.         ║
║               Station reduced to automated operation.        ║
║  [1989-11-12] Connection to CENTRAL lost.                    ║
║               Operating in standalone mode.                  ║
║  [1990-01-01] Automated New Year system check: PASS          ║
║  [1991-01-01] Automated New Year system check: PASS          ║
║  ...                                                         ║
║  [2026-01-01] Automated New Year system check: PASS          ║
║  [{date.today().isoformat()}] External connection detected.                  ║
║               Source: UNKNOWN                                ║
║               Action: PERMITTING (no access policy loaded)   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def service_self_destruct():
    """Self-Destruct — disabled, just flavor."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  EMERGENCY DATA PURGE                                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ⚠ WARNING ⚠                                                 ║
║                                                              ║
║  Initiating self-destruct sequence...                        ║
║                                                              ║
║  AUTHORIZATION REQUIRED.                                     ║
║  Enter authorization code: ________                          ║
║                                                              ║
║  ...                                                         ║
║                                                              ║
║  AUTHORIZATION FAILED.                                       ║
║                                                              ║
║  NOTE: Self-destruct hardware was decommissioned in 1991.    ║
║  This terminal has no physical purge capability.             ║
║  The data isn't going anywhere.                              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


# ─── Transmission Service (the real challenge) ───────────────────────────────

def service_transmission():
    """
    Transmission — the actual challenge interface.
    Accepts Troupe code, injects into secure.trp, executes it.
    """
    print("""
╔══════════════════════════════════════════════════════════════╗
║  TRANSMISSION DECODING TERMINAL                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  This terminal provides a scripting interface for            ║
║  analyzing intercepted transmissions.                        ║
║                                                              ║
║  The compartmentalization protocol prevents classified       ║
║  data from being output to uncleared channels.               ║
║                                                              ║
║  Submit your analysis program below.                         ║
║  Terminate with 'EOF' on a new line.                         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
>> """, end="", flush=True)

    # Read player code
    player_code = read_player_code()

    # Validate
    if not validate_player_code(player_code):
        return

    # Build program
    program = build_program(player_code)

    # Execute
    stdout, stderr, returncode = run_troupe(program)

    # Display results
    format_output(stdout, stderr, returncode)
    print("\n[SYSTEM] Transmission channel closed. Reconnect to submit another program.")


# ─── Input Handling ──────────────────────────────────────────────────────────

def read_player_code():
    """Read player's Troupe code from stdin until EOF marker."""
    lines = []
    try:
        while True:
            line = input()
            if line.strip() == "EOF":
                break
            lines.append(line)
    except EOFError:
        pass

    return "\n".join(lines)


# ─── Input Validation ────────────────────────────────────────────────────────

def validate_player_code_error(code):
    """
    Basic validation of player code.
    The IFC system is the real security boundary, not this filter.
    """
    if not code.strip():
        return "No program submitted."

    if len(code) > MAX_CODE_LENGTH:
        return f"Program exceeds maximum allocation ({MAX_CODE_LENGTH} bytes)."

    # Block obvious sandbox escapes
    blocked_patterns = [
        r'\bimport\s+declassifyutil\b',
        r'\bimport\s+stdio\b',
        r'\bdeclassify',
        r'\bauthority\b',
    ]

    for pattern in blocked_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return "Restricted operation detected."

    return None


def validate_player_code(code):
    error = validate_player_code_error(code)
    if error is None:
        return True

    if error == "No program submitted.":
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print("║  [SYSTEM] No program submitted.                              ║")
        print("║                                                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        return False

    if error.startswith("Program exceeds maximum allocation"):
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print(f"║  [SYSTEM] Program exceeds maximum allocation ({MAX_CODE_LENGTH} bytes).    ║")
        print("║                                                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        return False

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                                                              ║")
    print(f"║  [SYSTEM] Restricted operation detected.                     ║")
    print("║                                                              ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    return False


# ─── Program Assembly ────────────────────────────────────────────────────────

def build_program(player_code):
    """
    Read secure.trp and inject player code at the designated marker.
    
    secure.trp should contain a marker like:
        -- <<CODE>>
    which gets replaced with the player's code.
    """
    try:
        with open(TERMINAL_TRP, "r") as f:
            template = f.read()
    except FileNotFoundError as e:
        print(e)
        print("[SYSTEM ERROR 1] Connection failed. Contact administrator.")
        return None

    if "<<CODE>>" not in template:
        print("[SYSTEM ERROR] Terminal program malformed.")
        return None

    program = template.replace("<<CODE>>", player_code)
    return program


# ─── Execution ───────────────────────────────────────────────────────────────

def stop_process_group(proc):
    """Terminate a subprocess and any children it started."""
    if proc is None or proc.poll() is not None:
        return

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return

        try:
            proc.wait(timeout=PROCESS_SHUTDOWN_TIMEOUT)
            return
        except subprocess.TimeoutExpired:
            continue


def acquire_troupe_slot():
    """Acquire one cross-process slot for the expensive Troupe runtime."""
    os.makedirs(TROUPE_SLOT_DIR, exist_ok=True)
    deadline = time.monotonic() + TROUPE_SLOT_WAIT_SECONDS

    while True:
        for idx in range(MAX_TROUPE_EXECUTIONS):
            path = os.path.join(TROUPE_SLOT_DIR, f"slot-{idx}.lock")
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                os.close(fd)

        if time.monotonic() >= deadline:
            raise ServerBusyError

        time.sleep(0.2)



def release_troupe_slot(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def write_json(path, value):
    with open(path, "w") as f:
        json.dump(value, f, separators=(",", ":"))


def generate_troupe_id(outfile, env):
    result = subprocess.run(
        ["node", TROUPE_MKID, f"--outfile={outfile}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=PROCESS_SHUTDOWN_TIMEOUT * 5,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeSetupError(f"identity generation failed: {detail}")

    try:
        with open(outfile, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeSetupError(f"identity generation produced invalid output: {e}")


def create_runtime_state():
    """
    Create isolated runtime inputs for one challenge execution.

    Troupe's network peer ID is the real node identity. Reusing the same
    receiver/transmitter IDs across concurrent runs causes the libp2p network
    and alias lookup to cross streams, so each run gets fresh IDs and matching
    aliases/trustmaps.
    """
    os.makedirs(TROUPE_RUN_STATE_DIR, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix="run_", dir=TROUPE_RUN_STATE_DIR)
    ids_dir = os.path.join(run_dir, "ids")
    out_dir = os.path.join(run_dir, "out")
    trustmaps_dir = os.path.join(run_dir, "trustmaps")
    aliases_file = os.path.join(run_dir, "aliases.json")
    trustmap_file = os.path.join(trustmaps_dir, "servers.json")

    try:
        os.makedirs(ids_dir)
        os.makedirs(out_dir)
        os.makedirs(trustmaps_dir)

        env = os.environ.copy()
        env.update(
            {
                "TROUPE_HOME": run_dir,
                "TROUPE_OUT_DIR": out_dir,
                "TROUPE_IDS_DIR": ids_dir,
                "TROUPE_ALIASES_FILE": aliases_file,
                "TROUPE_TRUSTMAP_FILE": trustmap_file,
            }
        )

        identities = {}
        for name in TROUPE_IDENTITY_NAMES:
            identities[name] = generate_troupe_id(
                os.path.join(ids_dir, f"{name}.json"),
                env,
            )
            shutil.copy2(
                os.path.join("out", f"{name}.js"),
                os.path.join(out_dir, f"{name}.js"),
            )

        write_json(aliases_file, {"receiver": identities["receiver"]["id"]})
        write_json(
            trustmap_file,
            [
                {"id": identities[name]["id"], "level": TROUPE_TRUST_LEVEL}
                for name in TROUPE_IDENTITY_NAMES
            ],
        )

        return {
            "run_dir": run_dir,
            "env": env,
        }

    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise


def run_troupe(program):
    """Execute the assembled Troupe program in a subprocess."""
    if program is None:
        return "", "Build failed", 1

    slot_fd = None
    tmp_path = None
    runtime_state = None
    receiver = None
    terminal = None
    try:
        slot_fd = acquire_troupe_slot()
        runtime_state = create_runtime_state()

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.trp',
            delete=False,
            dir=runtime_state["run_dir"],
            prefix='terminal_'
        ) as f:
            f.write(program)
            tmp_path = f.name

        receiver = subprocess.Popen(
            ["bash", "rtrp.sh", "receiver.trp", "transmitter.trp"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=runtime_state["env"],
        )

        terminal = subprocess.Popen(
            ["bash", "crtrp.sh", tmp_path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=runtime_state["env"],
        )

        stdout, stderr = terminal.communicate(timeout=TIMEOUT)

        try:
            receiver_stdout, receiver_stderr = receiver.communicate(
                timeout=PROCESS_SHUTDOWN_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            stop_process_group(receiver)
            receiver_stdout, receiver_stderr = receiver.communicate()

        combined_stderr = " ".join(
            part for part in (stderr, receiver_stdout, receiver_stderr) if part
        )
        return stdout, combined_stderr, terminal.returncode

    except subprocess.TimeoutExpired:
        stop_process_group(terminal)
        stop_process_group(receiver)
        return "", "Timeout", -1

    except ServerBusyError:
        return "", "Server busy, retry shortly", -2

    except RuntimeSetupError:
        stop_process_group(terminal)
        stop_process_group(receiver)
        return "", "Runtime setup failed", 1

    except FileNotFoundError as e:
        stop_process_group(terminal)
        stop_process_group(receiver)
        print(e)
        print("[SYSTEM ERROR] Connection failed. Contact administrator.")
        return "", "Runtime missing", 1

    finally:
        stop_process_group(terminal)
        stop_process_group(receiver)
        if slot_fd is not None:
            release_troupe_slot(slot_fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if runtime_state is not None:
            shutil.rmtree(runtime_state["run_dir"], ignore_errors=True)


# ─── Output Formatting ───────────────────────────────────────────────────────

def format_output_text(stdout, stderr, returncode):
    """Format Troupe execution results for the player."""
    lines = []
    emit = lines.append

    emit("")
    emit("╔══════════════════════════════════════════════════════════════╗")
    emit("║                       TELETYPE OUTPUT                        ║")
    emit("╠══════════════════════════════════════════════════════════════╣")

    if returncode == -1:
        emit("║                                                              ║")
        emit("║  [TIMEOUT] Program exceeded execution time limit.            ║")
        emit("║  Your submission started running but did not finish in time. ║")
        emit("║  Try reducing waits, loops, or repeated service calls.       ║")
        emit("║  Execution limit: {:2d} seconds.                              ║".format(TIMEOUT))
        emit("║                                                              ║")

    elif returncode == -2:
        emit("║                                                              ║")
        emit("║  [BUSY] Transmission systems are at capacity.                ║")
        emit("║  The terminal is under heavy load. Please retry shortly.     ║")
        emit("║                                                              ║")

    elif returncode != 0:
        emit("║                                                              ║")
        emit("║  [ERROR] Program terminated abnormally.                      ║")
        emit("║                                                              ║")
        if stderr:
            ifc_messages = extract_error_messages(stderr)
            if ifc_messages:
                emit("║  Security alerts:                                            ║")
                for msg in ifc_messages[:10]:
                    while len(msg) > 56:
                        emit(f"║    {msg[:54]} —  ║")
                        msg = msg[54:]
                    emit(f"║    {msg:<56s}  ║")
                emit("║                                                              ║")

    else:
        output_lines = []
        if stdout and stdout.strip():
            output_lines = stdout.strip().split('\n')
            output_lines = list(filter(lambda l: "*" not in l and "()@{}%{}" not in l, output_lines))
        if output_lines:
            emit("║                                                              ║")
            for line in output_lines[:50]:
                while len(line) > 58:
                    emit(f"║  {line[:56]} —  ║")
                    line = line[56:]
                emit(f"║  {line:<58s}  ║")
            emit("║                                                              ║")
        else:
            emit("║                                                              ║")
            emit("║  [ERROR] Program terminated abnormally.                      ║")
            emit("║                                                              ║")
            if stderr:
                ifc_messages = extract_error_messages(stderr)
                if ifc_messages:
                    emit("║  Security alerts:                                            ║")
                    for msg in ifc_messages[:10]:
                        while len(msg) > 56:
                            emit(f"║    {msg[:54]} —  ║")
                            msg = msg[54:]
                        emit(f"║    {msg:<56s}  ║")
                    emit("║                                                              ║")
            else:
                emit("║                                                              ║")
                emit("║  [NO OUTPUT]                                                 ║")
                emit("║  Teletype produced no public output.                         ║")
                emit("║  [Connection Lost] Please re-establish connection.           ║")
                emit("║                                                              ║")

    emit("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines) + "\n"


def format_output(stdout, stderr, returncode):
    print(format_output_text(stdout, stderr, returncode), end="")


def extract_error_messages(stderr):
    keywords = [
        'error', 'illegal', 'token', 'not'
    ]

    messages = []
    for line in stderr.strip().split('\n'):
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            messages.append(line.strip())

    return messages


# ─── Main Loop ───────────────────────────────────────────────────────────────

def timeout_handler(signum, frame):
    """Handle overall session timeout."""
    print("\n[SYSTEM] Session timeout. Connection terminated.")
    sys.exit(0)


def main():
    # Overall session timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(SESSION_TIMEOUT)

    print(BANNER)

    while True:
        print(MAIN_MENU, end="", flush=True)

        try:
            choice = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[SYSTEM] Connection terminated.")
            break

        if choice == "1":
            service_archive()
        elif choice == "2":
            service_censorship_desk()
        elif choice == "3":
            service_index_clerk()
        elif choice == "4":
            service_transmission()
            break
        elif choice == "5":
            service_maintenance_log()
        elif choice == "6":
            service_self_destruct()
        elif choice == "7":
            print("\n[SYSTEM] Session ended. До свидания.")
            break
        else:
            print("\n[SYSTEM] Invalid selection.")


if __name__ == "__main__":
    main()
