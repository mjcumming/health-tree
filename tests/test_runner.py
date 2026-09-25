"""The fixture runner calls the engine as specified and catches every difference.

A scripted engine and policy stand in for the real ones. They return what a
correct engine would for a few fixtures, so the runner is tested before the
engine exists (ADR 0027).
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from health_tree.types import (
    Delivery,
    EngineSettings,
    Episode,
    EpisodeOpened,
    EpisodeResolved,
    Event,
    Explanation,
    Finding,
    Importance,
    JSONValue,
    Loudness,
    Node,
    NodeCondition,
    Notification,
    Observation,
    PolicyConfig,
    PolicyContext,
    ProbeRequested,
    QuietWindow,
    Readiness,
    Resolution,
    ResolutionNotice,
    Status,
)
from tests.runner import (
    EngineLike,
    FixtureMismatch,
    PolicyLike,
    load_fixture,
    run_fixture,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 24, hour, minute, second, tzinfo=UTC)


def _episode(
    episode_id: str,
    anchor: str,
    at: datetime,
    *,
    reasons: Iterable[str] = ("unreachable",),
    status: Status = Status.FAIL,
    form: str = "root",
    recorded: Iterable[str] = (),
    absorbed: Iterable[str] = (),
) -> Episode:
    return Episode(
        episode_id=episode_id,
        form="group" if form == "group" else "root",
        anchor=anchor,
        status=status,
        reasons=tuple(
            Finding(
                node_id=anchor, check_id=None, status=status, reason=reason, since=at
            )
            for reason in reasons
        ),
        recorded=frozenset(recorded),
        impact=frozenset(),
        importance=Importance.NORMAL,
        opened_at=at,
        updated_at=at,
        absorbed=frozenset(absorbed),
    )


def _notify(
    episode_id: str, loudness: Loudness, digest: str | None = None
) -> Notification:
    return Notification(
        episode_id=episode_id,
        recipient="michael",
        channels=("phone",),
        loudness=loudness,
        digest=digest,
    )


def _withdraw(episode_id: str, resolution: Resolution) -> ResolutionNotice:
    return ResolutionNotice(
        episode_id=episode_id,
        recipient="michael",
        channels=("phone",),
        resolution=resolution,
    )


def _condition(node_id: str, own: Status, *reasons: str) -> NodeCondition:
    return NodeCondition(node_id=node_id, own=own, reasons=reasons)


@dataclass
class Script:
    """What the scripted engine and policy return, and what they were asked."""

    events: dict[tuple[str, datetime], list[Event]] = field(default_factory=dict)
    explanations: dict[str, Explanation] = field(default_factory=dict)
    readiness: dict[tuple[str, datetime], Readiness] = field(default_factory=dict)
    on_event: dict[tuple[str, str], list[Delivery]] = field(default_factory=dict)
    digests: dict[datetime, list[Delivery]] = field(default_factory=dict)
    snapshot: dict[str, JSONValue] = field(default_factory=lambda: {"schema": 1})
    calls: list[tuple[str, object, datetime]] = field(default_factory=list)
    now: datetime = field(default_factory=lambda: _at(0, 0))


class ScriptedEngine:
    """Returns scripted events for each call, keyed by method and `now`."""

    def __init__(self, script: Script) -> None:
        """Share one script across restarts."""
        self.script = script

    def _events(self, method: str, detail: object, now: datetime) -> list[Event]:
        self.script.calls.append((method, detail, now))
        self.script.now = now
        return self.script.events.get((method, now), [])

    def register(self, node: Node, now: datetime) -> list[Event]:
        """Record the registration."""
        return self._events("register", node.node_id, now)

    def ingest_many(
        self, observations: Sequence[Observation], now: datetime
    ) -> list[Event]:
        """Record the batch."""
        batch = [(o.node_id, o.check_id, o.status.value) for o in observations]
        return self._events("ingest", batch, now)

    def quiet(self, window: QuietWindow, now: datetime) -> list[Event]:
        """Record the window."""
        return self._events("quiet", window, now)

    def advance(self, now: datetime) -> list[Event]:
        """Record the advance."""
        return self._events("advance", None, now)

    def snapshot(self) -> dict[str, JSONValue]:
        """Return the scripted state."""
        return self.script.snapshot

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> list[Event]:
        """Record the restore."""
        return self._events("restore", dict(state), now)

    def explain(self, node_id: str) -> Explanation:
        """Return the scripted explanation."""
        return self.script.explanations[node_id]

    def readiness(self, node_ids: Collection[str]) -> Readiness:
        """Return the scripted answer for the one function asked about."""
        (node_id,) = node_ids
        return self.script.readiness[node_id, self.script.now]


class ScriptedPolicy:
    """Returns scripted deliveries for each event and each `advance`."""

    def __init__(self, script: Script) -> None:
        """Share one script across restarts."""
        self.script = script

    def handle(
        self, event: Event, now: datetime, context: PolicyContext
    ) -> list[Delivery]:
        """Deliver what the script says for this event."""
        match event:
            case ProbeRequested():
                return []
            case _:
                key = (type(event).__name__, event.episode.episode_id)
                return self.script.on_event.get(key, [])

    def advance(self, now: datetime, context: PolicyContext) -> list[Delivery]:
        """Deliver scripted digests."""
        return self.script.digests.get(now, [])

    def snapshot(self) -> dict[str, JSONValue]:
        """Return the scripted state."""
        return {"schema": 1}

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> None:
        """Record the restore."""
        self.script.calls.append(("policy-restore", dict(state), now))


def _run(name: str, script: Script) -> None:
    def engine(_: EngineSettings) -> EngineLike:
        return ScriptedEngine(script)

    def policy(_: PolicyConfig) -> PolicyLike:
        return ScriptedPolicy(script)

    run_fixture(
        load_fixture(FIXTURES / f"{name}.yaml"),
        engine_factory=engine,
        policy_factory=policy,
    )


def _story_four() -> Script:
    stale = _episode("s1", "sensor", _at(4, 13), reasons=["stale"])
    return Script(
        events={("advance", _at(4, 13)): [EpisodeOpened(episode=stale)]},
        digests={_at(8, 0): [_notify("s1", Loudness.DIGEST, "morning")]},
        explanations={
            "lighting": Explanation(
                node_id="lighting",
                findings=(),
                nodes=(_condition("sensor", Status.UNKNOWN, "stale"),),
            )
        },
    )


def _scenario_54_urgent() -> Script:
    first = _episode("c1", "d1", _at(12, 1), reasons=["command_failed"])
    second = _episode("c2", "d2", _at(12, 1, 10), reasons=["command_failed"])
    group = _episode(
        "g",
        "controller",
        _at(12, 1, 20),
        reasons=["dependents_failing"],
        form="group",
        recorded=["d1", "d2", "d3"],
        absorbed=["c1", "c2"],
    )
    return Script(
        events={
            ("ingest", _at(12, 1)): [EpisodeOpened(episode=first)],
            ("ingest", _at(12, 1, 10)): [EpisodeOpened(episode=second)],
            ("ingest", _at(12, 1, 20)): [
                EpisodeOpened(episode=group),
                EpisodeResolved(
                    episode=first, resolution="absorbed", absorbed_into="g"
                ),
                EpisodeResolved(
                    episode=second, resolution="absorbed", absorbed_into="g"
                ),
            ],
        },
        on_event={
            ("EpisodeOpened", "c1"): [_notify("c1", Loudness.URGENT)],
            ("EpisodeOpened", "c2"): [_notify("c2", Loudness.URGENT)],
            ("EpisodeOpened", "g"): [_notify("g", Loudness.URGENT)],
            ("EpisodeResolved", "c1"): [_withdraw("c1", "absorbed")],
            ("EpisodeResolved", "c2"): [_withdraw("c2", "absorbed")],
        },
    )


def _scenario_49() -> Script:
    controller = _episode("k", "controller", _at(6, 1), recorded=["device"])
    return Script(
        events={("ingest", _at(6, 1)): [EpisodeOpened(episode=controller)]},
        readiness={
            ("function", _at(6, 0)): Readiness(answer="ready", nodes=()),
            ("function", _at(6, 2)): Readiness(
                answer="blocked",
                blocked_by="dependency",
                nodes=(
                    _condition("controller", Status.FAIL, "unreachable"),
                    _condition("device", Status.FAIL, "unreachable"),
                ),
            ),
        },
    )


def test_a_correct_digest_story_passes() -> None:
    """Bind, openings, a digest delivery, and `explain` all match (story 4)."""
    script = _story_four()
    _run("story-04-battery-digest", script)
    assert ("ingest", [("sensor", "freshness", "pass")], _at(3, 43)) in script.calls
    assert ("advance", None, _at(3, 58)) in script.calls


def test_a_correct_absorption_passes() -> None:
    """Membership compares as sets; events and deliveries keep their order."""
    _run("scenario-54-staggered-failures-urgent", _scenario_54_urgent())


def _scenario_19() -> Script:
    host = _episode("h", "host", _at(2, 41))
    return Script(events={("ingest", _at(2, 41)): [EpisodeOpened(episode=host)]})


def test_restart_restores_through_json() -> None:
    """A restart builds a new engine, registers the graph, then restores it."""
    script = _scenario_19()
    _run("scenario-19-restore-open-episode", script)
    restart = [call for call in script.calls if call[2] == _at(2, 42)]
    assert restart == [
        ("advance", None, _at(2, 42)),
        ("register", "host", _at(2, 42)),
        ("restore", {"schema": 1}, _at(2, 42)),
    ]


def test_restart_restores_the_policy_first(tmp_path: Path) -> None:
    """The policy is restored before the new engine's events reach it."""
    name = "story-04-battery-digest.yaml"
    document = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    restart = {"at": _at(5, 0), "restart": True, "expect": {"events": []}}
    document["steps"].insert(3, restart)
    (tmp_path / name).write_text(yaml.safe_dump(document), encoding="utf-8")
    script = _story_four()
    run_fixture(
        load_fixture(tmp_path / name),
        engine_factory=lambda _: ScriptedEngine(script),
        policy_factory=lambda _: ScriptedPolicy(script),
    )
    assert [call for call in script.calls if call[2] == _at(5, 0)] == [
        ("advance", None, _at(5, 0)),
        ("policy-restore", {"schema": 1}, _at(5, 0)),
        ("register", "sensor", _at(5, 0)),
        ("register", "lighting", _at(5, 0)),
        ("restore", {"schema": 1}, _at(5, 0)),
    ]


