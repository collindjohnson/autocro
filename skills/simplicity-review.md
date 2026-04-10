# Skill: simplicity-review

Enforce the "simpler is better" criterion on a generated variant. This skill is a gatekeeper that can override the composite score — a high composite with sloppy, oversized, or clever-for-its-own-sake code gets discarded.

## Inputs

- A variant folder at `variants/<slug>/` containing `patch.diff`, `hypothesis.md`, and `pre-validation.json`.
- `config.guardrails.max_diff_lines`.

## Output

Return one of: `ok` / `too_large` / `too_clever` / `debug_residue` / `dead_code`. If anything other than `ok`, the inner loop marks the variant as `discarded` regardless of composite.

Write a short decision line to `variants/<slug>/notes.md`:

```
## simplicity-review
decision: ok
reason: 14 diff lines, clean single-file CTA copy change
```

## Checks (fail on first failure)

### 1. Size

```
diff_lines = (lines starting with '+' but not '+++') + (lines starting with '-' but not '---')
```

- `diff_lines > config.guardrails.max_diff_lines` → decision: `too_large`, reason: `oversized: {n} > {max}`
- `diff_lines == 0` → decision: `too_large` (nothing to test), reason: `empty diff`

### 2. Debug residue

Search the added lines (`+` lines) for any of:

- `console.log`, `console.debug`, `console.warn`, `console.error` (unless already present in a comparable line being modified, not added net-new)
- `debugger;`, `import pdb`, `pdb.set_trace()`, `breakpoint()`
- `print(` in Python files unless the file already has `print(` calls nearby
- `dd(`, `var_dump(`, `console.table(`
- `alert(`, `window.alert(`
- `FIXME`, `XXX`, `HACK`, `TODO` markers added by the patch
- `TEMP`, `DEBUG` comments added by the patch

If any found, decision: `debug_residue`, reason: `contains {marker}`.

### 3. Dead code

Search the added lines for:

- Whole blocks of commented-out old code (3+ consecutive lines starting with `+//`, `+#`, `+/*`, `+<!--`). Small inline comments are fine; commented-out blocks of logic are not.
- Unreachable code (an `if (false)`, `if (0)`, or early `return` followed by more added logic).
- Unused imports added by the patch.
- Added functions or variables that are never referenced elsewhere in the diff.

If found, decision: `dead_code`, reason: `commented block | unreachable | unused import | unused symbol`.

### 4. Too clever

This is the judgment call. Flag the patch as `too_clever` if:

- It uses a framework feature in a non-idiomatic way (e.g. misuses React refs to bypass state, uses CSS `!important` instead of fixing specificity).
- It introduces a new abstraction (helper function, new component, new util file) for a change that only affects one location. Three similar lines is better than a premature abstraction.
- It conditionally imports or dynamically constructs paths to avoid a "trivial" refactor elsewhere.
- It uses a regex where a substring match would suffice.
- It uses `try/except` (or `try/catch`) to mask an actual bug rather than handle a real edge case.
- It renames things unrelated to the hypothesis under the banner of "cleanup".

If flagged, decision: `too_clever`, reason: `{one-line explanation}`.

A high composite does NOT excuse too-clever changes. A CTA copy change should be one line of HTML/JSX, not a new component, a new context provider, and a new hook.

### 5. Simplicity wins get a bonus note

If the diff has **negative** `diff_lines` (a deletion-only change that improves things) AND composite ≥ `discard_threshold`, the simplicity review passes AND the decision line includes a `+simplicity_bonus: true` note. The inner loop may use this as a tiebreaker when ranking.

## Decision

- `ok`: continue through the inner loop's decision logic in step 7.
- `too_large` | `too_clever` | `debug_residue` | `dead_code`: override the status to `discarded`, write the row with the reason in the description column, keep the variant folder for audit.

## Do not

- Do not re-score the composite from this skill — that's `pre-validate.md`'s job.
- Do not modify the patch. Discard if it's bad; never silently fix it.
- Do not ask the human to weigh in. Make the call and move on.
