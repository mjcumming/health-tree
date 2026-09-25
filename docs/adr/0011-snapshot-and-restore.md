# ADR 0011: State survives restarts through snapshot and restore

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Home Assistant restarts on every update. If state lived only in memory, every restart would lose open episodes, onsets, and holds. After startup grace, every known problem would open a new episode and notify again.

## Decision

- `snapshot()` returns all engine and policy state as JSON-compatible data with a `schema_version`.
- `restore(state, now)` runs after the adapter registers the graph:
  - Episodes whose anchor no longer exists resolve as `removed`.
  - Other episodes keep their ids.
  - Startup grace starts.
  - A restored episode whose anchor still fails continues without a new `opened` event.
- Migrations between schema versions are explicit functions, tested with fixtures.
- The adapter stores snapshots with Home Assistant's `Store`.

## Options considered

- **Rebuild from nothing.** Every restart becomes a notification storm.
- **Persistence inside the library.** Puts I/O in the core, against ADR 0003.
- **An event log replayed at start.** More machinery than the problem needs.

## Consequences

- Every piece of state needs a serialized form.
- Schema changes need a migration and a version bump.
- Round-trip tests are required. Scenarios 19 and 20 cover them.
