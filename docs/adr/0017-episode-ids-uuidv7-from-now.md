# ADR 0017: Episode ids are UUIDv7 built from `now`

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

An episode needs an id that survives updates and restarts, so the adapter can replace a message in place and a restored episode continues instead of reopening.

RFC 9562 defines UUIDv7: a millisecond timestamp, a version, counter or random bits, and more random bits. The ids sort by time. Home Assistant's context ids are ULIDs, the same idea from before the RFC.

Python 3.14's `uuid.uuid7()` takes no arguments and reads `time.time_ns()`. ADR 0003 says the engine never reads a clock.

## Decision

- An episode id is a UUIDv7, assigned when the episode opens and kept through updates, absorption, and restore.
- The engine builds it from `now`:
  - The 48-bit timestamp is `now` in milliseconds.
  - The 12 counter bits keep ids opened in the same millisecond in the order they opened.
  - The remaining bits are random.
- Ruff's banned-API list bans `uuid.uuid1`, `uuid.uuid6`, and `uuid.uuid7`, because they read the clock.
- The random bits are the engine's only input beyond its calls. `Engine` accepts an optional id factory, `(now) -> str`, so a test can make ids predictable.
- Fixtures do not predict ids. They bind the id of the episode that opened on an anchor and refer to it later (ADR 0012).

## Options considered

- **`uuid.uuid7()`.** Standard and one line, but it reads the clock, so ids would not follow the `now` that tests pass.
- **Ids derived from content, such as a hash of anchor and onset.** Fully deterministic, but two episodes on one anchor at the same instant collide, and callers start parsing meaning out of the id.
- **A counter.** Deterministic, but it restarts with the process unless it is snapshotted, and it does not sort across restores.
- **ULID.** What Home Assistant uses for contexts, and equivalent in practice. UUIDv7 is the standardized form and parses as a UUID everywhere.

## Consequences

- Ids sort by open time, across restarts too, because the timestamp comes from `now`.
- Tests that compare whole snapshots pass an id factory.
- A clock-reading id function in `src/` fails lint.
