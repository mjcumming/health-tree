"""Awareness and cancellation preserve evidence, routing, and restart semantics."""

from datetime import UTC, datetime, time, timedelta
import json

from hypothesis import given, strategies as st
import pytest

from health_tree.types import (
    Acknowledgment,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Loudness,
    Match,
    QuietHours,
    Rule,
    Status,
)
from tests.engine_helpers import T0, at
from tests.test_policy import CONTEXT, _episode, _kinds, _policy


def rule(
    *,
    loudness: Loudness = Loudness.NOTIFY,
    digest: str | None = None,
    require_acknowledgment: bool = True,
    escalate_after: timedelta | None = timedelta(minutes=10),
) -> Rule:
    """Create an opted-in repeating rule for operator scenarios."""
    return Rule(
        match=Match(),
        loudness=loudness,
        to=("michael",),
        digest=digest,
        remind_every=timedelta(minutes=5),
        escalate_after=escalate_after,
        require_acknowledgment=require_acknowledgment,
    )


@given(actor=st.one_of(st.none(), st.text(max_size=30)))
def test_first_acknowledgment_is_idempotent(actor: str | None) -> None:
    """Awareness is shared and its first actor survives a JSON round trip."""
    policy = _policy(rule())
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    policy.acknowledge("e1", at(1), actor_id=actor)
    assert policy.acknowledge("e1", at(2), actor_id="second") == []
    restored = _policy(rule())
    restored.restore(json.loads(json.dumps(policy.snapshot())), at(3))
    expected = Acknowledgment(episode_id="e1", at=at(1), actor_id=actor)
    assert restored.acknowledgment("e1") == expected
    assert restored.explain("e1")["acknowledgment"] == {
        "episode_id": "e1",
        "at": at(1).isoformat(),
        "actor_id": actor,
    }
    assert restored.advance(at(1200), CONTEXT) == []


def test_activation_preserves_acknowledgment_and_resolution_recipients() -> None:
    """Restarting attention cannot erase awareness or the recipient's all-clear."""
    policy = _policy(rule())
    episode = _episode()
    policy.handle(EpisodeOpened(episode=episode), T0, CONTEXT)
    policy.advance(at(30), CONTEXT)
    policy.acknowledge("e1", at(31))
    assert policy.activate(at(32), CONTEXT) == []
    assert policy.next_deadline() == datetime(2026, 9, 25, 8, tzinfo=UTC)
    assert _kinds(
        policy.handle(
            EpisodeResolved(episode=episode, resolution="cleared"), at(40), CONTEXT
        )
    ) == [("resolution", "cleared")]
    with pytest.raises(KeyError):
        policy.acknowledgment("e1")


def test_new_urgent_rule_is_not_suppressed_by_previous_awareness() -> None:
    """Only opted-in rules stop, so a newly reported independent reason can page."""
    policy = _policy(
        Rule(
            match=Match(reason=frozenset({"danger"})),
            loudness=Loudness.URGENT,
            to=("michael",),
        ),
        rule(),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    policy.acknowledge("e1", at(1))
    result = policy.handle(
        EpisodeUpdated(episode=_episode(reason="danger")), at(2), CONTEXT
    )
    assert _kinds(result) == [("urgent", "")]


@pytest.mark.parametrize(
    ("required", "count"),
    [pytest.param(True, 0, id="opted-in"), pytest.param(False, 1, id="ordinary")],
)
def test_acknowledgment_only_stops_opted_in_digests(required: bool, count: int) -> None:
    """A pending digest follows its rule's acknowledgment contract."""
    policy = _policy(
        rule(
            loudness=Loudness.DIGEST,
            digest="morning",
            require_acknowledgment=required,
            escalate_after=None,
        )
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    policy.acknowledge("e1", at(1))
    assert len(policy.advance(datetime(2026, 9, 25, 8, tzinfo=UTC), CONTEXT)) == count


@pytest.mark.parametrize("version", [1, 2])
def test_old_snapshots_restore_without_awareness(version: int) -> None:
    """Released snapshots acquire no implicit acknowledgment."""
    policy = _policy(rule())
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    state = json.loads(json.dumps(policy.snapshot()))
    state["schema_version"] = version
    del state["tracked"][0]["acknowledgment"]
    del state["tracked"][0]["pending"][0]["resume_at"]
    restored = _policy(rule())
    restored.restore(state, at(1))
    assert restored.acknowledgment("e1") is None
    assert _kinds(restored.advance(at(30), CONTEXT)) == [("notify", "")]


def test_unshelve_preserves_batch_and_quiet_hours() -> None:
    """Ending a shelf never overrides other reasons a delivery must wait."""
    policy = _policy(rule(), quiet=QuietHours(start=time(12), end=time(13)))
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    policy.shelve("e1", at(7200), at(1))
    assert policy.unshelve("e1", at(2), CONTEXT) == []
    assert policy.advance(at(30), CONTEXT) == []
    policy.acknowledge("e1", at(31))
    assert policy.advance(at(3600), CONTEXT) == []


def test_unshelve_releases_urgent_work_after_restore() -> None:
    """A shelf-held escalation retains its original due time across restart."""
    policy = _policy(rule())
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    policy.advance(at(30), CONTEXT)
    policy.shelve("e1", at(7200), at(31))
    policy.advance(at(600), CONTEXT)
    restored = _policy(rule())
    restored.restore(policy.snapshot(), at(601))
    assert _kinds(restored.unshelve("e1", at(602), CONTEXT)) == [("urgent", "")]
    assert restored.unshelve("e1", at(603), CONTEXT) == []


@pytest.mark.parametrize("action", ["acknowledge", "unshelve"])
def test_unknown_control_target_does_not_advance_clock(action: str) -> None:
    """Reject a stale id before advancing policy time."""
    policy = _policy(rule())
    arguments = {
        "acknowledge": ("missing", at(20)),
        "unshelve": ("missing", at(20), CONTEXT),
    }
    with pytest.raises(KeyError):
        getattr(policy, action)(*arguments[action])
    assert (
        policy.handle(EpisodeOpened(episode=_episode(status=Status.FAIL)), T0, CONTEXT)
        == []
    )
