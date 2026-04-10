# Adapter: Null Heatmap

kind: heatmap
id: null

A no-op adapter. Every read call returns empty. The inner loop treats heatmap as optional, so the loop runs fine without heatmap data — hypotheses will just rely on analytics + the judge rubric.

## requires

```yaml
env: []
command: []
```

## health

1. Always passes.

## capabilities

- page_attention: implemented (returns empty)
- click_map: implemented (returns empty)
- rage_clicks: implemented (returns empty)
- session_sample: implemented (returns empty)

## read

### page_attention(path)

Return:
```json
{"path": "<path>", "scroll_depth_p50": 0.0, "scroll_depth_p90": 0.0, "hotspots": []}
```

### click_map(path, limit)

Return: `[]`

### rage_clicks(path, limit)

Return: `[]`

### session_sample(path, n)

Return: `[]`

## idioms

- `skills/hypothesize.md` should not treat absence of heatmap data as evidence of anything. Just proceed without citing heatmap.

## fallbacks

- N/A.
- `mode: fixture`: same as `live` — returns empty.
