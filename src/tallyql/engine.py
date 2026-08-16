"""Streaming JSONL query pipeline for TallyQL."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .errors import ConfigError, PipelineError
from .models import Accumulator, AggKind, Aggregate, BadLine, FilterExpr
from .paths import evaluate_filter, get_value

SNIPPET_LEN = 64


def parse_line(line: str) -> dict[str, Any]:
    """Parse one JSONL line; raises json.JSONDecodeError on corruption."""
    stripped = line.strip()
    if not stripped:
        raise json.JSONDecodeError("empty line", line, 0)
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("line is not a JSON object", line, 0)
    return data


@dataclass
class PipelineResult:
    """Deterministic summary output of one pipeline run."""

    lines_total: int = 0
    lines_matched: int = 0
    lines_bad: int = 0
    groups: dict[str, dict[str, Any]] = field(default_factory=dict)
    bad_lines: list[BadLine] = field(default_factory=list)

    def sorted_groups(self) -> list[dict[str, Any]]:
        rows = []
        for key, accs in self.groups.items():
            row: dict[str, Any] = {"group": key if key != "" else "(all)"}
            for alias in accs:
                row[alias] = accs[alias].finalize()
            rows.append(row)
        rows.sort(key=lambda r: str(r["group"]))
        return rows


def _group_key(record: dict[str, Any], group_paths: list[str]) -> str:
    parts = [str(get_value(record, p)) for p in group_paths]
    return "|".join(parts)


def run_pipeline(
    reader: Iterable[str],
    group_paths: list[str],
    aggregates: list[Aggregate],
    filters: list[FilterExpr] | None = None,
    max_bad: int | None = None,
    strict: bool = False,
) -> PipelineResult:
    """Single-pass streaming pipeline.

    - group_paths=[] aggregates over the whole matched stream.
    - max_bad: stop with PipelineError after this many malformed lines.
    - strict: any malformed line is an immediate PipelineError.
    """
    result = PipelineResult()
    bad_seen = 0
    filters = filters or []
    for lineno, raw in enumerate(reader, start=1):
        result.lines_total += 1
        try:
            record = parse_line(raw)
        except json.JSONDecodeError as exc:
            result.lines_bad += 1
            bad_seen += 1
            result.bad_lines.append(
                BadLine(
                    line_no=lineno,
                    snippet=raw.strip()[:SNIPPET_LEN],
                    reason=str(exc.msg),
                )
            )
            if strict or (max_bad is not None and bad_seen > max_bad):
                raise PipelineError(
                    f"bad input exceeded limit at line {lineno}: {exc.msg}"
                ) from exc
            continue
        if not all(evaluate_filter(record, f.left, f.op, f.right) for f in filters):
            continue
        result.lines_matched += 1
        key = _group_key(record, group_paths)
        accs = result.groups.setdefault(key, {})
        for agg in aggregates:
            acc = accs.setdefault(agg.alias, Accumulator(agg=agg.agg, k=agg.k))
            value = agg.agg is AggKind.COUNT or get_value(record, agg.path)
            acc.add(value)
    if not result.groups and result.lines_matched == 0 and result.lines_bad == 0:
        # Fully empty / fully bad input with no usable data.
        if result.lines_total == 0:
            raise PipelineError("input stream is empty")
    if not result.groups and result.lines_matched == 0:
        # No rows produced any aggregate (fully malformed input, or filters
        # matched nothing). The caller decides whether that is an error.
        raise PipelineError(
            "no rows produced a result; input may be malformed or no filter matched"
        )
    if not aggregates:
        raise ConfigError("at least one aggregate is required")
    return result


def render_table(rows: list[dict[str, Any]], aliases: list[str]) -> list[str]:
    """Plain-text aligned table render, deterministic across runs."""
    headers = ["group"] + aliases
    cells: list[list[str]] = [[headers[0]] + [""] * len(aliases)] + [
        [str(r.get("group", ""))] + [(_fmt(r.get(a)) if a in r else "") for a in aliases]
        for r in rows
    ]
    widths = [max(len(c) for c in col) for col in zip(*cells, strict=True)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in cells]
    return lines


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False)
        if not isinstance(value, str)
        else value
    )
