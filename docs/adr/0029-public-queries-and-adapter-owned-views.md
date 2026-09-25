# ADR 0029: Public query records and adapter-owned views

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The RFP includes impact, coverage, and rollup. ADR 0027 leaves their public records for the fixtures that first exercise them. Consumers need stable read contracts rather than reading snapshots or private engine fields. Views must never affect the cause graph.

## Decision

Use the query contracts in RFP section 8:

- `Impact` contains the requested node, ordered `ImpactNode` records with their declared importance, and the maximum importance including the requested node. It describes potential consequences, independent of current failure.
- `Coverage` contains node ids with no checks and `CheckReference` records for never-observed and stale checks. The categories can overlap. Evidence-only checks count as checks, while readiness retains its existing affecting-check semantics. Staleness uses the engine's unknown hold and rejoin timing.
- `View` is immutable adapter configuration, passed to `rollup(view, group)`. Its groups are copied into a read-only mapping of frozen memberships. There is no engine registration API or snapshot change for views. Missing selected members raise `KeyError`; they are not silently omitted.
- `Rollup` contains one `RollupCounts` row for each `Status`. The row's fields partition nodes into `own_episode`, `recorded`, and `clear`, in that precedence. An episode anchor includes a passing anchor of a coalesced group. Multiple recording roots count a node once. Clear means no episode membership, not a passing observation.
- Queries read evaluated state without advancing time or modifying engine state. Results and view records are frozen, slotted, keyword-only dataclasses. No enums or closed string types are added.
- The fixture schema and runner support all three queries. Scenario 35 gets a coverage fixture; scenarios 57 to 60 specify the new contracts and edge cases.

## Options considered

- **Store named views in the engine.** Adds registration, replacement, removal, and persistence lifecycle for presentation configuration that does not influence evaluation. Passing the view keeps that responsibility with the adapter.
- **Infer groups from labels.** Would make the library interpret open metadata and leave grouping behavior implicit.
- **Count one node per episode.** Overcounts a shared dependent when two independent roots fail.
- **Use clear as a synonym for healthy.** Hides unknown evidence and failures waiting behind holds, gates, or quiet windows. Status and episode membership remain separate dimensions.
- **Expose only affecting checks in coverage.** Hides lost evidence from registered evidence-only checks. Readiness already supplies the capability-level answer.

## Consequences

- Consumers can build summaries without reproducing dependency traversal or episode classification.
- Adapters own view identity, persistence, and reconciliation after inventory changes.
- These query additions do not change episode lifecycle, policy behavior, or snapshot schema.
