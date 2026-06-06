#!/bin/bash
# run_troupe.sh — Compile and run multiple Troupe programs concurrently

set -e

# ─── Configuration ───────────────────────────────────────────────────────────

TROUPE="${TROUPE:-/Troupe}"
export HOME="${TROUPE_HOME:-/tmp}"
OUT_DIR="${TROUPE_OUT_DIR:-./out}"
IDS_DIR="${TROUPE_IDS_DIR:-./ids}"
ALIASES_FILE="${TROUPE_ALIASES_FILE:-aliases.json}"
TRUSTMAP_FILE="${TROUPE_TRUSTMAP_FILE:-./trustmaps/servers.json}"

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
            --aliases="$ALIASES_FILE" &
    else
        node "$TROUPE/rt/built/troupe.js" \
            -f="$OUT_DIR/${BASENAME}.js" \
            --id="$IDS_DIR/${BASENAME}.json" \
            --trustmap="$TRUSTMAP_FILE" \
            --aliases="$ALIASES_FILE" &
    fi

    PIDS+=($!)
done

# ─── Wait For All Processes ──────────────────────────────────────────────────

wait "${PIDS[@]}"
