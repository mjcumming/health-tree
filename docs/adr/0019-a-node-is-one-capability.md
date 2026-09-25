# ADR 0019: A node is one capability

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

A node's checks fold into one `own` status and one episode. That is right when every check describes the same thing working or not. It goes wrong when one node carries problems of different kinds.

The review of RFP 0.2 used the AI box. Its service has had `update_pending` open for ten months, and then its end-to-end probe fails. With both checks on one node:

- There is one episode, not the two that story 6 describes.
- Its labels merge `category: maintenance` with `category: fault`. If maintenance wins, the first-match maintenance rule sends the outage to the digest.
- When the probe passes, `own` drops to `warn`, not `pass`. Rule 15 calls that an update, so the outage never resolves.
- If a maintenance check ever reports `fail`, such as `backup_overdue`, every function that uses the box is muted and counted as impact.

The same thing happens when dependents need different parts of a node. If Frigate detection and Frigate recording share a node, a full recording disk mutes motion lighting, which only needs detection.

The engine cannot sort this out. It never reads categories or labels (ADR 0004).

## Decision

- A node is one capability: one thing that either works or does not, as its dependents see it.
- A check belongs on a node only if its `fail` means that node's dependents cannot do their job.
- Two tests decide where a check goes:
  - **Would its failure stop every dependent?** If not, it belongs on another node. Maintenance debt, such as `update_pending` or `backup_overdue`, gets its own node that nothing depends on. That node has its own episode and its own recovery, and it mutes nobody.
  - **Do dependents need different subsets of the checks?** Then the node is several capabilities, and each becomes a node.
- A leading indicator of the same capability stays on it. `battery_low` only ever reports `warn`, and the dead battery shows up as the same node going `stale`.
- A maintenance node is tied to its subject by a view or a label, never by an edge.
- The catalog applies the tests. The integration checks them with a lint. The engine does not change.

## Options considered

- **Episodes per check instead of per node.** Solves routing and recovery, but a node's checks would stop agreeing on whether it works. Inhibition would need a second notion of failure, and "one root, one episode" would be lost.
- **`affects_own: false` for maintenance checks, plus episodes from such checks.** Also an engine change, and it creates two kinds of episode on one node.
- **Leave it to the policy.** Per-reason matching (ADR 0020) fixes routing, but not recovery or wrongful muting.

## Consequences

- The catalog is responsible for the shape of nodes, not only for their checks. Its entries say which node each check lives on.
- A device can become several nodes. Views and `rollup` keep the owner's picture of one device.
- Story 6 becomes true as written: two nodes, two episodes.
- ADR 0020 still covers the case this does not remove: a node whose checks are all the same capability but carry different categories, such as `battery_low` next to `command_failed`.
