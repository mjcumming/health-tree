# RFP: Generic health tree

Design of record for this library. A Home Assistant integration is the first consumer. It lives in its own repository and is not part of this package. This document is the spec.

| | |
| --- | --- |
| Version | 0.5 |
| Date | 2026-09-24 |
| Status | Draft for review, with ADRs 0024 to 0029 accepted. A first engine and policy pass every fixture. Nothing is released until the types, stories, and scenarios are accepted. |
| Decisions | [docs/adr](adr/README.md) |
| Changes from 0.4 | Section 17 |

## Purpose

A house can lose a whole machine, a controller, one device, a battery, or a login, or fail to carry out a command, and today nothing says which of those happened. The owner finds out when the lights stop following motion, when the music will not play with guests over, or when Home Assistant stops because the disk filled.

Home Assistant already has the inventory: host, core, add-ons, integrations, devices, automations, and the external machines an integration depends on. It does not have a health layer that can tell a root failure from its symptoms, say what the failure takes down, and decide who hears about it and when.

This library is that layer, kept generic on purpose. Nodes, checks, dependencies, episodes, and an attention policy are the model. Home Assistant is one integration that fills them in. The core does not know what a battery, an add-on, or Frigate is. The integration registers a node and the checks that node actually has.

The split is what keeps the design changeable. A new fault is a new check in the catalog. A new notification preference is configuration. A parent failure mutes the children that depend on it, and it does not rewrite their status. Folding this into a Home Assistant integration first would tie the model to one inventory and make the next exception a special case in the core.

## 1. Problem

Operators find out a subsystem is dead when something that depends on it misbehaves. Monitoring either watches every leaf and pages on each one, or watches nothing.

Failures show up in five shapes. Each needs a different kind of check.

| Shape | Example | Check that catches it |
| --- | --- | --- |
| Loud | An integration fails to load | State |
| Quiet | A sensor stops reporting | Freshness: `ttl`, then `stale` |
| Plausible but wrong | A person sensor reads "clear" because the detector hung | Liveness of the signal path |
| Latent | A login expired; nobody notices until the music is wanted | State, evaluated when it breaks, not when it is used |
| Gradual | A disk fills; a battery drains | Capacity, with a projected deadline |

Two kinds of trouble are not component failures:

- An operation that did not do what it was told. The garage door was told to close and is still open.
- Maintenance debt with no symptom. Ten months of updates waiting on the AI box.

The library answers these questions for any system that can be drawn as dependencies:

- What is true of this node, from its own checks?
- What broke first, and what does it take down?
- Who should be told, how loudly, and when?
- Why is this function not working? Is this set of functions ready?
- What is not being watched at all?

## 2. Product

A pure Python 3.14 package with no Home Assistant imports, no I/O, no threads, no event loop, and no runtime dependencies. Every call that depends on time takes `now`. See ADR 0002, ADR 0003, and ADR 0013.

The library has three parts:

| Part | Module | Owns |
| --- | --- | --- |
| Engine | `health_tree` | Graph, checks, evaluation, inhibition, episodes, importance, quiet windows, snapshots, queries |
| Attention policy | `health_tree.policy` | Rules, recipients, loudness, quiet hours, digests, reminders, escalation, shelving |
| Conventions | `health_tree.conventions` | Standard reasons, categories, label keys, and annotation keys. Names and documentation only, never behavior |

The Home Assistant integration lives in its own repository, the same split as home-topology and Topomation. It has two parts:

| Part | Owns |
| --- | --- |
| Catalog | Problem definitions as data: which nodes get which checks, thresholds, remedies, links |
| Adapter | Discovery, observation producers, delivery, configuration, storage of snapshots |

A watchdog outside Home Assistant is a required part of any deployment. The library cannot report the death of the process it runs in.

### In scope

The house failed to do its job, is about to, or is accumulating maintenance risk. That covers components, operations, and maintenance.

- A directed acyclic graph of nodes and hard dependencies. Functions are nodes.
- Checks registered with the node that owns them.
- Status values `unknown`, `pass`, `warn`, and `fail`.
- Importance values `low`, `normal`, `high`, and `critical`, flowing up the graph.
- Separate `own` status and `inhibited_by`, the set of roots that mute a node. Loudness is not a status.
- Episodes: one per root, updated in place, absorbed when a root turns up late, coalesced when many siblings fail together, and one recovery.
- Holds, `ttl`, stale detection, a settle gate, startup grace, rejoin grace, and scoped quiet windows.
- Views: named groupings for summaries. They never mute.
- Queries: explain, impact, readiness, coverage, rollup.
- The attention policy, as a pure module configured with data.
- Snapshot and restore of all state.

### Out of scope for the first version

- Learned reporting rhythms, anomaly detection, learned baselines.
- Predictions inside the library. A check may report a projected deadline. The library does not compute one.
- Redundancy groups. The edge carries the field, and version 1 rejects it.
- Situation alerts: the garage open at night, a water leak, a door unlocked while away. The world is in a state the owner does not like; the house has not failed. These are security and safety alerting. They may share the policy later.
- Automatic remediation. An episode may carry a suggested action. The library never runs one.
- Notification transport, dashboards, and discovery. These belong to the integration.

## 3. Model

The model is four jobs, not one hierarchy. One tree cannot answer all four questions, because a single device sits in an area, belongs to an integration, routes through a controller, runs on a battery, and serves a function.

| Job | Question | Shape | Mutes? |
| --- | --- | --- | --- |
| Cause | What broke what? | One graph of hard dependencies | Yes. The only structure that may |
| Views | How do I read the house? | Named groupings, as many as needed | Never |
| Problem definitions | What can go wrong with this thing? | Checks attached by the catalog | No |
| Attention | What interrupts whom, how, and when? | Policy rules | Decides delivery, never status |

Two flows run over the cause graph:

- Cause flows down. A failed node mutes the dependents that fail with it.
- Importance flows up. An episode is as important as the most important thing its root takes down.

Nothing gets quieter because of where it sits in a tree. It gets quieter because a known cause explains it, or because the attention policy says so.

### What a node is

A node is one capability: one thing that either works or does not, as its dependents see it. A check belongs on a node only if its `fail` means that node's dependents cannot do their job. See ADR 0019.

- If a check's failure would not stop every dependent, it belongs on another node. Maintenance debt, such as `update_pending` or `backup_overdue`, gets its own node that nothing depends on. That node has its own episode and its own recovery, and it mutes nobody.
- If dependents need different subsets of a node's checks, the node is several capabilities. Frigate detection and Frigate recording are two nodes, so a full recording disk does not take down motion lighting.
- A leading indicator of the same capability stays on it. `battery_low` only ever reports `warn`, and the dead battery shows up as the same node going `stale`.
- A maintenance node is tied to its subject by a view or a label, never by an edge.

