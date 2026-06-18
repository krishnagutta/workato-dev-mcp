# Workato Dev MCP

A local MCP server that lets you **author and debug Workato recipes from Claude** (Code, Desktop, or any MCP client).

The official Workato Developer API MCP (`app.workato.com/mcp`) is management/read-only — it can't create or update recipe **code** or start/stop recipes. This server does, by wrapping the Workato Developer REST API operations a recipe developer actually needs.

Zero dependencies — standard library only, any **Python 3.8+**. No `pip install`.

## Quick install (Claude Code)

From the repo, one command registers the server with Claude Code:

```bash
WORKATO_TOKEN=your-developer-api-token bash bin/install.sh
```

Or bootstrap from scratch (clone + register) with one line:

```bash
curl -fsSL https://raw.githubusercontent.com/krishnagutta/workato-dev-mcp/main/bin/quickstart.sh | bash
```

Then start a new Claude session and try: *"list my Workato recipes"*.

### Even simpler — project-scoped auto-detection

This repo ships a `.mcp.json`. If a teammate opens the repo folder in Claude Code with `WORKATO_TOKEN` exported in their shell, Claude Code detects the server automatically — no `claude mcp add` needed. Approve it once when prompted.

```bash
export WORKATO_TOKEN=your-developer-api-token   # add to ~/.zshrc to persist
cd workato-dev-mcp
claude                                           # Claude Code picks up .mcp.json
```

## Prerequisites

- **Python 3.8+** (`python3 --version`) — already on macOS/Linux.
- **A Workato Developer API token** — Workato → Workspace admin → **API clients**. The *Recipe operator* role is enough for recipe CRUD. Copy the token (starts with `wrkaus-`).
- For Claude Code: the **`claude` CLI** installed (only needed for `bin/install.sh`).

## Manual setup (any MCP client)

If you'd rather wire it by hand (Claude Desktop, or pinning an absolute path):

```json
{
  "mcpServers": {
    "workato-dev": {
      "command": "python3",
      "args": ["/absolute/path/to/workato-dev-mcp/server.py"],
      "env": {
        "WORKATO_TOKEN": "your-developer-api-token",
        "WORKATO_API_BASE": "https://www.workato.com/api"
      }
    }
  }
}
```

- Claude Desktop config: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- Claude Code user scope: `~/.claude.json`.

Restart the client, start a new chat, and you should see the `workato-dev` tools.

## What it gives you (30 tools)

**Recipes**

| Tool | Purpose |
|---|---|
| `list_recipes` / `get_recipe` / `get_recipe_steps` | Find and inspect recipes (incl. the parsed code tree) |
| `create_recipe` / `update_recipe` | Author recipe code (JSON) |
| `start_recipe` / `stop_recipe` | Activate/deactivate (start = the validator) |
| `copy_recipe` / `delete_recipe` | Duplicate / remove |
| `list_recipe_versions` | Version history for tracking / rollback awareness |
| `list_jobs` / `get_job` | Debug — per-step input/output/error from job history |

**Workspace & config**

| Tool | Purpose |
|---|---|
| `whoami` | Confirm which workspace/user your token is in |
| `list_connections` / `list_folders` / `list_projects` | Browse for config wiring |
| `create_folder` | Create a folder (optionally nested) |
| `get_properties` / `upsert_properties` | Read/write account properties (config + feature flags) |

**API Platform — Workato MCP servers**

A Workato MCP server built on **API Platform** is an API collection exposed as MCP; its tools are API endpoints, each backed by a recipe. These tools let the dev MCP introspect that surface. (The AI-Hub-native MCP / Genie layer has no Developer API — manage it in the UI.)

| Tool | Purpose |
|---|---|
| `list_api_collections` | List API collections (each can be exposed as an MCP server) |
| `list_api_endpoints` | List a collection's endpoints — the MCP server's **tools**, with method/path/`active`/recipe |
| `list_api_clients` | List API clients (the credentialed consumers) |
| `list_api_access_profiles` | List access profiles (client ↔ collection scope bindings) |

**Lookup & data tables**

| Tool | Purpose |
|---|---|
| `list_lookup_tables` / `query_lookup_table` | Browse lookup tables; read rows (e.g. captured logs) |
| `add_lookup_table_row` | Append a row (capture/log writes) |
| `list_data_tables` | List Workato Data Tables |

**Knowledge base (two-tier, like the Studio MCP)**

| Tool | Purpose |
|---|---|
| `workato_recipe_tips` | Curated cheat sheet of recipe-authoring gotchas (the promoted tier) |
| `log_learning` | Append a newly discovered gotcha to `learnings.md` (the intake queue) |
| `get_learnings` | Read `learnings.md` back, optionally filtered by category |

## Auth & data residency

- `WORKATO_TOKEN` (required) — your personal Developer API token. Each dev uses their own; nothing is shared or hosted.
- `WORKATO_API_BASE` (optional) — defaults to `https://www.workato.com/api` (US). Set per your data center, e.g. `https://app.eu.workato.com/api`.

## The recipe edit loop

```
get_recipe(id, include_code=true)   # pull the code tree
  → edit the JSON in conversation
  → stop_recipe(id)                 # running recipes can't be updated
  → update_recipe(id, code=<json>)
  → start_recipe(id)                # start = the compiler; read validation errors
  → list_jobs / get_job             # after a test run, inspect real step I/O
```

Run `workato_recipe_tips` and `get_learnings` once before building — they capture the datapill format, the trigger `extended_output_schema` requirement, the HTTP string-body trick, custom-code schema gotchas, valid condition operands, and the job-log debugging pattern. These are the things that otherwise cost hours.

## Capturing learnings (two-tier, like the Studio MCP)

The knowledge base grows as you use it:

- **`learnings.md`** (repo root) is the **intake queue** — append-only, low-friction. When Claude discovers a gotcha that isn't already in `workato_recipe_tips`, it calls **`log_learning`** to append a dated, categorized entry. Then commit the file so teammates inherit it.
- **`workato_recipe_tips`** (the `_TIPS` block in `server.py`) is the **curated tier**. During periodic review, raw learnings are promoted into it and marked `**Status**: promoted` in `learnings.md`.

`log_learning` / `get_learnings` are pure local file operations — no Workato API call, no token needed. The file is anchored to the repo via `__file__`; override the location with `WORKATO_LEARNINGS_PATH` if needed.

## Notes / limits

- This is a **dev tool** — it can create, edit, start/stop, and delete recipes. Use a token scoped to a dev/impl workspace; be careful with `delete_recipe`.
- It does **not** touch the AI Hub layer (adding tools to an MCP server, server instructions, MCP Apps, or a tool's param-schema refresh) — those remain manual in the Workato UI. After a recipe **param-set** change, the MCP client that consumes that tool needs an app restart to see the new schema.
- Sharing: commit this folder to an internal git repo; teammates clone and either run `bin/install.sh` or export `WORKATO_TOKEN` and let `.mcp.json` auto-detect it.
