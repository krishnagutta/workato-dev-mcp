#!/usr/bin/env python3
"""
Workato Dev MCP — author and debug Workato recipes from Claude.

A zero-dependency stdio MCP server (stdlib only, Python 3.8+) that wraps the
Workato Developer REST API operations needed for recipe development: list/get/
create/update/copy/delete recipes, start/stop, read job history for debugging,
and browse connections/folders/projects.

The official Workato Developer API MCP (app.workato.com/mcp) is management/read
only — it cannot create or update recipe CODE or start/stop recipes. This fills
that gap, with no SDK install and no Python-version constraint.

Auth: set WORKATO_TOKEN to a Developer API token (Recipe operator role is enough
for recipe CRUD). Optionally set WORKATO_API_BASE for non-US data centers.

Run:  WORKATO_TOKEN=... python3 server.py     (speaks MCP over stdin/stdout)
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.environ.get("WORKATO_API_BASE", "https://www.workato.com/api")
TOKEN = os.environ.get("WORKATO_TOKEN", "")
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "workato-dev", "version": "1.0.0"}

RECIPES_PATH = "/recipes"
CONNECTIONS_PATH = "/connections"
FOLDERS_PATH = "/folders"
PROJECTS_PATH = "/projects"
ME_PATH = "/users/me"

# Two-tier knowledge base (mirrors the Studio MCP pattern): learnings.md is the
# append-only intake queue; workato_recipe_tips is the curated/promoted tier.
LEARNINGS_PATH = os.environ.get(
    "WORKATO_LEARNINGS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "learnings.md"),
)
LEARNING_CATEGORIES = ["Recipe", "Datapill", "Trigger", "Schema", "HTTP",
                       "Connection", "Job", "Lookup", "Error", "Other"]
PROMOTE_TARGETS = ["recipe_tips", "tool_description", "readme", "all"]
ENTRY_HEADING_RE = r"(?m)^(?=### \[\d{4}-\d{2}-\d{2}\])"


# ── HTTP to the Workato Developer API ─────────────────────────────────────────

def _request(method, path, params=None, body=None):
    """Call the Workato Developer API. Returns parsed JSON (or {error} on failure)."""
    if not TOKEN:
        return {"error": "WORKATO_TOKEN is not set in the environment."}

    url = f"{API_BASE}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)

    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}", "detail": exc.read().decode()[:600]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _items(response):
    if isinstance(response, list):
        return response
    return response.get("items", response.get("result", []))


def _parse_maybe_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _dump(obj):
    return json.dumps(obj, indent=2, default=str)


# ── Tool handlers ─────────────────────────────────────────────────────────────

def whoami():
    return _dump(_request("GET", ME_PATH,
                          params={"fields": "id,name,company_name,current_environment_type"}))


def list_connections():
    conns = _items(_request("GET", CONNECTIONS_PATH))
    return _dump([{"id": c.get("id"), "provider": c.get("provider"),
                   "name": c.get("name"), "connected": c.get("connected")} for c in conns])


def list_folders(parent_id=None):
    folders = _items(_request("GET", FOLDERS_PATH, params={"parent_id": parent_id, "per_page": 100}))
    return _dump([{"id": f.get("id"), "name": f.get("name"), "parent_id": f.get("parent_id")}
                  for f in folders])


def list_projects():
    projects = _items(_request("GET", PROJECTS_PATH, params={"per_page": 100}))
    return _dump([{"id": p.get("id"), "name": p.get("name"), "folder_id": p.get("folder_id")}
                  for p in projects])


def list_recipes(folder_id=None, running=None, name_contains=None):
    recipes = _items(_request("GET", RECIPES_PATH, params={"folder_id": folder_id, "per_page": 100}))
    out = []
    for r in recipes:
        if running is not None and bool(r.get("running")) != running:
            continue
        if name_contains and name_contains.lower() not in str(r.get("name", "")).lower():
            continue
        out.append({"id": r.get("id"), "name": r.get("name"),
                    "running": r.get("running"), "folder_id": r.get("folder_id")})
    return _dump(out)


def get_recipe(recipe_id, include_code=True):
    r = _request("GET", f"{RECIPES_PATH}/{recipe_id}")
    if "error" in r:
        return _dump(r)
    out = {"id": r.get("id"), "name": r.get("name"),
           "running": r.get("running"), "folder_id": r.get("folder_id")}
    if include_code:
        out["config"] = _parse_maybe_json(r.get("config"))
        out["code"] = _parse_maybe_json(r.get("code"))
    return _dump(out)


def get_recipe_steps(recipe_id):
    r = _request("GET", f"{RECIPES_PATH}/{recipe_id}")
    if "error" in r:
        return _dump(r)
    code = _parse_maybe_json(r.get("code")) or {}
    lines = [f"trigger: {code.get('provider')}.{code.get('name')} as={code.get('as')}"]

    def walk(block, depth=1):
        for step in block if isinstance(block, list) else []:
            lines.append("  " * depth + f"[{step.get('keyword')}] "
                         f"{step.get('provider', '')}.{step.get('name', '')} as={step.get('as')}")
            if step.get("block"):
                walk(step["block"], depth + 1)

    walk(code.get("block", []))
    return "\n".join(lines)


def create_recipe(name, folder_id, code, config):
    return _dump(_request("POST", RECIPES_PATH,
                          body={"recipe": {"name": name, "folder_id": folder_id,
                                           "code": code, "config": config}}))


def update_recipe(recipe_id, code=None, name=None, config=None):
    recipe = {}
    if code is not None:
        recipe["code"] = code
    if name is not None:
        recipe["name"] = name
    if config is not None:
        recipe["config"] = config
    if not recipe:
        return _dump({"error": "Provide at least one of code, name, config."})
    return _dump(_request("PUT", f"{RECIPES_PATH}/{recipe_id}", body={"recipe": recipe}))


def start_recipe(recipe_id):
    return _dump(_request("PUT", f"{RECIPES_PATH}/{recipe_id}/start"))


def stop_recipe(recipe_id):
    return _dump(_request("PUT", f"{RECIPES_PATH}/{recipe_id}/stop"))


def copy_recipe(recipe_id, folder_id):
    return _dump(_request("POST", f"{RECIPES_PATH}/{recipe_id}/copy", body={"folder_id": folder_id}))


def delete_recipe(recipe_id):
    return _dump(_request("DELETE", f"{RECIPES_PATH}/{recipe_id}"))


def list_jobs(recipe_id, limit=10):
    jobs = _items(_request("GET", f"{RECIPES_PATH}/{recipe_id}/jobs", params={"per_page": limit}))
    return _dump([{"id": j.get("id"), "status": j.get("status"), "is_error": j.get("is_error"),
                   "started_at": j.get("started_at"), "title": (j.get("title") or "")[:120]}
                  for j in jobs])


def get_job(recipe_id, job_id):
    detail = _request("GET", f"{RECIPES_PATH}/{recipe_id}/jobs/{job_id}")
    if "error" in detail:
        return _dump(detail)
    out = {"id": detail.get("id"), "status": detail.get("status"),
           "started_at": detail.get("started_at"), "lines": []}
    for line in detail.get("lines", []):
        out["lines"].append({
            "step": f"{line.get('adapter_name')}.{line.get('adapter_operation')}",
            "input": line.get("input"), "output": line.get("output"), "error": line.get("error"),
        })
    return _dump(out)


def list_recipe_versions(recipe_id, limit=20):
    resp = _request("GET", f"{RECIPES_PATH}/{recipe_id}/versions", params={"per_page": limit})
    versions = _items(resp) if isinstance(resp, list) else resp.get("data", [])
    return _dump([{"version_no": v.get("version_no"), "id": v.get("id"),
                   "author": v.get("author_name"), "comment": v.get("comment"),
                   "updated_at": v.get("updated_at")} for v in versions])


def create_folder(name, parent_id=None):
    return _dump(_request("POST", FOLDERS_PATH, body={"name": name, "parent_id": parent_id}))


def get_properties(prefix):
    """Account-level properties whose names start with prefix (config/feature flags)."""
    return _dump(_request("GET", "/properties", params={"prefix": prefix}))


def upsert_properties(properties_json):
    """Create/update account properties. properties_json is a JSON object string {name: value}."""
    try:
        props = json.loads(properties_json)
    except json.JSONDecodeError as exc:
        return _dump({"error": f"properties_json must be a JSON object: {exc}"})
    return _dump(_request("POST", "/properties", body={"properties": props}))


def list_lookup_tables():
    tables = _items(_request("GET", "/lookup_tables"))
    return _dump([{"id": t.get("id"), "name": t.get("name"),
                   "project_id": t.get("project_id"), "schema": t.get("schema")} for t in tables])


def query_lookup_table(table_id, limit=20):
    """Read rows from a lookup table (e.g. to inspect captured logs)."""
    return _dump(_request("GET", f"/lookup_tables/{table_id}/rows", params={"per_page": limit}))


def add_lookup_table_row(table_id, entry_json):
    """Append a row to a lookup table. entry_json is a JSON object string {column: value}."""
    try:
        entry = json.loads(entry_json)
    except json.JSONDecodeError as exc:
        return _dump({"error": f"entry_json must be a JSON object: {exc}"})
    return _dump(_request("POST", f"/lookup_tables/{table_id}/rows", body={"entry": entry}))


def list_data_tables():
    resp = _request("GET", "/data_tables")
    rows = resp.get("data", _items(resp)) if isinstance(resp, dict) else resp
    return _dump([{"id": t.get("id"), "name": t.get("name")} for t in (rows or [])])


def list_api_collections():
    """List API Platform collections (the endpoints behind API-collection-backed MCP servers)."""
    cols = _items(_request("GET", "/api_collections", params={"per_page": 100}))
    return _dump([{"id": c.get("id"), "name": c.get("name"), "version": c.get("version")} for c in cols])


def list_api_endpoints(api_collection_id):
    """List an API collection's endpoints — the tools an API-Platform-backed MCP server exposes."""
    eps = _items(_request("GET", "/api_endpoints",
                          params={"api_collection_id": api_collection_id, "per_page": 100}))
    return _dump([{"id": e.get("id"), "name": e.get("name"), "method": e.get("method"),
                   "path": e.get("path"), "active": e.get("active"), "flow_id": e.get("flow_id"),
                   "description": (e.get("description") or "")[:160]} for e in eps])


