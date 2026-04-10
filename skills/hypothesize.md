# Skill: hypothesize

Turn raw adapter data into 1-3 concrete, testable CRO hypotheses with predicted lift and data citations.

## Inputs

- The research direction chosen in step 1 of the inner loop (`exploit` / `explore` / `recombine` / `focus`).
- Raw analytics data you fetched in step 2 (top pages, funnel, conversions, traffic sources, etc).
- Raw heatmap data you fetched in step 2 (page attention, click map, rage clicks, session samples).
- The tail of `results.tsv` and any existing `variants/*/hypothesis.md` files (for recombine + avoiding duplicates).

## Output

Return 1-3 hypothesis objects in this shape (as thinking text, not written to disk yet — `generate-variant.md` receives one of them):

```
hypothesis: <one-sentence summary>
change: <concrete proposed edit to parent project, at the granularity of "change
         X in file Y to Z" — not yet a diff, but specific enough that generate-variant
         can write the patch>
predicted_lift_band: <low, mid, high>   # e.g. "0.5% to 2.0% absolute conversion lift"
expected_diff_lines: <int>              # rough estimate
data_citations:
  - "<adapter_id>:<capability> -> <short paraphrase of the data point>"
  - ...
reasoning: <2-4 sentences connecting the data to the proposed change, referencing
           the judge rubric and heuristic criteria where relevant>
rationale_for_simplicity: <why this is a small change rather than a big one>
```

## How to generate hypotheses

1. **Start from a real pain point.** Look for: pages with high traffic and low conversion, funnel steps with outsized drop-off, rage clicks on non-interactive elements, low scroll depth on conversion-critical pages, high-intent traffic sources landing on mis-matched pages.

2. **Name the specific mechanism.** Don't propose "improve the hero" — propose "replace 'Learn more' with a task-specific CTA verb because users from the referral source X arrive ready to sign up, evidenced by high pageview+low scroll on /". The mechanism should be checkable against the judge rubric in `harness/judge-rubric.md`.

3. **Prefer small changes.** A one-word CTA change that targets a specific drop-off beats a full hero redesign with vague motivation. The expected_diff_lines estimate should reflect this — anything > 50 lines should have a strong justification.

4. **Avoid duplicates.** Scan the last 50 rows of `results.tsv` and any hypothesis.md files under `variants/`. If your proposed change is substantively the same as a `pre_validated` or `pushed` variant, recombine it with another idea instead.

5. **Respect guardrails.** If the change would require touching a path in `config.guardrails.deny_globs`, reject the hypothesis before returning it. Never propose auth, payment, checkout-server, or secret-handling changes.

6. **Cite data tightly.** Every hypothesis must cite at least one specific data point from an adapter call. Citations go in `hypothesis.md` and in the `hypothesis_source` column of `results.tsv`. Format: `<adapter_id>:<capability>` — do not use branded tool names.

## Research direction rules

- **explore**: pick a `config.goal.target_paths` entry that has no rows in the last 10 iterations of `results.tsv`. If all target paths have been touched recently, pick the one with the highest measured or predicted conversion gap.
- **exploit**: pick a variant with `status=pre_validated` and a composite in the top quartile but below `push` threshold. Propose a tighter version of its idea.
- **recombine**: pick two `pre_validated` variants that target different pages or different mechanisms and propose a hypothesis that captures both insights without either's weaknesses.
- **focus**: if `config.focus` is set, all three hypotheses must be changes inside that single path.

## Anti-patterns to reject

- "Make the page more modern-looking" — not concrete, not cited.
- "Add trust badges" without a specific data point showing trust is the bottleneck.
- "Rewrite the entire copy" — too large, too vague.
- "A/B test two button colors" — weak mechanism, unlikely to produce meaningful lift.
- Any hypothesis whose data citation is hand-waved ("users probably don't like X") rather than adapter-grounded.

## Diversity penalty

If three out of your last five accepted hypotheses targeted the same page or the same element, add a note to the returned hypothesis reminding the caller to pick (b) explore next iteration. Do not produce a fourth same-element hypothesis in a row — propose something different even if it means lower predicted lift this iteration.

## Return format

Return hypotheses as structured text (as shown above) so the inner loop's step 4 can pick one and pass it to `generate-variant.md`. Do not write anything to disk from this skill — writing happens in `generate-variant.md` and `pre-validate.md`.
