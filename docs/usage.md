# Using health-tree

How an adapter drives the engine and the attention policy. The [README](../README.md) has the overview and a runnable example; the [RFP](rfp.md) is the full design.

## Registering a graph

Atomic graph registration is available since 0.3.0.

Use `engine.register_many(nodes, now)` when an adapter discovers multiple nodes
at once. The batch adds or replaces those nodes, keeps unchanged nodes and
retained check state, validates the final graph, and evaluates once. Empty
batches, duplicate node ids, cycles, and reserved redundancy groups are rejected
without changing state or time. `register(node, now)` has the same behavior for
one node. Apply initial evidence separately with `ingest_many`.

Only register monitored capabilities and the dependencies needed to describe
them. Healthy monitored nodes belong in the graph so they can report a later
failure. An unmonitored requirement belongs too: its missing evidence must remain
visible to readiness and coverage. An adapter's wider inventory need not be a
health graph. See [ADR 0033](adr/0033-atomic-graph-registration.md).

## Attention integration

Use `Policy.handle` for engine events and `advance` for due work. Deliveries carry
opaque recipients/channels and an output `cause` (`open`, `update`, `remind`,
`escalate`, `activate`, or `digest`). The adapter renders and transports them.
`explain(episode_id)` reads the evaluated rule, recipients and pending times without
advancing time. Snapshot data stays an opaque persistence contract.

Call `activate(now, context)` only when the owner starts attention afresh, such as
enabling notifications after record-only monitoring. It preserves episode identity
and age, restarts escalation, and returns or schedules initial requests subject to
batching, quiet hours and shelves. Reminders begin with each recipient's actual
request. An adapter can combine activation requests into summaries. Ordinary
restart uses `restore`, which preserves attention clocks and reads policy schemas
1, 2, or 3; new snapshots use schema 3. Scenarios 72 and 73 cover activation and
reminder holds. Older policy snapshots restore without an acknowledgment.

## Acknowledgment and temporary controls

Acknowledgment means someone has seen an open problem. It does not change checks,
readiness, episode identity, or the evidence required for recovery.

- `policy.acknowledge(episode_id, now, actor_id="owner")` records the first UTC
  time and optional opaque actor id, shared across recipients. Repeating the
  request preserves that first record. `policy.acknowledgment(episode_id)` reads it.
- A rule with `require_acknowledgment=True` stops its pending notifications,
  reminders, digests, and age escalation after acknowledgment. Other rules keep
  their configured behavior; silent updates and recovery still reach existing
  recipients. Restore and activation preserve awareness. A new episode starts
  unacknowledged.
- `policy.unshelve(episode_id, now, context)` ends a shelf early and reevaluates
  due attention under batching, quiet hours, and acknowledgment rules.
- `engine.cancel_quiet(window, now)` removes one matching quiet window. Other
  overlapping windows remain effective; observed health stays unchanged.

The adapter authorizes and persists these actions. Transport publication, phone
receipt, and dismissal never imply human acknowledgment. See [ADR 0034](adr/0034-acknowledgment-and-control-cancellation.md)
and executable scenarios 76–78 for restart, cancellation, and recovery behavior.
