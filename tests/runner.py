"""Run YAML fixtures against the engine and the policy (ADRs 0012, 0024, 0027).

`load_fixture` validates a fixture and builds the public records it describes.
`run_fixture` drives an engine and a policy through its steps and compares what
they return with what each step expects. The first step that differs raises
`FixtureMismatch`, naming every difference in that step.

Each step calls, in order and all at the step's `at`:

1. `engine.advance`
2. on a restart: snapshot both, round-trip the snapshots through JSON, build a
   new policy and restore it, then build a new engine, register the current
   graph, and restore it
3. `engine.register`, when the step adds or replaces a node
4. `engine.remove`, when the step removes one
5. `engine.quiet`, when the step opens a quiet window
6. `engine.ingest_many`, with the step's whole `ingest` list as one batch
7. `policy.shelve`, when the step shelves an episode
8. `policy.handle` for every event, in order, as each call returns them
9. `policy.advance`

The runner tracks open episodes from the events alone, and the current graph
from the fixture and its register and remove steps. It fills in no durations.
"""

from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
import json
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

from health_tree.engine import Engine
from health_tree.policy import Policy
from health_tree.types import (
    Check,
    Coverage,
    Delivery,
    Digest,
    Edge,
    EngineSettings,
    Episode,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Event,
    Explanation,
    Impact,
    Importance,
    JSONValue,
    Loudness,
    Match,
    Node,
    Notification,
    Observation,
    PolicyConfig,
    PolicyContext,
    ProbeRequested,
    QuietHours,
    QuietScope,
    QuietWindow,
    Readiness,
    Recipient,
    ResolutionNotice,
    Rollup,
    Rule,
    Status,
    View,
)
from tests.fixture_schema import parse_duration, validate_fixture

CONTEXT = PolicyContext()


class FixtureMismatch(AssertionError):
    """The engine or the policy did not do what a fixture step expects."""


class EngineLike(Protocol):
    """The part of the engine interface the runner calls."""

    def register(self, node: Node, now: datetime) -> list[Event]:
        """Add a node."""
        ...

    def remove(self, node_id: str, now: datetime) -> list[Event]:
        """Remove a node."""
        ...

    def ingest_many(
        self, observations: Sequence[Observation], now: datetime
    ) -> list[Event]:
        """Apply one atomic batch."""
        ...

    def quiet(self, window: QuietWindow, now: datetime) -> list[Event]:
        """Open a quiet window."""
        ...

    def advance(self, now: datetime) -> list[Event]:
        """Move time forward."""
        ...

    def snapshot(self) -> dict[str, JSONValue]:
        """Return all state."""
        ...

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> list[Event]:
        """Restore a snapshot."""
        ...

    def explain(self, node_id: str) -> Explanation:
        """Explain a node."""
        ...

    def readiness(self, node_ids: Collection[str]) -> Readiness:
        """Answer readiness."""
        ...

    def impact(self, node_id: str) -> Impact:
        """Return potential dependents."""
        ...

    def coverage(self) -> Coverage:
        """Return evidence gaps."""
        ...

    def rollup(self, view: View, group: str) -> Rollup:
        """Count one view group."""
        ...


class PolicyLike(Protocol):
    """The part of the policy interface the runner calls."""

    def handle(
        self, event: Event, now: datetime, context: PolicyContext
    ) -> list[Delivery]:
        """Handle one event."""
        ...

    def advance(self, now: datetime, context: PolicyContext) -> list[Delivery]:
        """Move time forward."""
        ...

    def shelve(self, episode_id: str, until: datetime, now: datetime) -> list[Delivery]:
        """Hold one episode's deliveries."""
        ...

    def snapshot(self) -> dict[str, JSONValue]:
        """Return all state."""
        ...

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> None:
        """Restore a snapshot."""
        ...


type EngineFactory = Callable[[EngineSettings], EngineLike]
type PolicyFactory = Callable[[PolicyConfig], PolicyLike]


