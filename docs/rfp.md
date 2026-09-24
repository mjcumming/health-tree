# RFP: Generic health tree

Design of record for this library. A Home Assistant integration is the first adapter, not part of the package. This document is the spec.

Status: draft for review. No implementation until the scenarios in section 8 are accepted.

## Purpose

A house can lose a whole machine, a controller, one device, or a battery, and today nothing says which of those happened. Home Assistant already has the inventory: host, core, add-ons, integrations, devices, and the external machines an integration depends on. It does not have a health layer that can tell a root failure from its symptoms.

This library is that layer, kept generic on purpose. Nodes, checks, and dependencies are the model. Home Assistant is one adapter that fills them in. The core does not know what a battery, an add-on, or Frigate is. The adapter registers a node and the checks that node actually has.

The split is what keeps the design changeable. A new fault is a new check in the adapter. A parent failure mutes the children that depend on it, and it does not rewrite their status. Those two rules are the whole reason for a separate library. Folding them into a Home Assistant integration first would tie the model to one inventory and make the next exception a special case in the core.

## 1. Problem

Operators find out a subsystem is dead when something that depends on it misbehaves. Monitoring either watches every leaf and pages on each one, or watches nothing.

The library answers three questions for any system that can be drawn as dependencies:

- What is true of this node, from its own checks?
- What does the subtree look like?
- Who should be told, once a failed dependency has muted its symptoms?

## 2. Product

A pure Python package with no Home Assistant imports and no I/O of its own.

The adapter, written later, registers nodes, supplies observations, and receives episodes. The first adapter is Home Assistant: config entries, add-ons, devices, entities, and external hosts such as a Frigate machine. A second adapter is not a goal. The boundary exists so the core does not grow Home Assistant branches.

### In scope

- A directed acyclic graph of nodes and hard dependencies.
- Checks registered with the node that owns them.
- Status values `unknown`, `pass`, `warn`, and `fail`.
- Separate `own` status, `summary`, and `attention`.
- Inhibition of notifications along dependencies when `own` is `fail`.
- Episodes: one report per root failure, replaced in place, plus one recovery.
- Holds, a global startup grace, and a rejoin grace.
- An injected clock, so tests do not sleep.

### Out of scope for the first version

- Learned reporting rhythms, predictive battery drain, radio baselines.
- A catalog of device faults (battery, communication error, signal).
- Notification transport, dashboards, repairs, to-do lists, acknowledgements.
- Discovery of nodes. The adapter registers them.
- Monitoring the library's host from inside a dead platform. The adapter places that check outside the process that can die.

## 3. Boundary

| Piece | Owns |
| --- | --- |
| Library | Graph, evaluation, inhibition, episodes, grace, holds |
| Adapter | Which nodes exist, which checks they have, how an observation is produced, where an episode is delivered |
| Check author | What a reason code means for that kind of node |

`kind` is an opaque string chosen by the adapter (`integration`, `device`, `service`, `disk`). The library does not branch on it.

`reason` is an opaque string chosen by the check author (`unreachable`, `low`, `fault`). The library stores it, displays it, and does not interpret it.

Severity is `digest`, `list`, or `page`, set on the node by the adapter. It selects how loud a root episode is. It is not a status.

## 4. Registration, and the failure list

The library has no preset failures for a device.

When the adapter adds a node, it registers that node's checks. A check declares:

- `check_id`
- `affects_own` (default true). False keeps the result as evidence and out of `own`.
- `fail_hold` and `clear_hold`
- `ttl`, after which a missing fresh observation becomes `unknown`

The statement "this device has a battery, and the battery can be low" is the adapter registering a check. It is not a capability profile, a base class, or a list of modes stored in the core.

A catalog of standard device faults inside the library is the complexity to refuse. It forces every new system to translate itself into batteries and radios, and it forces the core to change when a new fault appears. A new fault is a new check in the adapter. The core is unchanged.

What the core does require is that every check return the same shape: status, reason, time, and optional evidence. Two checks on one node produce one `own` status (the worst) and one episode. The episode lists both reasons.

## 5. Data

### Node

- `id`
- `kind`
- `depends_on`: ids of hard dependencies. Adding an edge that would cycle is rejected.
- `severity`
- checks, as registered

Inventory parentage is just the usual `depends_on` edges. An external machine is another edge. The Frigate integration depends on the Frigate host. The host does not depend on Home Assistant.

### Observation

Produced by the adapter, consumed by the library. Immutable.

