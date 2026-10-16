"""Independent sibling episodes retain evidence and controls when scope splits."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, time, timedelta
import json

import pytest

from health_tree.engine import Engine
from health_tree.policy import Policy
from health_tree.types import (
    Delivery,
    Digest,
    Episode,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Event,
    Loudness,
    Match,
    Node,
    Notification,
    PolicyConfig,
    PolicyContext,
    Recipient,
    ResolutionNotice,
    Rule,
    Status,
)
from tests.engine_helpers import SETTINGS, T0, at, check, node, obs, summary

CONTEXT = PolicyContext()


def _graph(*, ttl: float | None = None) -> tuple[Node, ...]:
    return (
        node("controller", checks=[check(clear_hold=0, ttl=ttl, unknown_hold=60)]),
        *(
            node(
                name,
                "controller",
                checks=[check(clear_hold=0, ttl=ttl, unknown_hold=60)],
            )
            for name in ("one", "two", "three")
        ),
    )


def _group(*, ttl: float | None = None) -> tuple[Engine, Episode]:
    engine = Engine(replace(SETTINGS, settle=timedelta(0)))
    engine.register_many(_graph(ttl=ttl), T0)
    events = engine.ingest_many(
        [
            obs("controller", Status.PASS, T0),
            *(obs(name, Status.FAIL, T0) for name in ("one", "two", "three")),
        ],
        T0,
    )
    assert len(events) == 1
    assert isinstance(events[0], EpisodeOpened)
    return engine, events[0].episode


def _restore(
    engine: Engine, *, seconds: int = 10, ttl: float | None = None
) -> tuple[Engine, list[Event]]:
    restored = Engine(
        replace(SETTINGS, coalesce_count=None, startup_grace=timedelta(minutes=2))
    )
    restored.register_many(_graph(ttl=ttl), at(seconds))
    return restored, restored.restore(
        json.loads(json.dumps(engine.snapshot())), at(seconds)
    )


def _policy(*, loudness: Loudness = Loudness.NOTIFY) -> Policy:
    return Policy(
        PolicyConfig(
            timezone=UTC,
            batch=timedelta(seconds=30),
            recipients={"owner": Recipient(channels=("phone",))},
            digests={},
            rules=(
                Rule(
                    match=Match(),
                    loudness=loudness,
                    to=("owner",),
                    require_acknowledgment=True,
                    remind_every=timedelta(minutes=1),
                ),
            ),
        )
    )


def _handle(policy: Policy, events: Sequence[Event], seconds: int) -> list[Delivery]:
    return [
        delivery
        for event in events
        for delivery in policy.handle(event, at(seconds), CONTEXT)
    ]


def test_restored_group_splits_during_startup_without_recovery() -> None:
    """Already-open faults continue despite startup grace and get truthful links."""
    original, group = _group()
    restored, events = _restore(original)
    openings = [event for event in events if isinstance(event, EpisodeOpened)]
    assert [event.episode.anchor for event in openings] == ["one", "two", "three"]
    assert {event.split_from for event in openings} == {group.episode_id}
    assert {event.episode.opened_at for event in openings} == {group.opened_at}
    assert events[-1] == EpisodeResolved(
        episode=replace(group, updated_at=at(10)),
        resolution="split",
        split_into=tuple(event.episode.episode_id for event in openings),
    )
    _, replay = _restore(restored, seconds=11)
    assert replay == []


def test_unwatched_dependency_does_not_block_an_existing_group_split() -> None:
    """A dependency without checks has no evidence to wait for."""
    graph = (node("controller"), *_graph()[1:])
    old = Engine(SETTINGS)
    old.register_many(graph, T0)
    events = old.ingest_many(
        [obs(name, Status.FAIL, T0) for name in ("one", "two", "three")], T0
    )
    assert summary(events) == [("opened", "controller")]
    restored = Engine(replace(SETTINGS, coalesce_count=None))
    restored.register_many(graph, at(1))
    assert summary(restored.restore(old.snapshot(), at(1))) == [
        ("opened", "one"),
        ("opened", "two"),
        ("opened", "three"),
        ("split", "controller"),
    ]


def test_unknown_restored_members_wait_for_evidence_before_splitting() -> None:
    """Expired evidence neither clears the group nor fabricates child faults."""
    original, group = _group(ttl=10)
    restored, events = _restore(original, seconds=11, ttl=10)
    assert len(events) == 1
    assert isinstance(events[0], EpisodeUpdated)
    assert events[0].episode.episode_id == group.episode_id
    assert events[0].episode.status is Status.UNKNOWN
    assert events[0].episode.reasons == ()
    assert events[0].episode.recorded == {"one", "two", "three"}
    events = restored.ingest_many(
        [
            obs("controller", Status.PASS, at(12)),
            obs("one", Status.FAIL, at(12)),
            obs("two", Status.FAIL, at(12)),
        ],
        at(12),
    )
    assert summary(events) == [("updated", "controller")]
    _, replay = _restore(restored, seconds=13, ttl=10)
    assert replay == []
    events = restored.ingest(obs("three", Status.PASS, at(14)), at(14))
    assert summary(events) == [
        ("opened", "one"),
        ("opened", "two"),
        ("split", "controller"),
    ]
    assert isinstance(events[-1], EpisodeResolved)
    assert events[-1].episode.episode_id == group.episode_id


def test_unknown_members_can_split_when_stale_hold_expires() -> None:
    """The existing stale rules provide the eventual findings, without invention."""
    original, _ = _group(ttl=10)
    restored, _ = _restore(original, seconds=11, ttl=10)
    events = restored.advance(at(70))
    opened = [event for event in events if isinstance(event, EpisodeOpened)]
    assert {event.episode.anchor for event in opened} == {"one", "two", "three"}
    assert all(event.episode.status is Status.UNKNOWN for event in opened)
    assert all(
        finding.reason == "stale"
        for event in opened
        for finding in event.episode.reasons
    )


def test_unknown_group_members_survive_parent_failure_and_recovery() -> None:
    """A real parent outage cannot erase unresolved restored member evidence."""
    original, _ = _group(ttl=10)
    engine = Engine(
        replace(
            SETTINGS,
            coalesce_count=None,
            settle=timedelta(0),
            rejoin_grace=timedelta(seconds=10),
        )
    )
    engine.register_many(_graph(ttl=10), at(11))
    engine.restore(original.snapshot(), at(11))
    engine.register_many(_graph(), at(12))
    events = engine.ingest(obs("controller", Status.FAIL, at(13)), at(13))
    parent = events[0]
    assert isinstance(parent, EpisodeOpened)
    assert parent.episode.recorded == {"one", "two", "three"}
    assert [finding.node_id for finding in parent.episode.reasons] == ["controller"]
    events = engine.ingest(obs("controller", Status.PASS, at(14)), at(14))
    assert summary(events) == [("updated", "controller")]
    assert isinstance(events[0], EpisodeUpdated)
    assert events[0].episode.recorded == {"one", "two", "three"}
    assert events[0].episode.reasons == ()
    assert engine.advance(at(24)) == []
    events = engine.ingest_many(
        [obs(name, Status.FAIL, at(25)) for name in ("one", "two", "three")], at(25)
    )
    assert summary(events) == [
        ("opened", "one"),
        ("opened", "two"),
        ("opened", "three"),
        ("split", "controller"),
    ]
    assert {
        event.split_from for event in events if isinstance(event, EpisodeOpened)
    } == {parent.episode.episode_id}


@pytest.mark.parametrize(
    ("grace", "before_pass", "pass_at", "final_at"),
    [
        pytest.param(0, 1, 2, 2, id="zero-grace"),
        pytest.param(10, 11, 12, 12, id="unknown-outlasts-grace"),
        pytest.param(10, 1, 2, 11, id="pass-before-grace"),
    ],
)
def test_transient_unknown_parent_preserves_split_history_and_controls(
    grace: int, before_pass: int, pass_at: int, final_at: int
) -> None:
    """Reload's unknown interval cannot discard ownership before actual recovery."""
    graph = (
        node("controller", checks=[check(clear_hold=0, ttl=None, unknown_hold=900)]),
        *(
            node(
                name,
                "controller",
                checks=[check(clear_hold=0, ttl=None, unknown_hold=900)],
            )
            for name in ("one", "two")
        ),
    )
    settings = replace(
        SETTINGS,
        coalesce_count=None,
        settle=timedelta(0),
        rejoin_grace=timedelta(seconds=grace),
    )
    engine = Engine(settings)
    engine.register_many(graph, T0)
    events = engine.ingest_many(
        [
            obs("controller", Status.FAIL, T0),
            obs("one", Status.WARN, T0),
            obs("two", Status.WARN, T0),
        ],
        T0,
    )
    source = events[0]
    assert isinstance(source, EpisodeOpened)
    policy = _policy(loudness=Loudness.URGENT)
    _handle(policy, events, 0)
    policy.acknowledge(source.episode.episode_id, T0, actor_id="resident")
    policy.shelve(source.episode.episode_id, at(100), T0)
    unknown = engine.ingest(obs("controller", Status.UNKNOWN, at(1)), at(1))
    _handle(policy, unknown, 1)
    assert summary(unknown) == [("updated", "controller")]
    assert isinstance(unknown[0], EpisodeUpdated)
    assert unknown[0].episode.recorded == {"one", "two"}
    assert engine.advance(at(before_pass)) == []
    restored = Engine(settings)
    restored.register_many(graph, at(before_pass))
    assert (
        restored.restore(json.loads(json.dumps(engine.snapshot())), at(before_pass))
        == []
    )
    restored_policy = _policy(loudness=Loudness.URGENT)
    restored_policy.restore(json.loads(json.dumps(policy.snapshot())), at(before_pass))
    events = restored.ingest(obs("controller", Status.PASS, at(pass_at)), at(pass_at))
    events.extend(restored.advance(at(final_at)))
    assert summary(events) == [
        ("opened", "one"),
        ("opened", "two"),
        ("split", "controller"),
    ]
    opened = [event for event in events if isinstance(event, EpisodeOpened)]
    assert {event.split_from for event in opened} == {source.episode.episode_id}
    assert isinstance(events[-1], EpisodeResolved)
    assert events[-1].split_into == tuple(event.episode.episode_id for event in opened)
    deliveries = _handle(restored_policy, events, final_at)
    assert all(isinstance(item, ResolutionNotice) or item.silent for item in deliveries)
    acknowledgments = [
        restored_policy.acknowledgment(event.episode.episode_id) for event in opened
    ]
    assert all(value is not None for value in acknowledgments)
    assert {value.actor_id for value in acknowledgments if value is not None} == {
        "resident"
    }
    assert {value.at for value in acknowledgments if value is not None} == {T0}
    first = opened[0].episode.episode_id
    assert restored_policy.rearm(first, at(final_at + 1), CONTEXT) == []
    assert restored_policy.explain(first)["pending"] == {"owner": at(100).isoformat()}


