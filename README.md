# Health Tree

A platform-agnostic Python library for health across a dependency graph: nodes, checks, dependency-aware episodes, and an attention policy.

A house, or any system you can draw as dependencies, can lose a whole machine, a controller, one device, a battery, or a login, or can fail to carry out a command. Usually nothing says which of those happened. You find out when the lights stop following motion, or when the music won't play with guests over. Monitoring tends to either page on every leaf or watch nothing.

Health Tree is the layer that tells a root failure from its symptoms, says what the failure takes down, and decides who hears about it and when.

Home Assistant is the first consumer. Its integration, [homeostatic](docs/rfp.md#11-home-assistant-integration-later), lives in its own repository and is not part of this package.

> **Status: first engine.** The engine and the attention policy pass every story and scenario fixture. The design of record is [docs/rfp.md](docs/rfp.md) (version 0.5, draft for review). ADRs 0001 to 0029 are accepted or superseded. Real observation proofs remain outstanding. Nothing is published to PyPI yet.

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

- What is true of this node, from its own checks?
- What broke first, and what does it take down?
- Who should be told, how loudly, and when?
- Why is this function not working? Is this set of functions ready?
- What isn't being watched at all?

## Model

The model is four jobs, not one hierarchy:

| Job | Question | Shape | Mutes? |
| --- | --- | --- | --- |
| Cause | What broke what? | One graph of hard dependencies | Yes, and it's the only thing that may |
| Views | How do I read the system? | Named groupings, as many as needed | Never |
| Problem definitions | What can go wrong with this thing? | Checks attached by the integration's catalog | No |
| Attention | What interrupts whom, how, and when? | Policy rules | Decides delivery, never status |

A node is one capability: something that either works or doesn't, as its dependents see it. Functions ("garage", "motion lighting") are nodes too, which is what makes the `explain`, `impact`, `readiness`, `coverage`, and `rollup` queries possible.

## Example

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

## Planned modules

| Part | Module | Owns |
| --- | --- | --- |
| Engine | `health_tree` | Graph, checks, evaluation, inhibition, episodes, importance, quiet windows, snapshots, queries |
| Attention policy | `health_tree.policy` | Rules, recipients, loudness, quiet hours, digests, reminders, escalation, shelving |
| Conventions | `health_tree.conventions` | Standard reasons, categories, and label names, with no behavior |

## Repository layout

```text
src/health_tree/     package (engine, policy, and conventions as they land)
tests/               unit and property tests, and the fixture runner
tests/fixtures/      stories and scenarios: the executable spec
docs/rfp.md          design of record
docs/adr/            architecture decision records
```

## Documentation

- [docs/rfp.md](docs/rfp.md): what the library does. Change it before changing behavior.
- [docs/adr](docs/adr/README.md): why, one decision per record.
- [docs/ideas/homeostatic-ui.md](docs/ideas/homeostatic-ui.md): working notes for the integration's owner-facing surface. Not the spec.
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

## License

[MIT](LICENSE)
