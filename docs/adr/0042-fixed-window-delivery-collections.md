# ADR 0042: Collect authorized requests in fixed windows

**Status:** Accepted
**Date:** 2026-10-18

**Extends:** ADRs 0028 and 0039. Applicable attention history now continues through absorption, replacing the former scenario 54 behavior. ADR 0034 continues to govern acknowledgment: absorption does not grant awareness to the new shared episode.

## Context

An adapter can assign unrelated episodes to the same saved notification and destination. Independent routes preserve those assignments, but immediate requests currently bypass batching. Homeostatic's accepted ADRs 0099 and 0102 require a fixed collection window after eligibility and attention history that survives causal reassociation.

## Decision

Add an optional `DeliveryCollections` wrapper around `DeliveryGroups`. Callers supply `CollectionRequest` records containing an authorized notification with resolved channels, an opaque group id encoding saved identity and compatible instructions, an explicit delay, accepted JSON instructions and content, and optional quiet hours with an IANA time-zone name. The library partitions each resolved destination and recipient. Different instruction payloads also partition collections; it never interprets their contents.

The first eligible request fixes the deadline. Later requests cannot extend it. Zero delay and digest requests bypass the wait. At the deadline only current eligible members are requested. Saved quiet hours can postpone a due collection until their next end, with no second delay. Empty collections disappear. New attention after closure starts a new window with its own message identity and exact membership, while updates of already presented members remain silent. `Policy.delivery_eligibility` exposes current authorization and an optional shelf expiry without exposing snapshots. Eligibility checks episode existence, current route recipient scope and acknowledgment; accepted collection timing and targets remain unchanged by configuration edits.

An explicit caller startup hold retains requests without beginning their windows. A per-rule batch override lets collection routes use zero ordinary batching while retaining policy quiet hours. Deferred batch flushing allows all events in one adapter observation cycle to settle before release, without admitting later arrivals to an expired window.

`CollectedGroup` exposes the existing `DeliveryGroup`, accepted instructions and exact contents. `pending()` exposes accepted requests for inspection. Snapshots preserve pending deadlines, membership, content, instructions, destinations and delivered reducer membership. Callers persist these with their outbox and retain stable retry identities. The library reads no clock and performs no I/O.

Policy absorption retains applicable per-route attention history. Notification `replaces` names exact predecessor episodes for membership transfer. Split successors carry the same explicit relationship. Collection replaces predecessor membership without reopening attention: pending openings retain their original deadline, and already requested openings become silent updates. Newly eligible routes still open independently. Acknowledgment remains scoped to the exact presented episodes; absorption does not grant acknowledgment to a new shared episode.

A pending request retains its accepted pause expiry when transferred. This applies to that request; it does not impose a predecessor's whole-episode shelf on a shared successor. Presented message identity and accepted instructions remain independent of a future reminder window. Transfer looks up accepted predecessor destinations even when current destination resolution changes or becomes empty.

Where both predecessor and successor already have an opening for the same route, recipient and accepted destination, absorption retains one opening history. An existing successor's pending plan wins an incompatible predecessor plan, without moving unrelated members between instruction sets. Compatible plans may inherit the earlier deadline. An already presented assignment on either side suppresses a redundant pending opening; genuine pending reminders and independently eligible assignments continue under their own instructions.

## Consequences

Adapters resolve recipients and targets once and render the exact returned members. They own saved identities and compatibility, not attention timers. Existing `DeliveryGroups.apply` remains available for immediate reduction. Collection has a bounded arrival window and cannot promise a single request for arbitrarily late arrivals. Delivery requests remain evidence of a request only.
