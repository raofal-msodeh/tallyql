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
