"""Invariants over random graphs and timelines (ADRs 0012 and 0024)."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json

from hypothesis import given, strategies as st

from health_tree.engine import Engine
from health_tree.types import (
    EngineSettings,
    Episode,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Event,
    Node,
    QuietWindow,
    Status,
    View,
)
from tests.engine_helpers import T0, at, check, counting_ids, node, obs

STATUSES = [Status.PASS, Status.WARN, Status.FAIL, Status.UNKNOWN]
type Batch = tuple[tuple[str, Status], ...]


@dataclass(frozen=True)
class Scenario:
    """A random graph and a random timeline of observation batches."""

    settings: EngineSettings
    nodes: tuple[Node, ...]
    steps: tuple[tuple[int, Batch], ...]


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    """Graphs whose edges point to earlier nodes, so they never cycle."""
    count = draw(st.integers(min_value=2, max_value=6))
    nodes = []
    for index in range(count):
        depends = draw(
            st.sets(st.integers(0, max(index - 1, 0)), max_size=min(index, 2))
        )
        holds = draw(st.sampled_from([(0, 30), (30, 30), (0, 0)]))
        ttl = draw(st.sampled_from([None, 300, 3600]))
        nodes.append(
            node(
                f"n{index}",
                *(f"n{d}" for d in sorted(depends)),
                checks=[
                    check(
                        raise_hold=holds[0],
                        clear_hold=holds[1],
                        ttl=ttl,
                        unknown_hold=600,
                    )
                ],
            )
        )
    names = [n.node_id for n in nodes]
    steps = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=1, max_value=400),
                st.dictionaries(
                    st.sampled_from(names), st.sampled_from(STATUSES), max_size=count
                ).map(lambda batch: tuple(sorted(batch.items()))),
            ),
            min_size=1,
            max_size=12,
        )
    )
    settings = EngineSettings(
        settle=timedelta(seconds=draw(st.sampled_from([0, 60, 120]))),
        rejoin_grace=timedelta(seconds=draw(st.sampled_from([0, 60]))),
        startup_grace=timedelta(seconds=draw(st.sampled_from([0, 90]))),
        coalesce_count=draw(st.integers(min_value=2, max_value=4)),
        coalesce_window=timedelta(seconds=60),
    )
    return Scenario(settings=settings, nodes=tuple(nodes), steps=tuple(steps))


def _without_startup_grace(scenario: Scenario) -> Scenario:
    settings = replace(scenario.settings, startup_grace=timedelta(0))
    return replace(scenario, settings=settings)


def _started(scenario: Scenario, **options: Callable[[datetime], str]) -> Engine:
    engine = Engine(scenario.settings, **options)
    for item in scenario.nodes:
        engine.register(item, T0)
    return engine


def _calls(
    engine: Engine, steps: tuple[tuple[int, Batch], ...], start: int = 0
) -> Iterator[tuple[int, list[Event]]]:
    """Advance to each step, then ingest its batch. Yield each call's events."""
    elapsed = start
    for delta, batch in steps:
        elapsed += delta
        now = at(elapsed)
        yield elapsed, engine.advance(now)
        if batch:
            yield elapsed, engine.ingest_many([obs(n, s, now) for n, s in batch], now)


@given(scenarios())
def test_queries_preserve_state_and_count_each_node_once(scenario: Scenario) -> None:
    """Queries partition inventory using the event history without altering it."""
    engine = _started(scenario)
    episodes = _replay(_calls(engine, scenario.steps))
    before = engine.snapshot()
    deadline = engine.next_deadline()
    members = frozenset(item.node_id for item in scenario.nodes)
    view = View(view_id="inventory", groups={"all": members})
    result = engine.rollup(view, "all")
    anchors = {episode.anchor for episode in episodes.values()}
    recorded = {name for episode in episodes.values() for name in episode.recorded}
    assert result.total == len(members)
    assert tuple(row.own for row in result.counts) == tuple(Status)
    assert sum(row.own_episode for row in result.counts) == len(anchors)
    assert sum(row.recorded for row in result.counts) == len(recorded - anchors)
    assert sum(row.clear for row in result.counts) == len(members - anchors - recorded)
    engine.coverage()
    for name in members:
        impact = engine.impact(name)
        dependent_ids = [item.node_id for item in impact.nodes]
        assert len(dependent_ids) == len(set(dependent_ids))
        assert name not in dependent_ids
    assert engine.snapshot() == before
    assert engine.next_deadline() == deadline


