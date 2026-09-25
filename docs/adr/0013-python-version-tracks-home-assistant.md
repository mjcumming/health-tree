# ADR 0013: Python version tracks Home Assistant

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Home Assistant supports one Python minor version at a time (its architecture ADR-0020). Release 2026.3 moved to Python 3.14, and core now requires 3.14.2 or later.

This library's only consumer is the Home Assistant integration. The RFP 0.1 scaffold said 3.12 or later.

## Decision

- `requires-python = ">=3.14"`.
- CI tests 3.14 and runs the next Python (3.15) as a non-blocking job.
- When Home Assistant moves to a new minor version, the floor moves with it, in a minor release of this library.
- Code uses 3.14 freely. Annotations are lazy (PEP 649), so `from __future__ import annotations` is banned by ruff, as in Home Assistant core.

## Options considered

- **Keep 3.12 or later.** More potential users, and more CI. The library cannot use 3.14 features, and it drifts from Home Assistant's style.
- **Pin to Home Assistant's exact patch release.** Needless friction.

## Consequences

- Contributors need Python 3.14. uv installs it automatically.
- Code reads like Home Assistant core.
- Installations running Python older than 3.14 cannot install new releases. That is acceptable because the integration already requires Home Assistant 2026.3 or later.
