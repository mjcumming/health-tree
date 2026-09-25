# ADR 0032: A situation is an edgeless node

**Status:** Proposed
**Date:** 2026-09-25
**Deciders:** Michael Cumming

## Context

ADR 0031 brings situation alerts into scope and leaves detection outside the library. That leaves the question of how a situation sits in the model. It must not behave like equipment:

- A dead door sensor must not mute or clear "front door open". Losing the evidence is not the door closing.
- An open door must not make the sensor, or any function that uses it, look broken.
- Two situations in the same area are two problems. They must never coalesce into one.
- Maintenance on the sensor's controller must not silence a water leak.
- Readiness answers whether the house can do its job. An open garage door does not stop the garage function from working.

ADR 0019 already has a shape that behaves this way: a maintenance node that nothing depends on, tied to its subject by a label or a view, never by an edge.

## Decision

- A situation is a node with no `depends_on`, which no other node depends on.
  - By convention its `kind` is `situation` and its label `category` is `situation`.
  - It is tied to its source by a label, such as `source`, or by a view. Never by an edge.
  - Its importance is the owner's, set on the node.
- Its check is the reporter's (ADR 0031). `ttl` is usually `None`, said explicitly, because a stateful reporter does not repeat an unchanged state. `unknown_hold` is required, as on every check.
- The engine does not change. The existing rules already give the behavior this ADR needs:

  | Rule | Why it holds for a situation |
  | --- | --- |
  | 7 to 9: inhibition | It has no dependency, so nothing mutes it or records it |
  | 13: settle gate | It has no dependency, so nothing gates it |
  | 18: coalescing | That needs a shared direct dependency, and it has none |
  | 7: nothing it mutes | Nothing depends on it |
  | 20: importance | Its impact is empty, so its importance is its own |
  | 22: scoped quiet windows | A window on a controller covers the controller and its dependents, and a situation is not a dependent |
  | 21 and 24: startup grace and restore | They cover it like any node. It opens when grace ends, and a restored episode continues with its id |
  | Readiness | No function depends on it, so readiness never reads it |

- The integration enforces the shape. Its lint rejects an edge to or from a situation node. An edge from a situation to its sensor would let the dead sensor mute it (rule 8). An edge from a function to a situation would make readiness report `blocked` because a door is open.
- Only startup grace covers the whole house. Maintenance uses scoped windows (rule 22), so the integration never offers the `all` scope for maintenance. To quiet one situation, the owner shelves its episode, or opens a quiet window scoped to that node.
- When the reporter turns `unknown`, the episode stays open. Its `fail` reason drops, so it matches no policy rule and is `record` until `unknown_hold` ends: no delivery is made, and the earlier message is not replaced. After the hold, the reason is `stale`. A situation of `high` or `critical` importance then matches the urgent rule and pages again. That is intended: the house can no longer tell whether the door is still open.

## Options considered

- **A fixed node role that the engine reads.** The engine would enforce the edge ban and keep situations out of global windows. That is a new closed type (ADR 0004) for behavior the engine never has to compute: the rules already give it. Revisit if a second consumer cannot enforce the shape, or if a lint proves not to be enough.
- **A separate condition-to-episode adapter with its own lifecycle.** It would copy episode ids, updates, snapshots, and restore, and drift from the engine's rules.
- **A check on the sensor's own node, with `affects_own` false.** Evidence-only checks open no episode. Making them open one would merge the situation with the sensor's health, which ADR 0019 rejects.

## Consequences

- Story 10 and scenarios 61 to 64 pass against the current engine and policy with no change to `src/`. This ADR is a rule for the shape of nodes, not a behavior change in the engine.
- The fixture runner can now check whether a delivery is silent, so story 10 can tell a second page apart from a silent update.
- `coverage` lists a situation check that was never observed or has gone stale. A reporter that stopped working is an evidence gap.
- `rollup` counts a situation in any view group that contains it, as an `own` failure while it holds. The integration keeps situations out of equipment views, or shows them separately.
- The engine cannot tell a situation from a maintenance node, or from any other edgeless node. The policy tells them apart by `category`, like everything else it routes.
