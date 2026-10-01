# Concepts

This page explains the model behind Health Tree: what each piece is, and why it behaves the way it does. For code, see [Using Health Tree](usage.md). For every rule in exact terms, see the [RFP](rfp.md).

## The parts

Health Tree has two state machines, and leaves everything with side effects to your code.

The engine, `health_tree.engine.Engine`, holds the dependency graph and the state of every check. You register nodes and feed it observations, and it returns events about episodes and answers queries. The policy, `health_tree.policy.Policy`, takes those events and returns deliveries: who to tell, how loudly and when. The code that connects them to a real system is called an adapter. It discovers what to watch, produces observations, keeps time, sends the deliveries and stores the state. [Homeostatic](https://github.com/mjcumming/homeostatic) is the adapter for Home Assistant.

The records the engine and the policy take and return are in `health_tree.types`. They're frozen dataclasses. Times are timezone-aware UTC, and durations are `timedelta`.

## Nodes and edges

A node is one capability: one thing that either works or doesn't, as the things that depend on it see it. A Zigbee coordinator is a node, and so is a light, a host or an integration's login. A node has an id, an optional `kind` (free text such as `device`; the library never reads it), labels, an importance and its checks.

An edge says one node needs another to do its job. The hall light depends on the coordinator, because when the coordinator is down the light can't work. Only hard dependencies are edges. Something a node needs some of the time isn't one, because a wrong edge does more harm than a missing one: it hides a real, independent failure behind an unrelated one, where a missing edge costs at most an extra message. The graph can't have cycles, and registering an edge that would close one raises `ValueError`. An edge can name a node that isn't registered yet; it takes effect when that node arrives. Each edge has a `group` field reserved for redundancy groups, and the engine rejects any value in it for now.

A function is a node for something the house does, like motion lighting or garage access. It depends on the devices it needs, usually has no checks of its own, and is where you say how much something matters (see [Importance](#importance)).

To decide what's one node, ask whether a check's failure stops everything that depends on the node. If it doesn't, the check belongs on another node. Frigate detection and Frigate recording are two nodes, so a full recording disk doesn't take down motion lighting. Maintenance with no symptom, such as pending updates, gets its own node that nothing depends on, so it never mutes anything. A warning that's an early sign of the same failure stays on the node: a low battery is a warning on the sensor whose dead battery will later make it go quiet.

A situation is a condition you want to hear about while everything is working, such as water on the floor or the front door open overnight. It's a node with no edges, and its one check is reported by something outside the library that decides whether the condition holds: `fail` while it holds, `pass` when it ends, and `unknown` when the reporter can't tell. With no edges, a situation stays apart from equipment health. A failing hub can't mute it, and no function's readiness depends on it. When the leak sensor dies, its reporter says `unknown`, and `unknown` never clears a situation.

Decision records: [A node is one capability](adr/0019-a-node-is-one-capability.md) and [A situation is an edgeless node](adr/0032-a-situation-is-an-edgeless-node.md).

## Checks and status

A check is one way a node can fail, such as `link` on a device or `command` on a garage door. Your adapter reports each result as an observation with a status and a reason. The reason is free text that names what happened, such as `unavailable`, `battery_low` or `command_failed`. An observation can also carry a human-readable message and a `due_at`, the time a warning becomes a failure, such as a login's expiry or the day a disk is projected to fill.

There are four statuses, ordered `pass` < `unknown` < `warn` < `fail`. A node's `own` status is the worst of its checks. `unknown` ranks above `pass` so that a check that's gone dark can't hide behind one that passes. A node with no checks is `unknown` and *unwatched*; that alone never opens an episode. A check with `affects_own=False` is evidence only. It's stored and listed by `coverage`, but it doesn't count toward `own` or readiness.

When a checker can't run, the adapter reports `unknown`. Not being able to look isn't evidence that something is broken.

Each check carries its own timing:

| Field | Meaning |
| --- | --- |
| `raise_hold` | How long a worse status has to persist before it takes effect. A flap to `fail` and back inside it never opens anything. |
| `clear_hold` | How long `pass` has to persist before a known problem clears. |
| `ttl` | How long an observation stays current. After that, the check is `unknown`. `None` means observations never expire, which suits a source that only reports changes. |
| `unknown_hold` | How long the check can stay `unknown` before it's *stale*. A stale check opens an episode with the reason `stale`. |

An improvement short of a clear, such as `fail` to `warn`, takes effect at once.

A new check starts `unknown`, and its `unknown_hold` runs from registration whether or not it has a `ttl`. Its first `pass` takes effect at once. Clearing a known problem, or a check that has gone stale, waits out `clear_hold`.

The library has no default for any duration. The adapter supplies every hold, every `ttl` and every engine setting, because the right values depend on how each source reports: a sensor that reports every few minutes and one that sends a daily heartbeat need very different `ttl` values.

Decision records: [Checks start unknown at registration](adr/0026-checks-start-unknown-at-registration.md) and [Durations are required](adr/0018-durations-are-required.md).

## Own status and muting

A node's `own` status comes only from its own checks, and a failed dependency never rewrites it. When the coordinator drops and the hall light goes unavailable, the light's `own` is `fail`, because that's what its check saw.

The engine mutes the light instead. A node is muted when it has a problem and one of its direct dependencies has `own` status `fail`. A muted node doesn't open an episode. It's recorded on the episode of the root failure that explains it, found by following failed dependencies until one isn't muted itself. A device behind two failed roots is recorded on both. Only `fail` mutes: a dependency at `warn` or `unknown` mutes nobody, so a sluggish coordinator can't hide a device's own fault.

Muting only stops new episodes. If the light already had an episode open from well before the coordinator failed, that episode stays open; [A root that turns up late](#a-root-that-turns-up-late) explains where the line is.

Decision records: [Status is observed, never rewritten](adr/0005-status-is-observed-never-rewritten.md).

## Episodes

An episode is one problem, from onset to resolution, anchored on one node. Its `reasons` list a finding for each check with a problem, with the check's status, reason, message, start time, `due_at` and labels. `recorded` lists the failing nodes it explains, and `impact` lists every node that depends on the anchor, directly or not. Each episode has an id, a UUIDv7 built from `now`, that sorts by opening time and stays the same through updates and restarts.

A node opens an episode when its `own` is `warn` or `fail`, or one of its checks is stale, unless it's muted, held by the [settle gate](#settle-gate), inside a [quiet window](#quiet-windows), or coalesced onto another episode. The engine reports changes as events. `EpisodeOpened` and `EpisodeUpdated` carry the whole episode as it now stands; an update means its status, reasons, recorded nodes, impact, importance or `due_at` changed. `EpisodeResolved` adds a resolution: `cleared`, `removed` (its anchor left the graph) or `absorbed` (it was folded into another episode). One call returns only the final result for each episode, however many observations it applied.

### One cause, one episode

The coordinator drops, and both lights go with it. When the three failures arrive together, one episode opens, on the coordinator, with both lights recorded. Its impact lists the lights and motion lighting.

### A root that turns up late

Often the symptoms arrive first. Say the hall light's episode opened, and the coordinator's failure arrived 40 seconds later. When the coordinator's episode opens, any open episode on a node it now mutes is absorbed if that node's trouble started no more than `settle` before the coordinator's. The light's episode resolves as `absorbed`, the light is recorded on the coordinator's episode, and that episode lists the absorbed id. An older episode stays open. A light that has been broken for days has a problem of its own, and the coordinator's outage doesn't explain it.

### Siblings that fail together

Sometimes the shared dependency looks fine. An Insteon controller can report healthy while thirty devices behind it report `command_failed` within a minute. When `coalesce_count` or more nodes that share a direct dependency would open episodes within `coalesce_window`, the engine puts them on one episode anchored on that dependency, with the extra reason `dependents_failing`. The dependency's own status doesn't change. If it already has an open episode, say for a warning, the devices join that one. Otherwise a `group` episode opens and absorbs the episodes the first few devices already opened. A device that fails later, while the episode still holds members, joins it.

Members that pass through `clear_hold` leave. When fewer than `coalesce_count` still fail, the grouping ends. A `group` episode resolves, a root episode carries on for its anchor alone, and the remaining devices wait out `rejoin_grace` and then open episodes of their own. Two devices still failing after the other twenty-eight recover are broken in their own right. If the shared dependency itself fails, its new episode absorbs the group.

### Recovery

A root episode resolves as `cleared` when its anchor has passed through `clear_hold` and it holds no members. If nodes it recorded still fail when the anchor clears, the episode stays open through their `rejoin_grace` instead of sending an all-clear. Those that recover leave. If `coalesce_count` or more still fail when the grace ends, they become the episode's members; otherwise the episode resolves and each one opens its own. A drop from `fail` to `warn` is an update. Only `pass` ends an episode.

The [garage door story](../tests/fixtures/story-08-garage-door.yaml) in the test fixtures follows one episode from a failed command to its resolution, with the policy's delivery along the way.

Decision records: [Episode lifecycle](adr/0007-episode-lifecycle.md) and [One anchor, one episode; coalesced members decide recovery](adr/0021-coalesced-members-decide-recovery.md).

## Importance

Each node has an importance: `low`, `normal` (the default), `high` or `critical`. You usually set it on functions and leave equipment at `normal`. An episode's importance is the highest over its anchor and its impact. The coordinator is an ordinary device, but motion lighting depends on it through the hall light and is `high`, so the coordinator's episode is `high`. Nobody has to rate every device by hand.

Importance is information for the policy, and it follows the graph without judgment. A low battery on the hall motion sensor also makes a `high` episode, because motion lighting depends on that sensor. Rule order is how you keep that battery out of the night (see [Rules](#rules)). A situation has nothing depending on it, so its importance is the one you gave it.

Decision records: [Importance flows up the cause graph](adr/0009-importance-flows-up.md).

## Time

Neither the engine nor the policy reads a clock. Every call takes `now`, a timezone-aware UTC `datetime`, and time moves only when you pass a later one. An earlier one raises `ValueError`. That's what lets the test suite replay a night of failures as a fixture, and what lets the whole state be saved as data.

Holds and expiry come due between calls. On both the engine and the policy, `next_deadline()` returns the next time anything would change on its own, and `advance(now)` applies everything due up to `now`. The engine applies each change at the time it was due, so a late call still gets the timing right. An adapter keeps one timer for the earlier of the two deadlines.

`EngineSettings` holds the engine's own timing: `settle`, `startup_grace`, `rejoin_grace`, and the coalescing pair `coalesce_count` and `coalesce_window`, which [Siblings that fail together](#siblings-that-fail-together) covers. Quiet windows are the one clock you open and close yourself.

### Settle gate

When a node starts failing while one of its dependencies is in doubt, the engine holds the node back for up to `settle` from its onset, in case the dependency is the cause. A dependency is in doubt when it's `unknown`, when a worse status is waiting out its `raise_hold`, or when the gate is holding it too. A dependency that passed on a current observation isn't in doubt, however long ago it reported, and one with no checks never holds anything up. While it holds a node, the engine emits `ProbeRequested` once for each doubtful dependency, and the adapter decides whether and how to look: ping the host, or refresh the entity. If the dependency's failure arrives, its episode opens with the node recorded. If not, the node opens its own episode when `settle` runs out.

### Startup grace

For `startup_grace` after the first call, and again after a restore, no episode opens anywhere. Integrations take a while to come back after a restart, and the grace keeps that wave of failures from turning into alerts. Anything still failing when it ends opens then.

### Rejoin grace

When a failed dependency stops failing, the nodes behind it get `rejoin_grace` to recover too before they can open episodes. A device that said nothing while its coordinator was down hasn't proved anything either way, so its stale clock restarts at the rejoin: it goes stale after `ttl` plus `unknown_hold` from then, or `unknown_hold` alone when `ttl` is `None`.

### Quiet windows

A `QuietWindow` stops episodes from opening in its scope until it ends. The scope is everything (`all`), one node (`node`), or a node and everything that depends on it (`node_and_dependents`). Maintenance uses the scoped forms, and startup grace is a window over everything. The engine keeps observing inside a window, and anything still failing when it ends opens then.

Quiet hours are a different clock. They belong to a recipient in the policy, and they delay notifications about episodes that have already opened.

Decision records: [A core with no I/O and explicit time](adr/0003-sans-io-core-explicit-time.md) and [The settle gate waits only on dependencies in doubt](adr/0022-settle-gate-waits-only-on-doubt.md).

## Views

A view is a set of named groups of node ids that the adapter defines, such as rooms or integrations. A device sits in a room, belongs to an integration and routes through a controller, and only the controller is an edge. Views are for the rest. They feed `rollup` and nothing else: they never mute, add dependencies or change importance. The engine doesn't keep them, so they aren't in snapshots, and the adapter passes the view with each `rollup` call.

## Queries

Queries read the state as of the last call. They never advance time or change anything, and an unknown node id raises `KeyError`.

| Query | Question it answers |
| --- | --- |
| `explain(node_id)` | Why isn't this working? The node's own findings, then every watched dependency, direct or not, that isn't passing, roots first. |
| `impact(node_id)` | What could this take down? Every node that depends on it, with its importance, whether or not anything is failing. |
| `readiness(node_ids)` | Can these functions do their job right now? |
| `coverage()` | What isn't being watched? Nodes with no checks, checks never observed and checks that are stale. |
| `rollup(view, group)` | How does this room or integration look? For each status, how many nodes are clear, anchor their own episode, or are recorded on another. |

Readiness reads `own` status only. Episodes, muting, quiet windows and shelving never change the answer, because a muted device is still broken. The answer is `blocked` if anything a function needs fails, otherwise `degraded` if something has a warning, otherwise `unknown` if something can't be seen, and `ready` when everything passes. A stale node counts as `unknown`: the library can't tell, so it doesn't guess. A node with no checks in the middle of the graph is looked through, while one at the bottom with nothing beneath it counts as `unknown`, because nobody is watching it. The answer names causes only. When the coordinator is down, the lights behind it aren't named, because their own hardware may be fine. A `blocked` answer also says whether the function is blocked by its own checks or by a dependency.

Decision records: [Readiness preserves unwatched branches](adr/0025-readiness-preserves-unwatched-branches.md) and [Public query records and adapter-owned views](adr/0029-public-queries-and-adapter-owned-views.md).

## The attention policy

The policy decides who hears about an episode, how loudly and when. Its configuration, `PolicyConfig`, is plain data: recipients, digests, rules, a `batch` delay and the time zone for clock times. The policy never changes anything about a node's health, whether or not someone was told.

### Recipients

A recipient is an id such as `owner`, with channel ids such as `phone` and optional quiet hours. Channel ids mean nothing to the library; your adapter decides that `phone` is a push to a particular app.

### Loudness

| Loudness | What happens |
| --- | --- |
| `record` | Kept, never sent |
| `digest` | Goes in the rule's digest |
| `notify` | Sent after `batch`, or when the recipient's quiet hours end |
| `urgent` | Sent at once, through quiet hours |

The `batch` delay gives absorption and coalescing time to land before a `notify` goes out, so the owner hears about the coordinator instead of the first light that noticed. `urgent` doesn't wait.

### Rules

Rules are tried in order for each reason on the episode, and the first rule that matches a reason decides that reason's loudness. The episode takes the loudest result over all its reasons, along with the rest of that rule: its recipients, digest, reminders and escalation. On a tie, the earlier rule wins.

A rule's `Match` can test the reason's status, reason, check id and labels, and how soon its `due_at` falls (`due_within`). The labels are the check's laid over the anchor node's, and `category` matches the `category` label. It can also test the episode's importance, its age, and the nodes it touches: its anchor, recorded nodes and impact. An empty `Match()` matches everything.

Because each reason is matched on its own, order carries meaning. Put the maintenance rule above the urgent rule, and a low battery waits for the digest even on a device behind a `high` function. A lock with a low battery and a failed command still pages, because the command reason reaches the urgent rule by itself.

The policy matches the rules again when an episode changes, and when its age or a `due_at` crosses a threshold some rule names. A disk that's filling sits in the digest until its projected `due_at` is less than a day away, and then a `due_within` rule raises it to `notify` without any new observation. A rise in loudness makes noise. Any other change silently replaces the message the recipient already has.

### Quiet hours

Quiet hours belong to a recipient and are read in the policy's time zone; 22:30 to 07:00 wraps past midnight. A `notify` that comes due inside them, reminders included, waits until they end. `urgent` goes through them, and digests go out at their own times.

### Digests

A `Digest` goes out at a clock time to one recipient, on the weekdays you choose (Monday is 0). A rule that sends to a digest can name its own recipients; otherwise the digest's recipient gets it. An episode appears in its digest once, or in every one while it's open if the digest sets `repeat_open`. An episode that resolves first is dropped, and an empty digest sends nothing. If your timer fires late, there's one current digest, never a backlog. `reports(now)` forecasts what each digest would hold.

### Reminders and escalation

`remind_every` repeats a notification to each recipient at that interval while the episode stays open. For a digest rule, it puts the episode back in the next digest. `escalate_after` raises an episode one loudness level once it has been open that long: pending updates that have sat in the digest for a month become a notification.

### Acknowledgment

Acknowledging an episode records that someone has seen it: the first time, and an optional actor id, shared by every recipient. On a rule with `require_acknowledgment=True`, it stops that episode's reminders, pending notifications, digest entries and escalation. It never changes the episode, its checks or readiness. It ends when the episode resolves, and a new episode starts unacknowledged.

### Shelving

Shelving holds one episode's notifications, reminders and digest entries until a time you choose, and unshelving ends the hold early. Silent updates and the resolution notice still reach anyone who already has the message. A shelf quiets an episode that's already open, where a quiet window stops episodes from opening at all.

### Activation

An adapter that has watched without notifying, and is now turning notifications on, calls `activate`. It starts attention afresh for every open episode, and escalation counts from that moment, so an old problem doesn't arrive already escalated.

### Deliveries

The policy returns `Notification` and `ResolutionNotice` records. A resolution goes silently to everyone who heard about the episode, and an episode that resolves before anyone heard about it sends nothing. [Turn events into deliveries](usage.md#turn-events-into-deliveries) covers what the fields mean for your code.

Decision records: [The attention policy is a pure library module](adr/0010-attention-policy-in-the-library.md), [The policy matches each reason; the loudest wins](adr/0020-policy-matches-each-reason.md), [Policy-owned acknowledgment](adr/0034-acknowledgment-and-control-cancellation.md) and [Scheduled open-problem reports](adr/0035-scheduled-open-problem-reporting.md).

## Snapshot and restore

`snapshot()` on the engine and on the policy returns all of its state as JSON-compatible data with a schema version. After a restart, the adapter builds a new engine and policy with the same settings and configuration, registers the graph, and calls `restore(state, now)` on each. Open episodes keep their ids and carry on without a new `opened` event. An episode whose anchor is no longer in the graph resolves as `removed`. The policy keeps track of who has been told, pending deliveries, shelves and acknowledgments, and matches its rules again against the current configuration. Startup grace starts again at restore.

Decision records: [State survives restarts through snapshot and restore](adr/0011-snapshot-and-restore.md).

## What stays outside the library

Health Tree reasons about what it's told. The adapter discovers nodes, decides what each check means and produces its observations, including deciding when a situation holds. It also sends deliveries, stores snapshots and decides who may acknowledge or shelve. The library never runs a fix: a check's annotations, such as a `remedy`, travel on its findings, and acting on them is up to you. It also can't report that the process it runs in has died, so a deployment needs a watchdog outside it.
