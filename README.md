# Health Tree

**Tell a root failure from its symptoms, say what it takes down, and decide who hears about it and when.**

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

Health Tree is a platform-agnostic Python library for health across a dependency graph: nodes, checks, dependency-aware episodes, and an attention policy.

A house, or any system you can draw as dependencies, can lose a whole machine, a controller, one device, a battery, or a login, or can fail to carry out a command. Usually nothing says which of those happened. You find out when the lights stop following motion, or when the music won't play with guests over. Monitoring tends to either page on every leaf or watch nothing.

Health Tree is the layer in between. It powers [Homeostatic](https://github.com/mjcumming/homeostatic), a Home Assistant integration, but has no Home Assistant code and no runtime dependencies, so it fits any system you can describe as a graph.

## Install

```bash
pip install health-tree
```

Requires Python 3.14. The package is pure Python with no dependencies.

## Quick example

A Zigbee coordinator drops, and the motion sensor and light behind it go unavailable with it. Health Tree opens **one** episode on the coordinator, records the devices as symptoms, and carries the importance of the function they serve:

```python
from datetime import UTC, datetime, timedelta

from health_tree.engine import Engine
from health_tree.types import (
    Check, Edge, EngineSettings, Importance, Node, Observation, Status,
)

def link(ttl: timedelta | None = None) -> Check:
    return Check(
        check_id="link",
        raise_hold=timedelta(0),
        clear_hold=timedelta(minutes=2),
        ttl=ttl,
        unknown_hold=timedelta(minutes=5),
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
now = datetime(2026, 9, 28, 22, 0, tzinfo=UTC)

engine.register_many(
    [
        Node(node_id="zigbee", kind="integration", checks=(link(),)),
        Node(node_id="hall_motion", kind="device",
             depends_on=(Edge(to="zigbee"),), checks=(link(),)),
        Node(node_id="hall_light", kind="device",
             depends_on=(Edge(to="zigbee"),), checks=(link(),)),
        Node(node_id="motion_lighting", kind="function",
             importance=Importance.HIGH,
             depends_on=(Edge(to="hall_motion"), Edge(to="hall_light"))),
    ],
    now,
)
engine.ingest_many(
    [Observation(node_id=n, check_id="link", status=Status.PASS,
                 reason="ok", observed_at=now)
     for n in ("zigbee", "hall_motion", "hall_light")],
    now,
)

# The coordinator drops, and both devices go unavailable with it.
now += timedelta(minutes=1)
events = engine.ingest_many(
    [Observation(node_id=n, check_id="link", status=Status.FAIL,
                 reason="unavailable", observed_at=now)
     for n in ("zigbee", "hall_motion", "hall_light")],
    now,
)
events += engine.advance(now + timedelta(seconds=30))

for event in events:
    episode = event.episode
    print(type(event).__name__, episode.anchor, episode.importance.value,
          sorted(episode.recorded))
# EpisodeOpened zigbee high ['hall_light', 'hall_motion']

print(engine.readiness(["motion_lighting"]).answer)
# blocked
```

The engine never reads a clock or does I/O. You pass `now` into every call, feed it observations, and act on the events it returns. The attention policy (`health_tree.policy`) turns those events into deliveries: who to tell, how loudly, and when.

## Principles

- **A node reports only what its own checks saw.** A failed dependency never rewrites a node's status.
- **Cause flows down.** A failed node mutes notifications for the dependents that fail with it.
- **Importance flows up.** An episode is as important as the most important thing its root takes down.
- **One root, one episode.** An episode is updated in place, absorbs roots that turn up late, coalesces siblings that fail together, and recovers once.
- **Attention is policy, not status.** Rules decide who hears what, how loudly, and when. Quiet hours, digests, reminders, and escalation are configuration.
- **Delivery is the integration's job.** A delivery names the episode, the recipient, the loudness, and the channel names. The integration turns those into a push, speech, a light, or a call.

## What it catches

| Shape | Example | Check that catches it |
| --- | --- | --- |
| Loud | An integration fails to load | State |
| Quiet | A sensor stops reporting | Freshness: `ttl`, then `stale` |
| Plausible but wrong | A person sensor reads "clear" because the detector hung | Liveness of the signal path |
| Latent | A login expired and nobody notices until the music is wanted | State, evaluated when it breaks |
| Gradual | A disk fills; a battery drains | Capacity, with a projected deadline |

It also covers operations that didn't do what they were told (the garage door was told to close and is still open) and maintenance debt with no symptom (months of pending updates).

It answers:

- What is true of this node, from its own checks? (`explain`)
- What broke first, and what does it take down? (episodes, `impact`)
- Who should be told, how loudly, and when? (`Policy`)
- Is this set of functions ready? (`readiness`, `rollup`)
- What isn't being watched at all? (`coverage`)

## Model

The model is four jobs, not one hierarchy:

| Job | Question | Shape | Mutes? |
| --- | --- | --- | --- |
| Cause | What broke what? | One graph of hard dependencies | Yes, and it's the only thing that may |
| Views | How do I read the system? | Named groupings, as many as needed | Never |
| Problem definitions | What can go wrong with this thing? | Checks attached by the integration's catalog | No |
| Attention | What interrupts whom, how, and when? | Policy rules | Decides delivery, never status |

A node is one capability: something that either works or doesn't, as its dependents see it. Functions ("garage", "motion lighting") are nodes too, which is what makes the `explain`, `impact`, `readiness`, `coverage`, and `rollup` queries possible.

## Behavior as executable stories

Behavior is specified as YAML stories and scenarios that the test suite runs. This one is abridged from [story 8](tests/fixtures/story-08-garage-door.yaml):

```yaml
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
```

The door is only a device, but the `garage` function that depends on it is `high` importance, so the episode is `high`. The policy's rule for high-importance operations makes it `urgent`, so it goes out at 23:10 through quiet hours. When the door reports the command completed and the clear hold passes, the episode resolves once.

## Design constraints

- Pure Python 3.14 with no runtime dependencies.
- No Home Assistant imports.
- No I/O, threads, event loop, sleeping, or clock reads. Every call that depends on time takes `now`, a timezone-aware UTC `datetime`. The integration supplies observations and the time, and carries out deliveries.
- The core knows nothing about batteries, add-ons, or any device. A new fault is a check registered by an adapter.
- State survives restarts through snapshot and restore.
- The library can't report the death of the process it runs in, so any deployment needs an external watchdog.

## Modules

| Part | Module | Owns |
| --- | --- | --- |
| Engine | `health_tree.engine` | Graph, checks, evaluation, inhibition, episodes, importance, quiet windows, snapshots, queries |
| Attention policy | `health_tree.policy` | Rules, recipients, loudness, quiet hours, digests, reminders, escalation, acknowledgment, shelving |
| Records | `health_tree.types` | The frozen records the engine and policy take and return |

## Documentation

- [docs/usage.md](docs/usage.md): registering a graph, driving the attention policy, acknowledgment, and temporary controls.
- [docs/rfp.md](docs/rfp.md): what the library does. Change it before changing behavior.
- [docs/adr](docs/adr/README.md): why, one decision per record.
- [CHANGELOG.md](CHANGELOG.md): what changed.
- [CONTRIBUTING.md](CONTRIBUTING.md): workflow, checks, and releases. AI agents: [AGENTS.md](AGENTS.md).
- [SECURITY.md](SECURITY.md): how to report a vulnerability.

## Project status

**0.4, alpha.** The engine and the attention policy pass every story and scenario fixture, and [Homeostatic](https://github.com/mjcumming/homeostatic) runs on it in a real-house pilot. The design of record is [docs/rfp.md](docs/rfp.md). ADRs 0001 to 0034 are accepted or superseded. Real observation proofs remain outstanding: synthetic scenarios establish library behavior, and adapters must supply and validate real observations. The API may still change before 1.0.

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

Repository layout:

```text
src/health_tree/     package: engine, policy, and types
tests/               unit and property tests, and the fixture runner
tests/fixtures/      stories and scenarios: the executable spec
docs/rfp.md          design of record
docs/adr/            architecture decision records
```

## License

[MIT](LICENSE)
