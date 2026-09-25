# ADR 0025: Readiness preserves every unwatched dependency branch

**Status:** Proposed
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Supersedes ADR 0023 when accepted, retaining its observed-status and stale-data rules.

## Context

Looking through a node without checks works when that node represents a function whose dependencies are watched. It fails when a branch ends at an unwatched controller. A passing sibling must not make that missing evidence disappear.

## Decision

- Readiness uses the function's own affecting checks and all its transitive dependencies. Episodes, inhibition, quiet windows, and shelving do not change it.
- Checks with `affects_own: false` are evidence only. For readiness, having only such checks is equivalent to having no checks.
- A node with no affecting checks and with dependencies is looked through. Its own `unknown` is ignored, but each dependency branch is evaluated.
- A terminal node with no affecting checks contributes `unknown`. This applies even when another branch passes or the function's own check passes.
- An observed `pass` contributes `ready`, `warn` contributes `degraded`, `fail` contributes `blocked`, and `unknown` contributes `unknown`, stale or not. Stale nodes are named with reason `stale`.
- The existing precedence remains `blocked`, `degraded`, `unknown`, `ready`. A warning winning that ordering does not prove an unknown branch works. The responsible nodes remain visible, including unknown branches.
- Names are ordered roots first. If the entire requested function and its dependency graph lack affecting checks, name all the unwatched nodes, retaining scenario 51. In a partially watched graph, name unwatched terminal requirements rather than the intermediate nodes looked through.
- A blocked answer identifies whether the function's own checks fail or its dependencies do. An automation can fall back on any answer other than `ready`.

## Options considered

- **Ignore every node without checks.** Allows a partially watched graph to claim readiness.
- **Treat all intermediate nodes without checks as unknown.** Prevents a declared function from becoming ready even when all of its actual requirements pass.
- **Use coverage only.** Leaves readiness giving reassurance despite a known gap in required evidence.

## Consequences

- Scenario 55 covers mixed coverage, a passing function with an unwatched dependency, and evidence-only terminal nodes.
- No new status, closed type, or graph edge kind is introduced.
- Accepting this ADR changes ADR 0023's status to superseded; its historical text remains unchanged.
