# TallyQL — Release audit (v1.0.0)

- Source: 7 modules in `src/tallyql/` (~800 LOC).
- Quality gates: `ruff check` clean (E,F,W,I,UP,B,SIM), `ruff format` applied, `mypy` strict passes, 60 pytest cases pass, 22 red-team scenarios pass.
- Artifact: `dist/tallyql-1.0.0.tar.gz` + `tallyql-1.0.0-py3-none-any.whl` (built with `python3 -m build`).
- Entry point: `tallyql = tallyql.cli:main`. Runtime dependencies: none.
- Security review: path traversal, symlink escape, directory inputs, absolute outputs, binary streams, and unbounded-line inputs all rejected pre-stream with exit code 3.
- License: MIT. Governance: CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, LICENSE, issue/PR templates, ADR, architecture doc, CI workflow.