The engine cannot apply these tests, because it never reads labels. The catalog applies them, and the integration checks them with a lint.

## 4. Boundary

| Piece | Owns |
| --- | --- |
| Engine | Graph, evaluation, inhibition, episodes, importance, windows, snapshots, queries |
| Policy | Who hears what, how loudly, and when |
| Conventions | Shared names, never behavior |
| Catalog (integration) | Which checks exist, which node each lives on (section 3), what their reasons mean, remedies and links |
| Adapter (integration) | Which nodes exist, how observations are produced, where deliveries go |
| Check author | How a check decides its status and reason |

A type is fixed only when the engine or the policy compares, orders, or escalates it. Everything the library only carries is an open string with conventions. See ADR 0004.

## 5. Types

### Fixed

| Type | Order | Why it is fixed |
| --- | --- | --- |
| `Status` | `pass` < `unknown` < `warn` < `fail` | `own` is the worst of a node's checks |
| `Importance` | `low` < `normal` < `high` < `critical` | An episode takes the maximum over its impact |
| `Loudness` | `record` < `digest` < `notify` < `urgent` | Quiet hours lower it; escalation raises it |

Worst-of order is `fail`, then `warn`, then `unknown`, then `pass`. `unknown` outranks `pass` so a dark check cannot be hidden by a sibling that passed.

"Warning" and "error" are not types. They are statuses of one problem. `battery_low` is `warn` at 20 percent. The same sensor going quiet is `fail` or `stale`.

### Open, with conventions

| Field | Examples | Where the vocabulary lives |
| --- | --- | --- |
| Node `kind` | `host`, `service`, `integration`, `device`, `function` | Integration |
| Observation `reason` | `unreachable`, `auth_required`, `battery_low`, `capacity_low`, `update_pending`, `command_failed` | `health_tree.conventions`, extended by the catalog |
| Label `category` | `fault`, `maintenance`, `operation` | Conventions |
| Label `actionable_by` | `self`, `human` | Conventions |
| Other labels | `area`, `site`, `integration` | Integration |
| Annotations | `remedy`, `link`, `summary` | Catalog |
| Recipient and channel ids | `michael`, `phone` | Configuration |

The library never branches on `kind`, `reason`, labels, or annotations. The engine produces two reasons of its own: `stale` and `dependents_failing`.

### Records

Records are immutable. Times are timezone-aware UTC. Durations are `timedelta`.

**Node**

- `id`
- `kind`
- `depends_on`: edges to hard dependencies. An edge that would close a cycle is rejected.
- `importance`: default `normal`
- `labels`
- checks, as registered

**Edge**

- `to`: the dependency's id
- `group`: redundancy group. Reserved. Version 1 rejects any value but none.

**Check**

- `check_id`
- `affects_own` (default true). False keeps the result as evidence and out of `own`.
- `raise_hold`: how long a worsening must persist before it takes effect
- `clear_hold`: how long `pass` must persist before a clear takes effect
- `ttl`: after this, a check with no fresh observation is `unknown`. `None`, said explicitly, disables expiry of an observation; it does not disable `unknown_hold` for a check that has never reported or reports `unknown`
- `unknown_hold`: how long `unknown` may last before a `stale` episode opens. Always a duration, because a checker that cannot run also reports `unknown`
- `labels`, `annotations`

**Observation**, produced by the adapter, consumed by the library:

- `node_id`, `check_id`
- `status`, `reason`, `observed_at`
- `message`: optional human text for this occurrence
- `evidence`: optional mapping of JSON-compatible values, such as `{"battery_pct": 9}`
- `due_at`: optional time at which this becomes a failure, such as a token expiry or a projected full disk

A control state is not an observation. The adapter may use a control state to compute one. The library never sees the switch.

**Episode**

- `episode_id`: a UUIDv7, assigned when the episode opens and built from `now`, never from the system clock. The timestamp is `now`, the counter bits keep ids opened in the same millisecond in the order they opened, and the rest is random. Opaque, time-sortable, and stable across updates and restarts. Fixtures assert the anchor, the onset, and that the id does not change. They do not predict the bits. See ADR 0017.
- `form`: `root`, or `group` for coalesced members whose anchor has no episode of its own
- `anchor`: the root node, or the shared dependency of a group
- `status`: the worst over the anchor's `own` and the `own` of any coalesced members
- `reasons`: each `warn` or `fail` check of the anchor and of any coalesced members, plus each check whose `unknown_hold` has elapsed, with status, reason, message, since, `due_at`, and the check's own labels and annotations. An unknown check contributes reason `stale` only after its hold; before that it still affects `own`, readiness, and coverage. Coalescing adds `dependents_failing`
- `recorded`: failing nodes muted by this episode, and coalesced members
- `impact`: every node that depends on the anchor, directly or not
- `importance`: the maximum over the anchor and its impact
- `labels`, `annotations`: the anchor node's. A check's labels stay on its reason and are never merged (ADR 0020)
- `absorbed`: ids of episodes folded into this one
- `opened_at`, `updated_at`, and `due_at`, the earliest over its reasons

**Events**, emitted by the engine:

- `EpisodeOpened`, `EpisodeUpdated`, and `EpisodeResolved`. A resolution is `cleared`, `removed`, or `absorbed`.
- `ProbeRequested`: the engine wants a fresh observation of a node. The adapter decides whether and how.

## 6. Rules

These are the rules from the health-tree design, restated as library law.

### Status

1. A node's `own` status comes only from its own checks.
2. `own` is the worst of the checks with `affects_own`, after holds and `ttl`. A node with no such checks is `unknown`. It never opens an episode for that, and `coverage` lists it.
3. A worsening waits out the check's `raise_hold`. A clear to `pass` waits out its `clear_hold`. An improvement from `fail` to `warn` takes effect at once. The engine has no flap branch.
4. A check with no fresh observation within `ttl` is `unknown`.
5. A checker that cannot run submits `unknown`, not `fail`.

A registered check starts `unknown`, with its `unknown_hold` measured from registration, even when `ttl` is `None`. The first `pass` takes effect immediately if the check has never reported `warn` or `fail` and has not become stale; clearing a known problem still requires `clear_hold`. An adapter registers a command check when it can establish its initial condition. A `pass` meaning no command is outstanding is valid only for that command-verification capability; it is not evidence that the device is reachable. There is no implicit passing or inactive state. See ADR 0026.

### Inhibition