def _replay(history: Iterator[tuple[int, list[Event]]]) -> dict[str, Episode]:
    """The episodes left open by a history. Fails on an impossible history."""
    open_episodes: dict[str, Episode] = {}
    for _, events in history:
        for event in events:
            match event:
                case EpisodeOpened(episode=episode):
                    assert episode.episode_id not in open_episodes
                    open_episodes[episode.episode_id] = episode
                case EpisodeUpdated(episode=episode):
                    assert episode.episode_id in open_episodes
                    open_episodes[episode.episode_id] = episode
                case EpisodeResolved(episode=episode):
                    del open_episodes[episode.episode_id]
    return open_episodes


def _failed_dependencies_of_openings(
    engine: Engine, scenario: Scenario, events: list[Event]
) -> list[str]:
    edges = {n.node_id: {edge.to for edge in n.depends_on} for n in scenario.nodes}
    return [
        condition.node_id
        for event in events
        if isinstance(event, EpisodeOpened) and event.episode.form == "root"
        for condition in engine.explain(event.episode.anchor).nodes
        if condition.node_id in edges[event.episode.anchor]
        and condition.own is Status.FAIL
    ]


@given(scenarios())
def test_events_are_a_consistent_history(scenario: Scenario) -> None:
    """Every update and resolution follows an opening, and an anchor has one root."""
    engine = _started(scenario, new_id=counting_ids())
    open_episodes = _replay(_calls(engine, scenario.steps))
    roots = [e.anchor for e in open_episodes.values() if e.form == "root"]
    assert len(roots) == len(set(roots))


@given(scenarios())
def test_a_muted_node_never_opens(scenario: Scenario) -> None:
    """Rule 8: a node with a failed hard dependency opens no episode."""
    engine = _started(scenario, new_id=counting_ids())
    failed = [
        name
        for _, events in _calls(engine, scenario.steps)
        for name in _failed_dependencies_of_openings(engine, scenario, events)
    ]
    assert failed == []


@given(scenarios())
def test_nothing_opens_inside_a_quiet_window(scenario: Scenario) -> None:
    """Rules 21 and 22: a window over everything holds every opening."""
    engine = _started(scenario, new_id=counting_ids())
    engine.quiet(QuietWindow(scope="all", until=at(10**6)), T0)
    events = [event for _, batch in _calls(engine, scenario.steps) for event in batch]
    assert not any(isinstance(event, EpisodeOpened) for event in events)


@given(scenarios())
def test_everything_resolves_once_all_checks_pass(scenario: Scenario) -> None:
    """Rule 15: when every check passes through its holds, nothing stays open."""
    engine = _started(scenario, new_id=counting_ids())
    history = list(_calls(engine, scenario.steps))
    passing = tuple((n.node_id, Status.PASS) for n in scenario.nodes)
    recovery = ((1, passing), (3600, ()), (3600, passing), (100, ()))
    history += _calls(engine, recovery, start=history[-1][0])
    assert _replay(iter(history)) == {}


@given(scenarios().map(_without_startup_grace), st.integers(min_value=0, max_value=11))
def test_restore_of_a_snapshot_loses_nothing(scenario: Scenario, cut: int) -> None:
    """Rule 24: a restored engine behaves exactly like the one it replaced."""
    original = _started(scenario)
    history = list(_calls(original, scenario.steps[: cut + 1]))
    elapsed = history[-1][0]
    restored = Engine(scenario.settings)
    for item in scenario.nodes:
        restored.register(item, at(elapsed))
    restored.restore(json.loads(json.dumps(original.snapshot())), at(elapsed))
    later = scenario.steps[cut + 1 :]
    before = [
        [type(e) for e in events] for _, events in _calls(original, later, elapsed)
    ]
    after = [
        [type(e) for e in events] for _, events in _calls(restored, later, elapsed)
    ]
    assert before == after


@given(scenarios())
def test_batch_order_does_not_matter(scenario: Scenario) -> None:
    """ADR 0024: an atomic batch gives the same state in any order."""
    forward = _started(scenario, new_id=counting_ids())
    backward = _started(scenario, new_id=counting_ids())
    reversed_steps = tuple((d, tuple(reversed(b))) for d, b in scenario.steps)
    list(_calls(forward, scenario.steps))
    list(_calls(backward, reversed_steps))
    assert forward.snapshot() == backward.snapshot()