@pytest.mark.parametrize("rejoin_seconds", [0, 10])
@pytest.mark.parametrize("recovered_status", [Status.PASS, Status.WARN])
def test_actual_dependency_failure_splits_only_after_rejoin(
    rejoin_seconds: int, recovered_status: Status
) -> None:
    """A real outage remains grouped, then its remaining faults regain controls."""
    engine = Engine(
        replace(
            SETTINGS,
            coalesce_count=None,
            rejoin_grace=timedelta(seconds=rejoin_seconds),
        )
    )
    engine.register_many(_graph(), T0)
    opened = engine.ingest_many(
        [obs(item.node_id, Status.FAIL, T0) for item in _graph()], T0
    )
    assert summary(opened) == [("opened", "controller")]
    source = opened[0]
    assert isinstance(source, EpisodeOpened)
    events = engine.ingest(obs("controller", recovered_status, at(1)), at(1))
    events.extend(engine.advance(at(1 + rejoin_seconds)))
    children = [event for event in events if isinstance(event, EpisodeOpened)]
    assert {event.episode.anchor for event in children} == {"one", "two", "three"}
    assert {event.split_from for event in children} == {source.episode.episode_id}
    assert all(
        not event.episode.recorded
        for event in events
        if isinstance(event, EpisodeUpdated)
        and event.episode.updated_at == at(1 + rejoin_seconds)
    )
    assert not any(
        isinstance(event, EpisodeResolved) and event.resolution == "cleared"
        for event in events
    )


