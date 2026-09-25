# ADR 0006: One cause graph, separate views, edges as records

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

A single device sits in an area, belongs to an integration, routes through a controller, runs on a battery, and serves functions. One hierarchy cannot answer all of those questions. Treating containment as dependency mutes the wrong things.

Multi-parent semantics differ between tools:

- Icinga 2 required every parent until 2.14.0, which added `redundancy_group` after two releases of changed behavior. Icinga 2.16.0 then had to "Prevent worst-case exponential complexity in dependency evaluation."
- Checkmk treats a host as reachable if any parent is up.

## Decision

- One directed acyclic graph of hard dependencies (`depends_on`) is the only structure that may mute. An edge that would close a cycle is rejected when it is added.
- Views are named groupings declared by the adapter, such as location, integration, or label. They feed `rollup` and never mute.
- Functions, meaning automations, occupancy, or "music in the backyard", are ordinary nodes.
- Edges are records: `Edge(to, group=None)`. `group` is reserved for redundancy, and version 1 rejects any other value.
- Evaluation is incremental, in topological order, with memoized results. It never enumerates paths.

## Options considered

- **A single tree.** Cannot represent routing, integration, and area at once.
- **Containment as dependency.** Areas would mute their devices.
- **Edges as bare ids.** Adding redundancy later would break the schema.

## Consequences

- The adapter must declare edges that Home Assistant cannot discover, such as backyard music depending on the backyard Eero node.
- Redundancy needs its own ADR before `group` is accepted.
- Rollups must count a node reached by several paths once.
