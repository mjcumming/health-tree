# ADR 0037: Evaluate independent attention routes for the same episode

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Michael Cumming

**Partially supersedes:** ADR 0020's single winning decision for an episode. Its matching rules continue to apply within each route.

## Context

A consumer may request immediate phone notification and a recurring morning report for the same problem. Ordered rules currently select only one of those behaviors. Separate adapter timers would duplicate the library's scheduling and attention controls.

## Decision

Add an opaque string `route` to `Rule`, `Notification` and `ResolutionNotice`, defaulting to the empty string. Rules in different routes run independently. Within each route, the first matching rule for each reason and the loudest result determine delivery as before. Route order follows first appearance in the configuration. The library never interprets route ids.

Batching, reminders, escalation, recipients and scheduled reports belong to a route. Acknowledgment and shelving belong to the episode and apply to every route. Acknowledgment suppresses only routes whose winning rule requires it. Other scheduled reports continue while the problem is open. Resolution withdraws every route's previously requested messages.

Delivery identity includes the route. Explanations retain an aggregate overview and expose each route's decision; reports identify their route. Snapshots preserve separate attention state by stable route id. Legacy configurations and snapshots retain their existing behavior. Restoring a changed set of routes preserves episode awareness and shelves, but new routes start with no delivery history; consumers call `activate` when explicitly applying changed reporting settings.

Activation accepts an optional collection of route ids so a consumer can restart attention only for changed routes. Omitting the selection preserves full activation. Unselected routes keep delivery history and clocks; unknown ids have no effect.

## Options considered

- Let every matching rule send: this loses ordered exceptions within a route.
- Schedule each report in the adapter: this duplicates quiet hours, shelving, acknowledgment and restart behavior.

## Consequences

Consumers can combine independently scheduled requests without changing episode identity. Consumers must include the route in their own message identity to avoid overwriting another schedule's request. Existing consumers using only the default route need no changes.
