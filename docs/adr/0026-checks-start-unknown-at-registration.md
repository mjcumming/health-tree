# ADR 0026: Checks start unknown at registration

**Status:** Proposed
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Clarifies initialization under ADRs 0007 and 0018, and which unknown checks contribute episode reasons under ADR 0020.

## Context

Scenario 44 registers a command check an hour before its first observation, with `unknown_hold: 15m`, but expects no stale reason. A null TTL only disables observation expiry; it cannot supply evidence that a check has passed.

The initial unknown state also needs to be distinguished from clearing an observed problem. Fixtures use an initial passing observation immediately, while recovery requires a hold.

## Decision

- A newly registered check starts `unknown`, with the unknown interval beginning at registration time. No default `pass` or inactive state is supplied.
- `ttl: None` disables expiry of a supplied observation. Never-observed checks and explicit `unknown` observations still use `unknown_hold`.
- Unknown checks affect `own`, readiness, and coverage immediately. They contribute an episode reason only after `unknown_hold`, with reason `stale`. An existing episode gains that reason through an update; a second episode does not open on the same node.
- An initial `pass` applies immediately if the check has never reported `warn` or `fail` and has not become stale. Once a problem is known, `pass` clears it only after `clear_hold`.
- The adapter registers an operation check when it can establish its initial condition. An observed `pass` meaning no command is outstanding describes command verification only. It does not assert device reachability or predict the next command will succeed.
- The library does not branch on operation labels or reasons. These rules apply to all checks.

## Options considered

- **All checks begin passing.** Invents evidence and conceals gaps.
- **Null TTL disables unknown handling.** A checker that cannot run could then remain unknown indefinitely without an episode.
- **A special inactive command state.** Adds a closed type and operation-specific behavior to the generic engine.

## Consequences

- Scenario 44 explicitly initializes its command check with an observation before exercising mixed-reason routing.
- Scenario 56 covers a never-observed null-TTL check, its stale episode and recovery, and a separately initialized command check.
- Startup windows can defer the opening of an episode, but they do not invent an initial passing observation.