def test_quiet_window_comes_before_the_batch() -> None:
    """The window is opened at the step's time, and readiness is asked after it."""
    script = _scenario_49()
    _run("scenario-49-readiness-ignores-quiet-window", script)
    window = QuietWindow(scope="node", node_id="device", until=_at(7, 0))
    assert ("quiet", window, _at(6, 2)) in script.calls


def _drop_opening(script: Script) -> None:
    del script.events["advance", _at(4, 13)]


def _probe_early(script: Script) -> None:
    script.events["advance", _at(3, 58)] = [ProbeRequested(node_id="sensor")]


def _wrong_reason(script: Script) -> None:
    (opened,) = script.events["advance", _at(4, 13)]
    assert isinstance(opened, EpisodeOpened)
    finding = replace(opened.episode.reasons[0], reason="unreachable")
    episode = replace(opened.episode, reasons=(finding,))
    script.events["advance", _at(4, 13)] = [EpisodeOpened(episode=episode)]


def _wrong_digest(script: Script) -> None:
    script.digests[_at(8, 0)] = [_notify("s1", Loudness.DIGEST, "evening")]


def _page_instead(script: Script) -> None:
    script.digests[_at(8, 0)] = [_notify("s1", Loudness.URGENT)]


def _withdraw_instead(script: Script) -> None:
    script.digests[_at(8, 0)] = [_withdraw("s1", "cleared")]


