# ADR 0022: The settle gate waits only on dependencies in doubt

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Supersedes ADR 0008 when accepted. Probe requests are unchanged.

## Context

ADR 0008 counts a dependency as unsettled when it "has no observation newer than the node's onset." Most Home Assistant entities report only on change, so that condition is true for nearly every dependency, nearly all the time. Almost every episode would wait for a probe answer or for the whole `settle`.

Story 8 shows the cost. The garage door fails to close at 23:10:30. The opener, its integration, and the hub all passed on their last observations, minutes or hours old. Under ADR 0008 the garage episode waits for probes before it can open. Up to `settle`, 2 minutes in the integration's starting values, is added to a failure the policy delivers as `urgent`. The policy's `urgent` skips `batch`, but it cannot skip the engine's gate, because the engine does not know loudness.

The gate exists to save a message that absorption would otherwise retract. That is worth a short wait when a parent really is in doubt, not on every failure.

## Decision

- A node may not open an episode while a hard dependency is in doubt, for at most `settle` from the node's onset. A dependency is in doubt when:
  - a worsening is inside its `raise_hold`, or
  - its `own` is `unknown`, or
  - it is gated itself.
- A dependency whose `own` is `pass` or `warn` on observations within `ttl` is not in doubt, however long ago it last reported.
- A dependency with no checks never gates.
- While gated, the engine emits `ProbeRequested(node_id)` once for each dependency in doubt.
- A parent whose failure is confirmed after the child's episode opened is handled by absorption (rule 16), as before.

## Options considered

- **Keep ADR 0008, and let the adapter answer probes fast.** The wait is then as long as the slowest probe, which for a cloud integration or a battery device can be the whole `settle`.
- **Let `urgent` bypass the gate.** Loudness belongs to the policy (ADR 0010). The engine would need to know the policy's decision before the episode exists.
- **A per-check flag that asks for a probe before a child may open.** Possible later, for a dependency known to report late. Not needed for any story now.

## Consequences

- Most episodes open at the time their own holds allow. Story 8 is delivered at 23:10:30.
- When a parent's last pass is out of date but still inside `ttl`, the child opens first and the parent's episode absorbs it moments later. For a `notify` episode, `batch` usually hides that. For an `urgent` one, the owner sees the first message replaced.
- Scenario 14 still holds: its parent has never been observed, so it is `unknown` and in doubt. Scenario 48 covers a dependency that is not in doubt.
