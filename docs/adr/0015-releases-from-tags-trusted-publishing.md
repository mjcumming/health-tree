# ADR 0015: Releases from tags through trusted publishing

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Home Assistant's dependency-transparency rule asks for:

- an OSI-approved license
- a source distribution on PyPI
- publication from a public CI pipeline
- PyPI versions that match tagged releases

pywiim and home-topology already publish from `v*` tags through PyPI trusted publishing.

## Decision

- **Versioning.** Semantic Versioning, starting at 0.x.
  - It stays below 1.0 until the Home Assistant integration has run in a real house.
  - Pre-releases use `aN`, `bN`, or `rcN`.
- **The version string.** It lives in `pyproject.toml` and in `health_tree.__version__`, and a test keeps the two equal.
- **The release workflow.** Pushing a `v*` tag runs `release.yml`, which:
  1. Checks that the tag equals the version.
  2. Builds the sdist and the wheel with uv.
  3. Checks both with twine.
  4. Publishes to PyPI through trusted publishing, in a `pypi` environment, with attestations.
  5. Creates a GitHub release whose notes come from `CHANGELOG.md`.
- **The changelog.** `CHANGELOG.md` follows Keep a Changelog, with `## [X.Y.Z] - YYYY-MM-DD` headings.

## Options considered

- **Manual uploads with twine.** Not reproducible, and fails Home Assistant's rule.
- **release-please or semantic-release.** More automation than one maintainer needs.

## Consequences

- One-time setup is needed: a trusted publisher on PyPI and a `pypi` environment on GitHub.
- No API tokens are stored anywhere.
