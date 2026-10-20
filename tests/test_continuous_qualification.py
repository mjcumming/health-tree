"""Continuous evidence and qualified routes preserve independent attention."""

from dataclasses import replace
from datetime import UTC, timedelta
import json
from typing import Any

import pytest

from health_tree.engine import Engine
from health_tree.policy import Policy
from health_tree.types import (
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Loudness,
    Match,
    Notification,
    PolicyConfig,
    PolicyContext,
    Recipient,
    Rule,
    Status,
)
from tests.engine_helpers import SETTINGS, T0, at, check, node, obs, summary


@pytest.mark.parametrize("continuous", [False, True])
def test_unknown_interrupts_only_continuous_worsening(continuous: bool) -> None:
    """A missing report cannot bridge a continuous worsening interval."""
    engine = Engine(SETTINGS)
    engine.register(
        node("camera", checks=[check(raise_hold=60, continuous=continuous)]), T0
    )
    engine.ingest(obs("camera", Status.PASS, T0), T0)
    engine.ingest(obs("camera", Status.WARN, at(1)), at(1))
    engine.ingest(obs("camera", Status.UNKNOWN, at(20)), at(20))
    engine.ingest(obs("camera", Status.WARN, at(30)), at(30))
    assert summary(engine.advance(at(61))) == (
        [] if continuous else [("opened", "camera")]
    )
    assert summary(engine.advance(at(90))) == (
        [("opened", "camera")] if continuous else []
    )


@pytest.mark.parametrize("continuous", [False, True])
def test_restore_requires_fresh_continuous_worsening(continuous: bool) -> None:
    """A stopped process does not complete an opted-in worsening interval."""
    graph = node("camera", checks=[check(raise_hold=60, continuous=continuous)])
    engine = Engine(SETTINGS)
    engine.register(graph, T0)
    engine.ingest(obs("camera", Status.PASS, T0), T0)
    engine.ingest(obs("camera", Status.WARN, at(1)), at(1))
    restored = Engine(SETTINGS)
    restored.register(graph, at(100))
    events = restored.restore(json.loads(json.dumps(engine.snapshot())), at(100))
    assert summary(events) == ([] if continuous else [("opened", "camera")])
    restored.ingest(obs("camera", Status.WARN, at(101)), at(101))
    assert restored.advance(at(160)) == []
    assert summary(restored.advance(at(161))) == (
        [("opened", "camera")] if continuous else []
    )


def test_restore_preserves_effective_problem_and_pending_recovery() -> None:
    """Continuous qualification changes neither issue identity nor clearing."""
    graph = node(
        "camera", checks=[check(raise_hold=30, clear_hold=20, continuous=True)]
    )
    engine = Engine(SETTINGS)
    engine.register(graph, T0)
    engine.ingest(obs("camera", Status.WARN, at(1)), at(1))
    opened = engine.advance(at(31))[0]
    assert isinstance(opened, EpisodeOpened)
    engine.ingest(obs("camera", Status.PASS, at(40)), at(40))
    restored = Engine(SETTINGS)
    restored.register(graph, at(50))
    assert restored.restore(engine.snapshot(), at(50)) == []
    resolved = restored.advance(at(60))
    assert summary(resolved) == [("cleared", "camera")]
    assert isinstance(resolved[0], EpisodeResolved)
    assert resolved[0].episode.episode_id == opened.episode.episode_id


