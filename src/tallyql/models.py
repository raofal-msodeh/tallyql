"""Core data models for TallyQL pipelines."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AggKind(str, Enum):  # noqa: UP042
    """Supported aggregate functions."""

    COUNT = "count"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    AVG = "avg"
    CARDINALITY = "cardinality"
    TOPK = "topk"

    def is_numeric(self) -> bool:
        return self in (AggKind.SUM, AggKind.MIN, AggKind.MAX, AggKind.AVG)


@dataclass(frozen=True)
class FilterExpr:
    """Typed filter expression: left operand, operator, right operand.

    Operands are either field paths (strings without operators) or literals.
    """

    left: str
    op: str  # eq, ne, gt, gte, lt, lte, contains, has
    right: str

    def __str__(self) -> str:
        return f"{self.left} {self.op} {self.right}"


@dataclass(frozen=True)
class Aggregate:
    """One aggregate column: agg(path) [as alias]."""

    agg: AggKind
    path: str
    alias: str
    k: int | None = None  # only for topk


def parse_aggregate(spec: str) -> Aggregate:
    """Parse 'count', 'sum(.amount)', 'topk(.status,5) as top'.

    Raises ValueError for malformed specs.
    """
    text = spec.strip()
    if not text:
        raise ValueError("empty aggregate spec")
    alias: str | None = None
    if " as " in text:
        text, alias = text.split(" as ", 1)
        text = text.strip()
        alias = alias.strip()
        if not alias:
            raise ValueError("empty alias in aggregate")
    low = text.lower()
    k: int | None = None
    # Shorthand: bare 'count' without parens aggregates the whole stream.
    if low == "count":
        return Aggregate(agg=AggKind.COUNT, path="", alias=alias or "count_all")
    if low.startswith("topk("):
        inner = text[len("topk(") :]
        if not inner.endswith(")"):
            raise ValueError("topk() missing closing paren")
        inner = inner[:-1].strip()
        parts = inner.split(",", 1)
        if len(parts) != 2:
            raise ValueError("topk requires (path, k)")
        path = parts[0].strip()
        try:
            k = int(parts[1].strip())
        except ValueError:
            raise ValueError("topk k must be an integer") from None
        if k <= 0:
            raise ValueError("topk k must be positive")
        agg = AggKind.TOPK
    else:
        if not low.startswith("count(") and not any(
            low.startswith(f"{fn}(") for fn in ("sum", "min", "max", "avg", "cardinality")
        ):
            raise ValueError(f"unknown aggregate function: {text}")
        start = low.find("(")
        if not text.endswith(")"):
            raise ValueError("aggregate missing closing paren")
        path = text[start + 1 : -1].strip()
        low_fn = low[:start]
        if low_fn.startswith("count"):
            agg = AggKind.COUNT
        elif low_fn.startswith("sum"):
            agg = AggKind.SUM
        elif low_fn.startswith("min"):
            agg = AggKind.MIN
        elif low_fn.startswith("max"):
            agg = AggKind.MAX
        elif low_fn.startswith("avg"):
            agg = AggKind.AVG
        else:
            agg = AggKind.CARDINALITY
    if not path:
        raise ValueError(f"aggregate {agg.value}() requires a path")
    if alias is None:
        alias = (
            f"{agg.value}_{path.lstrip('.').replace('.', '_').replace('[', '_').replace(']', '_')}"
        )
    return Aggregate(agg=agg, path=path, alias=alias, k=k)


def parse_filter(spec: str) -> FilterExpr:
    """Parse '.field op literal' — e.g. '.status eq \"ok\"', '.amount gt 5'.

    Raises ValueError for malformed filters.
    """
    text = spec.strip()
    if not text:
        raise ValueError("empty filter spec")
    ops = ("contains", "gte", "lte", "gt", "lt", "eq", "ne", "has")
    for op in ops:
        low = text.lower()
        idx = low.find(f" {op} ")
        if idx == -1:
            if low.endswith(f" {op}"):
                # 'has' without right operand is allowed for .field has
                idx = len(low) - len(op) - 2
            else:
                continue
        left = text[:idx].strip()
        right = text[idx + len(op) + 2 :].strip()
        if not left:
            raise ValueError(f"filter missing left operand: {spec}")
        return FilterExpr(left=left, op=op, right=right)
    raise ValueError(f"filter needs an operator ({', '.join(ops)}): {spec}")


@dataclass(frozen=True)
class BadLine:
    """Evidence of a malformed input line."""

    line_no: int
    snippet: str
    reason: str


@dataclass
class Accumulator:
    """Holds running state for one aggregate over one group."""

    agg: AggKind
    count: int = 0
    total: float = 0.0
    min_val: float | None = None
    max_val: float | None = None
    distinct: set[str] = field(default_factory=set)
    topk_map: dict[str, int] = field(default_factory=dict)
    k: int | None = None

    def add(self, value: Any) -> None:
        self.count += 1
        if self.agg == AggKind.COUNT:
            return
        if self.agg in (AggKind.SUM, AggKind.MIN, AggKind.MAX, AggKind.AVG):
            if value is None:
                return
            try:
                num = float(value)
            except (TypeError, ValueError):
                return
            if self.agg == AggKind.SUM:
                self.total += num
            elif self.agg == AggKind.MIN:
                self.min_val = num if self.min_val is None else min(self.min_val, num)
            elif self.agg == AggKind.MAX:
                self.max_val = num if self.max_val is None else max(self.max_val, num)
            elif self.agg == AggKind.AVG:
                self.total += num
        elif self.agg == AggKind.CARDINALITY:
            self.distinct.add(json.dumps(value, sort_keys=True, default=str))
        elif self.agg == AggKind.TOPK:
            key = json.dumps(value, sort_keys=True, default=str)
            self.topk_map[key] = self.topk_map.get(key, 0) + 1

    def finalize(self) -> Any:
        if self.agg == AggKind.COUNT:
            return self.count
        if self.agg == AggKind.SUM:
            if self.count == 0:
                return None
            return self.total if self.total != int(self.total) else int(self.total)
        if self.agg == AggKind.MIN:
            return self.min_val if self.min_val is not None else None
        if self.agg == AggKind.MAX:
            return self.max_val if self.max_val is not None else None
        if self.agg == AggKind.AVG:
            return round(self.total / self.count, 6) if self.count else None
        if self.agg == AggKind.CARDINALITY:
            return len(self.distinct)
        if self.agg == AggKind.TOPK:
            k = self.k if self.k else 3
            items = sorted(self.topk_map.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
            return [{"value": json.loads(key), "count": count} for key, count in items]