6. Inhibition reads `own` only. Views never inhibit.
7. Only `own == fail` mutes dependents. `warn` and `unknown` mute nobody.
8. Any one failed hard dependency is enough to mute.
9. A muted node keeps its `own` status. It is recorded on the episode of every root that mutes it, unless it already has an episode of its own (rule 17). `inhibited_by` is that set of roots, found transitively. For a host, an integration under it, and a device under that, the device is recorded on the host's episode.
10. Sideways nodes do not affect each other.
11. Inhibition stops new episodes from opening. It never closes an episode that was already open for an independent cause.

### Episodes

12. An episode opens when a node's `own` is `warn` or `fail` and the node is not muted, not gated, not coalesced onto another episode (rule 18), and not inside a quiet window. One also opens, with reason `stale`, when a check has been `unknown` for longer than its `unknown_hold`.
13. Settle gate. A node cannot open an episode while any hard dependency is in doubt: a worsening is inside its `raise_hold`, its `own` is `unknown`, or it is gated itself. A dependency that is `pass` or `warn` on observations within `ttl` is not in doubt, however long ago it last reported. A dependency with no checks never gates. The gate lasts at most `settle` from the node's onset. While gated, the engine emits `ProbeRequested` once for each dependency in doubt. A parent confirmed after the child's episode opened is handled by absorption (rule 16). See ADR 0022.
14. One root, one episode, updated in place. A change to reasons, recorded nodes, impact, importance, or `due_at` is an `updated` event.
15. A `root` episode resolves when its anchor's `own` has stayed `pass` through `clear_hold` and it holds no coalesced members. If nodes it recorded as muted still fail when the anchor clears, the episode stays open and holds them through their rejoin grace (rule 19), so there is no false all-clear. Held nodes that recover leave. When the grace ends, if `coalesce_count` or more still fail, they become the episode's members (rule 18). Otherwise the episode resolves and each still-failing node opens its own episode. A `group` episode resolves by its members (rule 18), never by its anchor. `fail` to `warn` is an update, not a recovery.
16. Absorption. When a root's episode opens, an open episode on a node that depends on it resolves as `absorbed` if that node's onset is no more than `settle` before the root's onset. The node is then recorded on the root's episode.
17. An episode whose onset is earlier than that stays open, and its node is not recorded on the root's episode. Two problems, two episodes. When the root recovers, that episode continues, and nothing opens twice.
18. Coalescing. When `coalesce_count` or more episodes would open within `coalesce_window` on nodes that share a direct hard dependency, those nodes are coalesced onto one episode anchored on that dependency, with reason `dependents_failing`. The anchor's `own` does not change. Stragglers left after a rejoin coalesce the same way. See ADR 0021.
    - One anchor, one episode. If the anchor already has an open episode, the members are recorded on it and the reason is added. Otherwise a `group` episode opens.
    - Episodes from that set that are already open are absorbed into it.
    - A direct dependent of the anchor that fails while the episode holds coalesced members joins it, and the episode is updated.
    - A member whose `own` has stayed `pass` through `clear_hold`, or that was removed, leaves, and the episode is updated.
    - When fewer than `coalesce_count` members still fail, `dependents_failing` is dropped. A `group` episode resolves as `cleared`. A `root` episode continues on its anchor. The remaining members wait out `rejoin_grace` as after a rejoin (rule 19), and those still failing then open their own episodes.
    - When a group's anchor opens its own episode, the group resolves as `absorbed`, and its members are recorded on the anchor's episode.
19. Rejoin grace. When a muting dependency returns to `pass` or `warn`, its dependents wait out `rejoin_grace` before they may open episodes. Their silence during the outage proves nothing, so each dependent check that is `unknown` starts over: its `stale` episode waits `ttl` plus `unknown_hold` from the rejoin, or `unknown_hold` alone when `ttl` is `None`.
20. An episode's importance is the maximum importance over its anchor and its impact.

### Windows

A quiet window and quiet hours are different clocks.

- A quiet window is engine state. While one covers a node, no episode opens there. Startup grace and maintenance use windows.
- Quiet hours belong to a recipient in the policy. An episode still opens. `notify` waits until they end. `urgent` is sent through them.

21. Startup grace is a global quiet window at start and after restore. During a quiet window, no episode opens in its scope. When the window ends, nodes that still fail open episodes then.
22. A quiet window covers everything, one node, or one node and its dependents. Maintenance uses the scoped form.

### Graph and state

23. An edge that would close a cycle is rejected. Nodes, edges, and checks can be added, removed, or changed at runtime. A removed node's open episode resolves as `removed`. Dependents it muted wait out `rejoin_grace`.
24. `snapshot()` returns all state as JSON-compatible data with a schema version. `restore()` runs after the graph is registered. Episodes whose anchor no longer exists resolve as `removed`. Other episodes keep their ids. A restored episode whose anchor still fails continues without a new `opened` event.
25. The engine emits events and answers queries. It never sends, stores, sleeps, or reads a clock. Its only input beyond its calls is the random part of episode ids, and `Engine` accepts an id factory so tests can remove even that.

## 7. Attention policy

The policy turns engine events into deliveries. It is pure, like the engine. It takes events, `now`, and context such as who is present where, and returns decisions. The adapter carries them out. See ADR 0010.

Configuration is data with a fixed shape:

- Recipients, each with channels (opaque ids), quiet hours, and optional sites. A recipient may be dynamic, such as whoever is home, resolved from context at send time.
- Digests, each with a schedule and a recipient.
- Rules, in order. They are matched once for each reason of an episode, and the first match wins for that reason. A reason is matched on its own status, reason, `due_within`, category, and labels (its check's labels laid over the anchor node's), and on the episode's importance and age. A rule sets loudness, recipients, digest, reminder interval, and escalation after an age. The episode takes the loudest result over its reasons, with the rest of the rule that produced it. On a tie, the earlier rule wins. See ADR 0020.

Loudness decides delivery:

| Loudness | Delivery |
| --- | --- |
| `record` | Stored, never sent |
| `digest` | Added to the recipient's next digest |
| `notify` | Sent now, or when the recipient's quiet hours end |
| `urgent` | Sent now, through quiet hours |

Delivery rules:

- Rules are matched again when an episode changes, and when its age or `due_at` crosses a threshold that some rule names. Those times feed `policy.next_deadline()`. A new match that raises loudness makes noise. One that lowers it never does.
- A new `notify` delivery waits `batch` so absorption and coalescing land first. `urgent` does not wait.
- An update makes noise only when loudness rises. Otherwise the adapter replaces the message silently.
- A resolution goes, silently, to whoever received the opening.
- A resolution delivery names the episode, recipient, and resolution (`cleared`, `removed`, or `absorbed`). It has no loudness or digest field: it silently updates or withdraws the existing message, and never pages again.
- An episode resolved before it was delivered is dropped from pending deliveries.
- An unresolved episode is reminded at its rule's interval and rises one level after its rule's age.
- Shelving is an operator action: `shelve(episode_id, until)` holds deliveries for one episode. Quiet windows are different. They stop episodes from opening at all.

The same ideas, as configuration in the integration:

```yaml
recipients:
  michael:
    channels: [phone]
    quiet_hours: "22:30-07:00"
  whoever_is_home:
    channels: [phone, kitchen_speaker]
digests:
  morning: {at: "08:00", to: michael}
rules:
  - match: {category: operation, importance: [high, critical]}
    loudness: urgent
    to: whoever_is_home
  - match: {status: warn, due_within: 24h}
    loudness: notify
    to: michael
  - match: {category: maintenance}
    loudness: digest
    digest: morning
    remind_every: 7d
    escalate_after: 30d
  - match: {status: [fail, unknown], importance: [high, critical]}
    loudness: urgent
    to: michael
  - match: {status: fail}
    loudness: notify
    to: michael
  - match: {}
    loudness: digest
    digest: morning
```

Within each reason the first match wins, so order carries meaning:

- The maintenance rule sits above the urgent rule. A dead battery never pages at night, whatever it takes down.
- `due_within` is limited to `warn`. A failure with a deadline still reaches the urgent rule.
- A reason is `unknown` only when it is stale. `[fail, unknown]` pages when a critical sensor goes quiet.
- Each reason is matched on its own, and the loudest result wins. A failed command on a lock whose battery is low still pages, although the maintenance rule matches the battery reason first.

## 8. Interface and queries

The engine and the policy are state machines with no I/O (ADR 0003). The names below are the shape of the interface, not final signatures.

The library requires every duration it uses. It does not fill in a missing one (ADR 0018). `settle`, `rejoin_grace`, startup grace, `coalesce_count`, and `coalesce_window` are engine settings. `batch` is policy configuration. `raise_hold`, `clear_hold`, `ttl`, and `unknown_hold` are fields on every check, set per check by the catalog. `ttl` may be `None`, said explicitly, to disable observation expiry; an unknown check still uses `unknown_hold` (ADR 0026). The integration supplies all of them, and its UI is where the owner changes them. Fixtures in this repository pass the numbers they need. Those numbers are test input, not product defaults.

```python
engine = Engine(settings, new_id=None)          # required durations; optional id factory (ADR 0017)
engine.register(node, now) -> list[Event]       # add or replace a node and its checks
engine.remove(node_id, now) -> list[Event]
engine.ingest(observation, now) -> list[Event]
engine.ingest_many(observations, now) -> list[Event]  # one atomic observation batch
engine.quiet(window, now) -> list[Event]        # scoped quiet window
engine.advance(now) -> list[Event]              # holds, ttl, gates, grace, windows
engine.next_deadline() -> datetime | None       # the adapter schedules one timer
engine.snapshot() -> dict
engine.restore(state, now) -> list[Event]

policy = Policy(config)
policy.handle(event, now, context) -> list[Delivery]
policy.advance(now, context) -> list[Delivery]  # digests, reminders, ends of quiet hours
policy.shelve(episode_id, until, now) -> list[Delivery]
policy.next_deadline() -> datetime | None
policy.snapshot() -> dict
policy.restore(state, now) -> None
```

`ingest_many` validates a non-empty batch before applying any of it, rejects repeated `(node_id, check_id)` pairs, then applies all observations and evaluates once. `ingest` is equivalent to a one-observation batch. The batch's intermediate states emit no events. Each affected episode emits only its final opening, update, or resolution for that call; one `advance` likewise evaluates all deadlines due at `now` together. Events returned by an earlier call remain part of the history. Separate arrivals may therefore open child episodes that a later call absorbs. The adapter must not wait to accumulate unrelated arrivals into a batch. See ADR 0024.

In fixtures, a step's `ingest` list is one call to `ingest_many`, with `observed_at` equal to the step's `at`. The runner first calls `engine.advance(at)`, then applies the step, and keeps the complete events from both calls. It feeds those events to the policy in order before calling `policy.advance(at, context)`. A batch cannot erase an event from the preceding `advance`. A step may also open a quiet window, after `advance` and before the batch. ADR 0027 gives the full order and the record shapes. Fixtures with staggered steps exercise separate arrivals, including any notifications already delivered.

Queries are read-only:

| Query | Answers |
| --- | --- |
| `explain(node_id)` | Why is this node or function not working? Its non-pass checks, then every non-pass node it depends on, roots first |
| `impact(node_id)` | What does this node take down? Its dependents, with importance |
| `readiness(node_ids)` | Can these functions perform as required, per IEC 60050-192? It reads `own` status only: episodes, muting, quiet windows, and shelving do not change the answer, and checks with `affects_own` false do not count. It considers each function's own affecting checks and every node the function depends on, directly or not. `ready` when all required evidence is `pass`. `degraded` when one is `warn`. `blocked` when one is `fail`. `unknown` when one is `unknown`, stale or not: the library cannot tell, and does not guess. A stale node is named with reason `stale`. A node with no affecting checks and with dependencies is looked through; its own `unknown` does not count, but every branch beneath it still does. A node with no affecting checks and no dependencies is an unwatched terminal requirement and contributes `unknown`, even if another branch or the function's own checks pass. When the function and everything beneath it lack affecting checks, the answer names all those unwatched nodes. The worst answer wins, in the order `blocked`, `degraded`, `unknown`, `ready`; a known warning does not establish that an unknown branch works. Only causes are named, roots first. A node whose state a failed dependency explains is left out, because its own hardware may be fine: when the Eero node is down, the speakers behind it are not named. `explain` shows the whole chain. A blocked function says whether its own checks fail or a dependency does, which IEV 192-02-23 calls an externally disabled state. See ADR 0025, which supersedes ADR 0023. |
| `coverage()` | What is not watched? Nodes with no checks, checks never observed, checks stale |
| `rollup(view, group)` | Counts by `own` status and inhibition for one group of one view: clear, own episode, or recorded on another. Each node is counted once |

Views are named groupings that the adapter declares, such as location, integration, or label. They feed `rollup` and nothing else.

### Query contracts

Queries read the state from the last engine call. They never advance time, emit events, change deadlines, or modify snapshots. Unknown node ids raise `KeyError`. Results use immutable records from `health_tree.types`. ADR 0029 records the public shapes and view boundary.

