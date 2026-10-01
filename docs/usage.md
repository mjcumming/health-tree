# Using Health Tree

These how-tos are for the code that connects Health Tree to a real system, called an adapter. [Homeostatic](https://github.com/mjcumming/homeostatic) is the adapter for Home Assistant. If node, check, episode or loudness are new words, read [Concepts](concepts.md) first.

## Shared setup

Every example on this page starts from this block. It describes a small Zigbee network: a coordinator, three devices behind it, and a high-importance function, motion lighting, that needs two of them. The policy has one recipient, `owner`. It sends an urgent alert when a failure breaks something important, holds other failures through the owner's quiet hours, and saves maintenance for the 08:00 digest.

```python
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from health_tree.engine import Engine
from health_tree.policy import Policy
from health_tree.types import (
    Check,
    Delivery,
    Digest,
    Edge,
    EngineSettings,
    Importance,
    Loudness,
    Match,
    Node,
    Observation,
    PolicyConfig,
    PolicyContext,
    QuietHours,
    QuietWindow,
    Recipient,
    ResolutionNotice,
    Rule,
    Status,
    View,
)

T0 = datetime(2026, 9, 29, 17, 0, tzinfo=UTC)  # noon in Chicago
SETTINGS = EngineSettings(
    settle=timedelta(minutes=2),
    rejoin_grace=timedelta(minutes=1),
    startup_grace=timedelta(0),
    coalesce_count=3,
    coalesce_window=timedelta(minutes=1),
)

# Availability arrives when it changes, so it never expires (ttl=None).
LINK = Check(
    check_id="link",
    raise_hold=timedelta(0),
    clear_hold=timedelta(seconds=30),
    ttl=None,
    unknown_hold=timedelta(minutes=15),
)
BATTERY = Check(
    check_id="battery",
    raise_hold=timedelta(0),
    clear_hold=timedelta(minutes=5),
    ttl=None,
    unknown_hold=timedelta(hours=24),
    labels={"category": "maintenance"},
)
NEEDS_COORDINATOR = (Edge(to="coordinator"),)
GRAPH = [
    Node(node_id="coordinator", kind="device", checks=(LINK,)),
    Node(
        node_id="hall_motion",
        kind="device",
        depends_on=NEEDS_COORDINATOR,
        checks=(LINK, BATTERY),
    ),
    Node(
        node_id="hall_light",
        kind="device",
        depends_on=NEEDS_COORDINATOR,
        checks=(LINK,),
    ),
    Node(
        node_id="porch_light",
        kind="device",
        depends_on=NEEDS_COORDINATOR,
        checks=(LINK,),
    ),
    Node(
        node_id="motion_lighting",
        kind="function",
        importance=Importance.HIGH,
        depends_on=(Edge(to="hall_motion"), Edge(to="hall_light")),
    ),
]

POLICY = PolicyConfig(
    batch=timedelta(seconds=30),
    timezone=ZoneInfo("America/Chicago"),
    recipients={
        "owner": Recipient(
            channels=("phone",),
            quiet_hours=QuietHours(start=time(22, 30), end=time(7, 0)),
        ),
    },
    digests={"morning": Digest(at=time(8, 0), to="owner")},
    rules=(
        # Maintenance waits for the morning, whatever it takes down.
        Rule(
            match=Match(category=frozenset({"maintenance"})),
            loudness=Loudness.DIGEST,
            digest="morning",
        ),
        # A failure that breaks something important goes out now, day or night.
        Rule(
            match=Match(
                status=frozenset({Status.FAIL}),
                importance=frozenset({Importance.HIGH, Importance.CRITICAL}),
            ),
            loudness=Loudness.URGENT,
            to=("owner",),
        ),
        # Other failures wait out the batch and the owner's quiet hours.
        Rule(
            match=Match(status=frozenset({Status.FAIL})),
            loudness=Loudness.NOTIFY,
            to=("owner",),
        ),
        # Anything else goes in the digest.
        Rule(match=Match(), loudness=Loudness.DIGEST, digest="morning"),
    ),
)
CONTEXT = PolicyContext()


def observe(node_id, check_id, status, reason, at, **details) -> Observation:
    return Observation(
        node_id=node_id,
        check_id=check_id,
        status=status,
        reason=reason,
        observed_at=at,
        **details,
    )


def healthy_engine() -> Engine:
    """An engine with GRAPH registered and every check passing at T0."""
    engine = Engine(SETTINGS)
    engine.register_many(GRAPH, T0)
    engine.ingest_many(
        [
            observe(n.node_id, c.check_id, Status.PASS, "ok", T0)
            for n in GRAPH
            for c in n.checks
        ],
        T0,
    )
    return engine


def describe(delivery: Delivery) -> str:
    """One line per delivery, for these examples."""
    if isinstance(delivery, ResolutionNotice):
        return f"resolved ({delivery.resolution}) to {delivery.recipient}"
    text = f"{delivery.cause} to {delivery.recipient}: {delivery.digest or delivery.loudness.value}"
    return text + ", silent" if delivery.silent else text
```

The durations are example values. The library has no defaults, so your adapter picks every one, and usually lets its users change them. Each section below runs on its own after this block, and within a section each block continues from the one before.

## Register a graph

Register what you know about in one `register_many` call. The engine checks the final graph before it changes anything, so a cycle or a repeated id rejects the whole call and leaves the engine as it was.

```python
engine = Engine(SETTINGS)
print(engine.register_many(GRAPH, T0))

coverage = engine.coverage()
print(coverage.no_checks)
print([f"{ref.node_id}/{ref.check_id}" for ref in coverage.never_observed])
print(engine.next_deadline())
```

```text
[]
('motion_lighting',)
['coordinator/link', 'hall_motion/link', 'hall_motion/battery', 'hall_light/link', 'porch_light/link']
2026-09-29 17:15:00+00:00
```

Every check starts `unknown`, and its `unknown_hold` runs from registration. If nothing reports within 15 minutes, the checks go stale and open episodes, so send current evidence as soon as you've registered.

To change a node, register it again with the same id. Checks that keep their id keep their observations and holds, and new checks start `unknown`. An edge can name a node you haven't registered yet; it takes effect when that node arrives. `engine.remove(node_id, now)` takes a node out, and its open episode resolves as `removed`.

```python
try:
    engine.register(
        Node(node_id="coordinator", depends_on=(Edge(to="hall_light"),)), T0
    )
except ValueError as error:
    print(error)
```

```text
an edge from coordinator would close a cycle
```

Register the things you watch and what they depend on, including a requirement you can't watch yet. A node with no checks still counts in readiness as `unknown` and is listed in `coverage().no_checks`, so the gap stays visible. You don't need to register your whole inventory.

## Feed observations

An `Observation` is one check result. Give it a `reason` that names what happened, such as `unavailable` or `battery_low`. Add a `message` for people and a `due_at` when the problem has a deadline, such as a login that expires or a disk projected to fill; both show up on the episode's reasons. `evidence` holds JSON-compatible details such as a battery percentage. The engine keeps it with the observation in its snapshot, but nothing in the engine reads it.

```python
engine = Engine(SETTINGS)
engine.register_many(GRAPH, T0)
engine.ingest_many(
    [
        observe(node.node_id, check.check_id, Status.PASS, "ok", T0)
        for node in GRAPH
        for check in node.checks
    ],
    T0,
)

now = T0 + timedelta(minutes=10)
low = Observation(
    node_id="hall_motion",
    check_id="battery",
    status=Status.WARN,
    reason="battery_low",
    observed_at=now,
    message="Battery at 9%",
    evidence={"battery_pct": 9},
)
for event in engine.ingest(low, now):
    episode = event.episode
    print(
        type(event).__name__,
        episode.anchor,
        episode.status.value,
        episode.importance.value,
    )
    for finding in episode.reasons:
        print(" ", finding.reason, finding.message, dict(finding.labels))
```

```text
EpisodeOpened hall_motion warn high
  battery_low Battery at 9% {'category': 'maintenance'}
```

The episode is `high` because motion lighting depends on the sensor. The policy's maintenance rule still sends it to the morning digest; see [Turn events into deliveries](#turn-events-into-deliveries).

`ingest_many` applies a batch atomically and evaluates once, so put observations that arrived together in one call. Don't hold back unrelated arrivals to build a bigger batch. The engine checks the whole batch first: an unregistered check, or the same check twice, rejects it and nothing is applied.

When your checker can't run, because the integration isn't loaded or the probe timed out, report `unknown`:

```python
now += timedelta(minutes=1)
print(
    engine.ingest(
        observe("hall_light", "link", Status.UNKNOWN, "integration_not_loaded", now),
        now,
    )
)
print(engine.next_deadline())
try:
    engine.ingest(observe("hall_light", "battery", Status.PASS, "ok", now), now)
except ValueError as error:
    print(error)
```

```text
[]
2026-09-29 17:26:00+00:00
('hall_light', 'battery') is not a registered check
```

The unknown check opens a `stale` episode if it's still unknown when its 15-minute `unknown_hold` runs out.

## Advance time and answer probes

The engine never reads a clock. Holds, expiry, the settle gate and quiet windows take effect only when you call it with a later `now`. Ask `next_deadline()` when that is, keep one timer, and call `advance(now)` when it fires. Every `now` is a timezone-aware UTC `datetime`, and it can't go backwards.

```python
engine = Engine(SETTINGS)
engine.register_many(GRAPH, T0)
# Everything reports except the coordinator, which stays unknown.
engine.ingest_many(
    [
        observe(n.node_id, c.check_id, Status.PASS, "ok", T0)
        for n in GRAPH
        for c in n.checks
        if n.node_id != "coordinator"
    ],
    T0,
)

now = T0 + timedelta(minutes=1)
print(
    engine.ingest(observe("hall_light", "link", Status.FAIL, "unavailable", now), now)
)
print(engine.next_deadline())
```

```text
[ProbeRequested(node_id='coordinator')]
2026-09-29 17:03:00+00:00
```

The hall light failed while the coordinator it depends on was in doubt. The engine holds the light back for up to `settle` (two minutes) and asks for a fresh observation of the coordinator. If nothing changes, the light opens its own episode at the 17:03 `advance`. Answer the probe if you can, by pinging the host or refreshing the entity:

```python
now += timedelta(seconds=5)
for event in engine.ingest(
    observe("coordinator", "link", Status.FAIL, "unreachable", now), now
):
    print(type(event).__name__, event.episode.anchor, sorted(event.episode.recorded))
```

```text
EpisodeOpened coordinator ['hall_light']
```

One episode, on the coordinator, with the light recorded on it. When both come back, the episode waits out the coordinator's `clear_hold` before it resolves:

```python
now += timedelta(minutes=10)
print(
    engine.ingest_many(
        [
            observe(n, "link", Status.PASS, "ok", now)
            for n in ("coordinator", "hall_light")
        ],
        now,
    )
)
now = engine.next_deadline()
for event in engine.advance(now):
    print(now, type(event).__name__, event.resolution)
```

```text
[]
2026-09-29 17:11:35+00:00 EpisodeResolved cleared
```

## Turn events into deliveries

Feed every event to `policy.handle` in the order the engine returned them, then call `policy.advance` with the same `now` to release anything due. Do it after every engine call, `advance` included. Your timer wakes at whichever comes first, the engine's deadline or the policy's.

```python
engine = healthy_engine()
policy = Policy(POLICY)


def step(events, now):
    deliveries = [
        delivery for event in events for delivery in policy.handle(event, now, CONTEXT)
    ]
    return deliveries + policy.advance(now, CONTEXT)


def next_wakeup():
    deadlines = [
        t for t in (engine.next_deadline(), policy.next_deadline()) if t is not None
    ]
    return min(deadlines, default=None)


now = T0 + timedelta(minutes=20)
events = engine.ingest(
    observe("hall_light", "link", Status.FAIL, "unavailable", now), now
)
print([describe(d) for d in step(events, now)])
```

```text
['open to owner: urgent']
```

The hall light breaks motion lighting, so the urgent rule sends it at once. The porch light breaks nothing important, so it gets `notify`, which waits out the 30-second `batch` first. At night, it would also wait for the owner's quiet hours to end.

```python
now += timedelta(minutes=1)
events = engine.ingest(
    observe("porch_light", "link", Status.FAIL, "unavailable", now), now
)
print([describe(d) for d in step(events, now)])
now = next_wakeup()
print(now, [describe(d) for d in step(engine.advance(now), now)])
```

```text
[]
2026-09-29 17:21:30+00:00 ['open to owner: notify']
```

When the hall light recovers, the owner gets a resolution notice for the message they already have:

```python
now += timedelta(minutes=5)
step(engine.ingest(observe("hall_light", "link", Status.PASS, "ok", now), now), now)
now = next_wakeup()
print(now, [describe(d) for d in step(engine.advance(now), now)])
```

```text
2026-09-29 17:27:00+00:00 ['resolved (cleared) to owner']
```

A low battery matches the maintenance rule and waits for the digest. `policy.reports(now)` shows what each digest would hold if it went out now, and `policy.explain(episode_id)` shows which rule decided an episode's loudness (`rule_index` counts from zero):

```python
now += timedelta(minutes=1)
events = engine.ingest(
    observe("hall_motion", "battery", Status.WARN, "battery_low", now), now
)
print(step(events, now))
battery = events[0].episode.episode_id
print(
    [
        (report["name"], report["next_at"], len(report["episodes"]))
        for report in policy.reports(now)
    ]
)
print(
    {key: policy.explain(battery)[key] for key in ("loudness", "rule_index", "digest")}
)

now = next_wakeup()
print(now, [describe(d) for d in step(engine.advance(now), now)])
```

```text
[]
[('morning', '2026-09-30T13:00:00+00:00', 1)]
{'loudness': 'digest', 'rule_index': 0, 'digest': 'morning'}
2026-09-30 13:00:00+00:00 ['digest to owner: morning']
```

The library never says how to reach anyone. Each `Notification` names the episode, the recipient, the recipient's channel ids from your configuration, the loudness and a `cause`: `open`, `update`, `remind`, `escalate`, `activate` or `digest`. Turning that into a phone push or a spoken announcement is your code's job, and so is the text. A delivery carries only the episode id, so keep the latest `Episode` from the engine's events and build the message from its anchor, reasons and impact. Tag each message with its episode id so you can replace it in place. A notification with `silent=True` replaces the message the recipient already has without alerting again, and a `ResolutionNotice` updates or withdraws it. In a digest entry, `previously_reported` says whether that recipient has heard about the episode before.

## Acknowledge an episode

Call `policy.acknowledge` when a person says they've seen an episode. On a rule with `require_acknowledgment=True`, that stops the reminders; [Acknowledgment](concepts.md#acknowledgment) lists everything else it stops and leaves alone. This rule set repeats urgent alerts until someone acknowledges them:

```python
from dataclasses import replace

urgent = replace(
    POLICY.rules[1], remind_every=timedelta(minutes=30), require_acknowledgment=True
)
policy = Policy(replace(POLICY, rules=(POLICY.rules[0], urgent, *POLICY.rules[2:])))
engine = healthy_engine()

now = T0 + timedelta(minutes=20)
events = engine.ingest(
    observe("hall_light", "link", Status.FAIL, "unavailable", now), now
)
episode_id = events[0].episode.episode_id
print([describe(d) for event in events for d in policy.handle(event, now, CONTEXT)])

now = policy.next_deadline()
print(now, [describe(d) for d in policy.advance(now, CONTEXT)])

now += timedelta(minutes=5)
print([describe(d) for d in policy.acknowledge(episode_id, now, actor_id="owner")])
acknowledgment = policy.acknowledgment(episode_id)
print(acknowledgment.at, acknowledgment.actor_id)
print(policy.next_deadline())
print(engine.readiness(["motion_lighting"]).answer)
```

```text
['open to owner: urgent']
2026-09-29 17:50:00+00:00 ['remind to owner: urgent']
['update to owner: urgent, silent']
2026-09-29 17:55:00+00:00 owner
2026-09-30 13:00:00+00:00
blocked
```

After the acknowledgment, the next deadline is the morning digest: the reminders have stopped. A second `acknowledge` keeps the first time and actor and returns nothing. The acknowledgment ends when the episode resolves, and a new episode starts unacknowledged. The actor id is any string you like, and your adapter decides who may acknowledge. A message that was delivered or dismissed doesn't count as an acknowledgment.

## Hold one episode's alerts

`policy.shelve(episode_id, until, now)` holds one episode's alerts until `until`, and `policy.unshelve` ends the hold early. [Shelving](concepts.md#shelving) says exactly what it holds.

```python
engine = healthy_engine()
policy = Policy(POLICY)

now = T0 + timedelta(minutes=20)
events = engine.ingest(
    observe("porch_light", "link", Status.FAIL, "unavailable", now), now
)
episode_id = events[0].episode.episode_id
for event in events:
    policy.handle(event, now, CONTEXT)
policy.shelve(episode_id, now + timedelta(hours=2), now)

now += timedelta(seconds=30)
print(policy.advance(now, CONTEXT), policy.next_deadline())

now += timedelta(minutes=10)
print([describe(d) for d in policy.unshelve(episode_id, now, CONTEXT)])
```

```text
[] 2026-09-29 19:20:00+00:00
['open to owner: notify']
```

When you release the shelf early, anything due goes out under the usual batch and quiet hours. To keep episodes from opening at all, [use a quiet window](#silence-equipment-during-maintenance).

## Silence equipment during maintenance

Open a [quiet window](concepts.md#quiet-windows) over the equipment you're working on, scoped to one `node` or a `node_and_dependents`. No episode opens inside it, but the engine keeps observing, so readiness still tells the truth. `engine.cancel_quiet(window, now)` ends one window early and leaves any others in force; anything still failing then opens at once.

```python
engine = healthy_engine()

now = T0 + timedelta(minutes=20)
window = QuietWindow(
    scope="node_and_dependents", node_id="coordinator", until=now + timedelta(hours=1)
)
engine.quiet(window, now)

now += timedelta(minutes=5)
down = [
    observe(n, "link", Status.FAIL, "unavailable", now)
    for n in ("coordinator", "hall_motion", "hall_light", "porch_light")
]
print(engine.ingest_many(down, now))
print(engine.readiness(["motion_lighting"]).answer)

now += timedelta(minutes=10)
for event in engine.cancel_quiet(window, now):
    print(type(event).__name__, event.episode.anchor, sorted(event.episode.recorded))
```

```text
[]
blocked
EpisodeOpened coordinator ['hall_light', 'hall_motion', 'porch_light']
```

## Turn notifications on for problems already open

If your adapter runs the policy but discards its deliveries until the user turns notifications on, call `policy.activate(now, context)` at that moment. It starts attention afresh for every open episode, as [Activation](concepts.md#activation) describes. Deliveries go out under the current rules, batch and quiet hours, with `cause` set to `activate`. Episode ids and opening times don't change.

```python
engine = healthy_engine()
policy = Policy(POLICY)

now = T0 + timedelta(minutes=20)
for node_id in ("hall_light", "porch_light"):
    now += timedelta(minutes=5)
    for event in engine.ingest(
        observe(node_id, "link", Status.FAIL, "unavailable", now), now
    ):
        policy.handle(event, now, CONTEXT)  # notifications are off: discard
    policy.advance(now, CONTEXT)

now += timedelta(hours=2)
print([describe(d) for d in policy.activate(now, CONTEXT)])
now = policy.next_deadline()
print(now, [describe(d) for d in policy.advance(now, CONTEXT)])
```

```text
['activate to owner: urgent']
2026-09-29 19:30:30+00:00 ['activate to owner: notify']
```

An ordinary restart uses `restore`, never `activate`.

## Save and restore across restarts

`snapshot()` returns JSON-compatible data with a schema version, for the engine and the policy separately. Store both. After a restart, build a new engine with the same settings, register the graph, then restore its snapshot. Restore the policy's snapshot into a new `Policy` built from your current configuration; it matches its rules again.

```python
import json

engine = healthy_engine()
policy = Policy(POLICY)
now = T0 + timedelta(minutes=20)
events = engine.ingest(
    observe("hall_light", "link", Status.FAIL, "unavailable", now), now
)
before = events[0].episode.episode_id
print([describe(d) for event in events for d in policy.handle(event, now, CONTEXT)])
saved = json.dumps({"engine": engine.snapshot(), "policy": policy.snapshot()})

# Restart.
now += timedelta(minutes=10)
state = json.loads(saved)
engine = Engine(SETTINGS)
engine.register_many(GRAPH, now)
events = engine.restore(state["engine"], now)
policy = Policy(POLICY)
policy.restore(state["policy"], now)
print(events)  # feed these to the policy, as after any engine call

now += timedelta(minutes=1)
engine.ingest(observe("hall_light", "link", Status.PASS, "ok", now), now)
now = engine.next_deadline()
for event in engine.advance(now):
    print(type(event).__name__, event.episode.episode_id == before, event.resolution)
    print([describe(d) for d in policy.handle(event, now, CONTEXT)])
```

```text
['open to owner: urgent']
[]
EpisodeResolved True cleared
['resolved (cleared) to owner']
```

The open episode came back with its id and no new `opened` event, and its resolution went to the recipient who had the original message. An episode whose anchor isn't in the new graph resolves as `removed`. Startup grace starts again at restore, so with a nonzero `startup_grace` nothing new opens while your sources reconnect. Views aren't in the snapshot; rebuild them from your own configuration.

## Ask questions about the graph

Queries read the state as of your last call and change nothing. An unknown node id raises `KeyError`.

```python
engine = Engine(SETTINGS)
engine.register_many(GRAPH, T0)
# The porch light hasn't reported yet.
engine.ingest_many(
    [
        observe(n.node_id, c.check_id, Status.PASS, "ok", T0)
        for n in GRAPH
        for c in n.checks
        if n.node_id != "porch_light"
    ],
    T0,
)
now = T0 + timedelta(minutes=5)
engine.ingest_many(
    [
        observe(n, "link", Status.FAIL, "unavailable", now)
        for n in ("coordinator", "hall_motion", "hall_light")
    ],
    now,
)

explanation = engine.explain("motion_lighting")
print("explain:", [(n.node_id, n.own.value, n.reasons) for n in explanation.nodes])

readiness = engine.readiness(["motion_lighting"])
print(
    "readiness:",
    readiness.answer,
    readiness.blocked_by,
    [n.node_id for n in readiness.nodes],
)

impact = engine.impact("coordinator")
print(
    "impact:",
    impact.importance.value,
    [(n.node_id, n.importance.value) for n in impact.nodes],
)

coverage = engine.coverage()
print(
    "coverage:",
    coverage.no_checks,
    [r.node_id for r in coverage.never_observed],
    coverage.stale,
)

zigbee = View(
    view_id="integration",
    groups={"zigbee": {"coordinator", "hall_motion", "hall_light", "porch_light"}},
)
for row in engine.rollup(zigbee, "zigbee").counts:
    print(
        "rollup:",
        row.own.value,
        "clear",
        row.clear,
        "own episode",
        row.own_episode,
        "recorded",
        row.recorded,
    )
```

```text
explain: [('coordinator', 'fail', ('unavailable',)), ('hall_motion', 'fail', ('unavailable',)), ('hall_light', 'fail', ('unavailable',))]
readiness: blocked dependency ['coordinator']
impact: high [('hall_motion', 'normal'), ('hall_light', 'normal'), ('porch_light', 'normal'), ('motion_lighting', 'high')]
coverage: ('motion_lighting',) ['porch_light'] ()
rollup: pass clear 0 own episode 0 recorded 0
rollup: unknown clear 1 own episode 0 recorded 0
rollup: warn clear 0 own episode 0 recorded 0
rollup: fail clear 0 own episode 1 recorded 2
```

`explain` lists every watched dependency that isn't passing, roots first. `readiness` names only the cause: the two devices are down because the coordinator is, so they're left out, and `blocked_by` says the function is blocked by a dependency rather than its own checks. `impact` lists what the coordinator could take down whether or not anything is failing. In the rollup, the coordinator anchors its own episode, the two devices are recorded on it, and the porch light, which hasn't reported, counts as `unknown` and clear of any episode.
