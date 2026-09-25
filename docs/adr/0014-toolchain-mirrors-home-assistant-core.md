# ADR 0014: The toolchain mirrors Home Assistant core

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The library should look and feel like Home Assistant code even though it is not part of Home Assistant. That is how pywiim and home-topology were meant to work, and agents trained on Home Assistant conventions should feel at home here.

Home Assistant core, as of September 2026, uses:

- uv
- ruff 0.16 for linting and formatting
- mypy 2 with strict flags
- prek running `.pre-commit-config.yaml`
- codespell, yamllint, and zizmor
- pytest 9
- GitHub Actions pinned to commit SHAs

## Decision

- **Environments and builds.** uv for environments, the lock file, and builds. `uv.lock` is committed. The build backend is hatchling, as in home-topology.
- **Linting.** Ruff lint with Home Assistant core's rule selection, adapted for a library that is not Home Assistant, and Google docstrings. The banned-API list enforces ADR 0002 and ADR 0003.
- **Formatting.** Ruff format replaces black and isort. The line length is ruff's default, 88.
- **Types.** mypy in strict mode, plus Home Assistant's extra flags, on `src` and `tests`.
- **Tests.**
  - pytest with Hypothesis.
  - Branch coverage through pytest-cov, failing under 95 percent.
  - Warnings are errors.
- **Hooks.** prek runs ruff and mypy from the locked environment, and runs codespell, yamllint, zizmor, and standard hygiene hooks from their own repositories.
- **CI.**
  - GitHub Actions pinned to SHAs, with version comments.
  - Least-privilege permissions.
  - `persist-credentials: false`.
  - Dependabot keeps pins and the lock file current.
- **Commands.** A Makefile wraps the commands, as in the maintainer's other repositories.

## Options considered

- **pywiim's black, isort, and ruff.** Three tools where one does the job, and it diverges from Home Assistant.
- **pylint, as Home Assistant core runs it.** Slow and tied to Home Assistant's plugins. Ruff's PL rules cover most of it.
- **pre-commit instead of prek.** Both read the same file. prek is what Home Assistant core uses now.

## Consequences

- Stricter than the maintainer's other two repositories: docstrings everywhere and strict mypy.
- A 95 percent coverage bar suits a pure engine and would not suit an I/O library.
- Hook repositories are updated with `uv run prek autoupdate`. Python tools are updated through the lock file.
