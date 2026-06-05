# Technical Requirements Document (TRD): Corporate Intern Simulator CTF

## 1. Executive Summary

This document outlines the end-to-end implementation for a 3-stage backend concurrency Capture The Flag (CTF) challenge. Designed for deployment on rCTF instanced infrastructure, players act as interns exploiting race conditions, database anomalies, and isolation level bypasses within simulated corporate mini-games.

Progression is strictly linear and gated via stateless, dynamically generated hexadecimal tokens injected at container boot.

## 2. Infrastructure & Global Architecture

* **Deployment Model:** Ephemeral Kubernetes pods via rCTF. Every team receives an isolated `Web Server + PostgreSQL` container pair.
* **Database Engine:** PostgreSQL (required for specific `READ COMMITTED` default behaviors).
* **Resource Limits:** Postgres `max_connections` strictly capped at **10-15** per team to prevent blind connection-pool exhaustion and force precise timing attacks.
* **Gating Mechanism:** "Stateless Hex Gating." When a pod boots, two 16-char hex strings are generated as environment variables. Beating Stage 1 leaks the Stage 2 token; beating Stage 2 leaks the Stage 3 token.

### 2.1 Boot Script (`entrypoint.sh`)

This script initializes the environment and ensures reproducible, automated exploits if a pod restarts.

```bash
#!/bin/sh
# Generate random hex tokens for progression gating
export TOKEN_STAGE_2=$(head -c 16 /dev/urandom | xxd -p)
export TOKEN_STAGE_3=$(head -c 16 /dev/urandom | xxd -p)

# Start the Python web server (e.g., FastAPI, Flask, uvicorn)
exec uvicorn main:app --host 0.0.0.0 --port 8000

```

---

## 3. Stage 1: Pinpoint (The Warmup TOCTOU)

**Objective:** Bypass a daily rate limit using an application-level Time-of-Check to Time-of-Use (TOCTOU) race condition.

### 3.1 Game Mechanics & Vulnerability

* **Mechanic:** Guess a hidden 5-letter word. Users are restricted to 5 guesses.
* **Vulnerability:** The application checks the guess count, evaluates the guess, and increments the counter sequentially without a database transaction or row-level lock.
* **Exploit:** Spraying 30+ concurrent HTTP requests allows all threads to read `guesses = 0` before the first `UPDATE` commits.

### 3.2 Python Implementation (FastAPI Example)

```python
import os
from fastapi import FastAPI, Header, HTTPException, Depends
from db_connector import db # Assume standard Postgres wrapper

app = FastAPI()

TOKEN_STAGE_2 = os.environ.get("TOKEN_STAGE_2")
TOKEN_STAGE_3 = os.environ.get("TOKEN_STAGE_3")
TARGET_WORD = "CRASH"

@app.post("/api/v1/pinpoint/guess")
def guess_word(user_id: int, word: str):
    # 1. The Check (No locks, vulnerable to race)
    record = db.execute("SELECT guesses FROM users WHERE id = %s", [user_id])
    if record['guesses'] >= 5:
        raise HTTPException(status_code=403, detail="Daily limit reached.")

    # 2. The Logic
    is_correct = (word.upper() == TARGET_WORD)

    # 3. The Act
    db.execute("UPDATE users SET guesses = guesses + 1 WHERE id = %s", [user_id])
    db.commit()

    if is_correct:
        return {
            "msg": "Correct. Promotion Unlocked.",
            "next_stage_token": TOKEN_STAGE_2
        }

    return {"msg": "Incorrect word."}

```

---

## 4. Stage 2: Queens (The Shell Game)

**Objective:** Exploit PostgreSQL's default `READ COMMITTED` isolation level to bypass a validation loop using a Non-Repeatable Read.

### 4.1 Game Mechanics & Vulnerability

* **Mechanic:** Place 8 queens on a grid. No shared rows allowed. High scores require stacking queens on specific color tiles, which is geometrically illegal.
* **Vulnerability:** The `/submit` endpoint is wrapped in a transaction, but iterates row-by-row to check for conflicts. In `READ COMMITTED`, each iteration takes a fresh snapshot.
* **Exploit:** The player submits a legal board. While the server loops through the rows, the player calls a fast `/move` endpoint to shift a queen from an already-checked row to an unchecked row, stacking them on high-value tiles.

### 4.2 Python Implementation

