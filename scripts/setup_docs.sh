#!/usr/bin/env bash
# Copy governance files from commitgrep, personalize for TallyQL.
cd /home/ubuntu/tallyql
SRC=/home/ubuntu/commitgrep

for f in LICENSE CODE_OF_CONDUCT.md CONTRIBUTING.md SECURITY.md CHANGELOG.md; do
    cp "$SRC/$f" .
done

mkdir -p .github/ISSUE_TEMPLATE
cp "$SRC/.github/.github/ISSUE_TEMPLATE/bug_report.md" .github/ISSUE_TEMPLATE/ 2>/dev/null || true
cp "$SRC/.github/.github/ISSUE_TEMPLATE/feature_request.md" .github/ISSUE_TEMPLATE/ 2>/dev/null || true
cp "$SRC/.github/.github/PULL_REQUEST_TEMPLATE.md" .github/ 2>/dev/null || true
# commitgrep layout was odd (.github/.github/); check commitgrep directly:
find "$SRC" -path "*/ISSUE_TEMPLATE*" -not -path "*/.git/*" 2>/dev/null
find "$SRC" -name "PULL_REQUEST_TEMPLATE*" -not -path "*/.git/*" 2>/dev/null

cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.whl
*.tar.gz
EOF

cat > makefile << 'EOF'
.PHONY: install test lint typecheck format clean build redteam

install:
	pip install -e ".[dev]"

test:
	python3 -m pytest

lint:
	ruff check src tests

typecheck:
	mypy src

format:
	ruff format src tests

clean:
	rm -rf build dist src/*.egg-info .mypy_cache .pytest_cache .ruff_cache

build:
	python3 -m build

redteam:
	bash scripts/red_team.sh
EOF

mkdir -p docs/adr examples
mkdir -p scripts
echo done
