# Contributing
## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
## Quality gate
```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest
python -m build
```
## Workflow
1. Fork and branch from `main`.
2. Add tests covering the change; keep `make quality` green.
3. Keep commits small and logical.
