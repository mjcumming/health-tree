# ADR 0024: Observation batches and fixture steps are explicit

**Status:** Proposed
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Supersedes ADR 0012 when accepted. The fixture approach and its invariants are retained; this decision defines how observations become engine calls.

## Context

Several coalescing fixtures submit three observations in one step and expect only a group opening or one update to an existing episode. The interface accepts one observation per call. After the first two separate calls, the grouping threshold has not been met and their episodes can already have opened. A later call cannot remove returned events.

An adapter sometimes receives one coherent set of observations, and sometimes receives independent callbacks. Both must have a testable contract.

## Decision

- `ingest_many(observations, now)` validates the complete non-empty batch before changing state. Duplicate `(node_id, check_id)` pairs are invalid. Apply all observations, then evaluate the graph and episodes once. Observation order does not determine the resulting state.
- `ingest(observation, now)` is a one-observation batch. It returns its events immediately. Adapters must not hold independent arrivals just to make a batch.
- A call emits only the final opening, update, or resolution for each affected episode. An `advance(now)` evaluates all due changes together as well. Opening an absorbing episode is emitted before resolutions of episodes absorbed into it.
- Events from earlier calls remain in the history. Staggered failures can open child episodes before a group absorbs them. Notification batching can drop pending deliveries; an urgent notification already sent cannot be unsent.
- Fixtures represent silent resolution deliveries with `episode`, `to`, and `resolution`, without a loudness or digest. They establish that a previously delivered child message is withdrawn or updated silently after absorption.
- YAML fixtures under `tests/fixtures/` are the executable specification. Each file's `id` matches its name, and `covers` names its stable story or scenario ids. A fixture may cover related scenarios together.
- Every fixture states its durations. `start` is engine creation and the beginning of startup grace. Step times are UTC, strictly increasing, and not before `start`.
- At each step the runner calls `engine.advance(at)`, then applies the step's atomic `ingest` list through `ingest_many`, or performs its restart. Observations in that list have `observed_at = at`. An expectation-only step just advances time. The runner does not insert other times.
- The runner retains events from every call in order, feeds them to `policy.handle`, then calls `policy.advance(at, context)`. These deliveries form the step's complete delivery list. The adapter uses the same ordering when observations and delivery deadlines coincide.
- `events` is the complete event list for the step. When `deliveries` is present, it is the complete delivery list. Mappings match the fields they name; unspecified fields remain free. `open` is the complete set of remaining open episodes.
- Event and delivery order is significant. Membership fields `recorded` and `absorbed` compare as sets after resolving episode bindings; their serialized list order is not part of the contract.
- Episode ids are bound with `bind`, then referenced as `$name`. Fixtures do not predict UUID bits. They may assert episode status, reasons, recorded members, and absorbed ids.
- One runner will feed the engine and policy when they exist. The current schema validator checks fixture structure only.
- Hypothesis will check the existing invariants: failed dependencies inhibit new episodes, an anchor has at most one open episode, quiet windows prevent openings, passed checks eventually resolve episodes, and snapshot/restore preserves state. Batch permutation invariance is added.

## Options considered

- **Keep single ingestion only and revise all group fixtures.** Valid for independent callbacks, but cannot express a coherent observation set without transient child episodes.
- **Treat all observations with equal timestamps as one batch.** A returned event cannot depend on whether another call will arrive with the same timestamp.
- **Wait inside the engine to accumulate observations.** Delays urgent events and obscures the explicit-time contract.

## Consequences

- The adapter can choose an explicit batch only when it already has the observations together.
- Scenarios 53 and 54 distinguish atomic batches from staggered arrivals, including notify and urgent delivery histories.
- The schema rejects duplicate check observations in a batch and can assert the membership and absorption fields that establish coalescing.
- Accepting this ADR changes ADR 0012's status to superseded; its historical text remains unchanged.