- `impact(node_id) -> Impact` returns the requested `node_id`, `nodes` as a tuple of `ImpactNode(node_id, importance)`, and `importance`, the maximum over the requested node and its dependents. Each registered transitive dependent appears once, dependencies first with registration order breaking ties, excluding the requested node. This is potential impact, regardless of observed status or episodes. Missing edge targets follow ADR 0028: they do not participate until registered.
- `coverage() -> Coverage` returns `no_checks` (node ids), `never_observed` (check references), and `stale` (check references). A `CheckReference` has `node_id` and `check_id`. Nodes are in dependency order and checks in registration order. All registered checks count, including evidence-only checks. `no_checks` means literally no checks, not no affecting checks; readiness still treats an evidence-only terminal node as unwatched. An explicit `unknown` report counts as observed. `stale` means effective `unknown` whose current unknown hold has elapsed, including rejoin timing. Expiry alone is not yet stale. Never-observed checks can also be stale, so the lists may overlap. Quiet windows and inhibition do not hide gaps. An empty engine returns empty lists.
- `rollup(view, group) -> Rollup` takes an adapter-owned `View(view_id, groups)`, where `groups` maps group names to sets of node ids. The record copies and freezes membership. Pass the view directly; there is no engine view registry and views are not in engine snapshots. Adapters restore their view configuration alongside their graph configuration. Groups may overlap; membership never adds dependencies or changes importance, readiness, episodes, or policy. An unknown group or an unregistered member of the selected group raises `KeyError`, rather than silently shrinking the count. Unselected groups are not validated against the graph. Empty groups are valid.
- A `Rollup` identifies `view_id` and `group`, with `counts`, a tuple of `RollupCounts` for all four statuses in `Status` order. Each row has `own`, `clear`, `own_episode`, and `recorded`. Classify each selected node once: an anchor of any open episode (including a group) is `own_episode`; otherwise membership in any open episode's `recorded` set is `recorded`; otherwise it is `clear`. Anchoring takes precedence over recording, and recording under multiple roots counts once. `clear` means no open episode membership, not healthy: a pending or quieted failure still counts under `own: fail`, and an unwatched node under `own: unknown`. The `total` property sums all rows and equals the selected group's size.

## 9. Stories

Written against this house. Node names are for reading. The fixtures use ids. Each story states what the owner is told, not only what the engine emits.

1. **Frigate host dies.** At 02:40 the host probe reports `unreachable`. The Frigate integration, its cameras, and its person sensors fail after it. Motion lighting in four rooms depends on the person sensors, and those functions are `high`. One episode opens, on the host. The integration and sensors are recorded. Impact lists the four functions, so the episode's importance is `high`. It is not maintenance. The policy delivers it at 02:40, through quiet hours. The owner reads: motion lighting is off in four rooms because the Frigate host is unreachable.
2. **Frigate is up and the detector hangs.** The person sensors keep reading "clear". The detector liveness check reports `fail`. One episode opens, on the Frigate service. Impact lists the same functions. Availability alone would have said nothing.
3. **Spotify needs a new login.** At 03:10 the Spotify entry reports `auth_required` / `fail`, labelled `actionable_by: human`, with a remedy and a link. Backyard music depends on it and is `normal`, so the episode's importance stays `normal`. One episode opens at 03:10. The policy delivers it at 07:00, when quiet hours end: in the morning, not during the party. At 18:00, `readiness` for backyard music reports `blocked` by the Spotify entry if its login still fails.
4. **The basement motion sensor's battery dies.** A week earlier, `battery_low` / `warn` reached the morning digest. At 03:58 the sensor stops reporting. Its freshness check turns `unknown` at `ttl`, and a `stale` episode opens at `unknown_hold`. The 08:00 digest reads: basement motion sensor went quiet, battery likely dead, with the battery type from the remedy. `explain` on basement motion lighting names the sensor. This timeline assumes the sensor reports at least every 15 minutes. A sensor that only sends a daily heartbeat needs a `ttl` of about a day, and its dead battery reaches the next day's digest instead. The catalog sets `ttl` from how each device actually reports.
5. **The disk fills.** The disk check reports `capacity_low` / `warn` with `due_at` six days out. It goes to the digest. When `due_at` is within 24 hours, a rule raises it to `notify`. If Home Assistant stops, the outside watchdog alerts through a path that does not run through Home Assistant.
6. **The AI box.** The host answers ping, and inference is dead. An end-to-end probe fails. One episode opens on the AI service, which depends on the AI host. Separately, the AI box's updates node has had `update_pending` open for ten months. It is its own node, which nothing depends on (section 3), so its episode is separate. It sits in the digest, is reminded weekly, and rose a level after 30 days. When inference comes back, the outage resolves and the updates episode stays open. `coverage` would have listed the box before it had any checks.
7. **An Eero node goes down.** The backyard speakers and the backyard music function depend on the backyard Eero node through a declared edge. One episode opens, on the Eero node. Impact lists backyard music.
8. **The garage door does not close.** Close is commanded at 23:10. At 23:10:30 the door is still open. The command check reports `command_failed` / `fail`, labelled `category: operation`, and the garage function has `high` importance. No dependency is in doubt, so the settle gate does not hold it. The policy delivers it at 23:10:30, through quiet hours, to whoever is home. The episode resolves when the door closes.
9. **The Insteon controller chokes.** The controller is `warn`, and its episode is open. Thirty Insteon devices report `command_failed` within a minute. They are recorded on the controller's episode, which gains the reason `dependents_failing`. One episode, not thirty-one. As devices recover, they leave it. If two are still failing after the rest recover, each gets its own episode: those two are broken on their own.

## 10. Scenarios the library must pass

Expressed only with nodes and checks. The core tests use ids. Scenario numbers are ids too. Fixtures cite them, so a new scenario takes the next number and nothing is renumbered.

### Engine

