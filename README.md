# Health Tree

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

Health Tree is a Python library for health across a dependency graph. You describe what depends on what and feed it check results. It works out which failure is the cause and which are symptoms, what the failure takes down and how much that matters, and who should hear about it, how loudly and when.

It's pure Python with no runtime dependencies and no Home Assistant code, and it does no I/O. It never reads a clock, opens a connection or sends a message; your code does those things. That keeps it usable for anything you can draw as a dependency graph.

> Using Home Assistant? Install [Homeostatic](https://github.com/mjcumming/homeostatic), the integration built on Health Tree. It discovers your integrations and devices, feeds them to the library and sends the notifications.

## The problem

When a Zigbee coordinator drops at 2 a.m., every device behind it goes unavailable too. A monitor that watches each one raises forty alerts, all about symptoms, and none of them says what actually stopped working or whether it's worth waking someone for. The same night, a motion sensor's battery runs low, which can wait for the morning. The same shape turns up anywhere there are dependencies: a database behind three services, or a router behind twenty hosts.

Handling this well takes two decisions. The first is what counts as one problem: the coordinator failed, and the devices failed because of it. The second is who to tell, and when. Hall motion lighting is out, and that's worth a page at 2 a.m. The battery isn't.

## How Health Tree handles it

You register *nodes*, things that either work or don't, such as the coordinator, a light or an integration's login, and the *edges* between them that say which nodes need which. A *function*, such as motion lighting, is a node too. It depends on the devices it needs and carries an importance from `low` to `critical`.

Your code reports check results as observations. The engine turns them into *episodes*: one per root cause, with the symptoms recorded on it, updated in place and resolved once. An episode is as important as the most important thing its root takes down, so the coordinator's episode is `high` because motion lighting is.

The attention policy turns episodes into deliveries using rules you configure. A high-importance outage goes out at once, through quiet hours. A low battery waits for the morning digest. Quiet hours, digests, reminders and escalation are configuration. Acknowledgment and shelving are calls your code makes when a person asks.

Health Tree never sends anything itself. Your code, called the *adapter*, discovers what to watch, reports observations, keeps time and delivers the messages. [Concepts](docs/concepts.md) explains each of these in detail.

## Example

The coordinator from above, with two devices behind it and the function that needs them both:

```python
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from health_tree.engine import Engine
from health_tree.policy import Policy
from health_tree.types import (
    Check,
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
    Recipient,
    Rule,
    Status,
)

link = Check(
    check_id="link",
    raise_hold=timedelta(0),
    clear_hold=timedelta(minutes=2),
    ttl=timedelta(hours=1),
    unknown_hold=timedelta(minutes=15),
)
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
engine.register_many(
    [
        Node(node_id="coordinator", checks=(link,)),
        Node(
            node_id="hall_motion", depends_on=(Edge(to="coordinator"),), checks=(link,)
        ),
        Node(
            node_id="hall_light", depends_on=(Edge(to="coordinator"),), checks=(link,)
        ),
        Node(
            node_id="motion_lighting",
            kind="function",
            importance=Importance.HIGH,
            depends_on=(Edge(to="hall_motion"), Edge(to="hall_light")),
        ),
    ],
    now,
)


def report(status: Status, reason: str) -> list[Observation]:
    return [
        Observation(
            node_id=n, check_id="link", status=status, reason=reason, observed_at=now
        )
        for n in ("coordinator", "hall_motion", "hall_light")
    ]


engine.ingest_many(report(Status.PASS, "ok"), now)
now += timedelta(minutes=1)  # the coordinator drops, and both devices with it
events = engine.ingest_many(report(Status.FAIL, "unavailable"), now)
for event in events:
    print(
        type(event).__name__,
        event.episode.anchor,
        event.episode.importance.value,
        sorted(event.episode.recorded),
    )

owner = Recipient(
    channels=("phone",), quiet_hours=QuietHours(start=time(22, 30), end=time(7, 0))
)
policy = Policy(
    PolicyConfig(
        batch=timedelta(seconds=30),
        timezone=ZoneInfo("America/Chicago"),
        recipients={"owner": owner},
        digests={},
        rules=(
            Rule(
                match=Match(
                    importance=frozenset({Importance.HIGH, Importance.CRITICAL})
                ),
                loudness=Loudness.URGENT,
                to=("owner",),
            ),
            Rule(match=Match(), loudness=Loudness.NOTIFY, to=("owner",)),
        ),
    )
)
for event in events:
    for delivery in policy.handle(event, now, PolicyContext()):
        print(delivery.recipient, delivery.loudness.value, delivery.channels)
```

```text
EpisodeOpened coordinator high ['hall_light', 'hall_motion']
owner urgent ('phone',)
```

Three nodes failed and one episode opened, anchored on the coordinator: the anchor is the root cause. The two devices are recorded on it as symptoms. Their own status is still `fail`, because that's what their checks saw. The episode is `high` because motion lighting depends on what failed.

It's 02:41 and the owner's quiet hours run until 07:00. Rules are checked in order and the first match wins, so a high-importance episode is `urgent`. Urgent deliveries skip the batch delay and quiet hours, so it goes out now. If motion lighting were `normal`, the second rule would match, `handle` would return nothing, and the notification would come out of `policy.advance` at 07:00.

The check's holds and the engine settings control timing: how long a failure must last before it counts, how long a recovery must last before it clears, and how failures that arrive together are grouped. [Time](docs/concepts.md#time) explains each one.

A delivery names the episode, the recipient and the recipient's channel ids. Turning it into a push notification, a spoken announcement or a flashing light is up to your code.

## How it fits into your code

Neither the engine nor the policy reads a clock. Every call takes `now`, and `next_deadline()` tells you when to call `advance` next, so your code needs one timer. Both save their whole state to JSON-compatible data with `snapshot()` and pick up again after a restart with `restore()`, with every episode, hold and reminder intact. The library makes the same decisions from the same inputs, so behavior can be written down as fixtures and replayed in tests.

The library reasons about what you tell it. It doesn't discover devices, decide when a condition such as a door left open holds, or deliver anything. It also can't report that its own process has died, so a deployment needs a watchdog outside it. [Using Health Tree](docs/usage.md) shows how an adapter does its share.

## Install

```bash
pip install health-tree
```

Health Tree needs Python 3.14 or newer. It's alpha software, and the API may change before 1.0.

## Documentation

- [Concepts](docs/concepts.md): nodes, checks, episodes, importance and the attention policy.
- [Using Health Tree](docs/usage.md): how-tos for adapter authors, with runnable examples.
- [RFP](docs/rfp.md): the design document, with every rule the engine and policy follow.
- [Architecture decisions](docs/adr/README.md): why it works the way it does.
- [Fixtures](tests/fixtures): stories and scenarios in YAML, which the test suite runs as the executable spec.
- [Changelog](CHANGELOG.md): what changed in each release.
- [Contributing](CONTRIBUTING.md): setup, checks and releases.
- [Security](SECURITY.md): how to report a vulnerability.

## License

[MIT](LICENSE)
