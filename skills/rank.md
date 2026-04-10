# Skill: rank

Re-read `results.tsv` and rewrite `variants/RANKED.md` with the current top candidates.

## Inputs

- `results.tsv` (14 columns).
- All `variants/v*/hypothesis.md` files (for description lookups and slug metadata).

## Output

Overwrite `variants/RANKED.md` with a markdown table of the current top candidates, newest ranking first. This file is consumed by the human on morning wake-up and by `hypothesize.md` step 1 for the next iteration.

## Ranking rules

1. **Group by `variant_slug`**, take the most recent row per slug. The same slug may appear multiple times as status transitions (e.g. `pushed` → `measuring` → `winner`).

2. **Exclude** slugs whose latest status is `discarded`, `crash`, or `loser`. Include `pre_validated`, `pushed`, `measuring`, `winner`.

3. **Score each remaining slug**:
   - If `measured_lift` is present (non-empty): use `measured_lift` as the rank score. This is real data and dominates.
   - Otherwise: use `composite` as the rank score (pre-validation prediction).
   - Ties: smaller `diff_lines` wins. Still tied: more recent row wins.

4. **Sort descending** by rank score. Top 20.

## `variants/RANKED.md` format

```markdown
# Ranked variants

Last updated: 2026-04-10T04:12:33Z
Scoring: `measured_lift` when available, otherwise `composite`. Ties broken by `diff_lines` ascending.

| rank | slug | status | score | diff | source | description |
|-----:|------|--------|------:|-----:|--------|-------------|
| 1 | v0002-hero-cta-verb | winner | +0.037 | 4 | myanalytics:top_pages,myheatmap:attention | replace "Learn more" with "Start free trial" |
| 2 | v0017-pricing-simplify | pushed | +0.62 | 28 | myanalytics:landing_pages/pricing | drop fourth pricing tier |
| ... |

## Calibration snapshot

Variants with both composite and measured_lift so far: N = 8
Pearson r = 0.41
Median measured_lift of variants with composite > 0.5: +0.018
Median measured_lift of variants with composite in (0.0, 0.5]: +0.004

## Re-weight recommendation for skills/pre-validate.md

{Optional: if the calibration correlation is < 0.2, suggest which signal's
weight should be reduced next run. Do not change config.yaml yourself.}
```

## Calibration snapshot

Compute the snapshot from all rows that have BOTH a non-empty `composite` AND a non-empty `measured_lift` (the latter implying the outer loop has polled). If fewer than 5 such rows exist, omit the snapshot section.

- **Pearson r**: `composite` vs `measured_lift` correlation.
- **Median measured_lift by composite bucket**: bucket by `[-1, 0]`, `(0, 0.5]`, `(0.5, 1]` and report median `measured_lift` in each.

## Re-weight recommendation

If the correlation is poor (`r < 0.2` and N ≥ 10), identify the signal with the highest weight and suggest reducing it by 5 percentage points in `config.prevalidation.weights`. Write the suggestion as a prose recommendation in RANKED.md — DO NOT edit `config.yaml` from this skill. The human decides whether to apply.

## Header line

The first lines of the file should state the timestamp and the scoring formula so the human reads it fresh every morning. Use ISO-8601 UTC.

## Do not

- Do not delete the old `RANKED.md` — overwrite it.
- Do not append a history section with past rankings. The file is a snapshot of current state; history lives in `results.tsv`.
- Do not edit `results.tsv` from this skill.
- Do not edit `config.yaml` from this skill.
