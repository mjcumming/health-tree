# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-09-25

### Added

- Explicit attention activation, read-only policy explanations and delivery causes.

### Fixed

- Reminders respect each recipient's quiet hours, shelving and record-only decisions. Escalation thresholds crossed during restart remain deliverable.

## [0.1.0] - 2026-09-25

### Added

- ADRs 0031 and 0032, accepted: situation alerts are in scope, reported from outside the library, and modeled as edgeless nodes. Story 10 and scenarios 61 to 64 have fixtures, and they pass against the current engine and policy.
- Fixture delivery expectations can assert `silent`, to tell a second page from a silent update.
- Public `impact`, `coverage`, and `rollup` queries with immutable result records and adapter-owned views. Query contracts and fixtures cover potential impact, evidence gaps, and counts without duplicate dependents (ADR 0029).
- Fixture steps that register and remove nodes at runtime and shelve episodes (ADR 0030, accepted).
- Fixtures for scenarios 7, 21, and 32 and stories 2, 6, 7, and 9. Every story and scenario now has a fixture, except scenarios 12, 26, and 38, which unit tests cover.
- RFP 0.5 specifies public query contracts and scenarios 57 to 60. Scenario 35 now has a coverage fixture, and the fixture runner supports all five queries.
- ADRs 0024 to 0026 and scenario fixtures 53 to 56 for atomic and staggered ingestion, partial readiness coverage, and initially unknown command checks.
- `health_tree.types`, the public records: fixed types, settings, nodes, checks, observations, episodes, events, quiet windows, query results, policy configuration, and deliveries (ADR 0027).
- `Engine` and `Policy` with their RFP section 8 signatures. Every method raises `NotImplementedError` until the engine is written.
- The fixture runner, tested against a scripted engine. Every fixture now runs, and a strict xfail marks each one the engine does not pass yet.
- A quiet-window fixture step, and a fixture for scenario 49.
- The engine. It covers check holds, `ttl`, and staleness; inhibition and the settle gate with probes; coalescing, joining, and dissolving groups; absorption; quiet windows and startup and rejoin grace; UUIDv7 episode ids; `explain` and `readiness`; `next_deadline`; and JSON snapshots with restore.
- The attention policy. It covers per-reason matching where the loudest wins, batching, quiet hours in the policy's time zone, digests, silent updates and resolution notices, age and deadline thresholds, reminders, escalation, shelving, and snapshots.
- Fixtures for scenarios 1 to 6, 8 to 11, 13, 15 to 17, 20, 22, 23, 25, 28 to 31, 34, 37, and 40 to 42, also covering stories 1, 3, and 5. Every fixture passes, and `PENDING` is empty.
- Unit tests for the engine and policy API, and Hypothesis properties: a consistent event history, one root episode per anchor, no opening under a failed dependency, none inside a quiet window, full recovery, snapshot and restore, and batch order.
- ADR 0028, accepted: the engine and policy semantics the RFP left open.
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

- RFP 0.6 moves situation alerts into scope. Evaluating conditions and serving as a life-safety alarm are out of scope. Engine and policy behavior are unchanged.
- The Homeostatic UI worksheet adds section 16, decisions for the first release: situation alerts detected only by Home Assistant rules bound as entities (pending an RFP change), one attribute-matching rule model for checks and exclusions, enrollment as an integration setting, importance on functions, notification content and timing owned by Homeostatic with delivery left to Home Assistant consumers, and the notification designed before the panel. Library behavior is unchanged.
- ADR 0029 is accepted: public query records and adapter-owned views.
- Documented current Home Assistant error and repair conventions in the UI worksheet, with release-source references and proposed reuse of native setup, reauthentication, entity availability, Repairs, diagnostics, and action errors.
- The Homeostatic UI proposal now includes user-created alerts and rule-reported conditions, with shared attention, explicit clearing and freshness, restart/schedule handling, and a proposed situation-alert scope extension. Library behavior is unchanged.
- Expanded the Homeostatic UI ideas worksheet with proposed setup, monitoring, alert, coverage, maintenance, and migration workflows, implementation gaps, and acceptance walkthroughs. These remain proposals, not library behavior changes.
- ADRs 0016 and 0024 to 0028 are accepted. ADR 0012 is superseded by 0024, and ADR 0023 by 0025.
- Rule 15: when an anchor recovers while nodes it muted still fail, its episode holds them through rejoin grace instead of sending an all-clear. They then become members, or each opens its own episode (scenario 4).
- Readiness names causes only. Hardware behind a failed dependency is not named, and `explain` shows the chain (scenarios 34 and 49).
- The README is expanded: the problem, principles, model, a worked example from story 8, design constraints, repository layout, and a documentation map.
- The README states that a delivery names the episode, recipient, loudness, and channel names, and that the integration carries those channels out.
- RFP 0.4 defines atomic observation batches, preserves unwatched readiness branches, specifies check initialization, and tightens the real-device evidence required for freshness proofs. ADRs 0024 to 0026 cover them.
- Scenario 44 now initializes its command check before testing mixed-reason routing. Group fixtures assert recorded members and absorbed ids.
- README and package documentation now point to RFP 0.4.
- RFP 0.3 settles the review of 0.2 (RFP section 15):
  - A node is one capability. Maintenance debt gets its own node.
  - Policy rules match each reason of an episode, and the loudest result wins.
  - One anchor, one episode. Coalesced members decide when it recovers.
  - The settle gate waits only on dependencies in doubt.
  - `readiness` reads observed status, and a stale dependency answers `unknown`.
  - Observation proofs for detector liveness, battery freshness, and command completion are part of acceptance.
- The minimum Python version is now 3.14, to match Home Assistant (ADR 0013).
- The Home Assistant integration repository is named `homeostatic` (RFP section 11), closing an open question from section 13.
- Ruff format replaces black and isort.
- Development dependencies moved from an optional extra to a `dev` dependency group.

## [0.0.0] - 2026-09-24

### Added

- Initial scaffold and RFP 0.1.
