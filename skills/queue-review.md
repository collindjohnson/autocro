# Skill: queue-review

The single chokepoint between the inner loop and the abtest adapter's `push_variant` capability. Every variant that is eligible to be pushed to the A/B test tool — in any mode — goes through this skill. No other skill may call `push_variant` directly.

This skill has two modes: `## append` (called by the inner loop when a variant is eligible but should be queued for human review) and `## drain` (called at the start of every inner-loop iteration to act on items the human has approved or rejected since the last run).

## Inputs

- `config.workflow.review_mode` — `"manual"` | `"auto"` | `"off"`.
- `config.workflow.auto_push_threshold`, `config.workflow.auto_allocation_pct`.
- `config.adapters.abtest.id` — the abtest adapter being used. If `null`, this skill is a no-op.
- `variants/PENDING.md` — append-only pending-review queue. Created on first append if missing.
- A variant folder `variants/<slug>/` with `patch.diff`, `hypothesis.md`, and `pre-validation.json`.

## The PENDING.md format

`PENDING.md` is a single markdown file. Each queued variant is one block separated by `---`:

```markdown
## <slug>

- status: awaiting_review    # awaiting_review | approved | rejected | deferred
- composite: 0.42
- diff_lines: 18
- queued_at: 2026-04-10T22:17:03Z
- hypothesis: "Make the pricing CTA more specific about the free trial length"
- patch: variants/<slug>/patch.diff
- experiment_id:               # filled in after push

<reviewer notes go here, free-form>

---
```

The human edits the `status:` line to approve, reject, or defer items between runs. The skill trusts whatever is in the file — it is the source of truth for queue state. A variant can appear in `PENDING.md` at most once; re-appending an existing slug is a no-op.

## Mode: `## append`

Called from the inner loop step 7 when:
- `composite >= config.prevalidation.thresholds.push`,
- simplicity review passed,
- `adapters.abtest.id != null`, AND
- the cascade landed in a branch that chose "queue for review" (manual mode always, or auto mode when `composite < auto_push_threshold`).

Steps:

1. Create `variants/PENDING.md` with an empty header if it does not exist:

   ```markdown
   # Pending review queue

   Edit the `status:` line on any block below to `approved`, `rejected`, or `deferred`.
   Next inner-loop iteration (or a manual drain) will act on your edits.

   ```

2. Check whether `## <slug>` already exists in the file. If so, no-op and return.

3. Append a block matching the format above. Fill in `composite` and `diff_lines` from `pre-validation.json`, `hypothesis` from the first line of `hypothesis.md`, and `queued_at` from the current ISO-8601 UTC timestamp.

4. Append an `awaiting_review` row to `results.tsv` (via `harness/check_results_row.py`). Use `experiment_id` empty.

5. Log a JSON-lines entry to `run.log`:
   ```json
   {"ts": "<iso>", "event": "variant_queued_review", "adapter": "<abtest_id>", "capability": null, "files_read": 3, "files_written": 2, "notes": "<slug> queued (composite=<x>)"}
   ```

6. Return `queued`.

## Mode: `## drain`

Called from the inner loop step 0 at the start of every iteration (unless `config.workflow.review_mode == "off"`), and also callable standalone if the user prompts "drain the review queue".

Steps:

1. If `variants/PENDING.md` does not exist, return `empty`.

2. Parse the file into blocks keyed by slug. For each block, read the `status:` field.

3. For each block with `status: awaiting_review`:

   - **If the Claude Code session is interactive** (the agent can prompt the human): present the block to the user via AskUserQuestion with four choices — `approve`, `reject`, `defer`, `skip`. Include the composite, diff_lines, hypothesis, and the path to `patch.diff` in the question so the human can decide without opening files. Collect the answer and treat `approve`/`reject`/`defer` as if the human had edited the status line.
   - **If the session is headless**: leave the block alone. Only human-edited `approved`/`rejected` entries are actioned.

4. For each block now marked `approved`:

   1. Call the abtest adapter's `push_variant` capability with:
      - `variant_dir: variants/<slug>`
      - `allocation_pct: 0` (manual mode always pushes at 0% — the human ramps via the adapter's `promote()` call. Auto mode never goes through drain; it pushes directly from the cascade at `auto_allocation_pct`.)
   2. On success: the adapter returns an `experiment_id`. Write `variants/<slug>/experiment.json`. Update the block in `PENDING.md`: set `status: pushed` and fill in `experiment_id`. Append a `status=pushed` row to `results.tsv` with the returned id. Log `event: variant_pushed` to `run.log` (this is the event name `skills/read-experiment.md` scans for when resolving push timestamps).
   3. On failure: revert `status:` to `awaiting_review`, append a `notes:` line describing the failure, and log `event: variant_push_failed` with notes including the error. Do not append a results.tsv row.

5. For each block marked `rejected`:

   - Append a `status=rejected` row to `results.tsv`. Log `event: variant_rejected`. Leave the block in `PENDING.md` with `status: rejected` for audit.

6. For each block marked `deferred`:

   - No-op. The block stays pending for the next drain.

7. Return a summary: `{approved: N, rejected: N, deferred: N, still_pending: N}`.

## Do not

- Do not call `push_variant` from any skill other than this one.
- Do not auto-approve pending items, even if they've been sitting for many iterations. "awaiting_review" is a terminal state from the agent's perspective — only the human (via AskUserQuestion or editing PENDING.md) can advance it.
- Do not delete entries from `PENDING.md`. Keep rejected and pushed entries in place for audit; they are simply ignored on future drains.
- Do not confuse `review_mode: auto` with this skill. Auto mode pushes variants live directly from the inner-loop step 7 cascade, bypassing the queue entirely (unless the variant scored below `auto_push_threshold`, in which case it lands here like a manual variant).
