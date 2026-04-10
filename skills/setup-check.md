# Skill: setup-check

The first thing `program.md` runs. Validates `config.yaml`, verifies every referenced adapter file exists, and confirms every `*_env` environment variable is actually set before the inner loop touches anything. On any problem, surface a structured, actionable error to the human and stop. No degraded-mode startup on user errors.

Invoked by `program.md` step 1. Calls `harness/yaml_to_json.py`, `harness/validate.py`, and (for adapter capability validation) `skills/validate-adapter.md`.

## Why this exists

Without this skill, the inner loop would start with a silently-wrong config or a missing env var, producing confusing output hours into a run. The rule is: every failure mode must stop setup with a line-addressed message that tells the human WHAT is wrong, WHERE, and HOW to fix it.

## Steps

### 1. Confirm `config.yaml` exists

```
ls autoresearch-web/config.yaml
```

If missing, stop with:

```
SETUP CHECK FAILED: config.yaml not found
expected: autoresearch-web/config.yaml
fix: cp autoresearch-web/config.example.yaml autoresearch-web/config.yaml
     then edit it to set project.root, goal.event, goal.target_paths,
     and the adapter ids you want.
setup stopped.
```

### 2. Convert `config.yaml` to JSON and run schema validation

```bash
python3 autoresearch-web/harness/yaml_to_json.py autoresearch-web/config.yaml \
  | python3 autoresearch-web/harness/validate.py config --stdin
```

This runs two layers of checks:

- `yaml_to_json.py` parses the config with a minimal YAML subset parser (stdlib only). If the config uses unsupported YAML features, it stops with a clear line number.
- `validate.py config` runs the draft-07 schema from `harness/schemas/config.json` plus post-schema rules: weights sum ≈ 1.0, `discard < push`, and a literal-secret heuristic for `config.adapters.*`.

On any failure, exit code is 2 (user error) or 3 (load/parser error). Surface the stderr block verbatim to the human and stop. Exit code 4 (internal helper crash) is NOT the user's fault — log a warning in `run.log` and continue, but mark the config as "unvalidated" so later steps know to be cautious.

### 3. Verify adapter files exist for every non-null, non-fixture id

For each `config.adapters.<kind>.id` that is neither `null` nor `"fixture"`:

```
ls autoresearch-web/adapters/<kind>/<id>.md
```

Missing file → stop with:

```
SETUP CHECK FAILED: adapter file not found
config.adapters.<kind>.id = "<id>"
expected: autoresearch-web/adapters/<kind>/<id>.md
exists: no
fix: either (a) set adapters.<kind>.id: null in config.yaml to run without that data source,
            (b) run skills/author-adapter.md to create it, or
            (c) git pull — the reference adapter may not be checked in yet.
setup stopped.
```

### 4. Parse each loaded adapter's `requires.env` list and verify the vars are set

For each adapter file loaded in step 3, read its `requires` block (the YAML frontmatter inside `## requires`) and for every name in `env`, check `os.environ`:

```bash
python3 -c 'import os, sys; print("SET" if os.environ.get(sys.argv[1]) else "MISSING")' VAR_NAME
```

Or, equivalently, the agent can check its own environment. A missing env var stops setup with:

```
SETUP CHECK FAILED: required env var not set
adapter: autoresearch-web/adapters/<kind>/<id>.md
missing: <VAR_NAME>
declared at: adapters/<kind>/<id>.md :: requires.env
fix: export <VAR_NAME>=<value>
     then re-run program.md setup.
setup stopped.
```

If `config.mode: fixture` is set, skip this check — fixture mode is supposed to run without real credentials. Note the skip in `run.log`.

### 5. Run `skills/validate-adapter.md` against each loaded adapter

For each non-null adapter, invoke `skills/validate-adapter.md` with the adapter path and the current `config.mode`. That skill runs each declared capability once (against live APIs or fixture data, per mode) and pipes the response to `harness/validate.py` to confirm the returned shape matches the contract.

Failure → stop setup with the full error block from validate.py's stderr. See `skills/validate-adapter.md` for the exact error format and what it tells the human about fixing the adapter's `## read` section.

### 6. Confirm success

If all five steps pass, write one line to `run.log`:

```
{"ts": "<ISO-8601>", "event": "setup_check_passed", "adapter": null, "capability": null, "files_read": <n>, "files_written": 1, "notes": "config.yaml and all enabled adapters validated"}
```

And tell the human:

```
setup-check passed: config.yaml OK, adapters validated ({n_adapters} enabled, {n_null} null), env vars set.
```

Then return control to `program.md` for the remaining setup steps.

## What this skill must NOT do

- **Do not edit `config.yaml`.** If a value is wrong, the human fixes it — the skill only reports.
- **Do not prompt the human for missing env vars.** Stop with an actionable error and let the human set them before re-running.
- **Do not guess at adapter ids.** If the file is missing, say so; don't silently fall back.
- **Do not skip a step on exit code 4.** Exit 4 is a helper crash; log a warning but flag the config as unvalidated — do not continue as if nothing happened.
- **Do not run the inner loop.** This skill is pure validation. `program.md` handles loop orchestration.

## Fixture mode note

When `config.mode: fixture`:

- Step 4 (env var check) is skipped — fixture adapters don't need credentials.
- Step 5 (validate-adapter) runs each capability against the fixture file's pre-shaped data via the adapter's `## fallbacks` `mode: fixture` branch. This proves both the adapter AND the fixture agree on the normalized shape, which is the whole point of fixture-mode validation.

If fixture mode fails validation, the bug is almost always in the adapter's `## read` section, the fixture sample file, or the schema — in that order.
