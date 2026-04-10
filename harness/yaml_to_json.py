#!/usr/bin/env python3
"""
Minimal YAML subset -> JSON converter, stdlib only.

Handles exactly the subset used by config.example.yaml:
  - block mappings (key: value, key:\\n  nested:)
  - block sequences (- item, - key: value)
  - scalars: null / ~ / "" (null), true/false/yes/no (bool), ints, floats,
    single- and double-quoted strings, plain strings
  - "#" comments (line-level and end-of-line, respecting quoted strings)
  - blank lines

Explicitly NOT supported (fails with a clear error pointing at the line):
  - flow style ({a: 1} / [a, b])
  - anchors and aliases (&foo, *foo)
  - multi-line strings (|, >)
  - multi-document streams (---)
  - tags (!!int, !<tag>)
  - complex keys

Why this exists: config.yaml needs to be validated by harness/validate.py
before program.md starts, and validate.py is JSON-only. PyYAML is a third-party
dep we refuse to add (see pyproject.toml). This converter covers the exact
shape config.example.yaml uses and errors loudly on anything weirder — so a
user running setup-check outside Claude Code still gets the fail-fast behavior.

Usage:
  python3 harness/yaml_to_json.py path/to/config.yaml   # -> JSON on stdout
  python3 harness/yaml_to_json.py -                      # -> read stdin
"""

import json
import re
import sys


# Patterns that identify YAML features this converter does not support.
# Flow-style sequences (`[a, b, c]`) ARE supported as a scalar-value shortcut
# when they appear on a mapping right-hand side; they're parsed in parse_scalar.
UNSUPPORTED_PATTERNS = [
    (re.compile(r"^\s*---\s*$"),                     "multi-document streams"),
    (re.compile(r"^\s*[A-Za-z_].*:\s*&\S+"),         "anchors"),
    (re.compile(r"^\s*[A-Za-z_].*:\s*\*\S+\s*$"),    "aliases"),
    (re.compile(r":\s*[|>][+\-]?\s*$"),              "multi-line string blocks"),
    (re.compile(r"^\s*[A-Za-z_]\w*:\s*\{"),          "flow-style mappings"),
    (re.compile(r"!!"),                              "tags"),
]


def die(line_no, msg):
    sys.stderr.write(
        f"YAML -> JSON FAILED at line {line_no}: {msg}\n"
        f"fix: this minimal converter supports only the subset used by "
        f"config.example.yaml. Either rewrite the offending line in that subset, "
        f"or install PyYAML and pipe through `python3 -c 'import yaml,json,sys;"
        f"print(json.dumps(yaml.safe_load(sys.stdin)))'`.\n"
    )
    sys.exit(3)


def strip_comment(s):
    """Remove a trailing '# comment' from a line, respecting quoted strings."""
    in_single = in_double = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return s[:i].rstrip()
    return s.rstrip()


def parse_scalar(raw, line_no):
    s = raw.strip()
    if s == "" or s == "~" or s.lower() == "null":
        return None
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    # flow-style sequence: [a, b, "c"]
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        inner = s[1:-1].strip()
        if not inner:
            return []
        parts = []
        buf = ""
        in_single = in_double = False
        for ch in inner:
            if ch == "'" and not in_double:
                in_single = not in_single
                buf += ch
            elif ch == '"' and not in_single:
                in_double = not in_double
                buf += ch
            elif ch == "," and not in_single and not in_double:
                parts.append(parse_scalar(buf, line_no))
                buf = ""
            else:
                buf += ch
        if buf.strip():
            parts.append(parse_scalar(buf, line_no))
        return parts
    # numbers
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    # plain string
    return s


def indent_of(line):
    """Return leading-space count. Tabs are an error."""
    if "\t" in line[: len(line) - len(line.lstrip())]:
        return -1
    return len(line) - len(line.lstrip(" "))


def preprocess(text):
    """Return list of (line_no, indent, content) for non-blank, non-comment lines."""
    rows = []
    for i, raw in enumerate(text.splitlines(), start=1):
        for pattern, label in UNSUPPORTED_PATTERNS:
            if pattern.search(raw):
                die(i, f"{label} are not supported by this minimal converter")
        stripped = strip_comment(raw)
        if not stripped.strip():
            continue
        ind = indent_of(stripped)
        if ind < 0:
            die(i, "tab indentation is not allowed — use spaces")
        rows.append((i, ind, stripped[ind:]))
    return rows


