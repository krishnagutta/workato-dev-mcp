#!/usr/bin/env bash
# Register the Workato Dev MCP with Claude Code (user scope).
# Run from anywhere; resolves this repo's path automatically.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$REPO_DIR/server.py"

# --- checks ---
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found (need Python 3.8+)."; exit 1; }
command -v claude  >/dev/null 2>&1 || { echo "ERROR: 'claude' CLI not found. Install Claude Code first."; exit 1; }
[ -f "$SERVER" ] || { echo "ERROR: server.py not found at $SERVER"; exit 1; }

# --- token ---
TOKEN="${WORKATO_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  read -rp "Paste your Workato Developer API token: " TOKEN
fi
[ -n "$TOKEN" ] || { echo "ERROR: no WORKATO_TOKEN provided."; exit 1; }
API_BASE="${WORKATO_API_BASE:-https://www.workato.com/api}"

# --- register ---
claude mcp remove workato-dev 2>/dev/null || true
claude mcp add workato-dev \
  --env "WORKATO_TOKEN=$TOKEN" \
  --env "WORKATO_API_BASE=$API_BASE" \
  -- python3 "$SERVER"

echo
echo "✅ Registered 'workato-dev' with Claude Code."
echo "   Start a new Claude session and try: \"list my Workato recipes\""