def _no_digest(script: Script) -> None:
    del script.digests[_at(8, 0)]


def _explain_nothing(script: Script) -> None:
    script.explanations["lighting"] = Explanation(
        node_id="lighting", findings=(), nodes=()
    )


def _resolve_twice(script: Script) -> None:
    (opened,) = script.events["advance", _at(4, 13)]
    assert isinstance(opened, EpisodeOpened)
    script.events["advance", _at(8, 0)] = [
        EpisodeResolved(episode=opened.episode, resolution="cleared")
    ]


def _register_noisily(script: Script) -> None:
    script.events["register", _at(3, 43)] = [ProbeRequested(node_id="sensor")]


def _json_unsafe_snapshot(script: Script) -> None:
    script.snapshot = {"schema": 1, "ids": ("s1",)}  # type: ignore[dict-item]


@pytest.mark.parametrize(
    ("name", "build", "break_it", "message"),
    [
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _drop_opening,
            "expected one opening on sensor, got 0",
            id="missing-event",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _probe_early,
            "expected 0 events, got 1",
            id="extra-event",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _wrong_reason,
            r"reasons: expected Counter\(\{'stale': 1\}\)",
            id="wrong-reason",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _wrong_digest,
            "digest: expected morning, got evening",
            id="wrong-digest",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _page_instead,
            "loudness: expected digest, got urgent",
            id="wrong-loudness",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _withdraw_instead,
            "expected a notification",
            id="notice-for-notification",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _no_digest,
            "expected 1 deliveries, got 0",
            id="missing-delivery",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _explain_nothing,
            r"explain lighting: expected \['sensor'\], got \[\]",
            id="wrong-explain",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _resolve_twice,
            "expected 0 events, got 1",
            id="unexpected-resolution",
        ),
        pytest.param(
            "story-04-battery-digest",
            _story_four,
            _register_noisily,
            "registering the graph at start emitted",
            id="noisy-registration",
        ),
        pytest.param(
            "scenario-19-restore-open-episode",
            _scenario_19,
            _json_unsafe_snapshot,
            "changes through JSON",
            id="snapshot-not-json",
        ),
    ],
)
def test_runner_reports_what_differs(
    name: str,
    build: Callable[[], Script],
    break_it: Callable[[Script], None],
    message: str,
) -> None:
    """Each kind of difference fails the step and says what it was."""
    script = build()
    break_it(script)
    with pytest.raises(FixtureMismatch, match=message):
        _run(name, script)


