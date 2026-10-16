# ADR 0040: Make sibling coalescing optional

**Status:** Accepted
**Date:** 2026-10-16

Partially supersedes the mandatory coalescing decisions in ADRs 0007 and 0021. Their behavior remains available for callers that supply a numeric count.

## Context

Several devices can be unavailable while their shared integration works. A common dependency and nearby episode opening times do not establish a common fault. Startup can make unrelated failures eligible together. Merging them gives acknowledgment and pause a broader scope than the device the user selected.

## Decision

Allow `EngineSettings.coalesce_count` to be `None`. This disables sibling coalescing, later joining, and coalescing of stragglers after a dependency recovers. Observed failing dependencies still suppress their affected dependents. Numeric counts retain existing behavior.

Existing coalesced members become independent root episodes. A recovered dependency retains its normal rejoin grace before releasing members. Unknown evidence without a valid current finding on either a watched dependency or a member retains unresolved scope until fresh evidence or stale timing allows a complete transition. In particular, a watched dependency passing through unknown during reload cannot release its members and later report an unrelated all-clear. A dependency without checks has no evidence to wait for. No failure finding or recovery is invented.

Each successor opening carries `split_from`, the exact predecessor episode id. When the predecessor has no independent problem remaining, it resolves with `resolution="split"` and the successor ids in `split_into`. Successor openings precede that resolution. A warning or failing predecessor retains its own episode. A split does not represent recovery.

The policy handles this relationship directly from public events. Each route carries the predecessor's acknowledgment, original actor and time, shelf expiry, attention age, and eligible delivery history into its explicit successors. Pending recipients keep their existing deadlines where still authorized. Matching runs against each successor's actual findings; inherited history cannot authorize a different destination. Existing messages are updated silently. Later failures receive no inherited controls, and successor controls are independent.

When several recovering dependencies share one affected node, they produce only one successor. If that successor already has an independent episode, its identity and controls remain unchanged. A new successor shared by multiple predecessors receives fresh attention with `split_from=None`; selecting one predecessor's acknowledgment or pause would arbitrarily suppress the other scope. Every ending predecessor links to the same successor through `split_into`.

## Options considered

- Only narrow the popup. The controls would still affect the other devices.
- Remove dependency edges. That loses suppression when the integration actually fails.
- Use a very large count. This leaves an arbitrary threshold and does not reliably retire existing groups.
- Resolve old groups as cleared or removed. Their problems did not recover and monitoring did not end.

## Consequences

Callers that select independent siblings must handle `split` as a non-recovery outcome and retain its successor links in history. Existing callers using numeric counts retain the same behavior. Saved engine and policy state remains readable; the engine emits the transition and the policy preserves controls without callers interpreting snapshots.
