#!/usr/bin/env bash
# One-step launcher for the Opto transparency dashboard.
# Usage:  ./run_dashboard.sh
set -e
cd "$(dirname "$0")"

# Install Opto (and deps) in editable mode the first time.
python3 -m pip install -e . >/dev/null 2>&1 || python3 -m pip install -e . --break-system-packages

PORT="${OPTO_DASHBOARD_PORT:-8800}"
echo "Opto dashboard → http://127.0.0.1:${PORT}"

# Open the browser shortly after the server starts.
( sleep 2; open "http://127.0.0.1:${PORT}" ) &

opto dashboard --port "${PORT}"
