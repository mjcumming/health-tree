# Contributing

The design of record is [docs/rfp.md](docs/rfp.md). Change that document before changing behavior. Decisions and their reasons are in [docs/adr](docs/adr/README.md).

The core stays free of Home Assistant and of any catalog of device faults. A new fault is a check registered by an adapter.

AI assistance is welcome. Whoever submits a change must have reviewed every line and be able to explain it. Agent instructions are in [AGENTS.md](AGENTS.md).

## Setup

You need [uv](https://docs.astral.sh/uv/) and git. uv installs Python 3.14 on its own.

```bash
git clone https://github.com/mjcumming/health-tree.git
cd health-tree
uv sync
uv run prek install
```

On Windows, uv and the `uv run` commands work in PowerShell. The `make` targets need Git Bash or WSL. Every target is a short `uv run` command you can run directly.

## Workflow

1. Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `test/…`, `chore/…`, or `ci/…`. The `no-commit-to-branch` hook blocks commits directly on `main`.
2. If behavior changes, update the RFP. Bump its version and add a line to its changes section. Add an ADR, or supersede one, if a decision changes.
3. Write the story or scenario fixture first, and watch it fail.
4. Implement.
5. Run `make check`.
6. Open a pull request to `main` and fill in the template. CI must pass.

## Checks

These are what CI runs:

```bash
uv run prek run --all-files   # ruff, ruff format, codespell, yamllint, zizmor, mypy, hygiene hooks
uv run pytest --cov           # tests, with branch coverage of at least 95 percent
uv build                      # sdist and wheel
```

Formatting is ruff's. Run `make format` before committing, or let the hooks fix files and stage them again.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, or `ci:`, followed by a short summary.

## Releasing

For maintainers:

1. Move the `[Unreleased]` entries in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`.
2. Set the version in `pyproject.toml` and `src/health_tree/__init__.py`. A test keeps them equal.
3. Merge to `main`.
4. Tag it and push the tag:

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The release workflow checks that the tag matches the version, builds, publishes to PyPI through trusted publishing, and creates the GitHub release from the changelog.

### One-time repository setup

- **PyPI.** Add a trusted publisher for project `health-tree`, owner `mjcumming`, repository `health-tree`, workflow `release.yml`, environment `pypi`.
- **GitHub environment.** Create an environment named `pypi`. Requiring your own approval is optional.
- **Branch protection.** Protect `main` and require the CI checks.
- **Security reporting.** Turn on private vulnerability reporting.
- **Coverage (optional).** Add a `CODECOV_TOKEN` secret for coverage reports.

### Maintenance

- Python tools are locked in `uv.lock`. Dependabot proposes updates weekly.
- Hook repositories are pinned in `.pre-commit-config.yaml`. Update them with `uv run prek autoupdate`.
- GitHub Actions are pinned to commit SHAs. Dependabot proposes updates weekly.

## Scope

This repository is the platform-agnostic library: the engine, the attention policy, conventions, tests, and documentation. Discovery, the catalog of checks, delivery, and configuration screens belong to the Home Assistant integration, which lives in its own repository.