def test_expiry_interrupts_continuous_worsening() -> None:
    """Expired evidence cannot qualify without another observed worsening."""
    engine = Engine(SETTINGS)
    engine.register(
        node("camera", checks=[check(raise_hold=60, ttl=10, continuous=True)]), T0
    )
    engine.ingest(obs("camera", Status.WARN, at(1)), at(1))
    assert engine.advance(at(61)) == []
    assert engine.explain("camera").findings == ()
    engine.ingest(obs("camera", Status.WARN, at(62)), at(62))
    assert engine.next_deadline() == at(72)


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_problem_qualifies_route_at_dependent_deadline(reverse: bool) -> None:
    """Affected membership alone cannot bypass the dependent's raise hold."""
    engine = Engine(replace(SETTINGS, settle=timedelta(0)))
    engine.register_many(
        [
            node("integration", checks=[check(ttl=None)]),
            node(
                "camera",
                "integration",
                checks=[check(raise_hold=60, clear_hold=0, continuous=True, ttl=None)],
            ),
        ],
        T0,
    )
    engine.ingest_many(
        [obs("integration", Status.PASS, T0), obs("camera", Status.PASS, T0)], T0
    )
    policy = Policy(
        PolicyConfig(
            batch=timedelta(0),
            timezone=UTC,
            recipients={"owner": Recipient(channels=("phone",))},
            digests={},
            rules=(
                Rule(
                    match=Match(
                        nodes=frozenset({"camera"}),
                        qualified_nodes=frozenset({"camera"}),
                        checks=frozenset({"state"}),
                    ),
                    loudness=Loudness.URGENT,
                    to=("owner",),
                ),
                Rule(match=Match(), loudness=Loudness.RECORD),
            ),
        )
    )
    observations = [
        obs("integration", Status.FAIL, at(1)),
        obs("camera", Status.WARN, at(1)),
    ]
    events = engine.ingest_many(
        list(reversed(observations)) if reverse else observations, at(1)
    )
    assert len(events) == 1
    opened = events[0]
    assert isinstance(opened, EpisodeOpened)
    assert opened.episode.qualified_nodes == frozenset({"integration"})
    assert policy.handle(opened, at(1), PolicyContext()) == []
    assert engine.advance(at(60)) == []
    updated = engine.advance(at(61))[0]
    assert isinstance(updated, EpisodeUpdated)
    assert updated.episode.episode_id == opened.episode.episode_id
    assert updated.episode.qualified_nodes == frozenset({"integration", "camera"})
    assert [finding.node_id for finding in updated.episode.reasons] == ["integration"]
    initial = policy.handle(updated, at(61), PolicyContext())
    assert len(initial) == 1
    assert isinstance(initial[0], Notification)
    assert not initial[0].silent
    uncertain = engine.ingest(obs("camera", Status.UNKNOWN, at(62)), at(62))[0]
    assert isinstance(uncertain, EpisodeUpdated)
    assert uncertain.episode.qualified_nodes == frozenset({"integration", "camera"})
    unknown_messages = policy.handle(uncertain, at(62), PolicyContext())
    assert all(
        isinstance(item, Notification) and item.silent for item in unknown_messages
    )
    assert engine.ingest(obs("camera", Status.WARN, at(63)), at(63)) == []
    requalified = engine.advance(at(123))[0]
    assert isinstance(requalified, EpisodeUpdated)
    resumed = policy.handle(requalified, at(123), PolicyContext())
    assert all(isinstance(item, Notification) and item.silent for item in resumed)
    assert requalified.episode.episode_id == opened.episode.episode_id
    recovered = engine.ingest(obs("camera", Status.PASS, at(124)), at(124))[0]
    assert isinstance(recovered, EpisodeUpdated)
    assert recovered.episode.qualified_nodes == frozenset({"integration"})
    policy.handle(recovered, at(124), PolicyContext())
    assert engine.ingest(obs("camera", Status.WARN, at(125)), at(125)) == []
    new_outage = engine.advance(at(185))[0]
    new_messages = policy.handle(new_outage, at(185), PolicyContext())
    assert len(new_messages) == 1
    assert isinstance(new_messages[0], Notification)
    assert not new_messages[0].silent


