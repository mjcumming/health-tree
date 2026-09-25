# ADR 0007: Episode lifecycle

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The goal is one message per root failure, updated in place, and one recovery. The review of RFP 0.1 found holes:

- `warn` and `unknown` had no path to anyone, so a dead battery went silent.
- A parent confirmed late produced two messages.
- An independent failure that predated its parent's would notify twice.
- A degraded parent (`warn`) produced a flood from its children.
- Stragglers after a rejoin each opened their own episode.

## Decision

The lifecycle is RFP rules 12 to 22:

- **Open.** `warn` and `fail` open episodes. `unknown` past `unknown_hold` opens a `stale` episode.
- **Resolve.** Recovery means `pass` through `clear_hold`. `fail` to `warn` is an update.
- **Absorb.** A dependent's episode whose onset is within `settle` of the root's onset folds into the root's episode.
- **Keep older problems.** An older, independent episode stays open (Hickam's dictum: two problems, two episodes).
- **Coalesce.** Many episodes under one direct dependency form one `group` episode with reason `dependents_failing`.
- **Quiet windows.** Startup grace and scoped maintenance windows stop episodes from opening. Rejoin grace applies after recovery.
- **Stable ids.** Episode ids survive restarts.
- **Events.** `opened`, `updated`, and `resolved`, where a resolution is `cleared`, `removed`, or `absorbed`.

## Options considered

- **An alert per node, with label-based inhibition** (the Alertmanager style). Floods on recovery and no impact list.
- **Open only on `fail`.** Dead batteries and slowly filling disks stay silent.
- **Absorb everything under a failed root.** Hides real, independent problems.

## Consequences

- The adapter must replace messages in place, using Home Assistant notification tags, and withdraw absorbed ones.
- More states to test. Scenarios 14 to 26 cover them.
- `settle`, `coalesce_count`, `coalesce_window`, and `unknown_hold` are required settings with no library defaults (ADR 0018). The integration supplies them, with starting values in RFP section 11.
