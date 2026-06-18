#!/usr/bin/env bash
# One-line bootstrap: clone the repo and register the MCP with Claude Code.
#   curl -fsSL https://raw.githubusercontent.com/<org-or-user>/workato-dev-mcp/main/bin/quickstart.sh | bash
set -euo pipefail

REPO_URL="${WORKATO_DEV_MCP_REPO:-https://github.com/krishnagutta/workato-dev-mcp.git}"
DEST="${WORKATO_DEV_MCP_DIR:-$HOME/workato-dev-mcp}"

command -v git >/dev/null 2>&1 || { echo "ERROR: git not found."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found (need 3.8+)."; exit 1; }

if [ -d "$DEST/.git" ]; then
  echo "Updating existing clone at $DEST"; git -C "$DEST" pull --ff-only
else
  echo "Cloning to $DEST"; git clone "$REPO_URL" "$DEST"
fi

bash "$DEST/bin/install.sh"
