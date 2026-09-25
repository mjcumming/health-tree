# ADR 0008: Settle gate and probe requests

**Status:** Superseded by 0022
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Children usually notice first. Entities go unavailable within seconds, while a host ping plus its hold confirms minutes later. Without handling, the child notifies, then the root does.

Nagios handles this with predictive dependency checks: on a state change, it checks what the host depends on. Alertmanager's `group_wait` exists partly so an inhibiting alert can arrive before the first notification.

## Decision

- A node may not open an episode while a hard dependency is unsettled, for at most `settle` from the node's onset. A dependency is unsettled when:
  - a worsening is inside its `raise_hold`, or
  - it has no observation newer than the node's onset, or
  - it is gated itself.
- A dependency with no checks never gates.
- While gated, the engine emits `ProbeRequested(node_id)` once for each unsettled dependency.
- The adapter may refresh that node. The engine never probes anything itself.

## Options considered

- **A fixed delay on every episode.** Slows everything, including failures with no parent in question.
- **Holds alone.** Fragile: every child's hold would have to exceed every parent's detection time.
- **Absorption alone.** Notifies first and retracts later.

## Consequences

- A child's episode can be delayed by up to `settle`.
- The adapter should answer probes quickly, for example with `homeassistant.update_entity` or a ping.
- A parent slower than `settle` is still handled, by absorption (ADR 0007).
