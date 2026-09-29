# ADR 0036: Accept expiring situation reports from external automations

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Michael Cumming

## Context

The owner chose to build the Home Assistant automation handoff before a dedicated
Homeostatic condition UI. ADR 0031 required a stateful entity and rejected direct
automation calls because those calls need expiry, ordering and restart semantics.
The library already supplies the required episode, unknown, TTL and persistence
behavior. The adapter can define the missing reporting contract without adding
condition evaluation or I/O to the library.

## Decision

This partially supersedes ADR 0031's entity-only Home Assistant reporter choice.
Its other decisions and ADR 0032's edgeless situation shape remain in force.

- A situation may be bound to an HA entity or explicitly configured for automation
  reports, never both. The automation evaluates the condition in HA.
- Direct reports express active, clear or unknown. The adapter maps them to
  ordinary fail, pass or unknown observations with its UTC acceptance time.
- Automation reports have an explicitly configured finite check TTL. The producer
  refreshes reports before expiry. Expiry means unknown, never clear; normal
  unknown_hold and attention rules still apply.
- One producer owns a situation id. Calls are serialized in arrival order. A
  repeated active report renews evidence on the existing episode; it is not a new
  occurrence. Delayed producers must reevaluate current state before reporting.
- On adapter restart or reload, restored automation situations require fresh
  evidence. The adapter reports unknown after restoring the engine, preserving
  an unresolved episode until a fresh clear report establishes recovery.
- The adapter persists processed state before publishing resulting notifications.
  Reports do not bypass policy, create recipients or enable notification delivery.
- Native HA action fields and a blueprint using HA condition/trigger selectors
  are in scope. A Homeostatic condition language/editor and one-shot informational
  event reporting are outside this increment.

## Consequences

No engine or policy behavior changes. Adapters can use ordinary observations,
explicit TTL, opaque snapshots and public events. Homeostatic owns service
authorization, validation, serialization and restart reconciliation. Its ADR 0032,
specification and executable HA scenarios define the concrete action and blueprint.
Entity-bound situations remain supported without requiring periodic refresh.
