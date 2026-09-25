# ADR 0005: Status is observed, never rewritten

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

When a parent fails, monitoring systems do one of three things with its children:

- **Rewrite them.** Shinken and Alignak show impacts as UNREACHABLE or UNKNOWN.
- **Freeze them.** A Zabbix dependent trigger does not change state while its master is in PROBLEM.
- **Keep their true state and mute notifications.** In Icinga 2, a host's state comes from its own check, and reachability is a separate flag.

Rewriting loses the truth. Drill-down lies, and after recovery nobody knows what actually failed.

## Decision

- A node's `own` status comes only from its own checks.
- Dependencies set `inhibited_by` and which episode records the node. They never change `own`.
- There is no `attention` enum. `silent`, `recorded`, and `notify` were the 0.1 values. Loudness (`record`, `digest`, `notify`, `urgent`) is a policy decision, not a node field. See ADR 0004 and ADR 0010.
- Views and rollups never change `own` or `inhibited_by`. `rollup` counts `own` status and inhibition: clear, own episode, or recorded on another.

## Options considered

- **Rewrite to unreachable.** Simple to display, but it loses truth and makes recovery ambiguous.
- **Freeze dependents.** Stale truth, and a re-evaluation lag after recovery.

## Consequences

- A UI can show the true state next to "muted by X".
- Children keep their failures after the parent recovers, so rejoin grace is needed (RFP rule 19).
- Each node carries `own` and `inhibited_by`. Delivery is not one of those fields.
