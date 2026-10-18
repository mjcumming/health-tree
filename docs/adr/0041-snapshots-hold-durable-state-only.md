# ADR 0041: Snapshots hold durable state only

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Michael Cumming

## Context

Homeostatic persists `Engine.snapshot()` and `Policy.snapshot()` after each refresh and, since its ADR 0097, skips a write whose serialized bytes equal the last verified write. That skip never applied, because both snapshots changed on every observation round even when no condition changed: the engine snapshot carried the clock and each of 1,757 check records carried its full last observation with its `observed_at`, and every policy route carried the clock. Measured on a 6,000-entity installation, that was 7.7 MB rewritten about 1.5 times a minute, roughly 17 GB a day, and a long garbage collection every few minutes from the allocation behind it. Between two idle saves one minute apart, the only fields that differed were those clocks and payloads.

ADR 0011 made state survive restarts through snapshot and restore. It did not say which state. The engine reads a check's stored observation payload for one purpose, to tell a never-observed check from an observed one in `coverage()`; everything else it needs after a restart is the check's effective status, its `since`, reason, message, deadlines and pending transition, which are durable facts.

## Decision

- A snapshot holds durable state: what a restart would otherwise lose and a consumer cannot re-derive from its next observation round. Two snapshots taken while no condition changed are equal.
- The engine snapshot moves to schema version 2. It no longer carries the clock or a check's last observation payload; each check record carries the payload's durable details instead: `observed`, the reason, message and due time a pending transition applies when its hold ends, and `expires_at` for evidence with a TTL. Schema 1 snapshots still restore, and those details are read from their payloads. A check with a TTL moves its expiry with each observation, which is a real change to its deadline.
- Policy route snapshots move to schema version 5. They persist each tracked episode's decision (loudness, recipients, digest) instead of the clock that restore used to recompute it, so the first advance after a restore still emits a crossing that happened while stopped, once. Versions 1 to 3 restore and decide as of their stored clock.
- Restore keeps every rule of ADR 0011: episodes keep their ids, startup grace starts again, and a restored episode whose anchor still fails continues without a new `opened` event.

## Options considered

- **Report whether a snapshot changed instead of changing its content.** A revision counter would let a consumer skip a write, but the stored payloads would still cost their bytes on every write that does happen, and every consumer would need the extra call.
- **Keep the payload but drop `observed_at`.** The payload is still re-derived by the next observation, and a consumer showing it after a restart would present stale evidence as current.
- **Leave it to consumers to strip fields.** The snapshot is opaque to them by design (Homeostatic's rules forbid reading into it), so the library has to own what it contains.

## Consequences

- Consumers that persist after every observation round can skip unchanged snapshots; the household installation's remaining per-minute churn moves to the adapter's own choices.
- The size of the engine snapshot falls by the observation payloads, about 0.7 MB of 2.1 MB on that installation.
- After a restore, `explain()` and views have no observation payload until the next observation of each check; consumers already re-observe every source at startup.
- Policy route snapshots still carry a copy of every tracked episode per route, 86 kB per route on that installation; that is durable and a separate size question.
