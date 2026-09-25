# ADR 0009: Importance flows up the cause graph

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The owner cares about functions and places, not components. A USB coordinator matters because the front-door lock depends on it. Shinken and Alignak gave a root problem the highest business impact among the things it broke.

Severity (how bad a problem is) and importance (how much anyone cares about the thing) are different axes. RFP 0.1 put a digest, list, or page severity on each node. That could not route a battery warning to a digest and a communication failure on the same device to a list.

## Decision

- `Importance` is a closed, ordered type (ADR 0004). It is set on nodes, defaults to `normal`, and is mostly set on functions.
- An episode's importance is the maximum over its anchor and its impact. The impact is every node that depends on the anchor, directly or not.
- Status stays on checks.
- Loudness is decided by the policy from status, importance, labels, deadlines, and age. It is never stored on nodes.

## Options considered

- **Importance of the root only.** A cheap component that breaks a critical function stays quiet.
- **Impact size as importance.** A hundred unimportant sensors would outrank the lock.
- **Severity on nodes (RFP 0.1).** Could not route per problem.

## Consequences

- Infrastructure often inherits high importance. Policy rules should combine importance with status, so a `warn` on a critical path need not page.
- Impact and importance are recomputed when edges change.