def list_api_clients():
    clients = _items(_request("GET", "/api_clients", params={"per_page": 100}))
    return _dump([{"id": c.get("id"), "name": c.get("name")} for c in clients])


def list_api_access_profiles():
    profiles = _items(_request("GET", "/api_access_profiles", params={"per_page": 100}))
    return _dump([{"id": p.get("id"), "name": p.get("name"), "api_client_id": p.get("api_client_id")}
                  for p in profiles])


def enable_api_endpoint(api_endpoint_id):
    """Activate an endpoint (turns the tool ON). The backing recipe must be started first or this fails."""
    return _dump(_request("PUT", f"/api_endpoints/{api_endpoint_id}/enable"))


def disable_api_endpoint(api_endpoint_id):
    return _dump(_request("PUT", f"/api_endpoints/{api_endpoint_id}/disable"))


def create_api_collection(name, project_id):
    return _dump(_request("POST", "/api_collections", params={"project_id": project_id}, body={"name": name}))


def log_learning(title, category, trigger, pattern, example=None, promote_to="recipe_tips"):
    """Append a discovered gotcha to learnings.md. Local file write — no Workato API call."""
    if not os.path.exists(LEARNINGS_PATH):
        return _dump({"error": "LEARNINGS_NOT_FOUND",
                      "detail": f"learnings.md not found at {LEARNINGS_PATH}",
                      "suggestion": "Ensure the repo is intact — learnings.md belongs in the repo root."})
    date = datetime.date.today().isoformat()
    lines = [f"\n### [{date}] {title}",
             f"**Category**: {category}",
             f"**Trigger**: {trigger}",
             f"**Pattern**: {pattern}"]
    if example:
        lines += ["**Example**:", "```", example, "```"]
    lines += [f"**Promote to**: {promote_to}", "**Status**: raw", ""]
    try:
        with open(LEARNINGS_PATH, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except OSError as exc:
        return _dump({"error": "WRITE_FAILED", "detail": str(exc),
                      "suggestion": "Check file permissions on learnings.md."})
    return _dump({"logged": True, "title": title, "date": date, "promote_to": promote_to,
                  "path": LEARNINGS_PATH,
                  "message": "Logged to learnings.md. Ask the user to commit it so the team benefits."})


def get_learnings(category=None):
    """Read the learnings.md intake log, optionally filtered to one category."""
    if not os.path.exists(LEARNINGS_PATH):
        return _dump({"error": "LEARNINGS_NOT_FOUND", "detail": f"Not found at {LEARNINGS_PATH}"})
    try:
        with open(LEARNINGS_PATH, encoding="utf-8") as fh:
            content = fh.read()
    except OSError as exc:
        return _dump({"error": "READ_FAILED", "detail": str(exc)})
    if not category:
        return content
    cat_line = re.compile(rf"(?m)^\*\*Category\*\*: {re.escape(category)}\s*$")
    entries = re.split(ENTRY_HEADING_RE, content)[1:]  # drop the preamble/format block
    matched = [e for e in entries if cat_line.search(e)]
    if not matched:
        return f"No learnings found in category '{category}'."
    return f"# Learnings — category: {category}\n\n" + "".join(matched)


def workato_recipe_tips():
    return _TIPS


# ── Tool registry (name -> handler, description, JSON schema) ──────────────────

def _schema(properties, required=None):
    return {"type": "object", "properties": properties, "required": required or []}

_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}

