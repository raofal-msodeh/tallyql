"""TallyQL — stream-query JSONL without a database.

Usage:
    tallyql group <path...> agg <spec...> [options]
    tallyql count <path...> [options]

Examples:
    tallyql group .service agg count topk(.status,5) /var/log/app.jsonl
    tallyql group .host agg "sum(.bytes) as bytes" -f '.level eq "error"' logs.jsonl
    tallyql count *.jsonl -f '.ok eq false'
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import IO, cast

from .engine import PipelineResult, render_table, run_pipeline
from .errors import ConfigError, InputError, PipelineError, TallyQLError
from .models import FilterExpr, parse_aggregate, parse_filter

USAGE = "tallyql <command> [options] <input...>"


class _Args:
    command: str
    inputs: list[str]
    group: list[str]
    agg: list[str]
    filter: list[str]
    max_bad: int | None
    strict: bool
    output: str | None


def _build_args(
    command: str,
    inputs: list[str],
    group_paths: list[str],
    aggs: list[str],
    filters: list[str],
    max_bad: int | None,
    strict: bool,
    output: str | None,
) -> _Args:
    """Assemble and validate parsed arguments into a typed namespace."""
    args = _Args()
    args.command = command
    args.inputs = inputs
    args.group = group_paths
    args.agg = aggs
    args.filter = filters
    args.max_bad = max_bad
    args.strict = strict
    args.output = output
    if not inputs:
        raise ConfigError("at least one input file is required")
    if command == "count" and inputs and (group_paths or aggs):
        raise ConfigError("count does not take group paths or --agg")
    return args


@contextlib.contextmanager
def _open_inputs(inputs: list[str]) -> Generator[list[tuple[str, IO[str]]], None, None]:
    """Open every input path, validating each before yielding the file list."""
    with contextlib.ExitStack() as stack:
        files: list[tuple[str, IO[str]]] = []
        for inp in inputs:
            if inp == "-":
                files.append(("-", cast(IO[str], sys.stdin)))
                continue
            p = Path(inp)
            if not p.exists():
                raise InputError(f"input does not exist: {inp}")
            if p.is_dir():
                raise InputError(f"input is a directory: {inp}")
            if ".." in p.parts:
                raise InputError(f"input path contains '..': {inp}")
            if not p.is_file():
                raise InputError(f"input is not a regular file: {inp}")
            if p.is_symlink():
                try:
                    resolved = p.resolve()
                except OSError as exc:
                    raise InputError(f"input symlink is broken: {inp} ({exc})") from exc
                if not str(resolved).startswith(str(Path.cwd().resolve())):
                    raise InputError(f"input symlink escapes project tree: {inp}")
            files.append((str(p), stack.enter_context(open(p, encoding="utf-8", errors="replace"))))
        yield files


def _parse_filters(args: _Args) -> list[FilterExpr]:
    return [parse_filter(spec) for spec in args.filter]


def _report(
    result: PipelineResult,
    input_names: list[str],
    args: _Args,
) -> dict[str, object]:
    """Build the JSON report; write it to --output when requested."""
    report: dict[str, object] = {
        "inputs": input_names,
        "lines_total": result.lines_total,
        "lines_matched": result.lines_matched,
        "lines_bad": result.lines_bad,
        "groups": result.sorted_groups(),
    }
    if args.output:
        out_path = Path(args.output)
        if out_path.is_absolute():
            raise InputError("output path must be relative")
        if ".." in out_path.parts:
            raise InputError("output path contains '..'")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def _print_bad_lines(pipeline: PipelineResult) -> None:
    for bad in pipeline.bad_lines[:5]:
        print(f"  bad L{bad.line_no}: {bad.reason} | {bad.snippet!r}")


def _cmd_group(args: _Args) -> int:
    aggregates = [parse_aggregate(spec) for spec in args.agg]
    if not aggregates:
        raise ConfigError("group needs at least one --agg spec")
    filters = _parse_filters(args)
    with _open_inputs(args.inputs) as files:
        pipeline = run_pipeline(
            _multi_reader(files),
            group_paths=[g.strip() for g in args.group],
            aggregates=aggregates,
            filters=filters,
            max_bad=args.max_bad,
            strict=args.strict,
        )
        aliases = [agg.alias for agg in aggregates]
        table = "\n".join(render_table(pipeline.sorted_groups(), aliases))
        if args.output:
            _report(pipeline, [name for name, _ in files], args)
        print(table)
        if not args.output:
            print(
                f"{pipeline.lines_total} lines | "
                f"{pipeline.lines_matched} matched | "
                f"{pipeline.lines_bad} bad",
            )
            _print_bad_lines(pipeline)
    return 0


def _cmd_count(args: _Args) -> int:
    filters = _parse_filters(args)
    with _open_inputs(args.inputs) as files:
        pipeline = run_pipeline(
            _multi_reader(files),
            group_paths=[],
            aggregates=[parse_aggregate("count")],
            filters=filters,
            max_bad=args.max_bad,
            strict=args.strict,
        )
        value = pipeline.sorted_groups()[0].get("count_all", 0)
        print(value)
        if args.output:
            _report(pipeline, [name for name, _ in files], args)
    return 0


def _multi_reader(files: list[tuple[str, IO[str]]]) -> Iterator[str]:
    for _, fh in files:
        yield from fh


def _manual_parse(argv: list[str]) -> _Args:
    """Hand-rolled argv parsing to avoid argparse ambiguity between
    multiple positional groups (inputs vs group paths vs --agg values).

    Sections switch when a marker flag is encountered; group paths are
    positional tokens starting with '.' (only valid in the inputs or
    group section). Deferred option tokens caught mid-group are applied
    as soon as the parser returns to the inputs section.
    """
    if len(argv) < 2 or argv[0] not in ("group", "count"):
        raise ConfigError(f"usage: {USAGE}")
    command = argv[0]
    rest = argv[1:]

    inputs: list[str] = []
    group_paths: list[str] = []
    aggs: list[str] = []
    filters: list[str] = []
    max_bad: int | None = None
    strict = False
    output: str | None = None
    deferred: list[str] = []

    section = "inputs"
    i = 0
    while i < len(rest):
        tok = rest[i]
        if section == "inputs":
            if tok in ("--agg", "-a"):
                section = "agg"
            elif tok in ("-f", "--filter"):
                section = "filter"
            elif tok == "--max-bad":
                i += 1
                if i >= len(rest):
                    raise ConfigError("--max-bad needs a value")
                max_bad = int(rest[i])
            elif tok == "--strict":
                strict = True
            elif tok in ("-o", "--output"):
                i += 1
                if i >= len(rest):
                    raise ConfigError("--output needs a value")
                output = rest[i]
            elif tok.startswith("."):
                section = "group"
                group_paths.append(tok)
            else:
                inputs.append(tok)
        elif section == "group":
            if tok in ("--agg", "-a"):
                section = "agg"
            elif tok in ("-f", "--filter"):
                section = "filter"
            elif tok in ("--max-bad", "--strict", "-o", "--output"):
                deferred.append(tok)
                section = "inputs"
            elif tok.startswith("."):
                group_paths.append(tok)
            else:
                raise ConfigError(f"expected group path starting with '.': {tok}")
        elif section == "agg":
            if tok in ("-f", "--filter"):
                section = "filter"
            elif tok == "--max-bad":
                i += 1
                if i >= len(rest):
                    raise ConfigError("--max-bad needs a value")
                max_bad = int(rest[i])
            elif tok == "--strict":
                strict = True
            elif tok in ("-o", "--output"):
                i += 1
                if i >= len(rest):
                    raise ConfigError("--output needs a value")
                output = rest[i]
            elif tok in ("--agg", "-a"):
                pass
            else:
                aggs.append(tok)
        elif section == "filter":
            filters.append(tok)
            section = "agg" if command == "group" else "inputs"
        i += 1

    for tok in deferred:
        inputs.append(tok)
        section = "inputs"

    return _build_args(command, inputs, group_paths, aggs, filters, max_bad, strict, output)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _manual_parse(list(argv) if argv else sys.argv[1:])
    except ConfigError as exc:
        print(f"tallyql: bad config: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "group":
            return _cmd_group(args)
        return _cmd_count(args)
    except (ConfigError, ValueError) as exc:
        print(f"tallyql: bad config: {exc}", file=sys.stderr)
        return 2
    except (InputError, PipelineError) as exc:
        print(f"tallyql: {exc}", file=sys.stderr)
        return 3
    except TallyQLError as exc:
        print(f"tallyql: {exc}", file=sys.stderr)
        return 4
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
