"""Policy behavior the fixtures cannot express: shelving, reminders, restore."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from health_tree.policy import Policy
from health_tree.types import (
    Delivery,
    Digest,
    Episode,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Finding,
    Importance,
    Loudness,
    Match,
    Notification,
    PolicyConfig,
    PolicyContext,
    ProbeRequested,
    QuietHours,
    Recipient,
    ResolutionNotice,
    Rule,
    Status,
)
from tests.engine_helpers import T0, at

CONTEXT = PolicyContext()
HOUR = timedelta(hours=1)


def _episode(
    episode_id: str = "e1",
    *,
    status: Status = Status.FAIL,
    reason: str = "fault",
    labels: dict[str, str] | None = None,
    importance: Importance = Importance.NORMAL,
) -> Episode:
    return Episode(
        episode_id=episode_id,
        form="root",
        anchor="device",
        status=status,
        reasons=(
            Finding(
                node_id="device",
                check_id="state",
                status=status,
                reason=reason,
                since=T0,
                labels=labels or {},
            ),
        ),
        recorded=frozenset(),
        impact=frozenset(),
        importance=importance,
        opened_at=T0,
        updated_at=T0,
    )


def _policy(*rules: Rule, quiet: QuietHours | None = None, zone: str = "UTC") -> Policy:
    return Policy(
        PolicyConfig(
            batch=timedelta(seconds=30),
            timezone=UTC if zone == "UTC" else ZoneInfo(zone),
            recipients={"michael": Recipient(channels=("phone",), quiet_hours=quiet)},
            digests={"morning": Digest(at=time(8), to="michael")},
            rules=rules
            or (Rule(match=Match(), loudness=Loudness.URGENT, to=("michael",)),),
        )
    )


def _kinds(deliveries: Sequence[Delivery]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for delivery in deliveries:
        match delivery:
            case Notification(loudness=loudness, silent=silent):
                result.append((loudness.value + ("-silent" if silent else ""), ""))
            case ResolutionNotice(resolution=resolution):
                result.append(("resolution", resolution))
    return result


def test_probes_and_unknown_episodes_deliver_nothing() -> None:
    """A probe is for the adapter; an unseen resolution has no recipients."""
    policy = _policy()
    assert policy.next_deadline() is None
    assert policy.handle(ProbeRequested(node_id="hub"), T0, CONTEXT) == []
    resolved = EpisodeResolved(episode=_episode(), resolution="cleared")
    assert policy.handle(resolved, T0, CONTEXT) == []


def test_an_update_for_an_unseen_episode_is_an_opening() -> None:
    """After a restore gap, the first update announces the episode."""
    policy = _policy()
    deliveries = policy.handle(EpisodeUpdated(episode=_episode()), T0, CONTEXT)
    assert _kinds(deliveries) == [("urgent", "")]


def test_same_loudness_updates_replace_silently() -> None:
    """RFP 7: an update that does not raise loudness makes no noise."""
    policy = _policy()
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    update = EpisodeUpdated(episode=_episode(reason="other"))
    assert _kinds(policy.handle(update, at(5), CONTEXT)) == [("urgent-silent", "")]
    assert policy.advance(at(6), CONTEXT) == []


def test_lowering_to_record_drops_pending_and_stays_quiet() -> None:
    """A pending notify is dropped when the episode no longer warrants one."""
    policy = _policy(
        Rule(
            match=Match(status=frozenset({Status.FAIL})),
            loudness=Loudness.NOTIFY,
            to=("michael",),
        ),
        Rule(match=Match(), loudness=Loudness.RECORD),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.next_deadline() == at(30)
    warn = EpisodeUpdated(episode=_episode(status=Status.WARN))
    assert policy.handle(warn, at(10), CONTEXT) == []
    assert policy.advance(at(30), CONTEXT) == []


def test_shelving_holds_every_kind_of_delivery() -> None:
    """Scenario 32: a shelved episode delivers nothing until the shelf ends."""
    policy = _policy(
        Rule(
            match=Match(reason=frozenset({"page"})),
            loudness=Loudness.URGENT,
            to=("michael",),
        ),
        Rule(
            match=Match(reason=frozenset({"note"})),
            loudness=Loudness.NOTIFY,
            to=("michael",),
        ),
        Rule(match=Match(), loudness=Loudness.DIGEST, digest="morning"),
    )
    until = T0 + 24 * HOUR
    for episode_id in ("page", "note", "later"):
        assert policy.shelve(episode_id, until, T0) == []
    for episode_id in ("page", "note", "later"):
        opened = EpisodeOpened(episode=_episode(episode_id, reason=episode_id))
        assert policy.handle(opened, T0, CONTEXT) == []
    assert policy.advance(at(30), CONTEXT) == []
    assert policy.advance(T0 + 20 * HOUR, CONTEXT) == []
    released = policy.advance(until, CONTEXT)
    assert sorted(_kinds(released)) == [("notify", ""), ("urgent", "")]
    assert _kinds(policy.advance(T0 + 44 * HOUR, CONTEXT)) == [("digest", "")]


def test_reminders_repeat_sent_messages() -> None:
    """An open episode is reminded at its rule's interval."""
    policy = _policy(
        Rule(
            match=Match(), loudness=Loudness.URGENT, to=("michael",), remind_every=HOUR
        )
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.next_deadline() == T0 + HOUR
    assert _kinds(policy.advance(T0 + HOUR, CONTEXT)) == [("urgent", "")]
    resolved = EpisodeResolved(episode=_episode(), resolution="cleared")
    assert _kinds(policy.handle(resolved, T0 + 2 * HOUR, CONTEXT)) == [
        ("resolution", "cleared")
    ]


def test_escalation_needs_somewhere_to_go() -> None:
    """A `record` rule with nowhere to deliver stays `record` when it escalates."""
    policy = _policy(Rule(match=Match(), loudness=Loudness.RECORD, escalate_after=HOUR))
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.next_deadline() == T0 + HOUR
    assert policy.advance(T0 + 2 * HOUR, CONTEXT) == []


def test_age_matches_raise_loudness_on_time() -> None:
    """ADR 0010: an age threshold is a deadline, and crossing it makes noise."""
    policy = _policy(
        Rule(match=Match(age=HOUR), loudness=Loudness.URGENT, to=("michael",)),
        Rule(match=Match(), loudness=Loudness.DIGEST, digest="morning"),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.next_deadline() == T0 + HOUR
    assert _kinds(policy.advance(T0 + HOUR, CONTEXT)) == [("urgent", "")]


def test_quiet_hours_that_do_not_wrap_midnight() -> None:
    """Quiet hours inside one day hold `notify` until they end."""
    policy = _policy(
        Rule(match=Match(), loudness=Loudness.NOTIFY, to=("michael",)),
        quiet=QuietHours(start=time(12), end=time(13)),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.advance(at(30), CONTEXT) == []
    assert _kinds(policy.advance(T0 + HOUR, CONTEXT)) == [("notify", "")]


def test_digests_follow_the_policy_time_zone() -> None:
    """08:00 in Chicago is 13:00 UTC in September."""
    policy = _policy(
        Rule(match=Match(), loudness=Loudness.DIGEST, digest="morning"),
        zone="America/Chicago",
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.next_deadline() == T0 + HOUR
    assert _kinds(policy.advance(T0 + HOUR, CONTEXT)) == [("digest", "")]


def test_snapshot_restores_through_json() -> None:
    """A restored policy keeps what it owes and whom it told."""
    rules = (
        Rule(
            match=Match(reason=frozenset({"page"})),
            loudness=Loudness.URGENT,
            to=("michael",),
        ),
        Rule(match=Match(), loudness=Loudness.NOTIFY, to=("michael",)),
    )
    old = _policy(*rules)
    old.handle(EpisodeOpened(episode=_episode("paged", reason="page")), T0, CONTEXT)
    old.handle(EpisodeOpened(episode=_episode("waiting")), T0, CONTEXT)
    old.shelve("other", T0 + HOUR, T0)
    state = json.loads(json.dumps(old.snapshot()))
    new = _policy(*rules)
    new.restore(state, at(10))
    assert new.snapshot() == old.snapshot() | {"now": new.snapshot()["now"]}
    assert _kinds(new.advance(at(30), CONTEXT)) == [("notify", "")]
    resolved = EpisodeResolved(episode=_episode("paged"), resolution="cleared")
    assert _kinds(new.handle(resolved, at(40), CONTEXT)) == [("resolution", "cleared")]
    with pytest.raises(ValueError, match="schema"):
        new.restore({"schema_version": 0}, at(50))


@pytest.mark.parametrize(
    "when",
    [
        pytest.param(T0.replace(tzinfo=None), id="naive"),
        pytest.param(T0.astimezone(ZoneInfo("America/Chicago")), id="not-utc"),
    ],
)
def test_time_must_be_utc(when: datetime) -> None:
    """The policy takes UTC `now`, like the engine."""
    with pytest.raises(ValueError, match="UTC"):
        _policy().advance(when, CONTEXT)


def test_time_must_not_go_backwards() -> None:
    """`now` never decreases."""
    policy = _policy()
    policy.advance(at(10), CONTEXT)
    with pytest.raises(ValueError, match="backwards"):
        policy.advance(at(5), CONTEXT)


def test_a_deadline_is_a_policy_deadline() -> None:
    """`due_within` makes `due_at` minus the window a time to match again."""
    policy = _policy(
        Rule(
            match=Match(due_within=HOUR),
            loudness=Loudness.URGENT,
            to=("michael",),
        ),
        Rule(match=Match(), loudness=Loudness.DIGEST, digest="morning"),
    )
    episode = _episode()
    due = replace(episode.reasons[0], due_at=T0 + 3 * HOUR)
    opened = EpisodeOpened(episode=replace(episode, reasons=(due,)))
    assert policy.handle(opened, T0, CONTEXT) == []
    assert policy.next_deadline() == T0 + 2 * HOUR
    assert _kinds(policy.advance(T0 + 2 * HOUR, CONTEXT)) == [("urgent", "")]


@pytest.mark.parametrize("loudness", [Loudness.NOTIFY, Loudness.URGENT])
def test_shelf_holds_reminders(loudness: Loudness) -> None:
    """Scenario 72: shelving holds a reminder already due."""
    policy = _policy(
        Rule(match=Match(), loudness=loudness, to=("michael",), remind_every=HOUR)
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    policy.advance(at(30), CONTEXT)
    policy.shelve("e1", T0 + 3 * HOUR, at(40))
    assert policy.advance(T0 + 2 * HOUR, CONTEXT) == []
    assert policy.next_deadline() == T0 + 3 * HOUR
    result = policy.advance(T0 + 3 * HOUR, CONTEXT)
    assert isinstance(result[0], Notification)
    assert result[0].cause == "remind"


def test_activation_preserves_age_and_explanation_is_detached() -> None:
    """Scenario 73: attention clocks do not rewrite episode age matches."""
    policy = _policy(
        Rule(
            match=Match(age=HOUR),
            loudness=Loudness.NOTIFY,
            to=("michael",),
            escalate_after=HOUR,
        ),
        Rule(match=Match(), loudness=Loudness.RECORD),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.activate(T0 + 2 * HOUR, CONTEXT) == []
    state = policy.snapshot()
    detail = policy.explain("e1")
    assert detail["loudness"] == "notify"
    assert detail["opened_at"] == T0.isoformat()
    assert detail["attention_since"] == (T0 + 2 * HOUR).isoformat()
    assert detail["rule_index"] == 0
    detail["pending"] = {}
    assert policy.snapshot() == state
    sent = policy.advance(T0 + 2 * HOUR + timedelta(seconds=30), CONTEXT)
    assert isinstance(sent[0], Notification)
    assert sent[0].cause == "activate"
    with pytest.raises(KeyError):
        policy.explain("missing")


def test_record_after_delivery_never_reminds() -> None:
    """Scenario 72: a lower record rule with destinations cannot send reminders."""
    policy = _policy(
        Rule(
            match=Match(age=HOUR),
            loudness=Loudness.RECORD,
            to=("michael",),
            remind_every=HOUR,
        ),
        Rule(match=Match(), loudness=Loudness.URGENT, to=("michael",)),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.advance(T0 + 2 * HOUR, CONTEXT) == []
    assert policy.next_deadline() == T0 + 20 * HOUR


def test_legacy_policy_snapshot_restores() -> None:
    """Schema one has no attention origin or pending delivery cause."""
    policy = _policy(Rule(match=Match(), loudness=Loudness.NOTIFY, to=("michael",)))
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    state = json.loads(json.dumps(policy.snapshot()))
    state["schema_version"] = 1
    for tracked in state["tracked"]:
        del tracked["attention_since"]
        del tracked["sent_at"]
        for pending in tracked["pending"]:
            del pending["cause"]
    restored = _policy(Rule(match=Match(), loudness=Loudness.NOTIFY, to=("michael",)))
    restored.restore(state, at(10))
    assert _kinds(restored.advance(at(30), CONTEXT)) == [("notify", "")]


def test_restore_crossing_escalation_emits_once() -> None:
    """Scenario 73: downtime cannot silently consume an escalation threshold."""
    rules = (
        Rule(
            match=Match(),
            loudness=Loudness.NOTIFY,
            to=("michael",),
            escalate_after=HOUR,
        ),
    )
    old = _policy(*rules)
    old.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    old.advance(at(30), CONTEXT)
    new = _policy(*rules)
    new.restore(old.snapshot(), T0 + 2 * HOUR)
    result = new.advance(T0 + 2 * HOUR, CONTEXT)
    assert isinstance(result[0], Notification)
    assert result[0].cause == "escalate"
    assert new.advance(T0 + 2 * HOUR, CONTEXT) == []


def test_recipient_quiet_hours_do_not_block_other_reminders() -> None:
    """Scenario 72: each recipient has an independent reminder clock."""
    policy = Policy(
        PolicyConfig(
            batch=timedelta(0),
            timezone=UTC,
            digests={},
            recipients={
                "awake": Recipient(channels=("phone",)),
                "quiet": Recipient(
                    channels=("phone",),
                    quiet_hours=QuietHours(start=time(12), end=time(15)),
                ),
            },
            rules=(
                Rule(
                    match=Match(),
                    loudness=Loudness.NOTIFY,
                    to=("awake", "quiet"),
                    remind_every=HOUR,
                ),
            ),
        )
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert [item.recipient for item in policy.advance(T0, CONTEXT)] == ["awake"]
    assert policy.next_deadline() == T0 + HOUR
    assert [item.recipient for item in policy.advance(T0 + HOUR, CONTEXT)] == ["awake"]
    assert [item.recipient for item in policy.advance(T0 + 3 * HOUR, CONTEXT)] == [
        "quiet",
        "awake",
    ]