def test_split_preserves_pending_deadline_and_independent_controls() -> None:
    """Existing pending work keeps its due time; pausing one successor is local."""
    original, group = _group()
    policy = _policy()
    assert policy.handle(EpisodeOpened(episode=group), T0, CONTEXT) == []
    _, events = _restore(original)
    assert _handle(policy, events, 10) == []
    children = [event.episode for event in events if isinstance(event, EpisodeOpened)]
    policy.shelve(children[0].episode_id, at(100), at(11))
    assert policy.advance(at(29), CONTEXT) == []
    deliveries = policy.advance(at(30), CONTEXT)
    assert {delivery.episode_id for delivery in deliveries} == {
        child.episode_id for child in children[1:]
    }
    assert all(
        isinstance(delivery, Notification) and not delivery.silent
        for delivery in deliveries
    )
    assert policy.explain(children[0].episode_id)["pending"] == {
        "owner": at(100).isoformat()
    }


def test_split_preserves_acknowledgment_shelf_and_reminder_history() -> None:
    """Old controls retain their actor and expiry, without covering future faults."""
    original, group = _group()
    policy = _policy(loudness=Loudness.URGENT)
    policy.handle(EpisodeOpened(episode=group), T0, CONTEXT)
    policy.acknowledge(group.episode_id, at(2), actor_id="resident")
    policy.shelve(group.episode_id, at(100), at(3))
    restored = _policy(loudness=Loudness.URGENT)
    restored.restore(json.loads(json.dumps(policy.snapshot())), at(10))
    _, events = _restore(original)
    deliveries = _handle(restored, events, 10)
    assert all(isinstance(item, ResolutionNotice) or item.silent for item in deliveries)
    children = [event.episode for event in events if isinstance(event, EpisodeOpened)]
    acknowledgments = [restored.acknowledgment(child.episode_id) for child in children]
    assert all(value is not None for value in acknowledgments)
    assert {value.at for value in acknowledgments if value is not None} == {at(2)}
    assert {value.actor_id for value in acknowledgments if value is not None} == {
        "resident"
    }
    assert restored.rearm(children[0].episode_id, at(11), CONTEXT) == []
    assert restored.explain(children[0].episode_id)["pending"] == {
        "owner": at(100).isoformat()
    }
    restored.unshelve(children[0].episode_id, at(12), CONTEXT)
    assert restored.acknowledgment(children[0].episode_id) is None
    assert restored.acknowledgment(children[1].episode_id) is not None
    later = replace(
        children[0], episode_id="later", opened_at=at(15), updated_at=at(15)
    )
    deliveries = restored.handle(EpisodeOpened(episode=later), at(15), CONTEXT)
    assert len(deliveries) == 1
    assert isinstance(deliveries[0], Notification)
    assert not deliveries[0].silent
    assert restored.acknowledgment("later") is None