def split_key_value(content, line_no):
    """Split a 'key: value' line into (key, remainder). remainder may be ''."""
    # find the first unquoted colon
    in_single = in_double = False
    for i, ch in enumerate(content):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            key = content[:i].strip()
            remainder = content[i + 1 :].strip()
            if key.startswith(("'", '"')) and key[0] == key[-1]:
                key = key[1:-1]
            return key, remainder
    die(line_no, f"expected 'key: value' but found {content!r}")


def parse_block(rows, start, base_indent):
    """Parse a block (mapping or sequence) and return (value, next_index)."""
    if start >= len(rows):
        return None, start

    first_line_no, first_ind, first_content = rows[start]
    if first_ind < base_indent:
        return None, start

    # sequence?
    if first_content.startswith("- ") or first_content == "-":
        return parse_sequence(rows, start, first_ind)

    # otherwise mapping
    return parse_mapping(rows, start, first_ind)


def parse_mapping(rows, start, base_indent):
    result = {}
    i = start
    while i < len(rows):
        line_no, ind, content = rows[i]
        if ind < base_indent:
            break
        if ind > base_indent:
            die(line_no, f"unexpected extra indentation (got {ind}, expected {base_indent})")
        if content.startswith("-"):
            die(line_no, "sequence item where mapping key expected")
        key, remainder = split_key_value(content, line_no)
        if remainder != "":
            result[key] = parse_scalar(remainder, line_no)
            i += 1
        else:
            # child block on the next line
            if i + 1 >= len(rows) or rows[i + 1][1] <= base_indent:
                result[key] = None
                i += 1
            else:
                child, next_i = parse_block(rows, i + 1, rows[i + 1][1])
                result[key] = child
                i = next_i
    return result, i


def parse_sequence(rows, start, base_indent):
    result = []
    i = start
    while i < len(rows):
        line_no, ind, content = rows[i]
        if ind < base_indent:
            break
        if ind > base_indent:
            die(line_no, f"unexpected extra indentation inside sequence")
        if not (content == "-" or content.startswith("- ")):
            break
        after_dash = content[1:].lstrip(" ")
        if after_dash == "":
            # "-" with nested block on next line
            if i + 1 >= len(rows) or rows[i + 1][1] <= base_indent:
                result.append(None)
                i += 1
                continue
            child, next_i = parse_block(rows, i + 1, rows[i + 1][1])
            result.append(child)
            i = next_i
            continue

        # inline content after the dash
        if ":" in after_dash and not (after_dash.startswith("'") or after_dash.startswith('"')):
            # mapping item: "- key: value" (and possibly additional keys at deeper indent)
            item_base = ind + 2  # typical "- " offset
            key, remainder = split_key_value(after_dash, line_no)
            item = {}
            if remainder != "":
                item[key] = parse_scalar(remainder, line_no)
            else:
                # child sub-block for this key
                if i + 1 < len(rows) and rows[i + 1][1] > item_base:
                    child, next_i = parse_block(rows, i + 1, rows[i + 1][1])
                    item[key] = child
                    i = next_i
                    # continue absorbing further keys at item_base
                    while i < len(rows):
                        nl, nind, ncontent = rows[i]
                        if nind != item_base or ncontent.startswith("-"):
                            break
                        k2, r2 = split_key_value(ncontent, nl)
                        if r2 != "":
                            item[k2] = parse_scalar(r2, nl)
                            i += 1
                        else:
                            if i + 1 < len(rows) and rows[i + 1][1] > item_base:
                                child2, next_i2 = parse_block(rows, i + 1, rows[i + 1][1])
                                item[k2] = child2
                                i = next_i2
                            else:
                                item[k2] = None
                                i += 1
                    result.append(item)
                    continue
            result.append(item)
            i += 1
            continue

        # scalar item
        result.append(parse_scalar(after_dash, line_no))
        i += 1
    return result, i


def convert(text):
    rows = preprocess(text)
    if not rows:
        return {}
    value, _ = parse_block(rows, 0, rows[0][1])
    return value


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: yaml_to_json.py <file.yaml | ->\n")
        sys.exit(3)
    arg = sys.argv[1]
    try:
        if arg == "-":
            text = sys.stdin.read()
        else:
            text = open(arg, "r").read()
    except OSError as exc:
        sys.stderr.write(f"INPUT LOAD FAILED: {arg}: {exc}\n")
        sys.exit(3)
    try:
        data = convert(text)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(
            f"YAML -> JSON FAILED: unexpected parser error: {exc}\n"
            f"fix: this file likely uses YAML features outside the supported subset. "
            f"Run it through PyYAML or yq and pipe the JSON into validate.py directly.\n"
        )
        sys.exit(3)
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