TOOLS = [
    ("whoami", whoami, "Return the authenticated user and workspace for the current token.",
     _schema({})),
    ("list_connections", list_connections,
     "List Workato connections (id, provider, name, connected) for wiring recipe config.", _schema({})),
    ("list_folders", list_folders, "List folders, optionally under a parent folder id.",
     _schema({"parent_id": _STR})),
    ("list_projects", list_projects, "List Workato projects (id, name, root folder).", _schema({})),
    ("list_recipes", list_recipes,
     "List recipes with optional filters: folder_id, running (bool), name_contains (substring).",
     _schema({"folder_id": _STR, "running": _BOOL, "name_contains": _STR})),
    ("get_recipe", get_recipe,
     "Fetch a recipe. With include_code=true returns the parsed code tree + config (source of truth for editing).",
     _schema({"recipe_id": _INT, "include_code": _BOOL}, ["recipe_id"])),
    ("get_recipe_steps", get_recipe_steps,
     "Return a compact step tree (keyword/provider/name/as) for quick structure inspection.",
     _schema({"recipe_id": _INT}, ["recipe_id"])),
    ("create_recipe", create_recipe,
     "Create a recipe. code and config are JSON strings (the code tree and connection config array). folder_id is a string.",
     _schema({"name": _STR, "folder_id": _STR, "code": _STR, "config": _STR},
             ["name", "folder_id", "code", "config"])),
    ("update_recipe", update_recipe,
     "Update a recipe's code/name/config (code & config as JSON strings). Stop a running recipe first.",
     _schema({"recipe_id": _INT, "code": _STR, "name": _STR, "config": _STR}, ["recipe_id"])),
    ("start_recipe", start_recipe,
     "Start (activate) a recipe. Start-time validation errors surface here — read them to debug.",
     _schema({"recipe_id": _INT}, ["recipe_id"])),
    ("stop_recipe", stop_recipe,
     "Stop (deactivate) a recipe. Required before updating a running recipe's code.",
     _schema({"recipe_id": _INT}, ["recipe_id"])),
    ("copy_recipe", copy_recipe,
     "Server-side copy of a recipe into a folder (preserves step `as` ids).",
     _schema({"recipe_id": _INT, "folder_id": _STR}, ["recipe_id", "folder_id"])),
    ("delete_recipe", delete_recipe,
     "Permanently delete a recipe. Cannot be undone — confirm with the user first.",
     _schema({"recipe_id": _INT}, ["recipe_id"])),
    ("list_jobs", list_jobs, "List recent jobs for a recipe (id, status, started_at, title).",
     _schema({"recipe_id": _INT, "limit": _INT}, ["recipe_id"])),
    ("get_job", get_job,
     "Fetch one job's per-step input/output/error — see what each adapter call actually sent/got, "
     "and catch errors a 'succeeded' job hid in a catch block.",
     _schema({"recipe_id": _INT, "job_id": _STR}, ["recipe_id", "job_id"])),
    ("list_recipe_versions", list_recipe_versions,
     "List a recipe's version history (version_no, author, comment) — for tracking/rollback awareness.",
     _schema({"recipe_id": _INT, "limit": _INT}, ["recipe_id"])),
    ("create_folder", create_folder, "Create a folder, optionally under a parent folder id.",
     _schema({"name": _STR, "parent_id": _STR}, ["name"])),
    ("get_properties", get_properties,
     "Get account properties whose names start with a prefix (config/feature flags).",
     _schema({"prefix": _STR}, ["prefix"])),
    ("upsert_properties", upsert_properties,
     "Create/update account properties. properties_json is a JSON object string {name: value}.",
     _schema({"properties_json": _STR}, ["properties_json"])),
    ("list_lookup_tables", list_lookup_tables, "List lookup tables (id, name, schema).", _schema({})),
    ("query_lookup_table", query_lookup_table,
     "Read rows from a lookup table by id (e.g. to inspect captured query logs).",
     _schema({"table_id": _INT, "limit": _INT}, ["table_id"])),
    ("add_lookup_table_row", add_lookup_table_row,
     "Append a row to a lookup table. entry_json is a JSON object string {column: value}. "
     "Table must have a defined schema. Useful for writing capture/log rows.",
     _schema({"table_id": _INT, "entry_json": _STR}, ["table_id", "entry_json"])),
    ("list_data_tables", list_data_tables, "List Workato Data Tables (id, name).", _schema({})),
    ("list_api_collections", list_api_collections,
     "List API Platform collections — each is an API product that can be exposed as a Workato MCP server.",
     _schema({})),
    ("list_api_endpoints", list_api_endpoints,
     "List an API collection's endpoints — the TOOLS an API-Platform-backed Workato MCP server exposes. "
     "Shows each tool's method, path, active flag, and backing recipe (flow_id). Run list_api_collections first.",
     _schema({"api_collection_id": _INT}, ["api_collection_id"])),
    ("list_api_clients", list_api_clients,
     "List API clients — the credentialed consumers that call API-Platform endpoints.", _schema({})),
    ("list_api_access_profiles", list_api_access_profiles,
     "List API access profiles — scope/auth bindings between API clients and collections.", _schema({})),
    ("enable_api_endpoint", enable_api_endpoint,
     "Activate an API-Platform endpoint — turns an inactive tool ON in its MCP-exposed collection. "
     "PREREQUISITE: start the backing recipe (flow_id) first, or enable fails. This mutates a LIVE MCP "
     "server's tool surface — confirm the endpoint id and intent with the user before calling.",
     _schema({"api_endpoint_id": _INT}, ["api_endpoint_id"])),
    ("disable_api_endpoint", disable_api_endpoint,
     "Deactivate an API-Platform endpoint — turns a tool OFF so MCP clients can no longer call it. "
     "Mutates a live MCP server's tool surface — confirm with the user first.",
     _schema({"api_endpoint_id": _INT}, ["api_endpoint_id"])),
    ("create_api_collection", create_api_collection,
     "Create an API collection (which can then be exposed as a Workato MCP server). Needs name + project_id. "
     "Note: endpoints themselves are added in the UI — there is no create-endpoint Developer API.",
     _schema({"name": _STR, "project_id": _INT}, ["name", "project_id"])),
    ("log_learning", log_learning,
     "Append a newly discovered Workato recipe/API gotcha to learnings.md (the team intake queue). "
     "CALL THIS AUTOMATICALLY when you hit a non-obvious behavior NOT already in workato_recipe_tips — "
     "a schema quirk, an invalid formula/operand, a datapill that won't bind, an HTTP body that strips "
     "pills, an unexpected job result. Then tell the user to commit learnings.md so the team benefits.",
     _schema({"title": _STR,
              "category": {"type": "string", "enum": LEARNING_CATEGORIES},
              "trigger": _STR, "pattern": _STR, "example": _STR,
              "promote_to": {"type": "string", "enum": PROMOTE_TARGETS}},
             ["title", "category", "trigger", "pattern"])),
    ("get_learnings", get_learnings,
     "Read the learnings.md intake log — accumulated team discoveries not yet promoted into "
     "workato_recipe_tips. Optionally filter to one category. Consult this alongside workato_recipe_tips "
     "before building a recipe.",
     _schema({"category": {"type": "string", "enum": LEARNING_CATEGORIES}})),
    ("workato_recipe_tips", workato_recipe_tips,
     "Hard-won gotchas for authoring Workato recipes via the Developer API (the curated tier). "
     "Read before building/editing. New discoveries go to log_learning first.",
     _schema({})),
]
_HANDLERS = {name: fn for name, fn, _desc, _s in TOOLS}
_TOOL_DEFS = [{"name": name, "description": desc, "inputSchema": schema}
              for name, _fn, desc, schema in TOOLS]


