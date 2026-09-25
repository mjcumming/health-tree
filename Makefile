.PHONY: help setup format lint typecheck test cov build check clean

help:
	@echo "setup      Create the environment and install the git hooks"
	@echo "format     Format and auto-fix with ruff"
	@echo "lint       Run every hook: ruff, format, codespell, yamllint, zizmor, mypy"
	@echo "typecheck  Run mypy"
	@echo "test       Run the tests"
	@echo "cov        Run the tests with branch coverage (fails under 95 percent)"
	@echo "build      Build the sdist and wheel, then check them"
	@echo "check      Everything CI runs"
	@echo "clean      Remove build and cache files"

setup:
	uv sync
	uv run prek install

format:
	uv run ruff format
	uv run ruff check --fix

lint:
	SKIP=no-commit-to-branch uv run prek run --all-files

typecheck:
	uv run mypy

test:
	uv run pytest

cov:
	uv run pytest --cov --cov-report=term-missing --cov-report=xml

build:
	rm -rf dist
	uv build
	uvx twine check --strict dist/*

check: lint cov build

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov coverage.xml .coverage