def test_split_reminder_deadline_does_not_restart() -> None:
    """Silent replacements retain the original recipient reminder clock."""
    original, group = _group()
    policy = _policy(loudness=Loudness.URGENT)
    policy.handle(EpisodeOpened(episode=group), T0, CONTEXT)
    _, events = _restore(original)
    _handle(policy, events, 10)
    assert policy.advance(at(59), CONTEXT) == []
    deliveries = policy.advance(at(60), CONTEXT)
    assert len(deliveries) == 3
    assert all(
        isinstance(item, Notification) and item.cause == "remind" for item in deliveries
    )


def test_older_independent_failure_keeps_its_identity_after_parent_recovery() -> None:
    """An unrelated pre-existing child issue is neither duplicated nor controlled."""
    engine = Engine(
        replace(
            SETTINGS,
            coalesce_count=None,
            settle=timedelta(0),
            rejoin_grace=timedelta(0),
        )
    )
    engine.register_many(_graph(), T0)
    events = engine.ingest_many(
        [
            obs("controller", Status.PASS, T0),
            obs("one", Status.FAIL, T0),
            obs("two", Status.PASS, T0),
            obs("three", Status.PASS, T0),
        ],
        T0,
    )
    older = events[0]
    assert isinstance(older, EpisodeOpened)
    events = engine.ingest_many(
        [obs(name, Status.FAIL, at(10)) for name in ("controller", "two", "three")],
        at(10),
    )
    assert summary(events) == [("opened", "controller")]
    events = engine.ingest(obs("controller", Status.PASS, at(11)), at(11))
    assert summary(events) == [
        ("opened", "two"),
        ("opened", "three"),
        ("split", "controller"),
    ]
    recovered = engine.ingest(obs("one", Status.PASS, at(12)), at(12))
    assert len(recovered) == 1
    assert isinstance(recovered[0], EpisodeResolved)
    assert recovered[0].episode.episode_id == older.episode.episode_id


