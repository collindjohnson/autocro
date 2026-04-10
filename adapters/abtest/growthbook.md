# Adapter: GrowthBook

kind: abtest
id: growthbook

Reference adapter for [GrowthBook](https://www.growthbook.io) — an open-source feature flag and experimentation platform. The REST API is clean and maps 1:1 to the abtest contract: create experiments at the caller-requested coverage, poll results, promote by updating phase coverage, and archive. Works with both cloud and self-hosted GrowthBook.

## requires

```yaml
env:
  - GROWTHBOOK_API_KEY           # personal access token or secret key with experiment write scope
  - GROWTHBOOK_DATASOURCE_ID     # datasource UUID from GrowthBook settings > Data Sources
  - GROWTHBOOK_API_HOST          # OPTIONAL: override for self-hosted (default: https://api.growthbook.io)
command: [curl, jq]
```

## health

1. `curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $GROWTHBOOK_API_KEY" "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments?limit=1"` → expect HTTP 200.
2. Parse the response: `jq '.experiments'` → expect an array (possibly empty on new workspaces).
3. Verify the datasource exists: `curl -sS -H "Authorization: Bearer $GROWTHBOOK_API_KEY" "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/data-sources/$GROWTHBOOK_DATASOURCE_ID"` → expect HTTP 200 with an object whose `id` matches.
4. If HTTP 401 / 403: stop with `credentials invalid for GROWTHBOOK_API_KEY — regenerate at $GROWTHBOOK_API_HOST/settings/keys and ensure it has Experiment write scope`.

## capabilities

- push_variant: implemented
- get_experiment: implemented
- list_experiments: implemented
- promote: implemented
- archive: implemented

## read

### get_experiment(experiment_id)

Call:
```bash
# 1. Experiment metadata
EXP=$(curl -sS -H "Authorization: Bearer $GROWTHBOOK_API_KEY" \
  "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments/$experiment_id")

# 2. Latest results snapshot (may 404 if the experiment has no data yet)
RES=$(curl -sS -H "Authorization: Bearer $GROWTHBOOK_API_KEY" \
  "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments/$experiment_id/results" || echo '{}')
```

Transform:
```
status:
  if EXP.status == "running"     -> "running"
  if EXP.status == "stopped"     -> "stopped"
  if EXP.status == "draft"       -> "running"   (GrowthBook "draft" is equivalent to 0% allocation, which is our running-but-not-live state)
  if EXP.results == "won"        -> "completed"
  if EXP.results == "lost"       -> "completed"
  if EXP.results == "inconclusive" -> "completed"
  otherwise                      -> "running"

visitors    = sum of RES.analyses[0].variations[i].users   (0 if missing)
lift        = RES.analyses[0].variations[1].chanceToWin is a probability, not lift —
              use the "relative" metric effect: RES.analyses[0].variations[1].metrics[goal_metric_id].expected
ci_low      = RES.analyses[0].variations[1].metrics[goal_metric_id].ciLow
ci_high     = RES.analyses[0].variations[1].metrics[goal_metric_id].ciHigh
p           = 1 - RES.analyses[0].variations[1].metrics[goal_metric_id].chanceToWin   (GB reports chanceToWin, not p directly)
started_at  = EXP.dateCreated
ended_at    = EXP.phases[-1].dateEnded  (null if status != stopped/completed)
```

Return:
```jsonc
{"experiment_id": "<gb-exp-id>", "status": "running", "visitors": 4200,
 "lift": 0.037, "ci_low": 0.012, "ci_high": 0.061, "p": 0.032,
 "started_at": "2026-03-25T00:00:00Z", "ended_at": null}
```

### list_experiments()

Call:
```bash
curl -sS -H "Authorization: Bearer $GROWTHBOOK_API_KEY" \
  "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments?limit=100"
```

Transform:
```
for each EXP in .experiments:
  experiment_id = EXP.id
  status        = (same mapping as get_experiment)
  lift          = 0 unless EXP.results[0] has an expected effect (lazy — lift comes from a /results call)
```

Return:
```jsonc
[{"experiment_id": "exp_abc123", "status": "running", "lift": 0.0},
 {"experiment_id": "exp_def456", "status": "completed", "lift": 0.021}, ...]
```

## write

### push_variant(slug, patch_path, description, allocation_pct)

Create a new experiment with one control + one treatment variation, at `allocation_pct / 100` coverage and a 50/50 split within that coverage. The caller passes `allocation_pct=0` in manual/off mode (the experiment is created as a GrowthBook draft; the human ramps later via `promote()`) and `config.workflow.auto_allocation_pct` (default 50) in auto mode (the experiment goes live immediately).

Validate: `allocation_pct` must be an integer in `[0, 100]`. Reject anything else with a clear error.

Call:
```bash
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
COVERAGE=$(python3 -c "print(${allocation_pct} / 100.0)")

curl -sS -X POST \
  -H "Authorization: Bearer $GROWTHBOOK_API_KEY" \
  -H "Content-Type: application/json" \
  "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments" \
  -d @- <<EOF
{
  "trackingKey": "${slug}",
  "name": "${slug}",
  "description": "${description} (patch: ${patch_path})",
  "datasourceId": "${GROWTHBOOK_DATASOURCE_ID}",
  "variations": [
    {"key": "0", "name": "control"},
    {"key": "1", "name": "treatment"}
  ],
  "phases": [
    {
      "name": "Main",
      "coverage": ${COVERAGE},
      "variationWeights": [0.5, 0.5],
      "dateStarted": "${NOW}"
    }
  ]
}
EOF
```

Transform the response:
```
experiment_id  = .id
adapter        = "growthbook"
allocation     = allocation_pct / 100.0
allocation_pct = allocation_pct
started_at     = NOW
```

Return:
```jsonc
{"experiment_id": "exp_abc123", "adapter": "growthbook",
 "allocation": 0.5, "allocation_pct": 50,
 "started_at": "2026-04-10T12:34:56Z"}
```

### promote(experiment_id, allocation)

Promote by PATCHing the experiment's latest phase `coverage` value. This is only called manually by the human — the agent never auto-promotes.

Call:
```bash
curl -sS -X PATCH \
  -H "Authorization: Bearer $GROWTHBOOK_API_KEY" \
  -H "Content-Type: application/json" \
  "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments/$experiment_id" \
  -d "{\"phases\": [{\"coverage\": ${allocation}, \"variationWeights\": [0.5, 0.5]}]}"
```

Return:
```jsonc
{"experiment_id": "exp_abc123", "allocation": 0.5}
```

### archive(experiment_id)

Stop the experiment. GrowthBook has `status=stopped` for permanently ending; archive moves it out of the active list.

Call:
```bash
curl -sS -X PATCH \
  -H "Authorization: Bearer $GROWTHBOOK_API_KEY" \
  -H "Content-Type: application/json" \
  "${GROWTHBOOK_API_HOST:-https://api.growthbook.io}/api/v1/experiments/$experiment_id" \
  -d '{"status": "stopped", "results": "inconclusive"}'
```

Return:
```jsonc
{"experiment_id": "exp_abc123", "status": "stopped"}
```

## idioms

- **GrowthBook uses `chanceToWin` (a Bayesian probability) instead of frequentist `p`.** The Transform step converts it with `p = 1 - chanceToWin`. This is an approximation and breaks down when `chanceToWin` is close to 0.5 — be explicit in hypothesis.md that the p-value is Bayesian-derived.
- **GrowthBook experiments must be attached to a "datasource".** `GROWTHBOOK_DATASOURCE_ID` is a required env var because there is no sensible default. Get the ID from GrowthBook settings > Data Sources > (your source) > the id in the URL.
- **`trackingKey` must be unique per experiment.** The adapter uses the variant slug (e.g. `v0042-hero-cta`) as the tracking key, which guarantees uniqueness given the slug rules in `skills/generate-variant.md`.
- **Coverage vs variation weights**: `coverage` is the fraction of all users included in the experiment; `variationWeights` is the split between control and treatment within that coverage. We always set `variationWeights: [0.5, 0.5]` and only move `coverage`. Do NOT try to control traffic by adjusting variation weights.
- **Promotion is manual only in `review_mode: "manual"`.** The agent never calls `promote` from the inner loop. Humans ramp allocation after real results come in. In `review_mode: "auto"` the variant is created at `auto_allocation_pct` coverage up front, so no ramp is needed.
- **Rate limit**: GrowthBook cloud is documented at 60 req/min for the v1 API. Self-hosted has no enforced limit.
- **Last verified: 2026-04**

## fallbacks

- **HTTP 5xx / transient failure**: retry once. On second failure, log to `run.log` and skip the call for this iteration (return empty / status-unchanged).
- **HTTP 401 / 403**: stop with `credentials invalid for GROWTHBOOK_API_KEY`.
- **HTTP 404 on get_experiment**: the experiment ID was deleted upstream. Return `{"experiment_id": experiment_id, "status": "stopped", "visitors": 0, "lift": 0, "ci_low": 0, "ci_high": 0, "p": 1, "started_at": "...", "ended_at": "...current time..."}` and log a warning.
- **HTTP 429 (rate limit)**: back off 60s, retry once, return empty.
- **`mode: fixture`**: bypass the live calls and delegate to `adapters/abtest/fixture.md` behavior: `get_experiment` reads from `fixtures/experiment-sample.json`, `list_experiments` returns that array, `push_variant` / `promote` / `archive` return deterministic stub responses matching the schema (see fixture.md). This is MANDATORY so `skills/validate-adapter.md` can verify the adapter without hitting GrowthBook.
