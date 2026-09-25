# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- RFP 0.2, the design of record, in place of 0.1. It adds:
  - the four jobs of the model and the two flows over the cause graph
  - fixed and open types
  - functions as nodes, and the explain, impact, readiness, coverage, and rollup queries
  - the attention policy
  - stories drawn from real failures, and 42 scenarios
- Architecture decision records 0001 to 0023, all accepted except 0016 (rules for AI-assisted development, still proposed). 0013 (Python 3.14) and 0019 to 0023 (the review of 0.2) were accepted after review; accepting 0022 supersedes 0008.
- A fixture schema validator, and fixtures for scenarios 14, 19, 24, 36, 43 to 48, and 50 to 52, and stories 4 and 8. The schema accepts `readiness` queries.
- Development rules: `AGENTS.md`, `CLAUDE.md`, and a rewritten `CONTRIBUTING.md`. Also `SECURITY.md`.
- Tooling that mirrors Home Assistant core:
  - uv with a lock file, and hatchling
  - ruff for linting and formatting
  - mypy in strict mode
  - pytest with Hypothesis and branch coverage
  - prek hooks (codespell, yamllint, zizmor)
  - `.editorconfig`, `.gitattributes`, and a Makefile
- GitHub workflows: CI, tag-driven release through trusted publishing, and CodeQL with dependency review. Also Dependabot, issue templates including one for failure stories, a pull request template, and CODEOWNERS.
- The `py.typed` marker, and package tests for the version, dependencies, and typing.

### Changed

- RFP 0.3 settles the review of 0.2 (RFP section 15):
  - A node is one capability. Maintenance debt gets its own node.
  - Policy rules match each reason of an episode, and the loudest result wins.
  - One anchor, one episode. Coalesced members decide when it recovers.
  - The settle gate waits only on dependencies in doubt.
  - `readiness` reads observed status, and a stale dependency answers `unknown`.
  - Observation proofs for detector liveness, battery freshness, and command completion are part of acceptance.
- The minimum Python version is now 3.14, to match Home Assistant (ADR 0013).
- Ruff format replaces black and isort.
- Development dependencies moved from an optional extra to a `dev` dependency group.

## [0.0.0] - 2026-09-24

### Added

- Initial scaffold and RFP 0.1.