@pytest.mark.parametrize(
    ("recoveries", "predecessor", "resolutions_expected"),
    [
        pytest.param(((1, ("a", "b")),), None, ["split", "split"], id="together"),
        pytest.param(
            ((1, ("a",)), (3, ("b",))), "b", ["cleared", "split"], id="staggered"
        ),
    ],
)
def test_shared_dependent_gets_one_successor_when_multiple_roots_recover(
    recoveries: tuple[tuple[int, tuple[str, ...]], ...],
    predecessor: str | None,
    resolutions_expected: list[str],
) -> None:
    """Overlapping root scopes never create duplicate child identities."""
    graph = (
        node("a", checks=[check(clear_hold=0, ttl=None)]),
        node("b", checks=[check(clear_hold=0, ttl=None)]),
        node("child", "a", "b", checks=[check(clear_hold=0, ttl=None)]),
    )
    engine = Engine(
        replace(SETTINGS, coalesce_count=None, rejoin_grace=timedelta(seconds=1))
    )
    engine.register_many(graph, T0)
    events = engine.ingest_many(
        [obs(item.node_id, Status.FAIL, T0) for item in graph], T0
    )
    roots = {
        event.episode.anchor: event.episode
        for event in events
        if isinstance(event, EpisodeOpened)
    }
    assert set(roots) == {"a", "b"}
    events = []
    for second, names in recoveries:
        events.extend(
            engine.ingest_many(
                [obs(name, Status.PASS, at(second)) for name in names], at(second)
            )
        )
        events.extend(engine.advance(at(second + 1)))
    opened = [event for event in events if isinstance(event, EpisodeOpened)]
    assert len(opened) == 1
    assert opened[0].episode.anchor == "child"
    predecessors: dict[str | None, str | None] = {
        None: None,
        **{name: episode.episode_id for name, episode in roots.items()},
    }
    assert opened[0].split_from == predecessors[predecessor]
    resolutions = [event for event in events if isinstance(event, EpisodeResolved)]
    assert len(resolutions) == 2
    assert [event.resolution for event in resolutions] == resolutions_expected
    assert resolutions[-1].split_into == (opened[0].episode.episode_id,)
    assert engine.advance(at(5)) == []


def test_split_preserves_independent_route_timing() -> None:
    """Immediate, pending and scheduled routes retain their separate obligations."""
    original, group = _group()
    policy = Policy(
        PolicyConfig(
            timezone=UTC,
            batch=timedelta(seconds=30),
            recipients={"owner": Recipient(channels=("phone",))},
            digests={"report": Digest(at=time(12, 1), to="owner")},
            rules=(
                Rule(
                    route="immediate",
                    match=Match(),
                    loudness=Loudness.URGENT,
                    to=("owner",),
                ),
                Rule(
                    route="batched",
                    match=Match(),
                    loudness=Loudness.NOTIFY,
                    to=("owner",),
                ),
                Rule(
                    route="scheduled",
                    match=Match(),
                    loudness=Loudness.DIGEST,
                    digest="report",
                ),
            ),
        )
    )
    assert [
        item.route for item in policy.handle(EpisodeOpened(episode=group), T0, CONTEXT)
    ] == ["immediate"]
    _, events = _restore(original)
    deliveries = _handle(policy, events, 10)
    assert {item.route for item in deliveries} == {"immediate"}
    assert all(isinstance(item, ResolutionNotice) or item.silent for item in deliveries)
    assert [item.route for item in policy.advance(at(30), CONTEXT)] == ["batched"] * 3
    assert [item.route for item in policy.advance(at(60), CONTEXT)] == ["scheduled"] * 3


@pytest.mark.parametrize("child_loudness", [Loudness.NOTIFY, Loudness.RECORD])
def test_split_does_not_inherit_unauthorized_recipient(
    child_loudness: Loudness,
) -> None:
    """Child matching removes the old recipient and applies its own instruction."""
    original, group = _group()
    policy = Policy(
        PolicyConfig(
            timezone=UTC,
            batch=timedelta(seconds=30),
            recipients={
                "old": Recipient(channels=("old_phone",)),
                "new": Recipient(channels=("new_phone",)),
            },
            digests={},
            rules=(
                Rule(
                    match=Match(reason=frozenset({"dependents_failing"})),
                    loudness=Loudness.URGENT,
                    to=("old",),
                ),
                Rule(match=Match(), loudness=child_loudness, to=("new",)),
            ),
        )
    )
    policy.handle(EpisodeOpened(episode=group), T0, CONTEXT)
    _, events = _restore(original)
    assert _handle(policy, events, 10) == [
        ResolutionNotice(
            episode_id=group.episode_id,
            recipient="old",
            channels=("old_phone",),
            resolution="split",
        )
    ]
    deliveries = policy.advance(at(40), CONTEXT)
    expected_count = 3 if child_loudness is Loudness.NOTIFY else 0
    assert len(deliveries) == expected_count
    assert all(item.recipient == "new" for item in deliveries)
