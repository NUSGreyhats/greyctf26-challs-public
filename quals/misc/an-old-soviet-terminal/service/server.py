#!/usr/local/bin/python

"""
Forgotten Soviet Intelligence Server — CTF Challenge
A Troupe IFC challenge where players must leak a classified document.
"""

import subprocess
import tempfile
import os
import sys
import signal
import re
from datetime import date

# ─── Configuration ───────────────────────────────────────────────────────────

TIMEOUT = 10
MAX_CODE_LENGTH = 600
TERMINAL_TRP = "./terminal.trp"

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

def validate_player_code(code):
    """
    Basic validation of player code.
    The IFC system is the real security boundary, not this filter.
    """
    if not code.strip():
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print("║  [SYSTEM] No program submitted.                              ║")
        print("║                                                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        return False
    
    if len(code) > MAX_CODE_LENGTH:
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print(f"║  [SYSTEM] Program exceeds maximum allocation ({MAX_CODE_LENGTH} bytes).    ║")
        print("║                                                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        return False

    # Block obvious sandbox escapes
    blocked_patterns = [
        r'\bimport\s+declassifyutil\b',
        r'\bimport\s+stdio\b',
        r'\bdeclassify',
        r'\bauthority\b',
    ]

    for pattern in blocked_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            print()
            print("╔══════════════════════════════════════════════════════════════╗")
            print("║                                                              ║")
            print(f"║  [SYSTEM] Restricted operation detected.                     ║")
            print("║                                                              ║")
            print("╚══════════════════════════════════════════════════════════════╝")
            
            return False

    return True


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

def run_troupe(program):
    """Execute the assembled Troupe program in a subprocess."""
    if program is None:
        return "", "Build failed", 1

    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.trp',
        delete=False,
        dir='/tmp',
        prefix='terminal_'
    ) as f:
        f.write(program)
        tmp_path = f.name

    try:
        error = subprocess.Popen(
            ["bash", "rtrp.sh", "receiver.trp", "transmitter.trp"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        result = subprocess.run(
            ["bash", "crtrp.sh", tmp_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT
        )
        error.wait()
        return result.stdout, result.stderr + " " + " ".join(error.stdout.readlines()), result.returncode

    except subprocess.TimeoutExpired:
        return "", "Timeout", -1

    except FileNotFoundError as e:
        print(e)
        print("[SYSTEM ERROR] Connection failed. Contact administrator.")
        return "", "Runtime missing", 1

    finally:
        try:
            os.unlink(tmp_path)
            pass
        except OSError:
            pass


# ─── Output Formatting ───────────────────────────────────────────────────────

def format_output(stdout, stderr, returncode):
    """Format Troupe execution results for the player."""
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                       TELETYPE OUTPUT                        ║")
    print("╠══════════════════════════════════════════════════════════════╣")

    if returncode == -1:
        print("║                                                              ║")
        print("║  [TIMEOUT] Program exceeded time allocation.                 ║")
        print("║  Session terminated after {:2d} seconds.                         ║".format(TIMEOUT))
        print("║                                                              ║")

    elif returncode != 0:
        print("║                                                              ║")
        print("║  [ERROR] Program terminated abnormally.                      ║")
        print("║                                                              ║")
        if stderr:
            ifc_messages = extract_error_messages(stderr)
            if ifc_messages:
                print("║  Security alerts:                                            ║")
                for msg in ifc_messages[:10]:
                    while len(msg) > 56:
                        print(f"║    {msg[:54]} —  ║")
                        msg = msg[54:]
                    print(f"║    {msg:<56s}  ║")
                print("║                                                              ║")

    else:
        output_lines = []
        if stdout and stdout.strip():
            output_lines = stdout.strip().split('\n')
            output_lines = list(filter(lambda l: "*" not in l and "()@{}%{}" not in l, output_lines))
        if output_lines:
            print("║                                                              ║")
            for line in output_lines[:50]:
                while len(line) > 58:
                    print(f"║  {line[:56]} —  ║")
                    line = line[56:]
                print(f"║  {line:<58s}  ║")
            print("║                                                              ║")
        else:
            print("║                                                              ║")
            print("║  [ERROR] Program terminated abnormally.                      ║")
            print("║                                                              ║")
            if stderr:
                ifc_messages = extract_error_messages(stderr)
                if ifc_messages:
                    print("║  Security alerts:                                            ║")
                    for msg in ifc_messages[:10]:
                        while len(msg) > 56:
                            print(f"║    {msg[:54]} —  ║")
                            msg = msg[54:]
                        print(f"║    {msg:<56s}  ║")
                    print("║                                                              ║")
            else:
                print("║                                                              ║")
                print("║  [NO OUTPUT]                                                 ║")
                print("║  Teletype produced no public output.                         ║")
                print("║  [Connection Lost] Please re-establish connection.           ║")
                print("║                                                              ║")

    print("╚══════════════════════════════════════════════════════════════╝")


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
    signal.alarm(120)  # 2 minute total session

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
