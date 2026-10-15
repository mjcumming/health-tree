# Contributing

The design of record is [docs/rfp.md](docs/rfp.md). Change it before you change behavior. Decisions and their reasons are in [docs/adr](docs/adr/README.md).

The core stays free of Home Assistant and of any catalog of device faults. A new fault is a check that an adapter registers.

AI assistance is welcome. Whoever submits a change must have reviewed every line and be able to explain it. Agent instructions are in [AGENTS.md](AGENTS.md).

## Setup

You need [uv](https://docs.astral.sh/uv/) and git. uv installs Python 3.14 on its own.

```bash
git clone https://github.com/mjcumming/health-tree.git
cd health-tree
uv sync
uv run prek install
```

Use Linux or WSL for the full check suite. The `uv run` commands also work in PowerShell; native Windows tests need IANA time-zone data, which `uv run --with tzdata pytest --cov` supplies for that run. The `make` targets use Git Bash or WSL. Every target is a short `uv run` command you can run directly.

## Workflow

The maintainer can commit small documentation and repository housekeeping changes straight to `main` after reviewing the diff and running the relevant checks. CI runs after the push. Changes to behavior, APIs, dependencies, or release contents go through this review path:

1. Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `test/…`, `chore/…`, or `ci/…`.
2. If behavior changes, update the RFP. Bump its version and add a line to its changes section. Add an ADR, or supersede one, if a decision changes.
3. Write the story or scenario fixture first, and watch it fail.
4. Implement and run `make check`.
5. Open a pull request to `main` and fill in the template. CI must pass.

### Complete a change

Keep each change small enough to review as one outcome. One person or agent owns completion across all affected repositories, including delegated work. Identify that owner, the governing decision, affected files and observable completion condition in the task's opening update.

- Finish or explicitly park overlapping implementation before another task changes that subsystem. A handoff names the remaining work and files it owns. Parallel reviews, tests and disjoint edits can continue; preserve unrelated changes.
- Read the owning RFP section and relevant decisions first. Resolve contradictions at their owning source before dependent edits. Accepted decisions remain binding; proposals and prototypes do not override them. When the maintainer changes a decision, record its supersession and update the behavior and executable coverage together.
- Replacement includes removal of obsolete code, callers, routes, configuration paths, fixtures and guidance. Required compatibility or intentionally dormant behavior needs a concrete use and a linked decision. Discarded development configurations alone do not justify migration machinery; preserve published contracts and saved user data as required.
- Verify the complete promised outcome, including integration boundaries, and inspect the final diff. Record any acceptance that remains unverified. When a recurring mistake can be checked mechanically, add the smallest useful check to the existing test or validation runner.
- Keep unfinished acceptance in the [RFP acceptance section](docs/rfp.md#12-acceptance), implemented unreleased changes in the changelog, and published changes under their release. ADRs own rationale. Link to each owner; read changing versions, thresholds and file inventories from configuration or discovery instead of copying them into guidance.
- Close with the result, verification and specific remaining work, including cross-repository adoption. State commit, release and installation status separately when relevant. Partial verification cannot close the whole outcome; external actions still require maintainer authorization.

## Checks

CI runs these:

```bash
uv run prek run --all-files   # ruff, ruff format, codespell, yamllint, zizmor, mypy, hygiene hooks
uv run pytest --cov           # tests, with branch coverage of at least 95 percent
uv build                      # sdist and wheel
```

Ruff does the formatting. Run `make format` before you commit, or let the hooks fix the files and stage them again.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, or `ci:`, followed by a short summary.

## Releasing

For maintainers:

1. Move the `[Unreleased]` entries in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`.
2. Set the version in `pyproject.toml` and `src/health_tree/__init__.py`. A test keeps them equal.
3. Merge to `main` and confirm the exact release revision passed CI.
4. Tag it and push the tag:

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The release workflow checks that the tag matches the version, runs the required checks on that revision, builds the package, publishes it to PyPI through trusted publishing, and creates the GitHub release from the changelog.

### One-time repository setup

- **PyPI.** Add a trusted publisher for project `health-tree`, owner `mjcumming`, repository `health-tree`, workflow `release.yml`, environment `pypi`.
- **GitHub environment.** Create an environment named `pypi`. You don't have to require your own approval.
- **Branch protection.** Block force pushes and deletion of `main`. The maintainer can still push directly, and CI runs on pushes and pull requests.
- **Security reporting.** Turn on private vulnerability reporting.
- **Coverage (optional).** Add a `CODECOV_TOKEN` secret for coverage reports.

### Maintenance

- Python tools are locked in `uv.lock`. Dependabot proposes updates weekly.
- Hook repositories are pinned in `.pre-commit-config.yaml`. Update them with `uv run prek autoupdate`.
- GitHub Actions are pinned to commit SHAs. Dependabot proposes updates weekly.

## Scope

This repository is the platform-agnostic library: the engine, the attention policy, conventions, tests, and documentation. Discovery, the catalog of checks, delivery, and configuration screens belong to the Home Assistant integration, [Homeostatic](https://github.com/mjcumming/homeostatic), which lives in its own repository.
