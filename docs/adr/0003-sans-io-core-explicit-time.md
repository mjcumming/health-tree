# ADR 0003: A core with no I/O and explicit time

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Home Assistant runs one asyncio event loop. Anything that blocks or sleeps on it stalls the house.

Holds, `ttl`, grace periods, digests, and reminders all depend on time, and tests that sleep are slow and flaky.

The sans-I/O pattern (h11, h2, wsproto) solves both: the protocol logic is a pure state machine, and the caller does all I/O.

## Decision

- The engine and the policy are synchronous state machines.
- They do no I/O, start no threads, use no event loop, and never read a clock.
- Every call that depends on time takes `now`, a timezone-aware UTC `datetime`. Naive datetimes are rejected.
- Durations are `timedelta`.
- Calls return events or deliveries.
- `next_deadline()` tells the caller when to call `advance(now)` again, so the adapter needs one timer, not a polling loop.
- Ruff's banned-API list enforces this. It bans `asyncio`, `threading`, `time.time`, `time.monotonic`, `time.sleep`, `datetime.datetime.now`, `datetime.datetime.utcnow`, `datetime.date.today`, `uuid.uuid1`, `uuid.uuid6`, `uuid.uuid7`, and `homeassistant`.
- The random part of episode ids is the one input that does not arrive through a call. ADR 0017 explains it, and lets tests replace it.

## Options considered

- **An asyncio library.** Natural inside Home Assistant, but it couples the model to an event loop and makes tests slower and harder.
- **An injected clock object.** Hides time inside the engine and still needs someone to schedule wake-ups.
- **A fixed tick.** Wasteful and imprecise.

## Consequences

- Safe to call from Home Assistant callbacks: no `await`, no blocking.
- Tests are deterministic and run without sleeping.
- The adapter owns scheduling, with one `async_track_point_in_utc_time` at a time.
- Calls must stay fast, so evaluation must be incremental rather than a full recomputation per observation.
- The engine is not thread-safe. One caller at a time.