- `node_id`, `check_id`
- `status`: `unknown`, `pass`, `warn`, or `fail`
- `reason`
- `observed_at`
- `evidence`: optional string

A control state is not an observation. The adapter may use a control state to compute one. The library never sees the switch.

### After evaluation

- `own`: worst status of checks with `affects_own`, considering holds and ttl. No fresh observation within ttl yields `unknown` for that check.
- `summary`: worst of `own` and the `summary` of nodes that list this node as a dependency. Display only.
- `attention`: `silent`, `recorded`, or `notify`.
- `inhibited_by`: the dependency whose `own` is `fail`, if any.

Worst-of order is `fail`, then `warn`, then `unknown`, then `pass`. `unknown` outranks `pass` so a dark check cannot be hidden by a sibling that passed.

## 6. Rules

These are the rules from the health-tree design, restated as library law.

1. A node's `own` status comes only from its own checks.
2. Inhibition reads `own` only. `summary` never inhibits.
3. Only `own == fail` mutes dependents. `warn` and `unknown` mute nobody.
4. Muted nodes keep their `own` status. They are recorded on the ancestor's episode.
5. Sideways nodes do not affect each other.
6. Any one failed hard dependency is enough to mute.
7. When the muting dependency returns to `pass` or `warn`, dependents wait out the rejoin grace. A dependent still `fail` after that opens its own episode.
8. Fail and clear both wait out the check's hold. The notifier has no flap branch.
9. Startup grace is global. During it, attention is `silent` for every node.
10. A checker that cannot run submits `unknown`, not `fail`.
11. Notify on episode transitions. One root node, one episode, one message replaced in place, one recovery when `own` has stayed `pass` or `warn` through the clear hold.
12. Severity chooses digest, list, or page. The library emits the episode either way. The adapter delivers it.

## 7. Reporting

The library yields episode events:

- `opened` with the root node, its reasons, and the recorded descendants
- `updated` when reasons or the descendant list change
- `resolved` when the root's `own` has cleared

It does not send mail, push notifications, or write a to-do list. The Home Assistant adapter maps `page` and `list` onto notification calls, and `digest` onto a scheduled summary. Acknowledgement, if wanted, lives in that adapter.

## 8. Scenarios the library must pass

Written against this house, expressed only with nodes and checks. Names are adapter concerns. The core tests use ids.

1. Host probe `unreachable` / `fail`. Integration that depends on it is `fail`. Devices under the integration are `fail`. One episode, on the host. Integration and devices are recorded, not separate episodes.
2. Same graph, host `pass`, one device check `fault` / `fail` held past `fail_hold`. One episode, on that device.
3. Controller node `fail`. Ten device `fault` observations. One episode, on the controller. Devices recorded.
4. Controller recovers. Three devices still `fault`. They stay recorded through rejoin grace, then each opens an episode.
5. Parent `unknown`, child `fail`. Child episode opens. Unknown does not hide it.
6. Parent `warn`, child `fail`. Child episode opens.
7. Parent `own` is `pass` and `summary` is `fail` only because a child failed. The child is the root. The parent does not mute it.
8. Two checks on one device, `low` / `warn` and `fault` / `fail`. One episode. Both reasons listed. `own` is `fail`.
9. A check with `affects_own` false returns `fail`. `own` stays `pass` if every affecting check passed. The evidence is still stored.
10. Observation older than ttl. That check is `unknown`. A sibling `pass` does not keep the node at `pass`.
11. Startup grace covers a wave of `fail` observations. No episode until grace ends, and only for nodes still `fail`.
12. An edge that would cycle is rejected.
13. Status flips `fail`/`pass` inside `fail_hold`. No episode.

## 9. Home Assistant adapter, later

Not part of this library. Recorded so the boundary stays visible.

- Build nodes from the supervisor host, the core, add-ons, config entries, devices, and selected external hosts.
- Register checks at registration time. Examples for this house, owned by the adapter: host reachability, integration state (`setup_error` as `not_running` / `fail`, `setup_retry` as `degraded` / `warn` until its hold, then `fail`), Insteon communication-error count, battery percentage, MQTT or ESPHome availability for nodes the operator marked.
- Map episodes to notifications. Page for host, broker, and controller failures. List for a single device. Digest for batteries.
- Leave learned silence, Device Sentinel, and a fault catalog out.

## 10. Acceptance

The library is done when section 8 passes without a Home Assistant import, and a new fault can be introduced by registering a check in a test adapter without editing the core.
