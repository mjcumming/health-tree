"""Compatible message membership keeps independent attention and recovery."""

from dataclasses import replace
import json

import pytest

from health_tree.delivery_groups import DeliveryGroups
from health_tree.types import (
    JSONValue,
    Loudness,
    Notification,
    Resolution,
    ResolutionNotice,
)


def notification(
    identity: str = "first",
    *,
    recipient: str = "owner",
    channels: tuple[str, ...] = ("phone",),
    loudness: Loudness = Loudness.URGENT,
    route: str = "immediate",
    digest: str | None = None,
) -> Notification:
    """Build a policy delivery for one independently identified problem."""
    return Notification(
        episode_id=identity,
        recipient=recipient,
        channels=channels,
        loudness=loudness,
        route=route,
        digest=digest,
    )


def resolution(
    member: Notification, reason: Resolution = "cleared"
) -> ResolutionNotice:
    """Retain the policy's exact resolution without interpreting its reason."""
    return ResolutionNotice(
        episode_id=member.episode_id,
        recipient=member.recipient,
        channels=member.channels,
        route=member.route,
        resolution=reason,
    )


def test_partial_recovery_keeps_message_and_last_resolution_closes() -> None:
    """A continuing problem is never hidden by another member's recovery."""
    groups = DeliveryGroups()
    first, second = notification(), notification("second")
    opened = groups.apply(
        [first, second],
        {("first", "immediate"): "subject", ("second", "immediate"): "subject"},
    )
    assert len(opened) == 1
    assert opened[0].members == (first, second)
    assert opened[0].silent is False
    partial = groups.apply([resolution(first)], {})
    assert partial[0].key == opened[0].key
    assert partial[0].members == (second,)
    assert partial[0].silent is True
    assert partial[0].closed is False
    final = groups.apply([resolution(second, "removed")], {})
    assert final[0].closed is True
    assert final[0].changes == (resolution(second, "removed"),)
    assert groups.apply([resolution(second)], {}) == []


@pytest.mark.parametrize(
    "second",
    [
        pytest.param(notification("second", recipient="other"), id="recipient"),
        pytest.param(notification("second", channels=("email",)), id="channels"),
    ],
)
def test_recipient_and_channels_partition_messages(second: Notification) -> None:
    """Shared subjects cannot leak a recipient's content to another route."""
    groups = DeliveryGroups()
    updates = groups.apply(
        [notification(), second],
        {("first", "immediate"): "subject", ("second", "immediate"): "subject"},
    )
    assert len(updates) == 2
    assert updates[0].key != updates[1].key
    assert updates[0].members == (notification(),)
    assert updates[1].members == (second,)


def test_compatible_routes_group_and_independent_instructions_do_not() -> None:
    """The caller declares compatibility without deleting independent routes."""
    first = notification()
    compatible = notification(route="other-policy")
    independent = notification(route="deliberate")
    updates = DeliveryGroups().apply(
        [first, compatible, independent],
        {
            ("first", "immediate"): "compatible",
            ("first", "other-policy"): "compatible",
            ("first", "deliberate"): "independent",
        },
    )
    assert len(updates) == 2
    assert updates[0].members == (first, compatible)
    assert updates[1].members == (independent,)


def test_snapshot_preserves_keys_and_deactivation_preserves_survivor() -> None:
    """Restoring is silent and ending one route cannot dismiss another."""
    original = DeliveryGroups()
    first = notification()
    report = notification(
        "second", route="report", loudness=Loudness.DIGEST, digest="morning"
    )
    opened = original.apply(
        [first, report],
        {("first", "immediate"): "subject", ("second", "report"): "subject"},
    )
    restored = DeliveryGroups()
    restored.restore(json.loads(json.dumps(original.snapshot())))
    assert restored.snapshot() == original.snapshot()
    assert restored.apply([], {}) == []
    assert restored.deactivate(routes=[]) == []
    partial = restored.deactivate(routes=["immediate"])
    assert partial[0].key == opened[0].key
    assert partial[0].members == (report,)
    assert partial[0].changes == ()
    assert partial[0].silent is True
    assert restored.deactivate()[0].closed is True
    assert restored.deactivate() == []


@pytest.mark.parametrize(
    ("member", "new_group"),
    [
        pytest.param(notification(channels=("email",)), "subject", id="channels"),
        pytest.param(notification(), "new-subject", id="subject"),
    ],
)
def test_moving_member_cleans_old_message(member: Notification, new_group: str) -> None:
    """Route changes retain the old destination needed for message cleanup."""
    groups = DeliveryGroups()
    opened = groups.apply([notification()], {("first", "immediate"): "subject"})
    changed = groups.apply([member], {("first", "immediate"): new_group})
    assert len(changed) == 2
    assert changed[0].key == opened[0].key
    assert changed[0].channels == ("phone",)
    assert changed[0].closed is True
    assert changed[0].silent is True
    assert changed[1].members == (member,)


def test_batch_hides_transient_members_and_retains_new_attention() -> None:
    """A complete batch avoids a false all-clear between old and new problems."""
    groups = DeliveryGroups()
    first, second = notification(), notification("second")
    assert (
        groups.apply([first, resolution(first)], {("first", "immediate"): "subject"})
        == []
    )
    groups.apply([first], {("first", "immediate"): "subject"})
    changed = groups.apply(
        [resolution(first), second], {("second", "immediate"): "subject"}
    )
    assert changed[0].members == (second,)
    assert changed[0].silent is False
    quiet = groups.apply(
        [replace(second, silent=True)], {("second", "immediate"): "subject"}
    )
    assert quiet[0].silent is True


@pytest.mark.parametrize("group", [None, "", 1])
def test_invalid_group_is_atomic(group: object) -> None:
    """Bad explicit assignments cannot partly change previous membership."""
    groups = DeliveryGroups()
    before = groups.snapshot()
    with pytest.raises(ValueError, match="nonempty string"):
        groups.apply(
            [notification(), notification("second")],
            {("first", "immediate"): "valid", ("second", "immediate"): group},  # type: ignore[dict-item]
        )
    assert groups.snapshot() == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("episode_id", 1, id="string"),
        pytest.param("silent", "yes", id="boolean"),
        pytest.param("loudness", "invalid", id="loudness"),
    ],
)
def test_invalid_snapshot_is_atomic(field: str, value: JSONValue) -> None:
    """Malformed persisted membership cannot replace the valid state."""
    groups = DeliveryGroups()
    groups.apply([notification()], {("first", "immediate"): "subject"})
    before = groups.snapshot()
    state = json.loads(json.dumps(before))
    state["members"][0]["notification"][field] = value
    with pytest.raises((ValueError, TypeError)):
        groups.restore(state)
    assert groups.snapshot() == before


def test_snapshot_rejects_unknown_schema_empty_group_and_duplicate_member() -> None:
    """Invalid membership identities are rejected explicitly."""
    groups = DeliveryGroups()
    with pytest.raises(ValueError, match="snapshot"):
        groups.restore({"schema_version": 0})
    groups.apply([notification()], {("first", "immediate"): "subject"})
    state = json.loads(json.dumps(groups.snapshot()))
    state["members"].append(state["members"][0])
    with pytest.raises(ValueError, match="duplicate"):
        groups.restore(state)
    state["members"][0]["group_id"] = ""
    with pytest.raises(ValueError, match="nonempty"):
        groups.restore(state)