def _keep_first_child_open(script: Script) -> None:
    events = script.events["ingest", _at(12, 1, 20)]
    script.events["ingest", _at(12, 1, 20)] = events[:2]
    script.on_event.pop(("EpisodeResolved", "c2"))


def _swap_resolutions(script: Script) -> None:
    events = script.events["ingest", _at(12, 1, 20)]
    script.events["ingest", _at(12, 1, 20)] = [events[0], events[2], events[1]]


def _absorb_only_one(script: Script) -> None:
    opened = script.events["ingest", _at(12, 1, 20)][0]
    assert isinstance(opened, EpisodeOpened)
    group = replace(opened.episode, absorbed=frozenset({"c1"}))
    script.events["ingest", _at(12, 1, 20)][0] = EpisodeOpened(episode=group)


def _page_for_withdrawal(script: Script) -> None:
    script.on_event["EpisodeResolved", "c1"] = [_notify("c1", Loudness.URGENT)]


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        pytest.param(
            _keep_first_child_open,
            r"open: expected \['\$group_ep'\], got \['\$group_ep', '\$second_child'\]",
            id="left-open",
        ),
        pytest.param(
            _swap_resolutions,
            r"events\[1\] episode: expected \$first_child, got \$second_child",
            id="order-matters",
        ),
        pytest.param(
            _absorb_only_one,
            "absorbed: expected",
            id="membership",
        ),
        pytest.param(
            _page_for_withdrawal,
            "expected a resolution notice",
            id="noisy-withdrawal",
        ),
    ],
)
def test_runner_checks_absorption_histories(
    break_it: Callable[[Script], None], message: str
) -> None:
    """Scenario 54's history is exact about order, membership, and silence."""
    script = _scenario_54_urgent()
    break_it(script)
    with pytest.raises(FixtureMismatch, match=message):
        _run("scenario-54-staggered-failures-urgent", script)


def _ready_too_soon(script: Script) -> None:
    script.readiness["function", _at(6, 2)] = Readiness(answer="ready", nodes=())


def _device_first(script: Script) -> None:
    blocked = script.readiness["function", _at(6, 2)]
    script.readiness["function", _at(6, 2)] = replace(
        blocked, nodes=tuple(reversed(blocked.nodes))
    )


def _blocked_by_own(script: Script) -> None:
    blocked = script.readiness["function", _at(6, 2)]
    script.readiness["function", _at(6, 2)] = replace(blocked, blocked_by="own")


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        pytest.param(
            _ready_too_soon,
            "readiness function answer: expected blocked, got ready",
            id="answer",
        ),
        pytest.param(
            _device_first,
            r"names: expected \['controller', 'device'\], got \['device', 'controller'\]",
            id="roots-first",
        ),
        pytest.param(
            _blocked_by_own,
            "by: expected dependency, got own",
            id="externally-disabled",
        ),
    ],
)
def test_runner_checks_readiness(
    break_it: Callable[[Script], None], message: str
) -> None:
    """Readiness is exact about the answer, the order of names, and the cause."""
    script = _scenario_49()
    break_it(script)
    with pytest.raises(FixtureMismatch, match=message):
        _run("scenario-49-readiness-ignores-quiet-window", script)
