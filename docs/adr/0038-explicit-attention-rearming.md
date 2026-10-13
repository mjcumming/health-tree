# ADR 0038: Let a caller rearm acknowledgment after a confirmed change

**Status:** Accepted
**Date:** 2026-10-13

## Context

A producer can confirm a new risk while the same condition remains open. Low reserve on mains, for example, becomes an operational risk when backup power starts. Independent attention routes retain episode-scoped acknowledgment, so switching to an acknowledgment schedule cannot itself request renewed awareness.

## Decision

Add `Policy.rearm(episode_id, now, context)`. A caller uses it after confirming a meaningful change. The library clears an existing acknowledgment across the episode's routes and reevaluates attention from `now`. Each route announces according to its configured rule. A shelf remains in force. Episode identity, condition evidence and destination cleanup remain unchanged. Rearming without an acknowledgment is a no-op; ordinary policy updates already announce a rise in loudness.

The library never infers which changes warrant rearming and never branches on a reason or device type. A caller passes the updated episode through `handle` before rearming it. Unknown episode ids raise `KeyError`; UTC and monotonic time requirements remain.

## Consequences

Adapters can request renewed awareness without falsely resolving a condition. Acknowledgment remains durable unless the caller explicitly rearms it. A consumer must avoid rearming on repeated readings or missing evidence.
