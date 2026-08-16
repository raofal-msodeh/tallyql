"""Field path resolution and filter evaluation for TallyQL.

Field path grammar: `.a.b[0].c` — tokens separated by `.` with optional
`[n]` array indices. Paths must start with `.`. Index tokens `[n]` are
non-negative integers only.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import ConfigError

_INDEX = re.compile(r"^(.+)\[(-?\d+)\]$")
_INT_LITERAL = re.compile(r"^-?\d+$")
_FLOAT_LITERAL = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")
_QUOTED_LITERAL = re.compile(r'^"(.*)"$')


def parse_tokens(path: str) -> list[str]:
    """Split `.a.b[0].c` into ["a", "b[0]", "c"]. Path must start with `.`."""
    text = path.strip()
    if not text.startswith("."):
        raise ConfigError(f"field path must start with '.': {path}")
    text = text[1:]
    if not text:
        raise ConfigError(f"empty field path: {path}")
    tokens: list[str] = []
    current = ""
    for ch in text:
        if ch == ".":
            if current:
                tokens.append(current)
            current = ""
        else:
            current += ch
    if current:
        tokens.append(current)
    out: list[str] = []
    for tok in tokens:
        if tok.startswith("["):
            m2 = re.match(r"^\[(-?\d+)\]$", tok)
            if not m2:
                raise ConfigError(f"invalid token in path: {path}")
            idx = int(m2.group(1))
            if idx < 0:
                raise ConfigError(f"negative array index not allowed: {path}")
            out.append(f"[{idx}]")
            continue
        m = _INDEX.match(tok)
        if m:
            name, idx = m.group(1), int(m.group(2))
            if idx < 0:
                raise ConfigError(f"negative array index not allowed: {path}")
            out.append(name)
            out.append(f"[{idx}]")
            continue
        if not re.match(r"^[A-Za-z0-9_@-]+$", tok):
            raise ConfigError(f"invalid token in path: {path}")
        out.append(tok)
    if not out:
        raise ConfigError(f"empty field path: {path}")
    return out


def get_value(record: Any, path: str) -> Any:
    """Resolve a field path against a record; returns None when missing."""
    tokens = parse_tokens(path)
    cur: Any = record
    for tok in tokens:
        if cur is None:
            return None
        m = _INDEX.match(tok)
        if m:
            idx = int(m.group(1))
            if not isinstance(cur, (list, tuple)):
                return None
            if idx >= len(cur):
                return None
            cur = cur[idx]
        elif tok.startswith("["):
            m2 = re.match(r"^\[(-?\d+)\]$", tok)
            idx = int(m2.group(1)) if m2 else 0
            if not isinstance(cur, (list, tuple)):
                return None
            if idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(tok)
    return cur


def literal_value(text: str) -> Any:
    """Interpret a literal operand: int, float, quoted string, bool-ish."""
    t = text.strip()
    m = _QUOTED_LITERAL.match(t)
    if m:
        return m.group(1)
    if _INT_LITERAL.match(t):
        return int(t)
    if _FLOAT_LITERAL.match(t):
        return float(t)
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null" or t == "~":
        return None
    return t


def evaluate_filter(record: dict[str, Any], left: str, op: str, right: str) -> bool:
    """Evaluate one FilterExpr against a record. Missing paths fail closed."""
    left_val = get_value(record, left)
    if op == "has":
        return left_val is not None
    right_val = literal_value(right)
    if left_val is None:
        return False
    try:
        if op == "eq":
            return bool(left_val == right_val)
        if op == "ne":
            return bool(left_val != right_val)
        if op in ("gt", "gte", "lt", "lte"):
            # Mixed string/number comparisons fail closed for determinism.
            if type(left_val) is not type(right_val):
                # int/float cross-compare; everything else fails closed.
                if not (isinstance(left_val, (int, float)) and isinstance(right_val, (int, float))):
                    return False
            if op == "gt":
                return bool(left_val > right_val)
            if op == "gte":
                return bool(left_val >= right_val)
            if op == "lt":
                return bool(left_val < right_val)
            return bool(left_val <= right_val)
        if op == "contains":
            if isinstance(right_val, str) and isinstance(left_val, str):
                return bool(right_val in left_val)
            if isinstance(left_val, str):
                return str(right_val) in left_val
            return False
    except TypeError:
        return False
    return False
