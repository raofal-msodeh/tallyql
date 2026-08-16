# TallyQL — Discovery Notes

## The problem

Developers and SREs accumulate JSONL output from logs, audit streams, CI artifacts, and API scrapers, then need one-off answers: "how many events per user?", "which status codes dominate?", "what is the sum of bytes per host in a window?". The dominant tool, `jq`, makes these questions painful rather than hard.

Evidence gathered:

1. **Multi-level grouping in jq is famously awkward.** A 2015 Stack Overflow question ("Use jq to count on multiple levels", 11k views) about per-user counts with per-domain sub-counts from a JSONL DNS log requires either `group_by` twice with nested `map`/`from_entries`, or a hand-written `reduce inputs as $line` accumulator [1]. These are expert-level filters that most users cannot derive or audit.

2. **`group_by` requires sorting the entire stream in memory.** jq's `group_by` first sorts the slurped array, so it both needs all input buffered (`-s`) and cannot emit results incrementally. Commenters on the same thread note that "a very large number of lines" causes "performance issues and/or capacity constraints", solved only by switching to the reduce pattern — a different language paradigm per query [1].

3. **Cross-file aggregation needs hardcoded keys.** Aggregating arrays across multiple files with `jq -s '{shapes: map(.shapes)|add}'` forces the user to hardcode the key name; a general merge requires `reduce .[] as $item ({}; . * $item) | keys[]` — deep-merge semantics that silently overwrite rather than count [2] [3].

4. **Alternatives push toward heavy installs.** ClickHouse Local runs real SQL over files but is a multi-hundred-MB engine install for an ad-hoc question [4]. `trdsql`/`jqsql` and `qsv` are capable but add their own syntax layers and dependencies. Pure-Python one-off scripts get written every time because there is no small, typed, deterministic middle ground.

## Existing alternatives

| Tool | What it does well | Gap |
|---|---|---|
| jq | Expressive filters, fast streaming | group_by sorts whole slurp in memory; multi-level counts need reduce-wizardry; fragile on corrupted lines |
| ClickHouse Local | SQL over files | heavy install, overkill, server-shaped UX |
| trdsql / jqsql | SQL or jq over files | extra runtime dependencies, different syntax per tool |
| qsv / visidata | Big CSV/TSV tooling | JSONL support secondary; learning curve |
| pandas one-off scripts | Familiar | no CLI ergonomics, no streaming, import cost |

## Thesis

> For **developers and SREs** who suffer from **recurring ad-hoc counting/grouping questions over JSONL streams** this provides **TallyQL — a filter→group→summarize pipeline CLI** unlike **jq's in-memory sorted group_by and heavy SQL engines** by **streaming one pass, failing fast on corrupt lines with a structured error report, and emitting deterministic count/sum/min/max/top-k summaries with typed filters**.

## Differentiators (scope decisions)

1. **Streaming single-pass**: counts, sums, distinct counts, min/max accumulate with O(groups) memory, never O(lines).
2. **Typed expressions, not a query language**: field paths (`a.b[0]`), literals, comparisons, `and/or`, and aggregates (`count`, `sum`, `min`, `max`, `avg`, `topk`, `cardinality`) composed as CLI flags — auditable, CI-safe, no parser ambiguity.
3. **Corruption-tolerant with evidence**: each malformed line is counted and reported (line number, first bytes) instead of silently skipping or aborting; optionally strict mode fails the run.
4. **Zero dependencies**, Python 3.11+, typed with `mypy --strict`, deterministic output (sorted groups, stable JSON) for golden-file testing.
5. **Not a database**: no indexes, no joins, no schema inference beyond per-line parsing. Documented as such in README.

## Sources

[1]: https://stackoverflow.com/questions/31035704/use-jq-to-count-on-multiple-levels "Use jq to count on multiple levels — Stack Overflow (2015, 11k views)"
[2]: https://stackoverflow.com/questions/63264954/aggregate-json-arrays-from-multiple-files-grouping-by-key "Aggregate json arrays from multiple files — Stack Overflow (2020)"
[3]: https://dev.to/davidmaceachern/how-to-query-json-data-in-the-terminal-3gin "How to query JSON data in the terminal — dev.to (2020)"
[4]: https://clickhouse.com/resources/engineering/run-sql-on-json-file "Run SQL on JSON file with ClickHouse Local (2026)"
