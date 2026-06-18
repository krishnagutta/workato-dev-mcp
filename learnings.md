# Workato Dev Learnings

Append-only intake log. When Claude discovers a new Workato recipe/API pattern, schema rule, or gotcha during a build session, it appends an entry here via the `log_learning` tool.

Entries get promoted into the curated tier — the `workato_recipe_tips` tool (`_TIPS` in `server.py`) and/or this repo's docs — during periodic review. This is the same two-tier system the Studio MCP uses (`learnings.md` → curated patterns doc).

---

## Entry format

```
### [YYYY-MM-DD] Short title
**Category**: Recipe | Datapill | Trigger | Schema | HTTP | Connection | Job | Lookup | Error | Other
**Trigger**: What caused the discovery (e.g. "start_recipe failed with [line, [[field, value, msg]]]")
**Pattern**: What we learned — specific and actionable, written for the next teammate
**Example** (optional):
​```
# minimal recipe-code / datapill / formula snippet showing the correct or incorrect form
​```
**Promote to**: recipe_tips | tool_description | readme | all
**Status**: raw
```

---

<!-- newest entries first; the entries below are seeded from workato_recipe_tips so the format is concrete -->

### [2026-06-17] HTTP make_request_v2 body as a dict strips datapills on save
**Category**: HTTP
**Trigger**: A rest.make_request_v2 step built its JSON body as a structured object; after update_recipe the body persisted as {} and all datapills were gone.
**Pattern**: For HTTP-connector calls with no native action, do NOT build request.body as a dict — it strips datapills on save. Build the JSON body as a STRING in a preceding Ruby (custom_code) step, then set request.body to a single string pill `#{_dp(ruby.output.body)}`. String bodies persist datapills.
**Promote to**: recipe_tips
**Status**: promoted
