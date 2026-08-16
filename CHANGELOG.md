# Changelog

All notable changes to TallyQL are documented in this file.

## [1.0.0] — 2026-08-16

### Added

- Initial release of the `tallyql` CLI for searching Git history.
- Message-pattern search (`-p`/`--pattern`) with optional case-insensitivity (`-i`).
- Pickaxe code search (`-S`/`--code`) for finding commits that change occurrences of a string.
- Author filtering (`-a`/`--author`), path filtering (`-f`/`--paths`), and date windows (`-s`/`--since`, `-u`/`--until`).
- Match limit (`-n`/`--max`) and JSON report export (`-o`/`--out`).
- Human-readable summary on stdout: short hash, ISO-8601 author date, author, insertions/deletions/files changed, subject.
- Strict input validation: repository-root checks, path-traversal rejection, regex compilation checks, and date parsing with clear exit code 2 diagnostics.
- Zero runtime dependencies — the package requires only a local `git` binary and Node.js ≥ 16.
- Test suite of 19 unit and integration tests plus an 11-scenario red-team harness (`scripts/red_team.sh`) covering hostile inputs.
