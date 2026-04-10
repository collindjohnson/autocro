#!/usr/bin/env python3
"""
Deny-glob enforcement helper, stdlib only.

Takes a list of candidate file paths on stdin (one per line) and a path to
config.yaml (already converted to JSON; see harness/yaml_to_json.py). For every
candidate, walks `guardrails.deny_globs` with fnmatch and exits:

    0  every candidate is allowed (no deny_glob matched)
    2  at least one candidate matched a deny_glob — writes the violation to
       stderr and stops on the first hit, since variant generation should
       discard the hypothesis entirely and pick a new one
    3  input load failure (file missing, bad JSON, etc.)

Usage:
    python3 harness/check_path.py --config-json config.json < paths.txt

This helper replaces the prose "do not touch deny_globs" instruction in
program.md with a mechanical check that skills/generate-variant.md MUST call
before writing any patch.
"""

import argparse
import fnmatch
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="deny-glob enforcement helper (stdlib only)",
    )
    parser.add_argument("--config-json", required=True,
                        help="path to config.yaml already converted to JSON")
    parser.add_argument("--variant-slug", default="(unknown)",
                        help="variant slug for error messages (cosmetic)")
    args = parser.parse_args()

    cfg_path = Path(args.config_json)
    if not cfg_path.exists():
        sys.stderr.write(f"CHECK PATH FAILED: config file not found: {cfg_path}\n")
        sys.exit(3)
    try:
        config = json.loads(cfg_path.read_text())
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"CHECK PATH FAILED: config JSON parse error: {exc}\n")
        sys.exit(3)

    deny_globs = config.get("guardrails", {}).get("deny_globs", []) or []
    if not deny_globs:
        sys.stderr.write("CHECK PATH WARNING: no deny_globs configured — allowing all paths\n")

    candidates = [line.strip() for line in sys.stdin if line.strip()]
    if not candidates:
        sys.stderr.write("CHECK PATH FAILED: no candidate paths on stdin\n")
        sys.exit(3)

    for path in candidates:
        for i, glob in enumerate(deny_globs):
            if fnmatch.fnmatch(path, glob):
                sys.stderr.write(
                    f"DENY GLOB VIOLATION: cannot write patch\n"
                    f"variant: {args.variant_slug}\n"
                    f"offending path: {path}\n"
                    f"matched glob: {glob}   (guardrails.deny_globs[{i}])\n"
                    f"hint: the hypothesis targets a protected file. Discard the hypothesis "
                    f"and pick a different one — do not work around the deny list.\n"
                )
                sys.exit(2)

    sys.stderr.write(f"CHECK PATH OK: {len(candidates)} path(s) allowed\n")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"CHECK PATH HELPER CRASHED: {exc}\n")
        sys.exit(4)