# ── Minimal MCP stdio JSON-RPC loop ───────────────────────────────────────────

def _handle(method, params):
    if method == "initialize":
        return {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": _TOOL_DEFS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = _HANDLERS.get(name)
        if fn is None:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
        try:
            text = fn(**args)
        except Exception as exc:  # noqa: BLE001 - report tool errors as content, not crashes
            return {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "isError": True}
        return {"content": [{"type": "text", "text": text}], "isError": False}
    raise ValueError(f"Method not found: {method}")


def _send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_id = msg.get("id")
        method = msg.get("method")
        if msg_id is None:  # notification (e.g. notifications/initialized) — no response
            continue
        try:
            result = _handle(method, msg.get("params") or {})
            _send({"jsonrpc": "2.0", "id": msg_id, "result": result})
        except Exception as exc:  # noqa: BLE001
            _send({"jsonrpc": "2.0", "id": msg_id,
                   "error": {"code": -32603, "message": str(exc)}})


_TIPS = """\
Workato recipe authoring via Developer API — gotchas that cost real debugging time:

EDIT LOOP
- get_recipe(include_code) -> mutate the parsed code tree -> stop_recipe -> update_recipe(code=json) -> start_recipe.
- start_recipe is the compiler: its validation errors ([line, [[field, value, msg]]]) are your feedback loop.
- Step `number` fields must be sequential in DFS order — renumber the whole tree after inserting/removing steps.

DATAPILLS
- Reference an upstream output with a compact pill string:
  #{_dp('{"pill_type":"output","provider":"<adapter>","line":"<step as>","path":["field","subfield"]}')}
- Use compact JSON (no spaces) inside _dp. Array item paths use {"path_element_type":"current_item"}.
- Formula mode is `=_dp('...')` (supports .present?/.blank?/ternaries); interpolation mode is "#{_dp('...')}".

TRIGGER PARAMS (skill/genie MCP triggers)
- Parameter datapills (path ["parameters","x"]) FAIL start-validation unless the trigger carries a top-level
  extended_output_schema mirroring parameters_schema_json:
  "extended_output_schema":[{"label":"Parameters","name":"parameters","type":"object","properties":[<same params>]}]
- Changing a tool's PARAM SET doesn't reach an MCP client via reconnect — the client app must be RESTARTED
  (and the tool re-added in AI Hub). Description/enum/hint tweaks DO propagate on reconnect.

RETURN STEPS (workflow_return_result)
- result mapping is stripped to {} on save unless the step carries extended_input_schema
  [{label:"Result",name:"result",type:"object",properties:<result_schema entries>}].

CUSTOM CODE (workato_custom_code / Ruby)
- Add the workato_custom_code app to recipe config or start fails "missing adapter configuration".
- code_input.data is NULL at runtime unless the step's extended_input_schema is the exact form-schema-builder
  shape with "sticky":true,"type":"object". Omitting those = null data.

HTTP CONNECTOR (rest.make_request_v2) — endpoints with no native action
- request.body as a DICT strips datapills on save (persists {}). Build the JSON body as a STRING in a Ruby step,
  then set request.body to a single string pill "#{_dp(ruby.output.body)}". String bodies persist datapills.

CONDITIONS (if steps): valid operands include is_true / present / blank / equals_to. `equals` is INVALID.
CATCH: a catch goes INSIDE the try's block as the last element (sibling catch -> "catch expected in block").
DEBUGGING: a job can show "succeeded" while returning {result:{error:...}} (catch masking). Read get_job
  lines for real adapter input/output, not just job status.
"""


if __name__ == "__main__":
    main()
