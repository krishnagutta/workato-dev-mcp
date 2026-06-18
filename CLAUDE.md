# CLAUDE.md — Workato Dev MCP

Guidance for Claude when this repo's MCP server (`workato-dev`) is connected.

## What this is

A local stdio MCP that wraps the **Workato Developer REST API** so recipes can be
authored, started/stopped, and debugged from chat. It is the **BUILD** channel.
Do not confuse it with the **RUNTIME** channel (the AI Hub / APIM MCP that *executes*
published tools) — they are different systems with different auth.

## Source of truth

- **Recipe-authoring gotchas live in the MCP, not in training knowledge.** Workato's
  recipe-code JSON format, datapill syntax, and schema requirements are non-obvious and
  version-specific. Consult `get_learnings` and `workato_recipe_tips` before building or
  editing any recipe.

## Capturing learnings — the two-tier system (mirrors Studio MCP)

There are two tiers. Use both correctly.

### Tier 1 — `learnings.md` (intake queue), via `log_learning`

**This is where you write during a session.** Append-only, unreviewed, low-friction.
**Call `log_learning` AUTOMATICALLY** — even if the user didn't ask — whenever you hit a
non-obvious behavior that isn't already in `workato_recipe_tips`:

- `start_recipe` rejects something with a validation error not yet documented
- a datapill won't bind, a formula/operand turns out invalid, a schema is required somewhere
- an HTTP body strips pills, a job "succeeds" while masking an error in a catch block

After logging, tell the user: *"Logged to learnings.md — commit it and it'll get promoted
into workato_recipe_tips in the next review."* Do **not** hand-edit `_TIPS` mid-session.

### Tier 2 — `workato_recipe_tips` (`_TIPS` in `server.py`), curated

The reviewed, promoted knowledge. Entries here come from promoted `learnings.md` entries.
When asked to promote a learning: move it into `_TIPS` (and/or the README), then mark the
`learnings.md` entry `**Status**: promoted`.

Both the `log_learning` and `get_learnings` tools are pure local file operations on
`learnings.md` (anchored to the repo via `__file__`, override with `WORKATO_LEARNINGS_PATH`).
They never call the Workato API and need no token.

## Safety rules

- **Never** hardcode or echo `WORKATO_TOKEN`. It comes from the environment only.
- `delete_recipe` is destructive — confirm the recipe id and intent with the user first.
- `update_recipe` / `start_recipe` change live recipe state. Before editing a recipe,
  `stop_recipe` it (running recipes reject updates), and tell the user which recipe and
  workspace you're touching.
- Treat any production/sandbox workspace as off-limits unless the user explicitly approves
  the specific action. Prefer dev/impl workspaces.
- `enable_api_endpoint` / `disable_api_endpoint` change a **live MCP server's tool surface** —
  enabling an endpoint exposes that tool to every client of the collection. Name the endpoint
  and get explicit user approval before calling; enabling also requires the backing recipe to
  be started first. Never set Workato sharing/permissions or access profiles programmatically.
- The AI-Hub MCP-server API (`/api/mcp/mcp_servers`, assign_tools, etc.) is **not wired up** —
  the API client currently lacks MCP scope (the path returns the login page). Don't add tools
  against it until the scope is granted and a live GET returns JSON.

## The edit loop (always)

```
get_recipe(id, include_code=true)  →  edit JSON  →  stop_recipe(id)
  →  update_recipe(id, code=...)    →  start_recipe(id)   # start = the validator
  →  list_jobs / get_job            # inspect real per-step I/O after a test run
```

`start_recipe` is the compiler. Read its validation errors carefully — a recipe that
saves can still fail to start.

## Adding tools

Tools are registered in the `TOOLS` list in `server.py` as
`(name, handler_fn, description, schema)` tuples; `_HANDLERS` and `_TOOL_DEFS` derive
from it automatically. To add one:

1. Write a handler function `def my_tool(arg1, arg2=None): return _request(...)`.
2. Add a tuple to `TOOLS` with a clear description and a `_schema({...}, [required])`.
3. Smoke-test: pipe `initialize` + `tools/list` + a `tools/call` through `server.py`
   (see the recipe edit loop or `bin/`), confirm the tool count and a live result.

Keep handlers small and single-purpose. Descriptions are what the model reads to pick a
tool — make them specific about *when* to use each one.
