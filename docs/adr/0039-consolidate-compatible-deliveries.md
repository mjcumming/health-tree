# ADR 0039: Consolidate compatible deliveries without merging episodes

**Status:** Accepted
**Date:** 2026-10-14

## Context

Several independent problems can concern the same subject and reach the same recipient under compatible instructions. Sending a separate message for every problem duplicates attention. Inventing dependency edges or merging episodes would also change evidence, recovery and acknowledgment.

## Decision

Add an optional, pure `DeliveryGroups` reducer after the attention policy. The caller explicitly assigns each episode and route to an opaque group id after establishing compatible delivery instructions. Recipient and exact channel tuple partition each group further. The reducer does not infer compatibility from a destination, subject, label or reason.

Apply one batch of deliveries atomically. Each returned `DeliveryGroup` identifies the current delivered members and original changes. A new noisy notification makes the group noisy. Recovery of some members silently updates the surviving message; only an empty group closes it. A member added and resolved within a batch never produces a transient message. A stable key includes group, recipient and channels for transport identity. Moving a member to a different group or destination closes or updates the previous message using its previous channels.

Acknowledgment remains episode-scoped in `Policy`. A message's action carries the exact member episode ids presented to its recipient. Acknowledging them cannot cover a later member. Grouping neither changes policy routes nor bypasses a schedule or shelf: a member is included only after the policy delivers it. The caller may keep existing report presentation outside this reducer.

Snapshot and restore retain membership without producing delivery. Explicit deactivation removes selected route memberships and returns silent message updates; it does not manufacture recovery evidence. The caller persists reducer state and its transport outbox together, and handles delivery retry identities.

## Consequences

Consumers can consolidate messages while retaining separate causes, issue histories, routing and acknowledgment. The adapter remains responsible for compatibility, subject assignment, content and transport. This adds no graph edges and does not supersede independent attention routes or episode lifecycle rules.