```python
def verify_stage_2(x_corporate_token: str = Header(...)):
    if x_corporate_token != TOKEN_STAGE_2:
        raise HTTPException(status_code=403, detail="Interns not allowed.")

@app.post("/api/v2/queens/submit", dependencies=[Depends(verify_stage_2)])
def submit_board(user_id: int):
    # The Bait: A transaction that doesn't use SERIALIZABLE or REPEATABLE READ
    with db.transaction():
        # The Validation Loop
        for row_idx in range(8):
            # Postgres takes a NEW snapshot for every loop iteration
            result = db.execute(
                "SELECT count(*) as c FROM queens WHERE user_id = %s AND row_idx = %s",
                [user_id, row_idx]
            )
            if result['c'] > 1:
                raise HTTPException(status_code=400, detail="Row conflict detected.")

            # Natural delay to create a ~100ms weave window
            db.execute("INSERT INTO audit_log (event) VALUES ('row_check')")

        # The Blind Scoring: Sees committed changes made during the loop
        score_res = db.execute(
            "SELECT SUM(multiplier) as total FROM queens WHERE user_id = %s",
            [user_id]
        )

        if score_res['total'] > 10000: # Impossible without stacking
            return {
                "msg": "Executive Board approved.",
                "next_stage_token": TOKEN_STAGE_3
            }

        return {"score": score_res['total']}

@app.post("/api/v2/queens/move", dependencies=[Depends(verify_stage_2)])
def move_queen(user_id: int, queen_id: int, new_row: int, new_col: int):
    # Fast mutator to interleave into the validation loop
    db.execute(
        "UPDATE queens SET row_idx=%s, col_idx=%s WHERE id=%s AND user_id=%s",
        [new_row, new_col, queen_id, user_id]
    )
    db.commit()
    return {"status": "moved"}

```

---

## 5. Stage 3: Crossclimb (The Dirty Oracle)

**Objective:** Exfiltrate data by reading uncommitted game states caused by an architectural "optimization" leak.

### 5.1 Game Mechanics & Vulnerability

* **Mechanic:** A word ladder. The user must find a 5-swap sequence but only has **1 swap remaining**.
* **Vulnerability:** The `/swap` endpoint (Writer) is slow and rolls back on failure. The `/hint` endpoint (Reader) uses `READ UNCOMMITTED` for performance.
* **Exploit:** The player submits a 5-swap sequence to the Writer. The unindexed database join creates an 800ms delay. The player queries the Reader to peek at the uncommitted hint score, mapping out the puzzle before the Writer inevitably issues a `ROLLBACK`.

### 5.2 Python Implementation

```python
def verify_stage_3(x_corporate_token: str = Header(...)):
    if x_corporate_token != TOKEN_STAGE_3:
        raise HTTPException(status_code=403, detail="Executives only.")

@app.post("/api/v3/crossclimb/swap", dependencies=[Depends(verify_stage_3)])
def execute_swap(user_id: int, sequence: list[str]):
    with db.transaction():
        moves = db.execute("SELECT moves_left FROM crossclimb_users WHERE id = %s", [user_id])
        if moves['moves_left'] < 1:
            raise HTTPException(status_code=400, detail="No moves left.")

        # Apply the hypothetical swaps (Uncommitted state)
        apply_swaps_to_db(user_id, sequence)

        # THE DELAY: Unindexed JOIN to choke the DB for ~800ms
        valid_words = db.execute("""
            SELECT count(*) as count
            FROM current_board b
            JOIN massive_unindexed_dictionary d ON b.word = d.word
            WHERE b.user_id = %s
        """, [user_id])

        if valid_words['count'] != 5:
            # Reverts the hypothetical state. The player "spent" nothing.
            db.rollback()
            raise HTTPException(status_code=400, detail="Invalid sequence.")

        db.execute("UPDATE crossclimb_users SET moves_left = moves_left - 1 WHERE id = %s", [user_id])
        return {"flag": "grey{d1rty_r3ads_m4k3_c0rp0r4t3_0r4cl3s}"}

@app.get("/api/v3/crossclimb/hint", dependencies=[Depends(verify_stage_3)])
def get_hint(user_id: int):
    # THE ORACLE: Explicitly drop isolation level to read the Writer's dirty state
    db.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")

    res = db.execute(
        "SELECT count(*) as c FROM current_board WHERE is_correct = TRUE AND user_id = %s",
        [user_id]
    )
    db.commit() # Reset session isolation

    return {"correct_words_in_position": res['c']}

```

## 6. Database Schema Pre-requisites

To ensure the unindexed join works effectively in Stage 3, initialize the PostgreSQL container with a dictionary table containing at least 250,000+ rows and strictly **no indexes** on the `word` column. Ensure the `audit_log` table in Stage 2 has an `INSERT` trigger or relies on natural disk I/O to create a reliable >50ms execution window.
