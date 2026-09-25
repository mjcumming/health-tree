# ADR 0033: Register graph changes atomically

**Status:** Accepted
**Date:** 2026-09-25
**Deciders:** Michael Cumming

## Context

An adapter can discover thousands of monitored sources at once. Registering each
node separately validates and evaluates the growing graph repeatedly. The live
Homeostatic pilot exposed this cost during a whole-catalog preview. Replacing
dependencies separately can also reject a valid final graph because an
intermediate graph has a cycle.

## Decision

Add `Engine.register_many(nodes, now)`. Validate the non-empty batch, its unique
node ids, and the resulting graph before mutating any state or advancing time.
Cycles and reserved redundancy groups reject the entire batch. Unmentioned nodes
remain. Forward references to unregistered targets keep their existing meaning.

Apply all replacements together, retain the state of matching check ids, start
new checks unknown, and evaluate once. Return only final-graph events. Existing
nodes retain their ordering; newly added nodes follow input order, with
dependencies evaluated first. `register` delegates to a singleton batch.

Fixtures gain a `register_many` list in the registration position defined by ADR
0030. A step cannot combine it with `register` or restart. Observations remain a
separate call, following registration. This does not change ADR 0024's requirement
to process independently arriving observations without waiting to accumulate them.

## Options considered

- **Repeated single registration.** Repeats graph evaluation and exposes
  intermediate topology.
- **Adapter access to engine internals or snapshots.** Couples the adapter to
  private state and bypasses validation.
- **Replace the entire graph.** Would conflate registration with removal and its
  episode-resolution semantics; not needed for this increment.

## Consequences

Adapters can initialize or update discovered nodes with one graph evaluation.
Single registration keeps its public behavior. Snapshots need no schema change.
The library still evaluates the whole graph per call; runtime scheduling and
inventory construction remain the adapter's responsibility. Scenario 74 covers
atomic rewiring, retained evidence, and restart; API tests cover rejection and
large graphs.
