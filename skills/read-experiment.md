# Skill: read-experiment

The outer-loop skill. Polls the abtest adapter for real results on experiments the inner loop has pushed, applies the user-controlled test-duration window, and decides whether to promote a variant to `winner`/`loser` and queue a follow-up test.

Called from the inner loop every `config.outer_loop.check_every` iterations (default 8) and ad-hoc when the human prompts "poll experiments now".

## Inputs

- `results.tsv` — read all rows, find the latest-per-slug row with `status in {pushed, measuring}`.
- `run.log` — scan for the matching `variant_pushed` or `variant_pushed_live` event to get the push timestamp.
- `config.workflow.test_window` — `{value, unit, on_winner}`. The setup step converted this into `test_window_hours`.
- `config.outer_loop.min_experiment_hours` — hard floor. `test_window_hours` is clamped to at least this.
- `config.outer_loop.required_significance` — minimum `1 - p` to call a winner.
- `config.adapters.abtest.id` — if `null`, this skill is a no-op.

## Steps

1. Log `event: outer_loop_poll` to `run.log`.

2. Build the candidate list: all slugs whose latest row has `status in {pushed, measuring}`.

3. For each candidate:

   3.1. Compute `age_hours = now - push_ts` where `push_ts` is the `ts` field of the matching `variant_pushed` or `variant_pushed_live` event in `run.log`. If no matching event is found, append a `notes` entry to `run.log` and skip this slug.

   3.2. **Window gate.** If `age_hours < test_window_hours`: do nothing, skip. The human explicitly wants each test to bake for this long before being judged, even if the adapter already reports significance.

   3.3. Call the abtest adapter's `get_experiment` capability (contract: `adapters/README.md`) with the stored `experiment_id`. The normalized shape returns `{experiment_id, status, visitors, lift, ci_low, ci_high, p, started_at, ended_at}`. Significance is derived as `1 - p`.

   3.4. **Significance gate.** If `(1 - p) < config.outer_loop.required_significance`: append a `status=measuring` row (no state change, just a checkpoint), log `event: outer_loop_poll` with notes "<slug> still measuring", and move on.

   3.5. **Decide winner vs loser.**
        - `lift > 0 AND ci_low > 0` → `status=winner`. Log `event: outer_loop_winner`.
        - `lift < 0 AND ci_high < 0` → `status=loser`. Log `event: outer_loop_loser`.
        - Otherwise (straddles zero) → treat as `loser` (no clear effect). Log `event: outer_loop_loser` with notes including the CI range.

   3.6. Append the appropriate row to `results.tsv` with the measured numbers filled in (`measured_lift`, `measured_ci_low`, `measured_ci_high`).

4. **Handle `on_winner`** for any slug that just became a `winner`:

   - `queue_followup` (default): invoke `skills/hypothesize.md` with `hypothesis_source=outer_loop:followup:<slug>` and a seed context that says "iterate on the winning hypothesis from <slug>; produce a new variant that pushes the same mechanism further or applies it to a related page". The returned hypothesis flows through the normal inner-loop steps 4-7 on the next iteration. Log `event: followup_queued`.
   - `stop`: do nothing further. The winner row is already written.
   - `notify_only`: append a one-line banner to `variants/RANKED.md` (`[WINNER] <slug>: lift=<x> [<ci_low>, <ci_high>]`). Do not queue a follow-up.

5. Return a summary: `{polled: N, still_measuring: N, winners: N, losers: N, followups_queued: N}`.

## Do not

- Do not bypass the `test_window_hours` gate. Even if the adapter says the test has reached significance after 2 days, the human's configured window (e.g. 2 weeks) is the contract.
- Do not ever edit old rows in `results.tsv`. Always append a new row with the new status. The analysis notebook groups by slug and keeps the latest.
- Do not push new variants from this skill. Hypothesis generation goes back through the inner loop like any other variant — the only thing this skill does to queue follow-ups is seed `hypothesize.md` with a targeted prompt.
- Do not call this skill if `config.adapters.abtest.id` is `null` — there are no real experiments to poll.