1. Host probe `unreachable` / `fail`. Integration that depends on it is `fail`. Devices under the integration are `fail`. One episode, on the host. Integration and devices are recorded, not separate episodes.
2. Same graph, host `pass`, one device check `fault` / `fail` held past `raise_hold`. One episode, on that device.
3. Controller node `fail`. Ten device `fault` observations. One episode, on the controller. Devices recorded.
4. Controller recovers. Three devices still `fault`. The controller's episode stays open and holds them through rejoin grace. Then, with `coalesce_count` 3, they become its members, with reason `dependents_failing`, and it resolves when they recover. No all-clear is sent while they still fail.
5. Parent `unknown`, child `fail`. The child is gated up to `settle`, and `ProbeRequested` names the parent. Then the child's episode opens. Unknown does not hide it.
6. Parent `warn`, child `fail`. Parent and child each have an episode.
7. Parent `own` is `pass`, and a node that depends on it fails. The child is the root. The parent does not mute it and has no episode.
8. Two checks on one device, `low` / `warn` and `fault` / `fail`. One episode. Both reasons listed. `own` is `fail`.
9. A check with `affects_own` false returns `fail`. `own` stays `pass` if every affecting check passed. The evidence is still stored.
10. Observation older than `ttl`. That check is `unknown`. A sibling `pass` does not keep the node at `pass`.
11. Startup grace covers a wave of `fail` observations. No episode until grace ends, and only for nodes still `fail`.
12. An edge that would cycle is rejected.
13. Status flips `fail` / `pass` inside `raise_hold`. No episode.
14. The child fails first. The parent's failure is confirmed inside `settle`. One episode, on the parent. The child never opens one.
15. The child's episode opened when its gate expired. The parent's failure is confirmed later, with an onset within `settle` of the child's. The child's episode resolves as `absorbed` into the parent's.
16. A child has been failing for days with an open episode. Then its parent fails. The child's episode stays open. After the parent recovers and rejoin grace passes, no new episode opens for the child.
17. A check goes `warn`: an episode opens. It goes `fail`: updated. It goes `warn`: updated. It goes `pass` through `clear_hold`: resolved.
18. A check stays `unknown` past `unknown_hold`. An episode opens with reason `stale`.
19. Snapshot with an open episode, restart, restore. After startup grace the anchor still fails. No new `opened` event. The same episode id continues.
20. Snapshot with an open episode, restart, restore. The anchor passes after the restart. The episode resolves after `clear_hold`. Nothing reopens.
21. A node with an open episode is removed. The episode resolves as `removed`. Its dependents wait out rejoin grace.
22. A device depends on two independent roots, and both fail. The device is recorded on both episodes. `inhibited_by` names both.
23. A root with `low` importance takes down a `critical` function. The episode's importance is `critical`.
24. A parent is `warn`, with its own episode open. `coalesce_count` children fail inside `coalesce_window`. They are recorded on the parent's episode, which gains the reason `dependents_failing`. No second episode opens. The parent's `own` stays `warn`.
25. A quiet window covers a node and its dependents. No episode opens inside it. A node still failing when it ends opens then.
26. An edge with a redundancy group is rejected in version 1.

### Policy

27. A `maintenance` episode at 03:58 is delivered in the 08:00 digest.
28. A `fail` episode of `normal` importance matching a `notify` rule at 03:00 is delivered at 07:00. A `fail` episode of `high` importance at 02:40 is delivered at 02:40. An `urgent` operation at 23:10 is delivered at 23:10.
29. An episode resolved at 05:00 is dropped from the 08:00 digest.
30. An unresolved `update_pending` episode is reminded every 7 days and rises one level after 30.
31. `capacity_low` with `due_at` 20 hours out matches a `due_within: 24h` rule.
32. A shelved episode delivers nothing until the shelf ends.

### Queries

33. `explain` on a function with no checks names the stale sensor it depends on.
34. `readiness` on backyard music reports `blocked`, naming the Eero node and the Spotify entry. The speakers behind the Eero node are not named: the Eero node explains them.
35. `coverage` lists a node with no checks and a check never observed.
36. A function depends on a node whose `own` is `warn`. `readiness` reports `degraded`, with that node. A `fail` dependency reports `blocked`. A `stale` one reports `unknown`, naming it with reason `stale`.

### Additions

Each is tagged with its area.

37. **Engine.** A controller is down for two hours. Devices whose checks have a one-hour `ttl` go `unknown` while muted. The controller recovers. No episode opens for a device that reports within `ttl` plus `unknown_hold` of the rejoin. A device still silent after that opens a `stale` episode.
38. **Engine.** Two episodes open in the same `advance`. Their ids sort in the order they opened, and both survive snapshot and restore.
39. **Policy.** `capacity_low` / `warn` opens with `due_at` 30 hours out and goes to the digest. Six hours later, with no new observation, the `due_within: 24h` rule matches and a `notify` delivery follows.
40. **Policy.** A `fail` episode of `critical` importance with `due_at` one hour out is `urgent`, not `notify`.
41. **Policy.** A `stale` episode of `high` importance that is not `maintenance` is delivered at once, through quiet hours. A `stale` episode on a battery device labelled `maintenance` still goes to the morning digest.
42. **Queries.** A function with no checks depends on a node with no checks, which depends on a sensor that is `unknown` but not yet stale. `readiness` looks through both and reports `unknown`, naming the sensor.
43. **Engine.** An AI service depends on an AI host. A separate updates node, with no edges, has `update_pending` / `warn` and an open episode. The service's probe reports `fail`. One episode opens on the service, and the updates episode is not touched. The probe passes through `clear_hold`. The service's episode resolves, and the updates episode stays open.
44. **Policy.** A lock has `battery_low` / `warn` labelled `category: maintenance`, and `command_failed` / `fail` labelled `category: operation`. A `high` function depends on it. The maintenance rule comes first. The episode is `urgent` and delivered through quiet hours. When the command check passes, the episode stays open on `battery_low`, its loudness falls to `digest` without noise, and it is in the morning digest.
45. **Engine.** A group episode holds three members on a parent that is `pass`, with `coalesce_count` 3. One member recovers. The group resolves as `cleared`. The two left wait out `rejoin_grace`, and each one still failing then opens its own episode.
46. **Engine.** A parent is `warn`, and its episode holds `coalesce_count` members. The parent returns to `pass` through `clear_hold` while the members still fail. The episode stays open. When the members pass through `clear_hold`, it resolves as `cleared`.
47. **Engine.** A group episode is open on a parent that is `pass`. The parent then fails. The parent's episode opens, the group resolves as `absorbed` into it, and the members are recorded on the parent's episode.
48. **Engine.** A hub last reported `pass` 20 minutes ago, inside its `ttl`. A device under it fails. Its episode opens at once, and no `ProbeRequested` is emitted.
49. **Queries.** A controller fails. A device under it fails and is recorded on the controller's episode. A quiet window covers the device. `readiness` on a function that depends on the device reports `blocked`, naming the controller only.
50. **Queries.** A function's own check fails while everything it depends on passes. `readiness` reports `blocked` by its own fault. A function whose dependency fails reports `blocked` by that dependency, externally disabled.
51. **Queries.** A function with no checks depends only on nodes with no checks. `readiness` reports `unknown`, naming them as unwatched.
52. **Engine.** A group episode is open on a controller. Another device under the controller fails. It joins the group, and the episode is updated. No episode opens for it.
53. **Engine.** Three children of a passing controller fail in one `ingest_many` call, with `coalesce_count` 3. Only the group opens; there are no intermediate child episodes or absorbed child ids. Reversing the observation order has the same result, apart from opaque ids.
54. **Engine and policy.** Three children fail ten seconds apart under a passing controller. The first two open their own episodes. The third arrival opens a group and absorbs the first two; their opening events remain in the history. With `notify` and `batch` 30 seconds, their pending deliveries are dropped and only the group is delivered after its own batch delay. An `urgent` variant delivers the first two openings immediately and then the group; absorption does not undo those deliveries.
55. **Queries.** A function needs a passing service and an unwatched terminal controller. Readiness is `unknown`, naming the controller, including through an intermediate node with no checks and when the function's own check passes. A terminal node with only evidence checks (`affects_own: false`) is also unwatched. A node with no checks above a watched, passing dependency can still be `ready`.
56. **Engine.** A command check is registered with `ttl: null` and `unknown_hold: 15m`, without an observation. Readiness is `unknown`. After the hold it opens a `stale` episode. Its first observed `pass` clears that episode only after `clear_hold`. A separate command check initialized with an observed `pass` does not become stale merely because no new command is issued.
57. **Queries.** A passing root supports two branches that share a critical function. `impact` lists both branches and the function once, excludes the root and unrelated nodes, and reports critical importance. A leaf's impact is empty and retains its own importance. Queries do not change state or events.
58. **Queries.** Two roots fail and record one shared device. A view containing all three counts two own episodes and one recorded failure. Overlapping groups do not change those episodes or duplicate a node inside one group. A quieted failure still counts as `fail`, with no episode membership. Unwatched nodes remain `unknown` in the counts.
59. **Queries.** Three failing siblings coalesce on a passing controller. Its rollup row is `pass` with one own episode, and the three siblings are recorded failures. A separately established child episode keeps its own-episode classification when a later parent failure inhibits it.
60. **Queries.** Coverage distinguishes no checks, never observed, expired but not yet stale, and stale after the unknown hold. Explicit unknown reports are observed, evidence-only checks are included, and never-observed checks can also be stale. Quiet windows do not hide gaps, restart preserves them, and fresh observations remove them. Rejoin resets stale timing consistently with scenario 37.

