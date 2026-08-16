# TallyQL Architecture

## Layers

- `models.py` — pure data and parsing: `AggKind` (count/sum/min/max/avg/cardinality/topk), `parse_aggregate` (specs like `sum(.bytes) as bytes`), `FilterExpr`/`parse_filter` (`.field op value`; ops: `eq ne gt gte lt lte contains has`), `Accumulator`, `BadLine`, `PipelineResult`.
- `paths.py` — path expression engine: `parse_tokens` (`.a.b[0].c`, rejects negative indexes and malformed prefixes), `get_value`, `literal_value`, `evaluate_filter` (mixed-type comparisons fail closed for determinism).
- `engine.py` — the streaming pipeline: `parse_line`, `run_pipeline` (single pass; groups keyed by `|`-joined path values; `PipelineError` on empty streams or no-usable-rows; `BadLine` snippets capped at 64 chars), `render_table` (aligned, deterministic sort order).
- `cli.py` — hand-rolled section parser and two commands (`group`, `count`). Maps errors to exit codes: 0 ok, 2 config, 3 input/pipeline, 4 internal.
- `errors.py` — typed hierarchy (`ConfigError`, `InputError`, `PipelineError`, `TallyQLError`).

## Parser design

`argparse` cannot disambiguate multiple positional groups (input files, group paths, and bare `--agg` values all compete for the same tokens), so the CLI parses sections explicitly: tokens before the first `.`-prefixed path are inputs; `.`-paths open the group section; `--agg` opens the aggregate section; `-f` opens the filter section. Options encountered mid-group are deferred and applied as inputs, never misinterpreted as group paths.

## Gate design

All hostile inputs (path traversal, directory inputs, symlink escapes, binary streams, unbounded lines, zero `--max-bad`, empty files, absolute outputs) are rejected before or during streaming with conventional exit codes. Symlinks resolving outside the current working directory are refused even when they point to regular files.

## Determinism

Groups sort lexicographically; top-k ties break lexicographically by value; aggregate aliases default to `{agg}_{path}` without the leading dot. Identical inputs always produce identical output on any machine.
