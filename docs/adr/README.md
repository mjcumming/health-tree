# Architecture decision records

Each file records one decision: the context, what was decided, the options that lost, and the consequences. The [RFP](../rfp.md) says what the library does. These say why.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-generic-core-home-assistant-separate.md) | A generic library; the Home Assistant integration in its own repository | Accepted |
| [0003](0003-sans-io-core-explicit-time.md) | A core with no I/O and explicit time | Accepted |
| [0004](0004-fixed-types-only-where-the-engine-computes.md) | Fixed types only where the engine computes | Accepted |
| [0005](0005-status-is-observed-never-rewritten.md) | Status is observed, never rewritten | Accepted |
| [0006](0006-one-cause-graph-separate-views-edge-records.md) | One cause graph, separate views, edges as records | Accepted |
| [0007](0007-episode-lifecycle.md) | Episode lifecycle | Accepted |
| [0008](0008-settle-gate-and-probe-requests.md) | Settle gate and probe requests | Superseded by 0022 |
| [0009](0009-importance-flows-up.md) | Importance flows up the cause graph | Accepted |
| [0010](0010-attention-policy-in-the-library.md) | The attention policy is a pure library module; its content is configuration | Accepted |
| [0011](0011-snapshot-and-restore.md) | State survives restarts through snapshot and restore | Accepted |
| [0012](0012-stories-and-scenarios-are-the-executable-spec.md) | Stories and scenarios are the executable spec | Accepted |
| [0013](0013-python-version-tracks-home-assistant.md) | Python version tracks Home Assistant | Accepted |
| [0014](0014-toolchain-mirrors-home-assistant-core.md) | The toolchain mirrors Home Assistant core | Accepted |
| [0015](0015-releases-from-tags-trusted-publishing.md) | Releases from tags through trusted publishing | Accepted |
| [0016](0016-rules-for-ai-assisted-development.md) | Rules for AI-assisted development | Proposed |
| [0017](0017-episode-ids-uuidv7-from-now.md) | Episode ids are UUIDv7 built from `now` | Accepted |
| [0018](0018-durations-are-required.md) | Durations are required; the library has no timing defaults | Accepted |
| [0019](0019-a-node-is-one-capability.md) | A node is one capability | Accepted |
| [0020](0020-policy-matches-each-reason.md) | The policy matches each reason; the loudest wins | Accepted |
| [0021](0021-coalesced-members-decide-recovery.md) | One anchor, one episode; coalesced members decide recovery | Accepted |
| [0022](0022-settle-gate-waits-only-on-doubt.md) | The settle gate waits only on dependencies in doubt | Accepted |
| [0023](0023-readiness-reads-own-status.md) | Readiness reads observed status, and stale is not a failure | Accepted |
| [0024](0024-atomic-observation-batches-and-fixture-steps.md) | Atomic observation batches and fixture steps; supersedes 0012 when accepted | Proposed |
| [0025](0025-readiness-preserves-unwatched-branches.md) | Readiness preserves unwatched branches; supersedes 0023 when accepted | Proposed |
| [0026](0026-checks-start-unknown-at-registration.md) | Checks start unknown at registration | Proposed |
| [0027](0027-public-records-and-the-runner-before-the-engine.md) | Public records, interface stubs, and the fixture runner come before the engine | Proposed |

## Writing one

Write an ADR when a decision changes the public interface or a rule in the RFP, would be easy to reverse by mistake, or picks between real alternatives. Details that are clear from the code do not need one.

- File name: `NNNN-short-slug.md`. Take the next number. Never reuse one.
- Status: `Proposed`, `Accepted`, `Deprecated`, or `Superseded by NNNN`.
- An accepted ADR is not edited for substance. Supersede it with a new one and update the old one's status.
- Add a row to the table above in the same change.

```markdown
# ADR NNNN: Title that states the decision

**Status:** Proposed
**Date:** YYYY-MM-DD
**Deciders:** Michael Cumming

## Context

What forces are at play? What problem does this solve?

## Decision

What we will do, concretely.

## Options considered

- **Option.** Why not.

## Consequences

- What gets easier, what gets harder, what to revisit.
```