## 11. Home Assistant integration, later

Not part of this library. Recorded so the boundary stays visible. It is a separate repository, named `homeostatic`. As of 2026-09-25, the name is free on GitHub (`mjcumming/homeostatic`) and PyPI, with no colliding Home Assistant or HACS project found. `homeostat` was considered and set aside: the name is live at github.com/freol35241/homeostat, an active, unrelated home-automation project.

- Nodes from the Supervisor host, the core, add-ons, config entries, devices, automations, scripts, and declared external hosts and functions.
- Edges. A wrong edge is worse than a missing one. It mutes a real, independent failure and inflates importance, while a missing edge costs at most an extra message. Discovery proposes, and only relationships that always hold become edges on their own:
  - Registered directly: `config_entry_id`, `via_device_id` (routing through a hub or bridge), and `parent_device_id` (parts of one physical product).
  - Candidates the owner confirms: the entities each automation references. A condition, a notify target, or a scene member is not needed on every run.
  - Declared by the owner: edges Home Assistant cannot see, such as backyard music on the backyard Eero node.
- Catalog entries, for example:
  - battery device class: `battery_low`, and a freshness check labelled `maintenance`
  - config entry state: `setup_retry` as `warn` until its hold, then `fail`; `setup_error` as `fail`; a pending reauthentication as `auth_required`
  - `update` entities: `update_pending`, labelled `maintenance`, on a maintenance node of its own (section 3)
  - the Supervisor resolution center: free space and other host issues
  - Frigate: detector and camera liveness from its stats, with detection and recording as separate nodes
  - external services: end-to-end probes, such as a small prompt to the AI box
  - covers, locks, and garage doors: command verification
  - backups: `backup_overdue`, on a maintenance node of its own
- Startup placeholders (`unavailable` with `restored: true`) map to `unknown`.
- Answer `ProbeRequested` with a fresh observation, for example `homeassistant.update_entity` or a ping. The engine never probes on its own.
- Deliveries through notify services with a tag, so messages are replaced in place; Repairs for fixable problems; and a digest.
- Function health exposed as entities, so automations can fall back, for example from camera occupancy to a PIR sensor. An automation falls back on any readiness answer but `ready`.
- `explain` and `readiness` exposed as services and as tools for Assist.
- Snapshots stored with Home Assistant's `Store`.
- A heartbeat to the outside watchdog.
- The settings UI owns the durations. Starting values, which the owner can change: `settle` 2 minutes, `rejoin_grace` 1 minute, `coalesce_count` 3, `coalesce_window` 60 seconds, `batch` 30 seconds, startup grace 2 minutes. The catalog sets `raise_hold`, `clear_hold`, `ttl`, and `unknown_hold` per check. Where it has none, the UI offers fallbacks the owner can change: `clear_hold` 2 minutes and `unknown_hold` 15 minutes.
- Create or restore the engine when Home Assistant reports it has started, not when the integration loads, so startup grace covers the settling period.

### Observation proofs

The engine is only as good as the observations it gets. A reachable host and a person sensor that keeps saying "clear" do not show that detection works. Three observation sources are proven in the integration while the library is built, not after it:

- **Detector liveness.** Frigate's stats show whether detection runs while the cameras deliver frames. Story 2 depends on it.
- **Battery-device freshness.** Home Assistant's [`last_reported`](https://developers.home-assistant.io/blog/2024/03/20/state_reported_timestamp/) records an integration writing an entity's state, even if the value did not change. It does not by itself prove communication with the physical device. The proof must identify a device-originated heartbeat, packet, sequence number, or successful live read, and show which integration reports actually follow that evidence. Cached or restored state writes must not refresh the freshness observation. Each device's verified reporting rhythm sets its `ttl`. If no live evidence is available, the adapter leaves freshness unknown and exposes the coverage gap. Story 4 depends on it.
- **Command completion.** The adapter reports `command_failed` when a commanded cover, lock, or garage door has not reached its target state in time. Story 8 depends on it.

Each proof records real traces from the house. The traces are converted to fixtures and replayed against the engine.