@dataclass(frozen=True, slots=True, kw_only=True)
class Step:
    """One fixture step: what to do at `at`, and what it must produce."""

    at: datetime
    register: Node | None
    remove: str | None
    quiet: QuietWindow | None
    ingest: tuple[Observation, ...]
    shelve: tuple[str, datetime] | None
    restart: bool
    expect: Mapping[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class Fixture:
    """A fixture, built into public records. `nodes` is in dependency order."""

    fixture_id: str
    start: datetime
    settings: EngineSettings
    policy: PolicyConfig | None
    nodes: tuple[Node, ...]
    views: Mapping[str, View]
    steps: tuple[Step, ...]


def load_fixture(path: Path) -> Fixture:
    """Validate a fixture file and build its records."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate_fixture(document, filename=path.name)
    data: dict[str, Any] = document
    return Fixture(
        fixture_id=data["id"],
        start=_timestamp(data["start"]),
        settings=_settings(data["settings"]),
        policy=_policy(data["policy"]) if "policy" in data else None,
        nodes=_in_dependency_order([_node(node) for node in data["graph"]]),
        views={
            name: View(
                view_id=name,
                groups={group: frozenset(members) for group, members in groups.items()},
            )
            for name, groups in data.get("views", {}).items()
        },
        steps=tuple(_step(step) for step in data["steps"]),
    )


def run_fixture(
    fixture: Fixture,
    *,
    engine_factory: EngineFactory = Engine,
    policy_factory: PolicyFactory = Policy,
) -> None:
    """Drive the engine and the policy through every step of `fixture`."""
    run = _Run(fixture, engine_factory, policy_factory)
    for index, step in enumerate(fixture.steps):
        run.step(index, step)


def _timestamp(value: object) -> datetime:
    parsed = (
        value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    )
    return parsed.astimezone(UTC)


def _clock(value: str) -> time:
    return time.fromisoformat(value)


def _strings(value: Mapping[str, Any] | None) -> dict[str, str]:
    return {str(key): str(item) for key, item in (value or {}).items()}


def _settings(data: Mapping[str, Any]) -> EngineSettings:
    return EngineSettings(
        settle=parse_duration(data["settle"]),
        rejoin_grace=parse_duration(data["rejoin_grace"]),
        startup_grace=parse_duration(data["startup_grace"]),
        coalesce_count=data["coalesce_count"],
        coalesce_window=parse_duration(data["coalesce_window"]),
    )


def _node(data: Mapping[str, Any]) -> Node:
    return Node(
        node_id=data["id"],
        kind=data.get("kind"),
        depends_on=tuple(Edge(to=target) for target in data.get("depends_on", [])),
        importance=Importance(data.get("importance", "normal")),
        labels=_strings(data.get("labels")),
        checks=tuple(_check(check) for check in data.get("checks", [])),
    )


def _check(data: Mapping[str, Any]) -> Check:
    ttl = data["ttl"]
    return Check(
        check_id=data["id"],
        raise_hold=parse_duration(data["raise_hold"]),
        clear_hold=parse_duration(data["clear_hold"]),
        ttl=None if ttl is None else parse_duration(ttl),
        unknown_hold=parse_duration(data["unknown_hold"]),
        affects_own=data.get("affects_own", True),
        labels=_strings(data.get("labels")),
        annotations=_strings(data.get("annotations")),
    )


def _in_dependency_order(nodes: Iterable[Node]) -> tuple[Node, ...]:
    """Dependencies before dependents, otherwise in fixture order."""
    pending = {node.node_id: node for node in nodes}
    ordered: list[Node] = []
    placed: set[str] = set()

    def place(node: Node) -> None:
        if node.node_id in placed:
            return
        for edge in node.depends_on:
            place(pending[edge.to])
        placed.add(node.node_id)
        ordered.append(node)

    for node in pending.values():
        place(node)
    return tuple(ordered)


def _step(data: Mapping[str, Any]) -> Step:
    at = _timestamp(data["at"])
    shelve = data.get("shelve")
    return Step(
        at=at,
        register=_node(data["register"]) if "register" in data else None,
        remove=data.get("remove"),
        quiet=_quiet(data["quiet"]) if "quiet" in data else None,
        ingest=tuple(_observation(item, at) for item in data.get("ingest", [])),
        shelve=(
            None if shelve is None else (shelve["episode"], _timestamp(shelve["until"]))
        ),
        restart=data.get("restart", False),
        expect=data["expect"],
    )


def _quiet(data: Mapping[str, Any]) -> QuietWindow:
    return QuietWindow(
        scope=cast(QuietScope, data["scope"]),
        node_id=data.get("node"),
        until=_timestamp(data["until"]),
    )


def _observation(data: Mapping[str, Any], at: datetime) -> Observation:
    return Observation(
        node_id=data["node"],
        check_id=data["check"],
        status=Status(data["status"]),
        reason=data["reason"],
        observed_at=at,
        message=data.get("message"),
        evidence=data.get("evidence", {}),
        due_at=_timestamp(data["due_at"]) if "due_at" in data else None,
    )


def _policy(data: Mapping[str, Any]) -> PolicyConfig:
    return PolicyConfig(
        batch=parse_duration(data["batch"]),
        timezone=UTC,
        recipients={
            name: _recipient(recipient)
            for name, recipient in data["recipients"].items()
        },
        digests={
            name: Digest(at=_clock(digest["at"]), to=digest["to"])
            for name, digest in data["digests"].items()
        },
        rules=tuple(_rule(rule) for rule in data["rules"]),
    )


def _recipient(data: Mapping[str, Any]) -> Recipient:
    quiet_hours = None
    if "quiet_hours" in data:
        start, end = data["quiet_hours"].split("-")
        quiet_hours = QuietHours(start=_clock(start), end=_clock(end))
    return Recipient(
        channels=tuple(data.get("channels", [])),
        quiet_hours=quiet_hours,
        sites=frozenset(data.get("sites", [])),
    )


def _rule(data: Mapping[str, Any]) -> Rule:
    to = data.get("to", [])
    return Rule(
        match=_match(data["match"]),
        loudness=Loudness(data["loudness"]),
        to=(to,) if isinstance(to, str) else tuple(to),
        digest=data.get("digest"),
        remind_every=(
            parse_duration(data["remind_every"]) if "remind_every" in data else None
        ),
        escalate_after=(
            parse_duration(data["escalate_after"]) if "escalate_after" in data else None
        ),
    )


def _one_or_many(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else [str(value)]


def _match(data: Mapping[str, Any]) -> Match:
    def strings(key: str) -> frozenset[str] | None:
        return frozenset(_one_or_many(data[key])) if key in data else None

    status = strings("status")
    importance = strings("importance")
    return Match(
        status=None if status is None else frozenset(map(Status, status)),
        importance=(
            None if importance is None else frozenset(map(Importance, importance))
        ),
        reason=strings("reason"),
        category=strings("category"),
        labels=_strings(data.get("labels")),
        age=parse_duration(data["age"]) if "age" in data else None,
        due_within=(
            parse_duration(data["due_within"]) if "due_within" in data else None
        ),
    )


def _through_json(state: Mapping[str, JSONValue], what: str) -> dict[str, JSONValue]:
    """Prove a snapshot is JSON-compatible data (rule 24)."""
    loaded: dict[str, JSONValue] = json.loads(json.dumps(state, allow_nan=False))
    if loaded != state:
        raise FixtureMismatch(f"the {what} snapshot changes through JSON")
    return loaded


@dataclass(slots=True)
class _Run:
    fixture: Fixture
    engine_factory: EngineFactory
    policy_factory: PolicyFactory
    engine: EngineLike = field(init=False)
    policy: PolicyLike | None = field(init=False)
    bindings: dict[str, str] = field(init=False, default_factory=dict)
    open: dict[str, Episode] = field(init=False, default_factory=dict)
    graph: dict[str, Node] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.graph = {node.node_id: node for node in self.fixture.nodes}
        self.engine = self.engine_factory(self.fixture.settings)
        config = self.fixture.policy
        self.policy = None if config is None else self.policy_factory(config)
        events = self._register(self.fixture.start)
        if events:
            raise FixtureMismatch(
                f"{self.fixture.fixture_id}: registering the graph at start emitted "
                f"{[self._describe(event) for event in events]}. Checks start "
                "unknown at registration (ADR 0026)"
            )

    def step(self, index: int, step: Step) -> None:
        events: list[Event] = []
        deliveries: list[Delivery] = []
        self._call(self.engine.advance(step.at), step.at, events, deliveries)
        if step.restart:
            self._restart(step.at, events, deliveries)
        if step.register is not None:
            self.graph[step.register.node_id] = step.register
            self._call(
                self.engine.register(step.register, step.at),
                step.at,
                events,
                deliveries,
            )
        if step.remove is not None:
            del self.graph[step.remove]
            self._call(
                self.engine.remove(step.remove, step.at), step.at, events, deliveries
            )
        if step.quiet is not None:
            self._call(
                self.engine.quiet(step.quiet, step.at), step.at, events, deliveries
            )
        if step.ingest:
            self._call(
                self.engine.ingest_many(step.ingest, step.at),
                step.at,
                events,
                deliveries,
            )
        if step.shelve is not None:
            assert self.policy is not None
            reference, until = step.shelve
            episode_id = self._resolve(reference) or reference
            deliveries.extend(self.policy.shelve(episode_id, until, step.at))
        if self.policy is not None:
            deliveries.extend(self.policy.advance(step.at, CONTEXT))
        problems = self._bind(step.expect, events)
        problems += self._track(events)
        problems += self._check(step.expect, events, deliveries)
        if problems:
            raise FixtureMismatch(
                "\n".join(
                    [
                        f"{self.fixture.fixture_id} step {index} at {step.at:%H:%M:%S}:",
                        *(f"  - {problem}" for problem in problems),
                        "  events:",
                        *(f"      {self._describe(event)}" for event in events),
                        "  deliveries:",
                        *(f"      {self._describe(item)}" for item in deliveries),
                    ]
                )
            )

    def _register(self, now: datetime) -> list[Event]:
        events: list[Event] = []
        for node in _in_dependency_order(self.graph.values()):
            events.extend(self.engine.register(node, now))
        return events

    def _call(
        self,
        new: list[Event],
        now: datetime,
        events: list[Event],
        deliveries: list[Delivery],
    ) -> None:
        events.extend(new)
        if self.policy is not None:
            for event in new:
                deliveries.extend(self.policy.handle(event, now, CONTEXT))

    def _restart(
        self, now: datetime, events: list[Event], deliveries: list[Delivery]
    ) -> None:
        engine_state = _through_json(self.engine.snapshot(), "engine")
        config = self.fixture.policy
        if self.policy is not None and config is not None:
            policy_state = _through_json(self.policy.snapshot(), "policy")
            self.policy = self.policy_factory(config)
            self.policy.restore(policy_state, now)
        self.engine = self.engine_factory(self.fixture.settings)
        self._call(self._register(now), now, events, deliveries)
        self._call(self.engine.restore(engine_state, now), now, events, deliveries)

    def _bind(self, expect: Mapping[str, Any], events: list[Event]) -> list[str]:
        problems: list[str] = []
        for name, spec in expect.get("bind", {}).items():
            opened = [
                event.episode.episode_id
                for event in events
                if isinstance(event, EpisodeOpened)
                and event.episode.anchor == spec["opened"]
            ]
            if len(opened) == 1:
                self.bindings[name] = opened[0]
            else:
                problems.append(
                    f"bind {name}: expected one opening on {spec['opened']}, "
                    f"got {len(opened)}"
                )
        return problems

    def _track(self, events: list[Event]) -> list[str]:
        problems: list[str] = []
        for event in events:
            match event:
                case EpisodeOpened(episode=episode):
                    if episode.episode_id in self.open:
                        problems.append(f"{self._name(episode)} opened twice")
                    self.open[episode.episode_id] = episode
                case (
                    EpisodeUpdated(episode=episode) | EpisodeResolved(episode=episode)
                ) if episode.episode_id not in self.open:
                    problems.append(f"{self._name(episode)} was not open")
                case EpisodeUpdated(episode=episode):
                    self.open[episode.episode_id] = episode
                case EpisodeResolved(episode=episode):
                    del self.open[episode.episode_id]
                case ProbeRequested():
                    pass
        return problems

    def _check(
        self,
        expect: Mapping[str, Any],
        events: list[Event],
        deliveries: list[Delivery],
    ) -> list[str]:
        problems = self._sequence(
            "events", expect["events"], events, self._event_problems
        )
        if "deliveries" in expect:
            problems += self._sequence(
                "deliveries", expect["deliveries"], deliveries, self._delivery_problems
            )
        if "open" in expect:
            problems += self._open_problems(expect["open"])
        queries = expect.get("queries", {})
        for node_id, spec in queries.get("explain", {}).items():
            names = [node.node_id for node in self.engine.explain(node_id).nodes]
            if names != spec["names"]:
                problems.append(
                    f"explain {node_id}: expected {spec['names']}, got {names}"
                )
        for node_id, spec in queries.get("readiness", {}).items():
            problems += self._readiness_problems(
                node_id, spec, self.engine.readiness([node_id])
            )
        problems += self._summary_queries(queries)
        return problems

    def _summary_queries(self, queries: Mapping[str, Any]) -> list[str]:
        problems: list[str] = []
        actual: dict[str, object]
        for node_id, spec in queries.get("impact", {}).items():
            impact = self.engine.impact(node_id)
            actual = {
                "node_id": impact.node_id,
                "nodes": [
                    {"node": node.node_id, "importance": node.importance.value}
                    for node in impact.nodes
                ],
                "importance": impact.importance.value,
            }
            problems += self._fields(
                f"impact {node_id}", {"node_id": node_id, **spec}, actual
            )
        if "coverage" in queries:
            coverage = self.engine.coverage()
            actual = {
                "no_checks": list(coverage.no_checks),
                "never_observed": [
                    {"node": ref.node_id, "check": ref.check_id}
                    for ref in coverage.never_observed
                ],
                "stale": [
                    {"node": ref.node_id, "check": ref.check_id}
                    for ref in coverage.stale
                ],
            }
            problems += self._fields("coverage", queries["coverage"], actual)
        for view_id, groups in queries.get("rollup", {}).items():
            for group, spec in groups.items():
                rollup = self.engine.rollup(self.fixture.views[view_id], group)
                expected = {
                    "view_id": view_id,
                    "group": group,
                    "counts": [
                        {
                            "own": status.value,
                            "clear": 0,
                            "own_episode": 0,
                            "recorded": 0,
                            **spec["counts"].get(status.value, {}),
                        }
                        for status in Status
                    ],
                    "total": spec["total"],
                }
                actual = {
                    "view_id": rollup.view_id,
                    "group": rollup.group,
                    "counts": [
                        {
                            "own": row.own.value,
                            "clear": row.clear,
                            "own_episode": row.own_episode,
                            "recorded": row.recorded,
                        }
                        for row in rollup.counts
                    ],
                    "total": rollup.total,
                }
                problems += self._fields(f"rollup {view_id}.{group}", expected, actual)
        return problems

    def _fields(
        self, what: str, expected: Mapping[str, Any], actual: Mapping[str, Any]
    ) -> list[str]:
        return [
            f"{what} {key}: expected {value}, got {actual[key]}"
            for key, value in expected.items()
            if actual[key] != value
        ]

    def _sequence[T](
        self,
        what: str,
        patterns: list[Mapping[str, Any]],
        actual: list[T],
        compare: Callable[[Mapping[str, Any], T], list[str]],
    ) -> list[str]:
        problems: list[str] = []
        if len(patterns) != len(actual):
            problems.append(f"expected {len(patterns)} {what}, got {len(actual)}")
        for index, (pattern, item) in enumerate(zip(patterns, actual, strict=False)):
            problems.extend(
                f"{what}[{index}] {problem}" for problem in compare(pattern, item)
            )
        return problems

    def _event_problems(self, pattern: Mapping[str, Any], event: Event) -> list[str]:
        kind, body = next(iter(pattern.items()))
        match kind, event:
            case "probe", ProbeRequested(node_id=node_id):
                return (
                    []
                    if node_id == body
                    else [f"probe: expected {body}, got {node_id}"]
                )
            case "opened", EpisodeOpened(episode=episode):
                return self._episode_problems(body, episode)
            case "updated", EpisodeUpdated(episode=episode):
                return self._episode_problems(body, episode)
            case "resolved", EpisodeResolved(episode=episode, resolution=resolution):
                problems = self._episode_problems({"episode": body["episode"]}, episode)
                if resolution != body["resolution"]:
                    problems.append(
                        f"resolution: expected {body['resolution']}, got {resolution}"
                    )
                return problems
        return [f"expected {kind}, got {self._describe(event)}"]

    def _episode_problems(
        self, pattern: Mapping[str, Any], episode: Episode
    ) -> list[str]:
        problems: list[str] = []
        for key, value in pattern.items():
            expected, actual = self._episode_field(key, value, episode)
            if expected != actual:
                problems.append(
                    f"{key}: expected {self._show(expected)}, got {self._show(actual)}"
                )
        return problems

    def _show(self, value: object) -> object:
        """Show bound episode ids by their fixture names."""
        match value:
            case str() if value in self.bindings.values():
                return self._alias(value)
            case set() | frozenset():
                return sorted(str(self._show(item)) for item in value)
        return value

    def _episode_field(
        self, key: str, value: Any, episode: Episode
    ) -> tuple[object, object]:
        """Return the expected and actual value of one field, comparably."""
        match key:
            case "episode":
                return self._resolve(value), episode.episode_id
            case "status":
                return Status(value), episode.status
            case "importance":
                return Importance(value), episode.importance
            case "reasons":
                return Counter(value), Counter(f.reason for f in episode.reasons)
            case "recorded":
                return set(value), set(episode.recorded)
            case "absorbed":
                return {self._resolve(ref) for ref in value}, set(episode.absorbed)
            case "anchor":
                return value, episode.anchor
            case "form":
                return value, episode.form
        raise ValueError(f"the runner does not compare episode field {key}")

    def _delivery_problems(
        self, pattern: Mapping[str, Any], delivery: Delivery
    ) -> list[str]:
        if "resolution" in pattern:
            if not isinstance(delivery, ResolutionNotice):
                return [f"expected a resolution notice, got {self._describe(delivery)}"]
            actual: dict[str, object] = {"resolution": delivery.resolution}
        else:
            if not isinstance(delivery, Notification):
                return [f"expected a notification, got {self._describe(delivery)}"]
            actual = {
                "loudness": delivery.loudness.value,
                "digest": delivery.digest,
                "silent": delivery.silent,
            }
        actual |= {
            "episode": delivery.episode_id,
            "to": delivery.recipient,
        }
        problems: list[str] = []
        for key, value in pattern.items():
            expected = self._resolve(value) if key == "episode" else value
            if expected != actual[key]:
                problems.append(
                    f"{key}: expected {self._show(expected)}, "
                    f"got {self._show(actual[key])}"
                )
        return problems

    def _open_problems(self, patterns: list[Mapping[str, Any]]) -> list[str]:
        expected = {self._resolve(pattern["episode"]) for pattern in patterns}
        if expected != set(self.open):
            wanted = sorted(map(self._alias, filter(None, expected)))
            return [
                f"open: expected {wanted}, got {sorted(map(self._alias, self.open))}"
            ]
        return [
            f"open {pattern['episode']} {problem}"
            for pattern in patterns
            for problem in self._episode_problems(
                pattern, self.open[str(self._resolve(pattern["episode"]))]
            )
        ]

    def _readiness_problems(
        self, node_id: str, spec: Mapping[str, Any], readiness: Readiness
    ) -> list[str]:
        actual = {
            "answer": readiness.answer,
            "names": [node.node_id for node in readiness.nodes],
            "by": readiness.blocked_by,
        }
        return [
            f"readiness {node_id} {key}: expected {value}, got {actual[key]}"
            for key, value in spec.items()
            if actual[key] != value
        ]

    def _resolve(self, reference: str) -> str | None:
        return self.bindings.get(reference.removeprefix("$"))

    def _alias(self, episode_id: str) -> str:
        names = [name for name, bound in self.bindings.items() if bound == episode_id]
        return f"${names[0]}" if names else episode_id

    def _name(self, episode: Episode) -> str:
        return f"{self._alias(episode.episode_id)} on {episode.anchor}"

    def _describe(self, item: Event | Delivery) -> str:
        match item:
            case EpisodeOpened(episode=episode) | EpisodeUpdated(episode=episode):
                kind = "opened" if isinstance(item, EpisodeOpened) else "updated"
                return (
                    f"{kind} {self._name(episode)} {episode.form} "
                    f"{episode.status.value} "
                    f"reasons={[f.reason for f in episode.reasons]} "
                    f"recorded={sorted(episode.recorded)} "
                    f"absorbed={sorted(map(self._alias, episode.absorbed))}"
                )
            case EpisodeResolved(episode=episode, resolution=resolution):
                return f"resolved {self._name(episode)} {resolution}"
            case ProbeRequested(node_id=node_id):
                return f"probe {node_id}"
            case Notification():
                return (
                    f"{item.loudness.value} {self._alias(item.episode_id)} to "
                    f"{item.recipient} digest={item.digest} silent={item.silent}"
                )
            case ResolutionNotice():
                return (
                    f"resolution {self._alias(item.episode_id)} to "
                    f"{item.recipient} {item.resolution}"
                )
