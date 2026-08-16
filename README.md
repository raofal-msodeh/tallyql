# TallyQL

**TallyQL** is a fast, zero-dependency command-line tool for querying JSONL streams without a database.

It counts, filters, groups, and aggregates JSON lines in a single streaming pass — think of it as a lightweight `jq group_by` that scales across multiple files and never loads the whole dataset into memory. It can emit a compact human-readable aligned table or a machine-friendly JSON report, ideal for log triage, DNS/event analysis, and CI pipelines.

It is part of the **FORGE20** portfolio: twenty independent, open-source developer tools built with strict quality gates.

| | |
| --- | --- |
| License | [MIT](LICENSE) |
| Language | Python 3.11+ (zero runtime dependencies) |
| Commands | 2 (`group`, `count`) |
| Tests | 60 unit/integration tests + 22 hostile-input red-team scenarios |

## Why TallyQL?

Summarizing JSONL data with `jq` or Python one-liners is error-prone: `jq`'s `group_by` requires a prior global sort (which fails on multi-file or unsorted streams), keys must be hard-coded per run, and cross-file aggregation needs ad-hoc shell glue. TallyQL wraps this in a single, validated CLI that:

- **Is truly streaming** — a single-pass pipeline keeps only group accumulators in memory; file size does not matter.
- **Aggregates across files and stdin** — pass any mix of paths or `-` for stdin and they are summed in one run.
- **Filters and groups together** — arbitrary JSON path expressions and comparisons in one command.
- **Validates every input** — path traversal (`..`), absolute output paths, symlinks escaping the tree, directories, and missing files all fail fast with clear messages and conventional exit codes.
- **Is deterministic** — groups are sorted lexicographically so identical inputs always produce identical tables, and malformed lines are reported (not silently dropped).

## Install

```bash
pip install .
# or, without installing, run directly:
python3 -m tallyql --help
```

## Usage

```text
tallyql group <input...> <group_paths...> --agg <spec...> [options]
tallyql count <input...> [options]
```

Options: `-f|--filter <expr>`, `--agg|-a <spec>` (group only), `--max-bad <n>`, `--strict`, `-o|--output <relpath>`.

Exit codes: `0` ok, `2` bad config, `3` input/pipeline error, `4` internal error.

### Examples

```bash
# Count all lines in a log file
tallyql count app.jsonl

# Count only failed requests
tallyql count app.jsonl -f '.status eq 500'

# Group events by service with several aggregates
tallyql group events.jsonl .service \
  --agg count \
  --agg "sum(.bytes) as bytes" \
  --agg "topk(.domain, 5) as domains"

# Multi-file + stdin mix, filter applied first
cat stream.jsonl | tallyql group fixed.jsonl - .host \
  --agg count \
  -f '.level eq "error"'
```

### Filter expressions

| Syntax | Meaning |
| --- | --- |
| `.field eq "v"` | equality (string/number/bool/null) |
| `.n gt 10` / `gte` / `lt` / `lte` | numeric comparison (mixed types fail closed) |
| `.field ne "v"` | inequality |
| `.tags contains "x"` | substring search |
| `.x has ""` | field presence |

### Aggregate specs

`count`, `sum(.path)`, `min(.path)`, `max(.path)`, `avg(.path)`, `cardinality(.path)`, `topk(.path, k)` — optionally aliased with `as name`.

## Design

The engine (`engine.py`) is a pure streaming pipeline: parse, filter, group, accumulate, render. Path expressions (`.a.b[0].c`) and literals are validated in `paths.py` and `models.py`; all failure modes map to typed errors in `errors.py`. The CLI (`cli.py`) uses a hand-rolled section parser because `argparse` cannot disambiguate multiple positional groups (inputs vs group paths vs aggregate values).

Full rationale is in [docs/architecture.md](docs/architecture.md) and [docs/adr/0001-foundation.md](docs/adr/0001-foundation.md); discovery research is in [docs/discovery-notes.md](docs/discovery-notes.md).

## Quality

```bash
ruff check src tests        # All checks passed
ruff format --check .       # formatted
mypy src                    # Success: no issues
python3 -m pytest           # 60 passed
bash scripts/red_team.sh    # 22 hostile-input scenarios passed
python3 -m build            # sdist + wheel
```

A GitHub Actions CI mirror is provided in [docs/ci-workflow.yml](docs/ci-workflow.yml).

## TallyQL vs alternatives

| Tool | Multi-file aggregation | Streaming (no global sort) | One-command filter+group | Validated inputs | Zero dependencies |
| --- | --- | --- | --- | --- | --- |
| jq `group_by` | no | no | partial | no | yes |
| Python + pandas | yes | no | yes | no | no |
| ClickHouse/TrdSQL | yes | no (SQL engine) | yes | no | no (heavy) |
| **TallyQL** | **yes** | **yes** | **yes** | **yes** | **yes** |

## License

MIT — see [LICENSE](LICENSE).
