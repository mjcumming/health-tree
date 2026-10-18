"""Fixed windows retain exact accepted membership and causal attention history."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
import json

import pytest

from health_tree._codec import as_list, as_object
from health_tree.delivery_collections import CollectionRequest, DeliveryCollections
from health_tree.policy import Policy
from health_tree.types import (
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
    QuietHours,
    Recipient,
    ResolutionNotice,
    Rule,
    Status,
)

T0 = datetime(2026, 10, 18, 20, 59, 30, tzinfo=UTC)
CONTEXT = PolicyContext()


def at(seconds: int) -> datetime:
    """Advance a supplied test clock without sleeping."""
    return T0 + timedelta(seconds=seconds)


def policy(*, rule: Rule | None = None) -> Policy:
    """Allow ordinary requests in one named route."""
    return Policy(
        PolicyConfig(
            batch=timedelta(0),
            timezone=UTC,
            recipients={
                "owner": Recipient(channels=("phone",)),
                "other": Recipient(channels=("phone",)),
            },
            digests={"report": Digest(at=time(21), to="owner", repeat_open=True)},
            rules=(
                rule
                or Rule(
                    match=Match(),
                    route="immediate",
                    loudness=Loudness.URGENT,
                    to=("owner", "other"),
                    require_acknowledgment=True,
                ),
            ),
        )
    )


def episode(
    identity: str, *, seconds: int = 0, absorbed: frozenset[str] = frozenset()
) -> Episode:
    """Build independently failing evidence with caller-supplied identity."""
    return Episode(
        episode_id=identity,
        form="root",
        anchor=identity,
        status=Status.FAIL,
        reasons=(
            Finding(
                node_id=identity,
                check_id="availability",
                status=Status.FAIL,
                reason="unavailable",
                since=at(seconds),
            ),
        ),
        recorded=frozenset(),
        impact=frozenset(),
        importance=Importance.NORMAL,
        opened_at=at(seconds),
        updated_at=at(seconds),
        absorbed=absorbed,
    )


def opening(attention: Policy, identity: str, *, seconds: int = 0) -> Notification:
    """Get a real independently authorized opening from policy."""
    deliveries = attention.handle(
        EpisodeOpened(episode=episode(identity, seconds=seconds)), at(seconds), CONTEXT
    )
    item = deliveries[0]
    assert isinstance(item, Notification)
    return item


def request(
    notification: Notification, *, delay: int = 60, group: str = "saved"
) -> CollectionRequest:
    """Accept a destination and its immutable instructions at eligibility."""
    return CollectionRequest(
        notification=notification,
        group_id=group,
        delay=timedelta(seconds=delay),
        instructions={"notification_id": group, "sound": "default"},
        content={"title": notification.episode_id},
    )


def test_thirty_unrelated_members_fixed_deadline_restart_and_late_window() -> None:
    """Thirty independent issues yield one exact message, then a distinct window."""
    attention = policy()
    collections = DeliveryCollections()
    first = request(opening(attention, "issue-0"))
    assert collections.apply([first], [], at(0), attention) == []
    others = [
        request(opening(attention, f"issue-{number}", seconds=10))
        for number in range(1, 30)
    ]
    assert collections.apply(others, [], at(10), attention) == []
    assert collections.next_deadline() == at(60)
    assert collections.apply([first], [], at(20), attention) == []
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    assert restored.snapshot() == collections.snapshot()
    assert restored.advance(at(59), attention) == []
    sent = restored.advance(at(60), attention)
    assert len(sent) == 1
    assert len(sent[0].group.members) == 30
    assert sent[0].group.silent is False
    assert len(sent[0].contents) == 30
    assert restored.advance(at(60), attention) == []
    assert (
        restored.apply(
            [request(opening(attention, "late", seconds=61))], [], at(61), attention
        )
        == []
    )
    later = restored.advance(at(121), attention)
    assert len(later) == 1
    assert [member.episode_id for member in later[0].group.members] == ["late"]
    assert later[0].group.key != sent[0].group.key


def test_boundary_with_deferred_flush_keeps_late_arrival_out() -> None:
    """A timer processed late cannot include requests eligible after its deadline."""
    attention = policy()
    collections = DeliveryCollections()
    collections.apply(
        [request(opening(attention, "early"))], [], at(0), attention, flush=False
    )
    collections.apply(
        [request(opening(attention, "boundary", seconds=60))],
        [],
        at(60),
        attention,
        flush=False,
    )
    sent = collections.advance(at(60), attention)
    assert [member.episode_id for member in sent[0].group.members] == ["early"]
    assert collections.next_deadline() == at(120)
    assert (
        collections.advance(at(120), attention)[0].group.members[0].episode_id
        == "boundary"
    )


@pytest.mark.parametrize("delay", [0, 60])
def test_recovery_and_acknowledgment_remove_only_pending_members(delay: int) -> None:
    """Exact controls cannot clear unrelated members or manufacture recovery."""
    attention = policy()
    collections = DeliveryCollections()
    one, two = opening(attention, "one"), opening(attention, "two")
    collections.apply(
        [request(one, delay=delay), request(two, delay=delay)],
        [],
        at(0),
        attention,
        flush=False,
    )
    attention.acknowledge("one", at(1))
    attention.handle(
        EpisodeResolved(episode=episode("two"), resolution="cleared"), at(1), CONTEXT
    )
    assert collections.advance(at(60), attention) == []
    assert collections.pending() == ()
    assert collections.next_deadline() is None


def test_zero_and_reports_bypass_wait_and_startup_starts_window_on_release() -> None:
    """An adapter startup hold precedes collection; reports add no delay."""
    attention = policy()
    collections = DeliveryCollections()
    immediate = collections.apply(
        [request(opening(attention, "zero"), delay=0)], [], at(0), attention
    )
    assert len(immediate) == 1
    held = request(opening(attention, "held", seconds=1))
    assert collections.apply([held], [], at(1), attention, held=True) == []
    assert collections.next_deadline() is None
    assert collections.advance(at(40), attention) == []
    assert collections.next_deadline() == at(100)
    assert len(collections.advance(at(100), attention)) == 1
    reports = policy(
        rule=Rule(
            match=Match(), route="report", loudness=Loudness.DIGEST, digest="report"
        )
    )
    reports.handle(EpisodeOpened(episode=episode("scheduled")), at(0), CONTEXT)
    report = reports.advance(at(30), CONTEXT)[0]
    assert isinstance(report, Notification)
    assert (
        len(
            DeliveryCollections().apply(
                [request(report, delay=600)], [], at(30), reports
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "partition", ["identity", "recipient", "destination", "instructions"]
)
def test_identity_recipient_destination_and_instructions_partition(
    partition: str,
) -> None:
    """A shared display setting cannot broaden an accepted audience."""
    attention = policy()
    first = request(opening(attention, "one"))
    second = request(opening(attention, "two"))
    changes = {
        "identity": replace(second, group_id="other-saved"),
        "recipient": replace(
            second, notification=replace(second.notification, recipient="other")
        ),
        "destination": replace(
            second, notification=replace(second.notification, channels=("other-phone",))
        ),
        "instructions": replace(second, instructions={"sound": "different"}),
    }
    collections = DeliveryCollections()
    assert collections.apply([first, changes[partition]], [], at(0), attention) == []
    assert len(collections.advance(at(60), attention)) == 2


def test_shared_destination_collects_once_and_other_destination_stays_separate() -> (
    None
):
    """A route targeting two channels shares only its common target with another."""
    attention = policy()
    first = request(replace(opening(attention, "one"), channels=("phone", "email")))
    second = request(opening(attention, "two"))
    collections = DeliveryCollections()
    collections.apply([first, second], [], at(0), attention)
    sent = collections.advance(at(60), attention)
    assert [(group.group.channels, len(group.group.members)) for group in sent] == [
        (("phone",), 2),
        (("email",), 1),
    ]


def test_due_collection_crossing_hours_waits_without_second_delay() -> None:
    """A collection due after closing waits until opening using saved hours."""
    attention = policy()
    collections = DeliveryCollections()
    accepted = replace(
        request(opening(attention, "door")),
        quiet_hours=QuietHours(start=time(21), end=time(7)),
    )
    collections.apply([accepted], [], at(0), attention)
    assert collections.advance(at(60), attention) == []
    next_open = datetime(2026, 10, 19, 7, tzinfo=UTC)
    assert collections.next_deadline() == next_open
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    assert len(restored.advance(next_open, attention)) == 1


def test_pending_setting_edit_retains_accepted_instructions_target_and_due() -> None:
    """Reactivation cannot move an existing request or reset its deadline."""
    attention = policy()
    collections = DeliveryCollections()
    first = request(opening(attention, "one"))
    collections.apply([first], [], at(0), attention)
    assert collections.deactivate(routes=["immediate"], preserve_pending=True) == []
    changed = replace(
        first, delay=timedelta(seconds=300), instructions={"sound": "changed"}
    )
    collections.apply([changed], [], at(10), attention)
    assert collections.next_deadline() == at(60)
    sent = collections.advance(at(60), attention)
    assert sent[0].instructions == first.instructions
    assert sent[0].group.channels == ("phone",)
    assert collections.deactivate()[0].group.closed is True
    assert collections.deactivate() == []


def test_pending_destination_edit_cannot_add_a_second_audience() -> None:
    """Reactivation preserves the original target even when presence changed."""
    attention = policy()
    collections = DeliveryCollections()
    original = request(opening(attention, "one"))
    collections.apply([original], [], at(0), attention)
    changed = replace(
        original,
        notification=replace(original.notification, channels=("new-phone",)),
        instructions={"new": True},
    )
    collections.apply([changed], [], at(10), attention)
    assert len(collections.pending()) == 1
    assert collections.pending()[0].notification.channels == ("phone",)
    assert (
        collections.advance(at(60), attention)[0].instructions == original.instructions
    )


def test_shelf_postpones_due_member_and_expiry_adds_no_collection_wait() -> None:
    """A temporary pause holds the exact accepted request until its expiry."""
    attention = policy()
    collections = DeliveryCollections()
    original = request(opening(attention, "one"))
    collections.apply([original], [], at(0), attention)
    attention.shelve("one", at(100), at(10))
    assert collections.advance(at(60), attention) == []
    assert collections.next_deadline() == at(100)
    assert len(collections.advance(at(100), attention)) == 1


def test_startup_held_collection_waits_for_pause_eligibility_before_starting() -> None:
    """Both startup and an existing pause must end before the first window starts."""
    attention = policy()
    collections = DeliveryCollections()
    collections.apply(
        [request(opening(attention, "one"))], [], at(0), attention, held=True
    )
    attention.shelve("one", at(100), at(10))
    assert collections.advance(at(50), attention) == []
    assert collections.next_deadline() == at(100)
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    assert restored.advance(at(100), attention) == []
    assert restored.next_deadline() == at(160)
    assert restored.advance(at(159), attention) == []
    assert len(restored.advance(at(160), attention)) == 1


def test_absorption_retains_only_accepted_members_pause_floor() -> None:
    """A child pause holds its accepted successor without shelving other issues."""
    attention = policy()
    collections = DeliveryCollections()
    original = request(opening(attention, "child"))
    collections.apply([original], [], at(0), attention)
    attention.shelve("child", at(100), at(10))
    collections.advance(at(10), attention)
    assert collections.next_deadline() == at(100)
    changes = attention.handle(
        EpisodeOpened(
            episode=episode("root", seconds=20, absorbed=frozenset({"child"}))
        ),
        at(20),
        CONTEXT,
    )
    collections.apply(
        [request(item) for item in changes if isinstance(item, Notification)],
        [],
        at(20),
        attention,
        flush=False,
    )
    ended = attention.handle(
        EpisodeResolved(
            episode=episode("child"), resolution="absorbed", absorbed_into="root"
        ),
        at(20),
        CONTEXT,
    )
    collections.apply(
        [],
        [item for item in ended if isinstance(item, ResolutionNotice)],
        at(20),
        attention,
    )
    collections.apply(
        [request(opening(attention, "independent", seconds=30), delay=0)],
        [],
        at(30),
        attention,
    )
    assert collections.advance(at(60), attention) == []
    assert collections.pending()[0].notification.episode_id == "root"
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    assert restored.advance(at(99), attention) == []
    assert restored.advance(at(100), attention)[0].group.members[0].episode_id == "root"


def test_repeated_opening_after_delivery_is_silent_and_reports_share_batch() -> None:
    """Replaying an opening cannot create another window; a report stays one batch."""
    attention = policy()
    collections = DeliveryCollections()
    original = request(opening(attention, "one"), delay=0)
    first = collections.apply([original], [], at(0), attention)
    repeated = collections.apply([original], [], at(1), attention)
    assert repeated[0].group.key == first[0].group.key
    assert repeated[0].group.silent
    assert collections.next_deadline() is None
    reports = policy(
        rule=Rule(
            match=Match(), route="report", loudness=Loudness.DIGEST, digest="report"
        )
    )
    reports.handle(EpisodeOpened(episode=episode("first")), at(0), CONTEXT)
    reports.handle(EpisodeOpened(episode=episode("second")), at(0), CONTEXT)
    deliveries = reports.advance(at(30), CONTEXT)
    sent = DeliveryCollections().apply(
        [request(item) for item in deliveries if isinstance(item, Notification)],
        [],
        at(30),
        reports,
    )
    assert len(sent) == 1
    assert len(sent[0].group.members) == 2


def test_pending_reminder_keeps_presented_instructions_through_partial_recovery() -> (
    None
):
    """An upcoming reminder cannot replace the identity of the visible message."""
    attention = policy(
        rule=Rule(
            match=Match(),
            route="immediate",
            loudness=Loudness.URGENT,
            to=("owner",),
            remind_every=timedelta(seconds=100),
        )
    )
    collections = DeliveryCollections()
    one, two = opening(attention, "one"), opening(attention, "two")
    collections.apply([request(one), request(two)], [], at(0), attention)
    first = collections.advance(at(60), attention)[0]
    reminders = attention.advance(at(100), CONTEXT)
    collections.apply(
        [request(item) for item in reminders if isinstance(item, Notification)],
        [],
        at(100),
        attention,
    )
    silent = replace(one, silent=True, cause="update")
    changed = collections.apply(
        [replace(request(silent), content={"title": "new details"})],
        [],
        at(105),
        attention,
    )
    assert changed[0].group.key == first.group.key
    assert changed[0].instructions["notification_id"] == "saved"
    assert changed[0].group.silent
    ended = attention.handle(
        EpisodeResolved(episode=episode("two"), resolution="cleared"), at(110), CONTEXT
    )
    partial = collections.apply(
        [],
        [item for item in ended if isinstance(item, ResolutionNotice)],
        at(110),
        attention,
    )
    assert partial[0].group.key == first.group.key
    assert partial[0].instructions["notification_id"] == "saved"
    assert [member.episode_id for member in partial[0].group.members] == ["one"]
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    next_message = restored.advance(at(160), attention)
    assert next_message[-1].group.key != first.group.key
    assert next_message[-1].instructions["notification_id"] == "saved"


@pytest.mark.parametrize("channels", [("new-phone",), ()])
@pytest.mark.parametrize("sent_before", [False, True])
def test_absorption_uses_accepted_destinations_even_when_current_targets_change(
    channels: tuple[str, ...], sent_before: bool
) -> None:
    """A changed or absent current destination cannot discard accepted attention."""
    attention = policy()
    collections = DeliveryCollections()
    collections.apply(
        [request(opening(attention, "child"), delay=0 if sent_before else 60)],
        [],
        at(0),
        attention,
    )
    changes = attention.handle(
        EpisodeOpened(
            episode=episode("root", seconds=10, absorbed=frozenset({"child"}))
        ),
        at(10),
        CONTEXT,
    )
    updates = collections.apply(
        [
            request(replace(item, channels=channels))
            for item in changes
            if isinstance(item, Notification)
        ],
        [],
        at(10),
        attention,
        flush=False,
    )
    ended = attention.handle(
        EpisodeResolved(
            episode=episode("child"), resolution="absorbed", absorbed_into="root"
        ),
        at(10),
        CONTEXT,
    )
    collections.apply(
        [],
        [item for item in ended if isinstance(item, ResolutionNotice)],
        at(10),
        attention,
        flush=False,
    )
    final = collections.advance(at(60), attention)
    latest = (updates if sent_before else final)[-1]
    assert latest.group.channels == ("phone",)
    assert latest.group.members[0].episode_id == "root"
    assert latest.group.silent is sent_before


@pytest.mark.parametrize("presented_anchor", ["root", "child"])
def test_absorption_does_not_reopen_when_either_member_already_presented(
    presented_anchor: str,
) -> None:
    """A pending opening cannot replay an assignment already shown on either anchor."""
    attention = policy()
    collections = DeliveryCollections()
    root, child = opening(attention, "root"), opening(attention, "child")
    collections.apply(
        [request(root, delay=0 if presented_anchor == "root" else 60)],
        [],
        at(0),
        attention,
    )
    collections.apply(
        [request(child, delay=0 if presented_anchor == "child" else 60)],
        [],
        at(0),
        attention,
    )
    changes = attention.handle(
        EpisodeUpdated(episode=episode("root", absorbed=frozenset({"child"}))),
        at(20),
        CONTEXT,
    )
    updates = collections.apply(
        [request(item) for item in changes if isinstance(item, Notification)],
        [],
        at(20),
        attention,
        flush=False,
    )
    ended = attention.handle(
        EpisodeResolved(
            episode=episode("child"), resolution="absorbed", absorbed_into="root"
        ),
        at(20),
        CONTEXT,
    )
    collections.apply(
        [],
        [item for item in ended if isinstance(item, ResolutionNotice)],
        at(20),
        attention,
    )
    assert all(item.group.silent for item in updates)
    assert collections.advance(at(60), attention) == []
    assert collections.pending() == ()


def test_absorption_collision_keeps_incompatible_successor_instructions_separate() -> (
    None
):
    """An existing successor acceptance cannot enter an incompatible old window."""
    attention = policy()
    collections = DeliveryCollections()
    child, unrelated = opening(attention, "child"), opening(attention, "unrelated")
    collections.apply([request(child), request(unrelated)], [], at(0), attention)
    root = opening(attention, "root", seconds=10)
    changed = replace(
        request(root), instructions={"notification_id": "saved", "sound": "changed"}
    )
    collections.apply([changed], [], at(10), attention)
    updates = attention.handle(
        EpisodeUpdated(
            episode=episode("root", seconds=10, absorbed=frozenset({"child"}))
        ),
        at(20),
        CONTEXT,
    )
    collections.apply(
        [
            replace(changed, notification=item)
            for item in updates
            if isinstance(item, Notification)
        ],
        [],
        at(20),
        attention,
        flush=False,
    )
    ended = attention.handle(
        EpisodeResolved(
            episode=episode("child"), resolution="absorbed", absorbed_into="root"
        ),
        at(20),
        CONTEXT,
    )
    collections.apply(
        [],
        [item for item in ended if isinstance(item, ResolutionNotice)],
        at(20),
        attention,
    )
    first = collections.advance(at(60), attention)
    assert [member.episode_id for member in first[0].group.members] == ["unrelated"]
    assert first[0].instructions["sound"] == "default"
    second = collections.advance(at(70), attention)
    assert [member.episode_id for member in second[0].group.members] == ["root"]
    assert second[0].instructions["sound"] == "changed"


@pytest.mark.parametrize("sent_before", [False, True])
def test_split_successors_inherit_one_pending_or_presented_window(
    sent_before: bool,
) -> None:
    """Each successor retains scope without recreating its predecessor opening."""
    attention = policy()
    collections = DeliveryCollections()
    original = opening(attention, "parent")
    collections.apply(
        [request(original, delay=0 if sent_before else 60)], [], at(0), attention
    )
    updates = []
    for identity in ("first", "second"):
        changed = attention.handle(
            EpisodeOpened(episode=episode(identity, seconds=10), split_from="parent"),
            at(10),
            CONTEXT,
        )
        updates.extend(
            collections.apply(
                [request(item) for item in changed if isinstance(item, Notification)],
                [],
                at(10),
                attention,
                flush=False,
            )
        )
    ended = attention.handle(
        EpisodeResolved(
            episode=episode("parent"),
            resolution="split",
            split_into=("first", "second"),
        ),
        at(10),
        CONTEXT,
    )
    collections.apply(
        [],
        [item for item in ended if isinstance(item, ResolutionNotice)],
        at(10),
        attention,
        flush=False,
    )
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    final = restored.advance(at(60), attention)
    assert all(update.group.silent for update in updates)
    assert len(final) == (0 if sent_before else 1)
    latest = (updates if sent_before else final)[-1]
    assert {member.episode_id for member in latest.group.members} == {"first", "second"}


def test_pending_resolution_deactivation_and_silent_refresh() -> None:
    """Explicit resolution cancels unsent content; delivered updates stay silent."""
    attention = policy()
    collections = DeliveryCollections()
    original = request(opening(attention, "one"))
    collections.apply([original], [], at(0), attention)
    notice = ResolutionNotice(
        episode_id="one",
        recipient="owner",
        channels=("phone",),
        route="immediate",
        resolution="removed",
    )
    assert collections.apply([], [notice], at(10), attention) == []
    assert collections.next_deadline() is None
    collections.apply([original], [], at(20), attention)
    assert collections.deactivate(routes=["immediate"]) == []
    assert collections.pending() == ()
    collections.apply([replace(original, delay=timedelta(0))], [], at(30), attention)
    silent = replace(
        original,
        notification=replace(original.notification, silent=True),
        content={"title": "changed"},
    )
    updated = collections.apply([silent], [], at(40), attention)
    assert updated[0].group.silent
    assert updated[0].contents[("one", "immediate")] == {"title": "changed"}
    restored = DeliveryCollections()
    restored.restore(json.loads(json.dumps(collections.snapshot())))
    assert restored.snapshot() == collections.snapshot()
    assert restored.apply([], [notice], at(50), attention)[0].group.closed


@pytest.mark.parametrize(
    "change",
    [
        "identity",
        "negative-delay",
        "time",
        "backwards",
        "schema",
        "duplicate",
        "channels",
        "deadline",
    ],
)
def test_reject_invalid_collection_inputs(change: str) -> None:
    """Invalid identity, timing and durable records fail explicitly."""
    attention = policy()
    collections = DeliveryCollections()
    original = request(opening(attention, "one"))
    collections.apply([original], [], at(0), attention)
    state = collections.snapshot()
    pending = as_object(as_list(state["pending"])[0])
    notification = as_object(pending["notification"])
    deadline = as_list(state["deadlines"])[0]
    actions: dict[str, Callable[[], object]] = {
        "identity": lambda: replace(original, group_id=""),
        "negative-delay": lambda: replace(original, delay=timedelta(seconds=-1)),
        "time": lambda: collections.advance(at(0).replace(tzinfo=None), attention),
        "backwards": lambda: collections.advance(at(-1), attention),
        "schema": lambda: collections.restore({"schema_version": -1}),
        "duplicate": lambda: collections.restore(
            {**state, "pending": [pending, pending]}
        ),
        "channels": lambda: collections.restore(
            {
                **state,
                "pending": [
                    {
                        **pending,
                        "notification": {
                            **notification,
                            "channels": [],
                        },
                    }
                ],
            }
        ),
        "deadline": lambda: collections.restore(
            {**state, "deadlines": [deadline, deadline]}
        ),
    }
    with pytest.raises(ValueError):
        actions[change]()


@pytest.mark.parametrize("sent_before", [False, True])
def test_absorption_preserves_pending_deadline_or_silent_opening(
    sent_before: bool,
) -> None:
    """Causal reassociation keeps authorization without generating a new opening."""
    attention = policy()
    collections = DeliveryCollections()
    collections.apply(
        [request(opening(attention, "child"), delay=0 if sent_before else 60)],
        [],
        at(0),
        attention,
    )
    shared = episode("root", seconds=10, absorbed=frozenset({"child"}))
    changes = attention.handle(EpisodeOpened(episode=shared), at(10), CONTEXT)
    notices = [change for change in changes if isinstance(change, Notification)]
    assert all(change.silent for change in notices)
    updates = collections.apply(
        [request(change) for change in notices], [], at(10), attention, flush=False
    )
    endings = attention.handle(
        EpisodeResolved(
            episode=episode("child"), resolution="absorbed", absorbed_into="root"
        ),
        at(10),
        CONTEXT,
    )
    collections.apply(
        [],
        [change for change in endings if isinstance(change, ResolutionNotice)],
        at(10),
        attention,
        flush=False,
    )
    assert all(update.group.silent for update in updates)
    final = collections.advance(at(60), attention)
    assert len(final) == (0 if sent_before else 1)
    assert {
        request.notification.episode_id for request in collections.pending()
    } == set()


def test_partial_recovery_updates_only_presented_members_and_recurs() -> None:
    """Recovery silently leaves the other issue visible and recurrence can open."""
    attention = policy()
    collections = DeliveryCollections()
    first, second = opening(attention, "one"), opening(attention, "two")
    collections.apply([request(first), request(second)], [], at(0), attention)
    sent = collections.advance(at(60), attention)[0]
    ended = attention.handle(
        EpisodeResolved(episode=episode("one"), resolution="cleared"), at(61), CONTEXT
    )
    updates = collections.apply(
        [],
        [change for change in ended if isinstance(change, ResolutionNotice)],
        at(61),
        attention,
    )
    assert len(updates) == 1
    assert updates[0].group.key == sent.group.key
    assert [member.episode_id for member in updates[0].group.members] == ["two"]
    assert updates[0].group.silent
    collections.apply(
        [request(opening(attention, "one-again", seconds=62))], [], at(62), attention
    )
    assert len(collections.advance(at(122), attention)) == 1