def test_old_snapshot_rebuilds_qualified_scope_without_new_episode() -> None:
    """Missing additive episode fields preserve saved identities and controls."""
    graph = node("camera", checks=[check(ttl=None)])
    engine = Engine(SETTINGS)
    engine.register(graph, T0)
    opened = engine.ingest(obs("camera", Status.WARN, T0), T0)[0]
    assert isinstance(opened, EpisodeOpened)
    config = PolicyConfig(
        batch=timedelta(0),
        timezone=UTC,
        recipients={"owner": Recipient(channels=("phone",))},
        digests={},
        rules=(
            Rule(
                match=Match(qualified_nodes=frozenset({"camera"})),
                loudness=Loudness.URGENT,
                to=("owner",),
            ),
            Rule(match=Match(), loudness=Loudness.RECORD),
        ),
    )
    policy = Policy(config)
    assert len(policy.handle(opened, T0, PolicyContext())) == 1
    policy_snapshot: dict[str, Any] = json.loads(json.dumps(policy.snapshot()))
    policy_snapshot["tracked"][0]["episode"].pop("qualified_nodes")
    snapshot: dict[str, Any] = json.loads(json.dumps(engine.snapshot()))
    snapshot["episodes"][0]["view"].pop("qualified_nodes")
    restored = Engine(SETTINGS)
    restored.register(graph, at(1))
    events = restored.restore(snapshot, at(1))
    assert len(events) == 1
    assert isinstance(events[0], EpisodeUpdated)
    assert events[0].episode.episode_id == opened.episode.episode_id
    assert events[0].episode.qualified_nodes == frozenset({"camera"})
    restored_policy = Policy(config)
    restored_policy.restore(policy_snapshot, at(1))
    messages = restored_policy.handle(events[0], at(1), PolicyContext())
    assert len(messages) == 1
    assert isinstance(messages[0], Notification)
    assert messages[0].silent
    assert restored_policy.explain(opened.episode.episode_id)["sent_to"] == ["owner"]


def test_pending_and_stale_unknown_never_qualify_affected_scope() -> None:
    """Potential impact and a stale reason establish no warning or failure."""
    engine = Engine(SETTINGS)
    engine.register(
        node("camera", checks=[check(raise_hold=60, unknown_hold=10, continuous=True)]),
        T0,
    )
    opened = engine.advance(at(10))[0]
    assert isinstance(opened, EpisodeOpened)
    assert opened.episode.qualified_nodes == frozenset()
    engine.ingest(obs("camera", Status.WARN, at(11)), at(11))
    assert engine.advance(at(70)) == []
    updated = engine.advance(at(71))[0]
    assert isinstance(updated, EpisodeUpdated)
    assert updated.episode.qualified_nodes == frozenset({"camera"})


def test_current_worsening_cannot_become_stale_during_qualification() -> None:
    """A fresh known warning replaces missing evidence while its hold runs."""
    engine = Engine(SETTINGS)
    engine.register(
        node("camera", checks=[check(raise_hold=60, unknown_hold=30, continuous=True)]),
        T0,
    )
    engine.ingest(obs("camera", Status.PASS, T0), T0)
    engine.ingest(obs("camera", Status.WARN, at(1)), at(1))
    engine.ingest(obs("camera", Status.UNKNOWN, at(20)), at(20))
    engine.ingest(obs("camera", Status.WARN, at(25)), at(25))
    assert engine.next_deadline() == at(85)
    assert engine.advance(at(84)) == []
    assert summary(engine.advance(at(85))) == [("opened", "camera")]


def test_new_unknown_after_pending_worsening_starts_its_own_unknown_hold() -> None:
    """Separate evidence gaps cannot borrow the earlier missing interval."""
    engine = Engine(SETTINGS)
    engine.register(
        node("camera", checks=[check(raise_hold=60, unknown_hold=30, continuous=True)]),
        T0,
    )
    engine.ingest(obs("camera", Status.PASS, T0), T0)
    engine.ingest(obs("camera", Status.UNKNOWN, at(20)), at(20))
    engine.ingest(obs("camera", Status.WARN, at(25)), at(25))
    engine.ingest(obs("camera", Status.UNKNOWN, at(30)), at(30))
    engine.ingest(obs("camera", Status.UNKNOWN, at(35)), at(35))
    assert engine.next_deadline() == at(60)
    assert engine.advance(at(59)) == []
    opened = engine.advance(at(60))[0]
    assert isinstance(opened, EpisodeOpened)
    assert opened.episode.reasons[0].reason == "stale"
    assert opened.episode.qualified_nodes == frozenset()
