#!/usr/bin/env bash
set -Eeuo pipefail

IMPORT_DIR="/opt/bf4br/imports"
PYTHON="/opt/bf4br-external-api/.venv/bin/python"
IMPORTER="$IMPORT_DIR/bf4br_probe_import.py"
RECONCILE="$IMPORT_DIR/reconcile_probe.py"

# Require exactly one archive argument.
if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <archive.tar.zst>"
    exit 1
fi

ARCHIVE="$(realpath -e -- "$1")"

if [[ ! -f "$ARCHIVE" || "$ARCHIVE" != *.tar.zst ]]; then
    echo "ERROR: Expected an existing .tar.zst archive."
    exit 1
fi

if [[ ! -f "$IMPORTER" || ! -f "$RECONCILE" ]]; then
    echo "ERROR: Importer or reconciliation SQL not found."
    exit 1
fi

cd "$IMPORT_DIR"

echo "========================================"
echo " BF4BR Probe Archive Import"
echo "========================================"
echo "Archive: $ARCHIVE"
echo

# STEP 1: Validate
echo "[1/3] Validating archive (dry run)..."

runuser -u postgres -- "$PYTHON" "$IMPORTER" \
    --archive "$ARCHIVE" \
    --limit 0

echo
echo "Validation command completed."
echo "Review the results above before proceeding."
echo

# STEP 2: Manual confirmation
read -r -p "Press ENTER to import, or CTRL+C to cancel: "

LOGFILE="$IMPORT_DIR/import-$(date -u +%Y%m%d-%H%M%S).log"
CANDIDATES="/var/tmp/$(basename "${LOGFILE%.log}")-candidates.jsonl"

echo
echo "[2/3] Importing archive..."
echo "Log: $LOGFILE"

runuser -u postgres -- "$PYTHON" "$IMPORTER" \
    --archive "$ARCHIVE" \
    --limit 0 \
    --execute \
    --candidates "$CANDIDATES" 2>&1 | tee "$LOGFILE"

echo
echo "Import command completed."
echo "Review the FINAL summary above."
echo

# STEP 3: Separate approval for reconciliation
read -r -p "Press ENTER to reconcile, or CTRL+C to cancel: "

echo
echo "[3/3] Reconciling completed reports..."

runuser -u postgres -- "$PYTHON" "$RECONCILE" --candidates "$CANDIDATES"

echo
echo "========================================"
echo " Import workflow finished!"
echo " Log: $LOGFILE"
echo "========================================"
