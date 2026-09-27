# ADR 0034: Acknowledgment and cancellation belong to their owning state machines

**Status:** Accepted
**Date:** 2026-09-26
**Deciders:** Michael Cumming

## Context

Operators need to record awareness and end temporary controls early. The library
must remain the authority for attention and episode behavior across adapters,
recipients, and restarts. Awareness does not establish recovery.

## Decision

The policy records the first explicit acknowledgment of an open episode, with
its UTC time and optional opaque actor id. Repeating it is idempotent. The record
is shared across recipients, survives restore and activation, and ends with the
episode. Absorption does not transfer awareness to another episode.

Rules opt in with `require_acknowledgment`, default false. Once acknowledged,
such a rule no longer escalates or sends outstanding or repeated notifications.
Silent updates and resolutions still reach existing recipients. Other rules,
including a newly matching urgent condition, keep their configured behavior.
Transport delivery and dismissal never acknowledge an episode implicitly.

`Policy.unshelve` removes an episode's delivery hold and reevaluates due work,
retaining batching, quiet hours, and acknowledgment. `Engine.cancel_quiet`
removes one window matching the supplied public `QuietWindow` and reevaluates
observations. Overlapping windows continue independently. Matching uses scope,
node, and original expiry, including windows restored from older snapshots.
The adapter retains a separate control id for each request and rejects repeated
cancellation of a removed control before calling the engine again.

## Consequences

No new closed enum or runtime dependency is needed. Policy snapshots advance
to version 3 and restore versions 1 and 2 with no acknowledgments. The engine
snapshot shape is unchanged. The adapter authorizes requests, persists both
state machines, and exposes actions without owning parallel attention state.
No action here repairs equipment or changes observed health.
