# Health Tree

**When the Zigbee coordinator drops at 2 a.m., forty entities go `unavailable`. Health Tree turns that into one alert, about the coordinator, that says the hall motion lighting is what you just lost and knows that is worth waking you for. When a battery dies, you read about it over coffee.**

[![PyPI](https://img.shields.io/pypi/v/health-tree.svg)](https://pypi.org/project/health-tree/)
[![Downloads](https://img.shields.io/pypi/dm/health-tree.svg?label=downloads)](https://pypistats.org/packages/health-tree)
[![Python](https://img.shields.io/pypi/pyversions/health-tree.svg)](https://pypi.org/project/health-tree/)
[![CI](https://img.shields.io/github/actions/workflow/status/mjcumming/health-tree/ci.yml?branch=main&label=CI)](https://github.com/mjcumming/health-tree/actions/workflows/ci.yml)
[![Security](https://img.shields.io/github/actions/workflow/status/mjcumming/health-tree/codeql.yml?branch=main&label=security)](https://github.com/mjcumming/health-tree/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/mjcumming/health-tree/branch/main/graph/badge.svg)](https://codecov.io/gh/mjcumming/health-tree)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue.svg)](https://mypy.readthedocs.io/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/github/license/mjcumming/health-tree.svg)](LICENSE)

Health Tree is the health engine under [Homeostatic](https://github.com/mjcumming/homeostatic), a Home Assistant integration. You describe what depends on what in your house and feed it observations. It tells a root failure from its symptoms, works out what the failure takes down and how much that matters, and decides who should hear about it, how loudly, and when.

It is pure Python with no Home Assistant code and no dependencies, so it also works for anything else you can draw as a dependency graph.

> **Want this in your house?** Install [Homeostatic](https://github.com/mjcumming/homeostatic). It discovers your integrations, devices, and automations, feeds them to Health Tree, and delivers the notifications. This repository is the reasoning underneath it.

## The problem

Home Assistant has the inventory of your house: host, add-ons, integrations, devices, automations, and the machines they depend on. What it lacks is a health layer. When the Frigate host goes down, it sees the Frigate integration fail, the cameras go `unavailable`, and the person sensors go `unavailable`. It does not see that those are one problem, or that motion lighting in four rooms just stopped working because of it. You find out when you walk into a dark hallway.

The quiet failures are worse. A motion sensor's battery dies and it simply stops talking; nothing turns red. The Spotify login expires at 3 a.m. and nobody notices until there are guests in the backyard. Frigate's host is up, so every availability check passes, but the detector hung and every person sensor has been reading "clear" ever since. The garage door was told to close and is still open. The AI box has had updates pending for ten months.

Failures come in five shapes, and each needs a different kind of check to catch it:

| Shape | Example | Check that catches it |
| --- | --- | --- |
| Loud | An integration fails to load | State |
| Quiet | A sensor stops reporting | Freshness: `ttl`, then `stale` |
| Plausible but wrong | A person sensor reads "clear" because the detector hung | Liveness of the signal path |
| Latent | A login expired and nobody notices until the music is wanted | State, evaluated when it breaks |
| Gradual | A disk fills; a battery drains | Capacity, with a projected deadline |

Two more kinds of trouble are not component failures at all: an operation that did not do what it was told (the garage door), and maintenance debt with no symptom (the updates). And a third is not a failure: a situation you asked to hear about while the house is working fine, like the front door left open overnight.

Monitoring today gives you two options. Watch every entity and drown, or watch nothing.

## What Health Tree does instead

You give it a graph of hard dependencies: the hall light and motion sensor depend on the Zigbee coordinator; the coordinator depends on the host; the *function* "motion lighting" depends on the light and the sensor. Functions are nodes like anything else, and they are where you say what matters: motion lighting is `high`, backyard music is `normal`.

Then three things happen that Home Assistant cannot do on its own.

**One cause, one episode.** When the coordinator fails and the devices behind it fail with it, one *episode* opens on the coordinator. The devices are recorded on it as symptoms, not paged separately. When an Insteon controller chokes and thirty devices report `command_failed` within a minute, that is one episode, not thirty-one. As devices recover they leave it, and if two are still broken after the rest come back, each gets its own episode: those two are broken on their own. If the root turns up late, its episode absorbs the ones already open on its symptoms. When it is over, it recovers once.

**Importance flows up.** The coordinator is just a box. But motion lighting depends on it and motion lighting is `high`, so the episode is `high`. An episode is as important as the most important thing its root takes down, which is what lets a policy say "wake me for this" without anyone rating every device by hand.

**Attention is policy, not status.** Rules decide who hears what, how loudly, and when. A high-importance outage is `urgent` and goes through quiet hours. A low battery goes to the 8 a.m. digest. Pending updates sit in the digest, get a weekly reminder, and rise a level after thirty days. Quiet hours, digests, reminders, escalation, acknowledgment, and shelving are configuration, not code.

Because every episode carries its cause, its reasons, its impact, and a loudness, an integration like Homeostatic can say things like:

> 02:40 · *Motion lighting is off in four rooms because the Frigate host is unreachable.*
>
> 08:00 digest · *The basement motion sensor went quiet at 03:58. Battery likely dead.*
>
> 07:00 · *Spotify needs a new login. Backyard music is blocked until it has one.* (Opened at 03:10, held until quiet hours ended.)

Health Tree also answers questions. What is true of this node, from its own checks (`explain`)? What broke first, and what does it take down (episodes, `impact`)? Is this set of functions ready right now, and if not, what is blocking it (`readiness`)? How does this room or this integration look as a whole (`rollup`)? And what in the house has no checks at all (`coverage`)?

## A story the test suite runs

Behavior is specified as stories drawn from real failures in one house, and the test suite runs them. Home Assistant users will find the format familiar. This is [story 8](tests/fixtures/story-08-garage-door.yaml), abridged:

```yaml
policy:
  recipients:
    michael: {channels: [phone], quiet_hours: "22:30-07:00"}
  digests:
    morning: {at: "08:00", to: michael}
  rules:
    - match: {category: operation, importance: [high, critical]}
      loudness: urgent
      to: michael
    - match: {category: maintenance}
      loudness: digest
      digest: morning
    - match: {status: fail}
      loudness: notify
      to: michael
    - match: {}
      loudness: digest
      digest: morning

graph:
  - id: hub
    kind: device
    checks: [{id: link, ttl: 1h, ...}]
  - id: garage_door
    kind: device
    depends_on: [hub]
    checks: [{id: command, labels: {category: operation}, ...}]
  - id: garage
    kind: function
    importance: high
    depends_on: [garage_door]

steps:
  - at: 2026-09-24T23:10:30Z
    ingest:
      - {node: garage_door, check: command, status: fail, reason: command_failed,
         message: Told to close at 23:10 and still open}
    expect:
      events:
        - {opened: {anchor: garage_door, importance: high, reasons: [command_failed]}}
      deliveries:
        - {loudness: urgent, to: michael}
  - at: 2026-09-24T23:11:00Z
    ingest:
      - {node: garage_door, check: command, status: pass, reason: command_completed}
  - at: 2026-09-24T23:11:31Z
    expect:
      events:
        - {resolved: {resolution: cleared}}
```

The door is only a device, but the `garage` function behind it is `high`, so the episode is `high`. The first rule matches a high-importance operation and makes it `urgent`, so it reaches Michael's phone at 23:10:30, through quiet hours. When the door reports the command completed and the 30-second clear hold passes, the episode resolves once. Had this been a `battery_low` warning on the door's hub instead, it would have fallen through to the last rule and waited for the morning digest, and nobody's sleep would have been touched.

There are eleven stories like this one and more than sixty finer-grained scenarios under [tests/fixtures](tests/fixtures). Together they are the executable spec.

## Using the library

The engine takes a graph and observations and returns events. Here the same Zigbee outage as above, in Python:

```python
from datetime import UTC, datetime, timedelta

from health_tree.engine import Engine
from health_tree.types import Check, Edge, EngineSettings, Importance, Node, Observation, Status

# One way a device can fail: its link drops. The holds keep flaps out of the alerts.
LINK = Check(
    check_id="link",
    raise_hold=timedelta(0),
    clear_hold=timedelta(minutes=2),
    ttl=timedelta(hours=1),
    unknown_hold=timedelta(minutes=5),
)


def device(node_id: str) -> Node:
    return Node(node_id=node_id, kind="device", depends_on=(Edge(to="zigbee"),), checks=(LINK,))


engine = Engine(
    EngineSettings(
        settle=timedelta(seconds=30),
        rejoin_grace=timedelta(minutes=2),
        startup_grace=timedelta(0),
        coalesce_count=3,
        coalesce_window=timedelta(minutes=1),
    )
)
now = datetime(2026, 9, 29, 7, 40, tzinfo=UTC)  # 02:40 in Chicago

# Two devices behind a Zigbee coordinator, serving one function you care about.
engine.register_many(
    [
        Node(node_id="zigbee", kind="integration", checks=(LINK,)),
        device("hall_motion"),
        device("hall_light"),
        Node(
            node_id="motion_lighting",
            kind="function",
            importance=Importance.HIGH,
            depends_on=(Edge(to="hall_motion"), Edge(to="hall_light")),
        ),
    ],
    now,
)


def observe(status: Status, reason: str) -> list[Observation]:
    return [
        Observation(node_id=n, check_id="link", status=status, reason=reason, observed_at=now)
        for n in ("zigbee", "hall_motion", "hall_light")
    ]


engine.ingest_many(observe(Status.PASS, "ok"), now)

# The coordinator drops, and both devices go unavailable with it.
now += timedelta(minutes=1)
events = engine.ingest_many(observe(Status.FAIL, "unavailable"), now)
events += engine.advance(now + timedelta(seconds=30))

for event in events:
    episode = event.episode
    print(type(event).__name__, episode.anchor, episode.importance.value)
    print("  recorded:", sorted(episode.recorded))
    print("  impact:  ", sorted(episode.impact))
# EpisodeOpened zigbee high
#   recorded: ['hall_light', 'hall_motion']
#   impact:   ['hall_light', 'hall_motion', 'motion_lighting']

print(engine.readiness(["motion_lighting"]).answer)
# blocked
```

Three nodes failed and one episode opened, on the coordinator. The two devices are recorded on it, and the episode took the `high` importance of the function it broke. Nothing about the devices' own status was rewritten: each still reports exactly what its own check saw.

The attention policy turns those events into deliveries:

```python
from datetime import time
from zoneinfo import ZoneInfo

from health_tree.policy import Policy
from health_tree.types import (
    Loudness,
    Match,
    PolicyConfig,
    PolicyContext,
    QuietHours,
    Recipient,
    Rule,
)

policy = Policy(
    PolicyConfig(
        batch=timedelta(0),
        timezone=ZoneInfo("America/Chicago"),
        recipients={
            "michael": Recipient(
                channels=("phone",),
                quiet_hours=QuietHours(start=time(22, 30), end=time(7, 0)),
            )
        },
        digests={},
        rules=(
            # High or critical importance is urgent and goes through quiet hours.
            Rule(
                match=Match(importance=frozenset({Importance.HIGH, Importance.CRITICAL})),
                loudness=Loudness.URGENT,
                to=("michael",),
            ),
            # Everything else waits for quiet hours to end.
            Rule(match=Match(), loudness=Loudness.NOTIFY, to=("michael",)),
        ),
    )
)

for event in events:
    for d in policy.handle(event, now, PolicyContext()):
        print(type(d).__name__, d.recipient, d.loudness.value, d.channels)
# Notification michael urgent ('phone',)
```

It is 02:40 and Michael's quiet hours run until 07:00, but the episode is `high`, so the first rule makes it `urgent` and it goes out now. Make `motion_lighting` `normal` instead and `handle` returns nothing at 02:40; the same notification comes out of `policy.advance` at 07:00.

A delivery names the episode, the recipient, the loudness, and the recipient's channel ids. It never says *how* to reach someone. The integration turns a delivery into a push notification, a spoken announcement, a light, or a phone call, and renders the message from the episode's cause, reasons, and impact.

The engine and the policy never read a clock and never do I/O. Every call takes `now`, and time only moves when you pass a later one. That is what makes the stories above runnable as tests, and it is why the whole state can be snapshotted to JSON and restored after a restart with every episode, hold, and reminder intact. [docs/usage.md](docs/usage.md) covers registration, acknowledgment, shelving, digests, and restart.

## Principles

- **A node reports only what its own checks saw.** A failed dependency never rewrites a node's status. A muted node is muted because a known cause explains it, not because of where it sits in a tree.
- **Cause flows down.** A failed node mutes notifications for the dependents that fail with it.
- **Importance flows up.** An episode is as important as the most important thing its root takes down.
- **One root, one episode.** Updated in place, absorbs roots that turn up late, coalesces siblings that fail together, and recovers once.
- **A node is one capability.** If a check's failure would not stop every dependent, it belongs on another node. Frigate detection and Frigate recording are two nodes, so a full recording disk does not take down motion lighting. Maintenance debt gets its own node that nothing depends on, so it never mutes anything.
- **Attention is policy, not status.** Rules decide who hears what, how loudly, and when. Nothing about a node's health changes because someone was or was not told.
- **Delivery is the integration's job.** The library decides; the integration acts.

The model is four separate jobs, not one hierarchy, because a single device sits in an area, belongs to an integration, routes through a controller, runs on a battery, and serves a function:

| Job | Question | Shape | Mutes? |
| --- | --- | --- | --- |
| Cause | What broke what? | One graph of hard dependencies | Yes, and it is the only thing that may |
| Views | How do I read the house? | Named groupings, as many as needed | Never |
| Problem definitions | What can go wrong with this thing? | Checks the integration attaches to each node | No |
| Attention | What interrupts whom, how, and when? | Policy rules | Decides delivery, never status |

## How it is built

- **Pure and deterministic.** Python 3.14, no runtime dependencies, no Home Assistant imports, no I/O, threads, event loop, sleeping, or clock reads. Ruff's banned-API list keeps the clock, threads, asyncio, and Home Assistant out of `src/`. The same inputs always produce the same events.
- **Specified before it was written.** The design of record is an [RFP](docs/rfp.md) that states every rule the engine follows. The public records and the fixture runner were written first; the engine was written to make the fixtures pass.
- **The spec is executable.** Eleven stories and more than sixty scenarios live as YAML fixtures under [tests/fixtures](tests/fixtures), run by one runner. Every behavior change ships with a fixture. The stories are the ones told above: the Frigate host, the hung detector, the expired login, the dead battery, the filling disk, the AI box, the Eero node, the garage door, the choking Insteon controller, the front door open overnight, the dishwasher out of rinse aid.
- **Tested past the fixtures.** 376 tests with more than 98 percent branch coverage, and Hypothesis properties over random graphs and timelines for the invariants: one root episode per anchor, a muted node never opens an episode, nothing opens inside a quiet window, everything resolves once every check passes, a restored snapshot behaves exactly like the engine it replaced, and batch order does not matter.
- **Every decision is written down.** Three dozen [architecture decision records](docs/adr/README.md) cover the choices that would be easy to reverse by mistake, from "status is observed, never rewritten" to "a situation is an edgeless node". An accepted ADR is never edited; it is superseded.
- **Strictly typed.** mypy in strict mode, and the ruff rule set Home Assistant core uses, so the code reads like the platform it serves.
- **Running.** Homeostatic runs on it in a real house.

## Modules

| Part | Module | Owns |
| --- | --- | --- |
| Engine | `health_tree.engine` | Graph, checks, evaluation, inhibition, episodes, importance, quiet windows, snapshots, queries |
| Attention policy | `health_tree.policy` | Rules, recipients, loudness, quiet hours, digests, reminders, escalation, acknowledgment, shelving, scheduled reports |
| Records | `health_tree.types` | The frozen records the engine and policy take and return |

Two things are deliberately not here. The library cannot report the death of the process it runs in, so any deployment needs an external watchdog. And it never decides that a situation holds: your own Home Assistant rule decides the front door has been open too long, and reports it.

## Install

```bash
pip install health-tree
```

Requires Python 3.14. The package is pure Python with no dependencies.

## Project status

**0.5, alpha.** The engine and the attention policy pass every story and scenario fixture, and [Homeostatic](https://github.com/mjcumming/homeostatic) runs on it in a real-house pilot. The design of record is [docs/rfp.md](docs/rfp.md). Synthetic scenarios establish the library's behavior; proofs against real device observations belong to adapters and remain outstanding. The API may still change before 1.0.

## Documentation

- [docs/usage.md](docs/usage.md): registering a graph, driving the attention policy, acknowledgment, and temporary controls.
- [docs/rfp.md](docs/rfp.md): what the library does. Change it before changing behavior.
- [docs/adr](docs/adr/README.md): why, one decision per record.
- [CHANGELOG.md](CHANGELOG.md): what changed.
- [CONTRIBUTING.md](CONTRIBUTING.md): workflow, checks, and releases. AI agents: [AGENTS.md](AGENTS.md).
- [SECURITY.md](SECURITY.md): how to report a vulnerability.

## Development

You need [uv](https://docs.astral.sh/uv/) and git. uv installs Python 3.14 itself.

```bash
git clone https://github.com/mjcumming/health-tree.git
cd health-tree
uv sync
uv run prek install
make check        # everything CI runs: hooks, tests with coverage, build
```

`make help` lists the other targets. On Windows, the `make` targets need Git Bash or WSL, and each one is a short `uv run` command you can run directly.

```text
src/health_tree/     package: engine, policy, and types
tests/               unit and property tests, and the fixture runner
tests/fixtures/      stories and scenarios: the executable spec
docs/rfp.md          design of record
docs/adr/            architecture decision records
```

## License

[MIT](LICENSE)
