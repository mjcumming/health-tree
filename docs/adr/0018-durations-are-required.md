# ADR 0018: Durations are required; the library has no timing defaults

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Every rule in the engine and the policy depends on a duration:

- holds
- `ttl`
- `unknown_hold`
- `settle`
- rejoin and startup grace
- the coalescing window
- `batch`

A default buried in a library becomes behavior nobody chose. It is also hidden from the owner who has to live with it. Test fixtures need numbers too, and those numbers must not leak into production.

## Decision

- The library requires every duration it uses and fills in none.
  - Engine settings: `settle`, `rejoin_grace`, startup grace, `coalesce_count`, `coalesce_window`.
  - Policy configuration: `batch`.
  - Per check: `raise_hold`, `clear_hold`, `ttl`, `unknown_hold`.
- `ttl` may be `None`, said explicitly, for a check that never goes stale. `unknown_hold` is always a duration, because a checker that cannot run also reports `unknown`.
- The integration supplies every value.
  - Its catalog sets per-check durations.
  - Its settings UI owns the rest, and supplies fallbacks, with starting values the owner can change (RFP section 11).
- Fixtures state every duration they use. Those numbers are test input, not defaults.

## Options considered

- **Defaults in the library.** Convenient, but they become behavior no one chose, and changing one silently changes every installation.
- **Defaults hidden in the integration's code.** Better, but still invisible to the owner. The settings UI makes them visible and editable.

## Consequences

- Constructing an engine or registering a check takes more arguments.
- A missing duration is an error at registration, not a surprise at 3 AM.
- The integration's settings UI is the one place to tune timing.
