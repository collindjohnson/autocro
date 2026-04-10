#!/usr/bin/env python3
"""
results.tsv row schema check, stdlib only.

Takes a tab-separated row on stdin and validates it against the 14-column
schema defined in program.md :: Logging. Used by the inner loop before
appending any row to results.tsv so a typo or a stray tab in a description
can't corrupt the append-only memory.

Column contract (see program.md lines 83-100):

    1  variant_slug        non-empty string
    2  hypothesis_source   non-empty string
    3  diff_lines          integer >= 0
    4  status              enum: proposed | pre_validated | pushed | measuring
                                 | winner | loser | discarded | crash
    5  lh_score            float in [-1, 1] or empty
    6  judge_score         float in [-1, 1] or empty
    7  persona_score       float in [-1, 1] or empty
    8  heuristic_score     float in [-1, 1] or empty
    9  composite           float in [-1, 1] or empty
    10 experiment_id       string or empty
    11 measured_lift       float or empty
    12 measured_ci_low     float or empty
    13 measured_ci_high    float or empty
    14 description         non-empty string, no tabs

Usage:
    echo -e "v0001\\tfixture:top_pages\\t4\\tpre_validated\\t\\t0.3\\t\\t0.2\\t0.28\\t\\t\\t\\t\\thero cta specificity" | python3 harness/check_results_row.py

Exit codes: 0 pass, 2 invalid row (user error), 3 input load failure.
"""

import sys


STATUSES = {"proposed", "pre_validated", "pushed", "measuring",
            "winner", "loser", "discarded", "crash"}


def die(at, problem, hint):
    sys.stderr.write(
        f"RESULTS ROW INVALID\n"
        f"at: column {at}\n"
        f"problem: {problem}\n"
        f"fix: {hint}\n"
    )
    sys.exit(2)


def parse_score(raw, column):
    if raw == "":
        return None
    try:
        v = float(raw)
    except ValueError:
        die(column, f"column {column} is not a number: {raw!r}",
            f"set column {column} to a float in [-1, 1] or leave it empty")
    if not (-1.0 <= v <= 1.0):
        die(column, f"column {column} value {v} is outside [-1, 1]",
            f"clamp column {column} to [-1, 1]")
    return v


def main():
    raw = sys.stdin.read().rstrip("\n")
    if not raw:
        sys.stderr.write("RESULTS ROW LOAD FAILED: no input on stdin\n")
        sys.exit(3)
    cols = raw.split("\t")
    if len(cols) != 14:
        sys.stderr.write(
            f"RESULTS ROW INVALID: expected 14 columns, got {len(cols)}\n"
            f"fix: ensure the row is tab-separated with exactly 14 fields. "
            f"Do not use tabs inside the description (column 14) — use spaces or semicolons.\n"
        )
        sys.exit(2)

    if not cols[0]:
        die(1, "variant_slug is empty",
            "set column 1 to the variant folder name under variants/")
    if not cols[1]:
        die(2, "hypothesis_source is empty",
            "set column 2 to a non-empty tag like 'ga4:top_pages' or 'outer_loop:poll'")

    try:
        diff_lines = int(cols[2])
    except ValueError:
        die(3, f"diff_lines is not an integer: {cols[2]!r}",
            "set column 3 to a non-negative integer (0 for no-op rows)")
    if diff_lines < 0:
        die(3, f"diff_lines is negative ({diff_lines})",
            "diff_lines must be >= 0")

    if cols[3] not in STATUSES:
        die(4, f"status {cols[3]!r} not in allowed set",
            f"use one of: {', '.join(sorted(STATUSES))}")

    for idx in (4, 5, 6, 7, 8):
        parse_score(cols[idx], idx + 1)

    # experiment_id (col 10) is free-form string or empty
    # measured_lift / ci_low / ci_high (11, 12, 13) are floats or empty but
    # not restricted to [-1, 1] (a real lift can theoretically exceed that band)
    for idx in (10, 11, 12):
        raw_v = cols[idx]
        if raw_v == "":
            continue
        try:
            float(raw_v)
        except ValueError:
            die(idx + 1, f"column {idx + 1} is not a number: {raw_v!r}",
                f"set column {idx + 1} to a float or leave it empty")

    if not cols[13]:
        die(14, "description is empty",
            "column 14 must contain a one-line human-readable summary of the variant or event")

    sys.stderr.write("RESULTS ROW OK\n")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"RESULTS ROW HELPER CRASHED: {exc}\n")
        sys.exit(4)
