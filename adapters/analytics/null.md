# Adapter: Null Analytics

kind: analytics
id: null

A no-op adapter. Every `read` call returns empty. Use this when no analytics adapter has been authored yet — the inner loop will run without analytics data and will rely entirely on heuristic heatmap (if enabled) or on explore-mode hypotheses that target `config.goal.target_paths` without citing traffic data.

## requires

```yaml
env: []
command: []
```

## health

1. Always passes. This adapter has nothing to check.

## capabilities

- top_pages: implemented (returns empty)
- landing_pages: implemented (returns empty)
- funnel: implemented (returns empty)
- traffic_sources: implemented (returns empty)
- conversions: implemented (returns empty)
- session_quality: implemented (returns empty)

## read

### top_pages(window, limit)

Return: `[]`

### landing_pages(window, limit)

Return: `[]`

### funnel(steps)

Return: `[]`

### traffic_sources(window, limit)

Return: `[]`

### conversions(event, window)

Return: `{"event": "<event>", "count": 0, "sessions": 0, "rate": 0.0}`

### session_quality(path, window)

Return: `{"path": "<path>", "avg_time_s": 0, "scroll_depth_p50": 0.0, "bounce_rate": 0.0, "engagement_score": 0.0}`

## idioms

- When this adapter is active, `skills/hypothesize.md` must fall back to heuristic / judge-rubric driven hypotheses that target `config.goal.target_paths` without citing traffic data.
- Hypotheses generated under this adapter should tag `hypothesis_source` as `null:<capability>` to make it visible in the analysis notebook that they were not data-grounded.

## fallbacks

- N/A. This adapter never makes live calls.
- `mode: fixture`: same as `live` — returns empty.
