#!/bin/bash
# run_troupe.sh — Compile and run multiple Troupe programs concurrently

set -e

# ─── Configuration ───────────────────────────────────────────────────────────

TROUPE="/Troupe"
OUT_DIR="./out"
IDS_DIR="./ids"

# ─── Argument Check ──────────────────────────────────────────────────────────

if [ $# -lt 1 ]; then
    echo "Usage: $0 <file1.trp> [file2.trp ...]"
    exit 1
fi

for INPUT_FILE in "$@"; do
    BASENAME=$(basename "$INPUT_FILE" .trp)
    if [ ! -f "$OUT_DIR/${BASENAME}.js" ]; then
        echo "Troupe file not compiled. Run with crtrp.sh"
        exit 1
    fi
done

# ─── Run All Concurrently ────────────────────────────────────────────────────

PIDS=()

for INPUT_FILE in "$@"; do
    BASENAME=$(basename "$INPUT_FILE" .trp)

    echo "[*] Running ${BASENAME}..."

    if [ ! -f "$IDS_DIR/${BASENAME}.json" ]; then
        node "$TROUPE/rt/built/troupe.js" \
            -f="$OUT_DIR/${BASENAME}.js" \
            --aliases="aliases.json" &
    else
        node "$TROUPE/rt/built/troupe.js" \
            -f="$OUT_DIR/${BASENAME}.js" \
            --id="$IDS_DIR/${BASENAME}.json" \
            --trustmap="./trustmaps/servers.json" \
            --aliases="aliases.json" &
    fi

    PIDS+=($!)
done

# ─── Wait For All Processes ──────────────────────────────────────────────────

wait "${PIDS[@]}"