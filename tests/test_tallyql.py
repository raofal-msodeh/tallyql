"""Comprehensive tests for TallyQL engine, paths, models, and CLI."""

import json
from pathlib import Path

import pytest

from tallyql.cli import main
from tallyql.engine import render_table, run_pipeline
from tallyql.errors import ConfigError, PipelineError
from tallyql.models import (
    Accumulator,
    AggKind,
    parse_aggregate,
    parse_filter,
)
from tallyql.paths import evaluate_filter, get_value, parse_tokens

DNS = [
    {"machine": "m1", "domain": "evil.com", "ts": 100},
    {"machine": "m1", "domain": "evil.com", "ts": 101},
    {"machine": "m1", "domain": "soevil.com", "ts": 102},
    {"machine": "m2", "domain": "bad.com", "ts": 103},
    {"machine": "m3", "domain": "soevil.com", "ts": 104},
]


def run_text(argv, stdin=None):
    """Run CLI capturing stdout; supports stdin override."""
    import io
    import sys

    saved_stdin = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    buf = io.StringIO()
    saved_stdout = sys.stdout
    sys.stdout = buf
    try:
        rc = main(argv)
    finally:
        sys.stdout = saved_stdout
        sys.stdin = saved_stdin
    return rc, buf.getvalue()


def write_jsonl(path: Path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


# ---------------- path resolution ----------------


def test_simple_path():
    assert get_value({"a": {"b": 1}}, ".a.b") == 1


def test_array_index():
    assert get_value({"a": [10, 20, 30]}, ".a[1]") == 20


def test_nested_array_object():
    assert get_value({"a": [{"k": 7}]}, ".a[0].k") == 7


def test_missing_path_is_none():
    assert get_value({"a": 1}, ".b") is None


def test_index_out_of_range_is_none():
    assert get_value({"a": [1]}, ".a[5]") is None


def test_non_object_index_is_none():
    assert get_value({"a": 5}, ".a.k") is None


def test_rejects_bad_path_prefix():
    with pytest.raises(ConfigError):
        parse_tokens("a.b")


def test_rejects_negative_index():
    with pytest.raises(ConfigError):
        parse_tokens(".a[-1]")


def test_rejects_empty_path():
    with pytest.raises(ConfigError):
        parse_tokens(".")


def test_rejects_invalid_token():
    with pytest.raises(ConfigError):
        parse_tokens(".a b")


# ---------------- filters ----------------


def test_filter_eq_string():
    assert evaluate_filter({"s": "ok"}, ".s", "eq", '"ok"') is True
    assert evaluate_filter({"s": "no"}, ".s", "eq", '"ok"') is False


def test_filter_eq_number():
    assert evaluate_filter({"n": 5}, ".n", "eq", "5") is True
    assert evaluate_filter({"n": 5}, ".n", "eq", "6") is False


def test_filter_comparison_mixed_types_fail_closed():
    # string vs number comparison fails closed for determinism.
    assert evaluate_filter({"n": "5"}, ".n", "gt", "4") is False


def test_filter_has_operator():
    assert evaluate_filter({"n": 5}, ".n", "has", "") is True
    assert evaluate_filter({"n": 5}, ".missing", "has", "") is False


def test_filter_missing_field_fails_closed():
    assert evaluate_filter({}, ".x", "eq", '"a"') is False


def test_filter_contains():
    assert evaluate_filter({"s": "hello world"}, ".s", "contains", '"world"') is True
    assert evaluate_filter({"s": "hello"}, ".s", "contains", '"x"') is False


def test_filter_bad_spec():
    with pytest.raises(ValueError):
        parse_filter("no operator here")


def test_filter_boolean_literal():
    assert evaluate_filter({"ok": True}, ".ok", "eq", "true") is True


# ---------------- aggregates ----------------


def test_parse_bare_count():
    agg = parse_aggregate("count")
    assert agg.agg == AggKind.COUNT
    assert agg.alias == "count_all"


def test_parse_aliased_count():
    agg = parse_aggregate("count as n")
    assert agg.alias == "n"


def test_parse_sum():
    agg = parse_aggregate("sum(.amount)")
    assert agg.agg == AggKind.SUM
    assert agg.path == ".amount"
    assert agg.alias == "sum_amount"


def test_parse_topk_with_k():
    agg = parse_aggregate("topk(.status, 5) as top")
    assert agg.agg == AggKind.TOPK
    assert agg.k == 5
    assert agg.alias == "top"


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_aggregate("")


def test_parse_rejects_unknown():
    with pytest.raises(ValueError):
        parse_aggregate("nonsense(.x)")


def test_parse_rejects_zero_k():
    with pytest.raises(ValueError):
        parse_aggregate("topk(.x, 0)")


# ---------------- accumulator ----------------


def test_accumulator_sum_averages_types():
    acc = Accumulator(agg=AggKind.SUM)
    acc.add(1)
    acc.add(2)
    acc.add("three")  # non-numeric skipped
    assert acc.finalize() == 3


def test_accumulator_min_max():
    acc = Accumulator(agg=AggKind.MIN)
    acc.add(10)
    acc.add(2)
    acc.add(7)
    assert acc.finalize() == 2


def test_accumulator_avg_rounded():
    acc = Accumulator(agg=AggKind.AVG)
    acc.add(10)
    acc.add(20)
    assert acc.finalize() == 15.0


def test_accumulator_cardinality():
    acc = Accumulator(agg=AggKind.CARDINALITY)
    acc.add({"a": 1})
    acc.add({"a": 1})
    acc.add({"b": 2})
    assert acc.finalize() == 2


def test_accumulator_topk_stable_order():
    acc = Accumulator(agg=AggKind.TOPK, k=2)
    for v in ["b", "a", "b", "c", "a", "a"]:
        acc.add(v)
    top = acc.finalize()
    assert [item["value"] for item in top] == ["a", "b"]


def test_accumulator_count_ignores_value():
    acc = Accumulator(agg=AggKind.COUNT)
    acc.add(None)
    assert acc.finalize() == 1


# ---------------- engine pipeline ----------------


def test_pipeline_single_group():
    import io

    reader = io.StringIO("".join(json.dumps(r) + "\n" for r in DNS))
    result = run_pipeline(
        reader,
        group_paths=[".machine"],
        aggregates=[parse_aggregate("count")],
    )
    rows = result.sorted_groups()
    assert len(rows) == 3
    m1 = next(r for r in rows if r["group"] == "m1")
    assert m1["count_all"] == 3


def test_pipeline_global_count():
    import io

    reader = io.StringIO("".join(json.dumps(r) + "\n" for r in DNS))
    result = run_pipeline(
        reader,
        group_paths=[],
        aggregates=[parse_aggregate("count")],
    )
    assert result.sorted_groups()[0]["count_all"] == 5


def test_pipeline_filter_applied():
    import io

    reader = io.StringIO("".join(json.dumps(r) + "\n" for r in DNS))
    result = run_pipeline(
        reader,
        group_paths=[],
        aggregates=[parse_aggregate("count")],
        filters=[parse_filter('.machine eq "m1"')],
    )
    assert result.sorted_groups()[0]["count_all"] == 3


def test_pipeline_bad_lines_reported():
    import io

    text = json.dumps(DNS[0]) + "\nnot-json\n" + json.dumps(DNS[1]) + "\n"
    result = run_pipeline(io.StringIO(text), group_paths=[], aggregates=[parse_aggregate("count")])
    assert result.lines_total == 3
    assert result.lines_bad == 1
    assert result.lines_matched == 2
    assert result.bad_lines[0].line_no == 2


def test_pipeline_strict_fails_on_bad_line():
    import io

    text = json.dumps(DNS[0]) + "\nnot-json\n"
    with pytest.raises(PipelineError):
        run_pipeline(
            io.StringIO(text),
            group_paths=[],
            aggregates=[parse_aggregate("count")],
            strict=True,
        )


def test_pipeline_max_bad_limit():
    import io

    text = "garbage1\ngarbage2\ngarbage3\n"
    with pytest.raises(PipelineError):
        run_pipeline(
            io.StringIO(text),
            group_paths=[],
            aggregates=[parse_aggregate("count")],
            max_bad=1,
        )


def test_pipeline_empty_input_fails():
    import io

    with pytest.raises(PipelineError):
        run_pipeline(io.StringIO(""), group_paths=[], aggregates=[parse_aggregate("count")])


def test_pipeline_non_object_line_bad():
    """A fully corrupt stream yields no usable rows and fails loudly."""
    import io

    with pytest.raises(PipelineError):
        run_pipeline(
            io.StringIO("[1, 2]\n"),
            group_paths=[],
            aggregates=[parse_aggregate("count")],
        )


def test_pipeline_sum_numeric_only():
    import io

    text = '{"x": 10}\n{"x": "skip"}\n{"x": 5}\n'
    result = run_pipeline(
        io.StringIO(text),
        group_paths=[],
        aggregates=[parse_aggregate("sum(.x)")],
    )
    assert result.sorted_groups()[0]["sum_x"] == 15


def test_pipeline_deterministic_sort_order():
    import io

    shuffled = [DNS[3], DNS[0], DNS[4], DNS[1], DNS[2]]
    result = run_pipeline(
        io.StringIO("".join(json.dumps(r) + "\n" for r in shuffled)),
        group_paths=[".machine"],
        aggregates=[parse_aggregate("count")],
    )
    assert [r["group"] for r in result.sorted_groups()] == ["m1", "m2", "m3"]


# ---------------- render table ----------------


def test_render_table_aligned():
    rows = [{"group": "g1", "n": 3}, {"group": "g2", "n": 1}]
    lines = render_table(rows, ["n"])
    assert "g1" in lines[1]
    assert lines[1].strip().endswith("3")
    assert lines[0].strip().startswith("group")


# ---------------- CLI end-to-end ----------------


@pytest.fixture
def inputs(tmp_path):
    p = tmp_path / "in.jsonl"
    write_jsonl(p, DNS)
    return tmp_path, p


def test_cli_count(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["count", str(p)])
    assert rc == 0
    assert out.strip() == "5"


def test_cli_count_with_filter(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["count", str(p), "-f", '.machine eq "m1"'])
    assert rc == 0
    assert out.strip() == "3"


def test_cli_group(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["group", str(p), ".machine", "--agg", "count"])
    assert rc == 0
    rows = [line.split() for line in out.splitlines()[1:] if line.split()]
    assert ["m1", "3"] in rows


def test_cli_group_topk(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["group", str(p), ".machine", "--agg", "topk(.domain,2) as top"])
    assert rc == 0
    assert '"evil.com"' in out


def test_cli_json_report(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["group", str(p), "--agg", "count", "-o", "report.json"])
    assert rc == 0
    report = json.loads(Path("report.json").read_text())
    Path("report.json").unlink()
    assert report["lines_total"] == 5
    assert report["lines_bad"] == 0


def test_cli_absolute_output_rejected(inputs):
    tmp_path, p = inputs
    rc, _ = run_text(["group", str(p), "--agg", "count", "-o", "/abs/path.json"])
    assert rc == 3


def test_cli_missing_input(inputs):
    rc, _ = run_text(["count", "/nonexistent/path/file.jsonl"])
    assert rc == 3


def test_cli_traversal_rejected(inputs):
    tmp_path, p = inputs
    rc, _ = run_text(["count", str(tmp_path / ".."), str(p).split("/")[-2] + "/../etc/passwd"])
    assert rc == 3


def test_cli_directory_rejected(inputs):
    tmp_path, _ = inputs
    rc, _ = run_text(["count", str(tmp_path)])
    assert rc == 3


def test_cli_bad_filter_syntax(inputs):
    tmp_path, p = inputs
    rc, _ = run_text(["count", str(p), "-f", "no-operator"])
    assert rc == 2


def test_cli_bad_agg_syntax(inputs):
    tmp_path, p = inputs
    rc, _ = run_text(["group", str(p), "--agg", "garbage"])
    assert rc == 2


def test_cli_no_command():
    rc, _ = run_text([])
    assert rc == 2


def test_cli_strict_bad_line(inputs):
    tmp_path, p = inputs
    p.write_text(p.read_text() + "garbage\n")
    rc, _ = run_text(["count", str(p), "--strict"])
    assert rc == 3


def test_cli_max_bad_inputs(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text("garbage1\ngarbage2\n")
    rc, _ = run_text(["count", str(p), "--max-bad", "0"])
    assert rc == 3


def test_cli_stdin(inputs):
    _, p = inputs
    rc, out = run_text(["count", "-", "-f", '.machine eq "m1"'], stdin=p.read_text())
    assert rc == 0
    assert out.strip() == "3"


def test_cli_multiple_inputs(inputs):
    tmp_path, p = inputs
    p2 = tmp_path / "in2.jsonl"
    write_jsonl(p2, DNS[:2])
    rc, out = run_text(["group", str(p), str(p2), ".machine", "--agg", "count"])
    assert rc == 0
    rows = [line.split() for line in out.splitlines()[1:] if line.split()]
    assert ["m1", "5"] in rows


def test_cli_sum_aggregate(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["group", str(p), ".machine", "--agg", "sum(.ts) as total"])
    assert rc == 0
    rows = [line.split() for line in out.splitlines()[1:] if line.split()]
    assert ["m1", "303"] in rows


def test_cli_avg_aggregate(inputs):
    tmp_path, p = inputs
    rc, out = run_text(["group", str(p), ".machine", "--agg", "avg(.ts) as avg_ts"])
    assert rc == 0
    rows = [line.split() for line in out.splitlines()[1:] if line.split()]
    assert ["m1", "101"] in rows