Each trace records the device and integration versions, source timestamps or sequence numbers, adapter receipt times, emitted observations, and the expected episode and delivery timeline. Include healthy operation, an induced or observed failure, and recovery. The freshness proof must include integration state writes while the device is disconnected; the detector proof must distinguish live camera frames from detector progress; the command proof must correlate the command target and deadline with a fresh resulting state. Record an unavailable signal as a failed proof or coverage gap, not a passing check. No real observation traces have been supplied in this repository yet; synthetic fixtures do not satisfy this acceptance item.

## 12. Acceptance

The library is done when:

- Every story in section 9 and every scenario in section 10 passes as a fixture, without a Home Assistant import.
- Traces from the observation proofs in section 11 replay as fixtures and pass.
- A new fault can be introduced by registering a check with a new reason in a test adapter, without editing the core.
- A new notification preference can be introduced by configuration alone.
- The package has no runtime dependencies, passes mypy in strict mode, and reads no clock.

## 13. Open questions

- Presence-based delivery, such as holding a maintenance item until the owner is at that site: version 1 or later.
- Redundancy group semantics, before version 2 (ADR 0006).
- Whether a dependency known to report late should ask for a probe before its dependents open (ADR 0022).

## 14. Changes from 0.1

- `warn` opens episodes. `unknown` past `unknown_hold` opens a `stale` episode. Recovery means `pass`.
- `fail_hold` is renamed `raise_hold` and applies to any worsening.
- Node `severity` (digest, list, page) is removed. Loudness lives in the attention policy, routed by labels.
- Added importance, its upward flow, and impact.
- Added the settle gate, probe requests, absorption, and the rule that older independent episodes stay open.
- Added coalescing into group episodes.
- Added snapshot and restore, and runtime graph changes.
- `inhibited_by` is a set of roots, found transitively.
- Edges are records, with a reserved redundancy group.
- Observations carry `message`, structured `evidence`, and `due_at`.
- `summary` is replaced by views and `rollup`.
- Functions are nodes. Added the queries explain, impact, readiness, and coverage.
- Added the attention policy and the conventions module to the library.
- Startup grace is generalized to scoped quiet windows.
- Section 8 of 0.1 became stories (section 9) and scenarios (section 10). Scenarios 1 to 13 carry over, with 4, 5, 6, and 7 restated.
- The Home Assistant integration is a separate repository. An outside watchdog is required.
- The `attention` enum (`silent`, `recorded`, `notify`) is removed. Inhibition is `inhibited_by` and recorded nodes. `rollup` counts status and inhibition. Loudness stays in the policy.
- A quiet window stops episodes from opening. Quiet hours only delay `notify`. A `fail` of `high` or `critical` importance is `urgent` and is delivered through quiet hours, after maintenance rules have had their match.
- Durations are required settings. The library has no timing defaults. The integration's settings UI owns them.
- `readiness` follows IEC 60050-192: `pass` is `ready`, `warn` is `degraded`, `fail` or `stale` is `blocked`.
- An episode id is a UUIDv7, assigned at open and kept across update and restore.
- Episode ids are built from `now`. Clock-reading id functions such as `uuid.uuid7()` are banned, and `Engine` accepts an id factory (ADR 0017).
- In the example policy, `due_within` is limited to `warn`, and the urgent rule covers stale episodes. The order of the rules is explained.
- The policy matches rules again when an episode changes and when its age or `due_at` crosses a threshold.
- After a rejoin, a dependent's `stale` clock starts over.
- `ttl` may be `None`. `unknown_hold` is always a duration. The catalog sets check durations, and the settings UI supplies fallbacks. `batch` starts at 30 seconds.
- `readiness` looks through nodes without checks, adds `unknown`, and says whether a blocked function is blocked by its own fault or by a dependency.
- Scenario numbers are ids. Scenarios 37 to 42 are added.

## 15. Changes from 0.2

- A node is one capability. A check lives on a node only if its failure stops that node's dependents. Maintenance debt gets its own node (ADR 0019).
- Episode labels are the anchor's, and each reason keeps its check's labels. Policy rules are matched per reason, and the loudest result wins (ADR 0020).
- One anchor, one episode. Coalesced nodes join an anchor's open episode instead of opening a second one, and later siblings join too. Members decide recovery, and a group whose anchor fails is absorbed (ADR 0021).
- The settle gate waits only on a dependency in doubt: inside `raise_hold`, `unknown`, or gated. An old `pass` within `ttl` does not gate (ADR 0022).
- `readiness` reads `own` status only. `stale` is `unknown`, not `blocked`. Nodes with no checks are looked through, and a function with nothing watched answers `unknown` (ADR 0023).
- In the integration, automation references are candidate edges that the owner confirms.
- Observation proofs for detector liveness, battery freshness, and command completion run alongside the library. Their traces are part of acceptance.
- Stories 3, 4, 6, 8, and 9, and scenarios 24 and 36, are restated. Scenarios 43 to 52 are added.

## 16. Changes from 0.3

- Explicit atomic `ingest_many` and one-observation `ingest`, with complete event histories across calls and a defined fixture runner order (ADR 0024).
- Readiness retains unknown terminal requirements in partially watched graphs, including evidence-only checks (ADR 0025).
- Checks start unknown at registration. `ttl: None` disables expiry, not the initial unknown hold. Initial passing observations and recovery holds are explicit (ADR 0026).
- Scenario 44 initializes its command check. Scenarios 53 to 56 cover atomic and staggered observations, partial coverage, and unobserved commands.
- Observation proofs distinguish integration state writes from fresh device evidence and require failure and recovery traces.
- Public record shapes, interface stubs, and the fixture runner land before the engine. A fixture step can open a quiet window, and scenario 49 has a fixture (ADR 0027).
- A first engine and policy pass every fixture. The semantics this RFP left open are recorded in ADR 0028. Fixtures are added for scenarios 1 to 6, 8 to 11, 13, 15 to 17, 20, 22, 23, 25, 28 to 31, 34, 37, and 40 to 42.
- Rule 15: an episode whose anchor recovers holds the nodes it muted that still fail through their rejoin grace, instead of sending a premature all-clear. Scenario 4 is restated.
- Readiness names causes only. A node whose state a failed dependency explains is left out. Scenarios 34 and 49 are restated.

## 17. Changes from 0.4

- Public result records and precise contracts for `impact`, `coverage`, and `rollup`, with adapter-owned immutable views (ADR 0029).
- Scenario 35 has a coverage fixture. Scenarios 57 to 60 cover potential impact, duplicate-free view counts, coalesced and independent episodes, and evidence gaps across expiry, restart, and rejoin.
- Queries read evaluated state without advancing time or modifying snapshots. Episode lifecycle and policy are unchanged.
