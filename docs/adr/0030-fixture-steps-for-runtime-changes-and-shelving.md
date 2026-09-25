# ADR 0030: Fixture steps for runtime graph changes and shelving

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Extends the runner order that ADRs 0024 and 0027 set out. It does not change either decision.

## Context

Rule 23 lets nodes, edges, and checks change at runtime, and scenario 21 removes a node. Scenario 32 shelves an episode. A fixture could express neither, so scenarios 21 and 32 were covered only by unit tests.

## Decision

- A step may `register` one node, written in the same form as a graph entry. It adds the node or replaces it. Later steps may refer to it, and its edges must name nodes the fixture already knows.
- A step may `remove` one node.
- A step may `shelve` a bound episode `until` a later time. The fixture must have a policy.
- A restart step does none of these.
- At each step the runner calls, in this order:
  1. `engine.advance`
  2. the restart
  3. `register`
  4. `remove`
  5. `quiet`
  6. `ingest_many`
  7. `policy.shelve`
  8. `policy.handle` for every event
  9. `policy.advance`
- The runner keeps the current graph. On a restart it registers that graph, not the one the fixture started with.

## Options considered

- **Unit tests only.** They already exist, but they sit apart from the stories and scenarios that make up the spec (ADR 0012).
- **A general list of engine calls per step.** It would be more flexible, but harder to read beside a story, and it would invite fixtures that test call order rather than behavior.

## Consequences

- Scenario 21 now has a fixture that removes a failed host, registers a replacement, and moves its dependent onto it. Scenario 32 has one that shelves a notification until the shelf ends.
- `policy.shelve`, `engine.register`, and `engine.remove` are part of the runner's protocols.
