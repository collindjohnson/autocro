# Adapter: <Human-readable name>

kind: <analytics | heatmap | abtest>
id: <unique lowercase kebab-case id, matches the filename>

## requires

```yaml
# Environment variables this adapter needs. Values are read from os.environ
# at call time; never inline real credentials here.
env: []

# CLI tools that must be on PATH when the adapter runs.
command: [curl, jq]

# Optional: MCP tools this adapter uses, if any.
# mcp: []
```

## health

Read-only operations that must succeed before the loop trusts this adapter. `program.md` runs these during setup. Structure as a numbered list with a concrete call and a pass criterion per step. Required adapter that fails health → setup stops.

1. TODO: describe the first health check.
2. TODO: describe the second health check.
3. TODO: describe the third health check (optional).

## capabilities

List the contract methods this adapter implements (see `adapters/README.md` for the full list per kind). Mark unsupported methods explicitly so the inner loop routes around them.

### analytics kind (delete lines that don't apply if this is a different kind)

- top_pages: not_implemented
- landing_pages: not_implemented
- funnel: not_implemented
- traffic_sources: not_implemented
- conversions: not_implemented
- session_quality: not_implemented

### heatmap kind

- page_attention: not_implemented
- click_map: not_implemented
- rage_clicks: not_implemented
- session_sample: not_implemented

### abtest kind

- push_variant: not_implemented
- get_experiment: not_implemented
- list_experiments: not_implemented
- promote: not_implemented
- archive: not_implemented

## read

For each implemented capability, document:

1. The exact call (curl, CLI, or MCP invocation) including all arguments.
2. Any transformation needed to normalize the raw response.
3. The normalized return shape (copy from `adapters/README.md`).

### <capability_name>(<args>)

Call:
```bash
# TODO: exact call
```

Transform:
```
# TODO: if the raw response differs from the normalized shape, describe the
# mapping here (e.g. "rename `page_url` -> `path`; divide `events` / `sessions`
# to compute `conv_rate`").
```

Return:
```jsonc
// TODO: paste the normalized shape from adapters/README.md exactly
```

Repeat this block for each implemented capability.

## write

(abtest adapters only; delete this section for analytics and heatmap adapters)

### push_variant(slug, patch_path, description, allocation_pct)

1. Validate `allocation_pct` is an integer in `[0, 100]`. The caller passes `0` in manual/off mode and `config.workflow.auto_allocation_pct` (default 50) in auto mode. Reject anything outside the range with a clear error.
2. TODO: create the experiment in the tool. Set the variant traffic to `allocation_pct / 100.0` in whatever field your tool uses (`coverage`, `weight`, `traffic_split`, etc.). Do NOT hardcode 0%.
3. TODO: attach the patch as documentation (link, upload, or metadata).
4. TODO: return `{"experiment_id": ..., "adapter": "<id>", "allocation": <allocation_pct / 100.0>, "started_at": "<ISO-8601>"}`.

### get_experiment(experiment_id)

1. TODO: fetch the experiment results.
2. TODO: map to the normalized shape with visitors / lift / CI / p.

### list_experiments()

1. TODO: list all experiments managed by this adapter.

### promote(experiment_id, allocation)

1. TODO: ramp traffic allocation (only called manually by the human — the agent does not auto-promote).

### archive(experiment_id)

1. TODO: stop or archive an experiment.

## idioms

Short rules for interpreting data from this tool. These shape how `skills/hypothesize.md` reads the adapter's output. Examples:

- TODO: "Sampling kicks in above N events — high-volume counts are estimates."
- TODO: "Timestamps are UTC."
- TODO: "Data lag is ~30 minutes."
- TODO: "Minimum meaningful sample size for conversion reporting is N sessions."

## fallbacks

How the adapter behaves when things go wrong. Must cover at minimum:

- **HTTP 5xx / transient failure**: TODO: retry once with smaller window; then warn and return empty.
- **HTTP 4xx auth failure**: TODO: stop with a clear "credentials invalid" error; do not retry.
- **Rate limit / quota exceeded**: TODO: back off, return empty, continue loop.
- **`mode: fixture`**: Bypass the live call entirely and read from `fixtures/<kind>-sample.json`. The file contains a pre-shaped response for every capability this adapter implements. This is mandatory — verification depends on it.
