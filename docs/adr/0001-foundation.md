# ADR-0001 — Foundation decisions for TallyQL

## Status
Accepted.

## Context
FORGE20 demands independent, high-quality developer tools. For project 8 the portfolio needed a log/JSONL triage utility to complement CommitGrep (git history) and DepDiff (dependency analysis).

## Decision
Build TallyQL: a zero-dependency, single-pass JSONL query CLI with two commands (`group`, `count`), typed errors, and deterministic table output.

Consequences considered:

1. **Streaming over in-memory sort.** `jq group_by` requires sorting the entire input first. We chose a streaming hash-group pipeline so multi-gigabyte logs work on modest hardware. Trade-off: output groups cannot be emitted before the stream ends, but table rendering stays cheap because only accumulators are retained.
2. **Hand-rolled argv parsing over argparse.** `argparse` cannot distinguish input files from group paths from bare aggregate values when several positional groups coexist. A small explicit section parser is clearer and easier to test.
3. **Fail closed on mixed-type comparisons.** String-vs-number comparisons evaluate to false rather than coercing, making filter results predictable.
4. **Bad lines reported, not dropped silently.** `lines_bad` and `bad_lines` appear in the JSON report; `--max-bad` and `--strict` bound tolerance.

## Consequences
- Zero runtime dependencies; Python 3.11+.
- Every hostile input maps to exit code 2 (config) or 3 (input/pipeline); never a traceback.
