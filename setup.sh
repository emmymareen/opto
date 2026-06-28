#!/usr/bin/env bash
# setup.sh — one-time Opto setup for Claude Code (and other Anthropic clients).
#
# - installs Opto
# - adds ANTHROPIC_BASE_URL to your shell profile so ALL Claude Code sessions
#   route through Opto automatically
#
# Run once:  ./setup.sh    Then:  ./optoctl start
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROXY_PORT="${OPTO_PORT:-8799}"
BASE_URL="http://127.0.0.1:${PROXY_PORT}"

echo "[opto] installing…"
python3 -m pip install -e . >/dev/null 2>&1 || python3 -m pip install -e . --break-system-packages

# pick the user's shell profile
case "${SHELL:-}" in
  */zsh) PROFILE="$HOME/.zshrc" ;;
  */bash) PROFILE="$HOME/.bashrc" ;;
  *) PROFILE="$HOME/.profile" ;;
esac
touch "$PROFILE"

MARK="# >>> opto (Claude Code routing) >>>"
if grep -q "$MARK" "$PROFILE"; then
  echo "[opto] profile already configured ($PROFILE)"
else
  {
    echo ""
    echo "$MARK"
    echo "export ANTHROPIC_BASE_URL=${BASE_URL}"
    echo "# <<< opto <<<"
  } >> "$PROFILE"
  echo "[opto] added ANTHROPIC_BASE_URL=${BASE_URL} to $PROFILE"
fi

cat <<EOF

[opto] setup complete.

  1. reload your shell:   source $PROFILE   (or open a new terminal)
  2. start Opto:          ./optoctl start
  3. use Claude Code normally — it now routes through Opto
  4. see savings:         ./optoctl status   or   open http://127.0.0.1:8800

To stop routing through Opto: ./optoctl stop  (and remove the opto block from $PROFILE).
Note: this routes terminal Claude Code. The Claude.ai web app / desktop Projects
cannot be routed (no endpoint override) — only API/CLI clients can.
EOF
