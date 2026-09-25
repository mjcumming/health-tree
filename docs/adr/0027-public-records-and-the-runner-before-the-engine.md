# ADR 0027: Public records, interface stubs, and the fixture runner come before the engine

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Refines ADR 0024's statement that the runner arrives with the engine. Settles the record shapes that RFP sections 5, 7, and 8 leave open.

## Context

The runner has to build settings, nodes, checks, observations, and quiet windows from a fixture, and read events, deliveries, and query answers back. So it needs the public records, and the records are the public interface. Writing the runner with the engine would freeze that interface and the engine's behavior in the same change, and the engine would pull the interface toward whatever was easiest to build.

The RFP names the fields but leaves some shapes open. What does an event carry? Is a resolution notice a delivery? What does a quiet window look like? What do the queries return? Which fixed values are enums?

## Decision

**Order.** `health_tree.types`, then `Engine` and `Policy` with the RFP section 8 signatures and bodies that raise `NotImplementedError`, then the runner. The engine follows.

- `tests/test_fixtures.py` runs every fixture. `PENDING` lists the fixtures the engine does not pass yet, marked `xfail(raises=NotImplementedError, strict=True)`. Because `xfail_strict` is on, a fixture that starts passing fails the run until it is taken off the list. The list is the scoreboard.
- Before the engine exists, `tests/test_runner.py` tests the runner against a scripted engine and policy. A scripted run of a correct fixture passes. Each kind of difference fails with a message that names it.

**Records.** Frozen, slotted, keyword-only dataclasses. A record checks only its own invariants, such as UTC times, non-negative durations, and fields that must appear together. Rules that depend on the graph or on time stay in the engine. Examples are cycles, `Edge.group`, and unknown node ids.

- `Status`, `Importance`, and `Loudness` are `Enum`s whose members compare in declaration order. Worst-of is `max`. They never compare with strings or with each other.
- Values the engine computes but never orders are `Literal` types, not new enums: episode form, resolution, quiet scope, readiness answer, and `blocked_by`. The engine produces them, so ADR 0004's test for fixed types holds. They are listed here because AGENTS.md asks for an ADR for any new closed type.
- `Node.node_id`, not `id`, like `Observation.node_id` and `Check.check_id`. `Node.kind` is optional.
- Episode ids are strings, as in ADR 0017. `recorded`, `impact`, and `absorbed` are `frozenset`s, matching ADR 0024's set comparison.
- `Finding` is one reason on an episode: node, check, status, reason, message, since, `due_at`, and the check's own labels and annotations. `check_id` is `None` only for `dependents_failing`.

**Events.** `EpisodeOpened` and `EpisodeUpdated` carry the whole `Episode` as it now stands. An adapter never has to query the engine to render a message. `EpisodeResolved` carries the final episode, the resolution, and `absorbed_into`, which is present exactly for `absorbed`. `ProbeRequested` names the node. The runner passes probes to the policy like any other event, and the policy may ignore them.

**Deliveries.** `Delivery` is `Notification | ResolutionNotice`.

- `Notification`: episode, recipient, channels, loudness, and `digest`, present exactly for `digest`. It also has `silent`, for an update that replaces a message without alerting again (RFP 7). `record` is never a notification.
- `ResolutionNotice`: episode, recipient, channels, and resolution. It has no loudness, so it cannot page.

**Quiet windows.** `QuietWindow(scope, until, node_id)`, where `scope` is `all`, `node`, or `node_and_dependents`, and `node_id` is present exactly for the scoped forms. A window starts at the `now` of the `quiet` call. In a fixture, a step's `quiet` opens a window at the step's `at`, after `advance` and before `ingest_many`. A restart step can do neither.

**Queries.** `explain(node_id)` returns an `Explanation`: the node's own findings, and `nodes`, its non-pass dependencies, roots first. The node asked about is never in `nodes`. `readiness(node_ids)` returns one `Readiness`: the answer, the responsible `nodes` roots first, and `blocked_by`, present exactly when the answer is `blocked`. Both name nodes as `NodeCondition`: node id, `own`, reasons, and whether the node is watched. `impact`, `coverage`, and `rollup` get their types with the fixtures that exercise them.

**Policy configuration.** `PolicyConfig` has a `timezone`. Quiet hours and digest times are clock times in that zone, and fixtures use UTC. `PolicyContext` has no fields yet. Presence arrives with the fixtures that need it (RFP 13).

**Runner order.** This extends ADR 0024. At each step the runner:

1. calls `engine.advance(at)`
2. on a restart, round-trips both snapshots through JSON, builds and restores a new policy, then builds a new engine, registers the graph, and restores the engine
3. opens the step's quiet window
4. calls `ingest_many`
5. passes each call's events to `policy.handle` in order
6. calls `policy.advance(at)`

The graph is registered at `start`, dependencies first, and registration must emit no events (ADR 0026). The runner tracks open episodes from the events. An update or resolution of an episode that is not open, or an opening of one that already is, is a mismatch. Episode `reasons` compare as a multiset of reason strings. `explain` and readiness names compare in order.

## Options considered

- **Runner with the engine, as ADR 0012 planned.** The interface and the behavior would freeze in one change, and the runner would first be tested by the engine it is meant to judge.
- **Skip fixture tests until the engine exists.** Skipped tests show no progress. Strict xfails show exactly which fixtures pass.
- **Events that carry only ids and changes.** Smaller, but every adapter would have to query the engine or keep its own copy of every episode.
- **One `Delivery` with optional loudness and resolution.** Easy to build something invalid, such as a withdrawal with a loudness. Two types make that impossible.
- **Enums for form, resolution, and the readiness answer.** The library never orders them. `Literal` keeps them closed, lets them type-check, and adds no enum machinery.

## Consequences

- The interface can be reviewed and type-checked before any engine code exists. Changing a record now means changing the runner and its tests, which is cheap. After the engine lands, it is not.
- Every new fixture has to be added to `PENDING` until it passes, and removed once it does.
- A fixture step can now open a quiet window. Scenario 49 is the first fixture that does.
- Fixture step kinds for `register` and `remove` at runtime, `shelve`, and policy context, and the types for `impact`, `coverage`, and `rollup`, are still to come. Each arrives with the first fixture that needs it.
