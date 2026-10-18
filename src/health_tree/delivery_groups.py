"""Consolidate authorized deliveries while preserving independent episodes."""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json

from health_tree._codec import JSONObject, as_list, as_object
from health_tree.types import Delivery, JSONValue, Loudness, Notification

type _MemberKey = tuple[str, str, str]
type _GroupKey = tuple[str, str, tuple[str, ...]]


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryGroup:
    """One message replacement, with exact delivered members and changes.

    `closed` withdraws the message; its changes retain each original resolution.
    Empty changes indicate delivery deactivation or movement, never recovery.
    Acknowledgment acts on the episode ids in the message actually presented.
    """

    group_id: str
    recipient: str
    channels: tuple[str, ...]
    members: tuple[Notification, ...]
    changes: tuple[Delivery, ...]
    silent: bool

    @property
    def key(self) -> str:
        """Return a stable message key partitioned by recipient and channels."""
        identity = json.dumps(
            [self.group_id, self.recipient, self.channels], separators=(",", ":")
        )
        return hashlib.sha256(identity.encode()).hexdigest()

    @property
    def closed(self) -> bool:
        """Whether this message has no remaining delivered problems."""
        return not self.members


class DeliveryGroups:
    """Keep message membership after policy timing and routing have decided.

    Group ids are caller-owned. Assign the same id only after verifying complete
    delivery instructions are compatible. Recipient and channels partition it
    further. Persist the snapshot together with the transport outbox.
    """

    __slots__ = ("_members",)

    def __init__(self) -> None:
        """Start without delivered messages."""
        self._members: dict[_MemberKey, tuple[str, Notification]] = {}

    def apply(
        self,
        deliveries: Iterable[Delivery],
        group_ids: Mapping[tuple[str, str], str],
    ) -> list[DeliveryGroup]:
        """Apply a batch atomically, retaining only its final message states.

        Args:
            deliveries: Policy-authorized changes in their original order.
            group_ids: Explicit group for every incoming notification's episode
                and route. Resolutions use retained membership instead.
        """
        changes = tuple(deliveries)
        for delivery in changes:
            if isinstance(delivery, Notification):
                group_id = group_ids[(delivery.episode_id, delivery.route)]
                if not isinstance(group_id, str) or not group_id:
                    raise ValueError("a delivery group needs a nonempty string id")
        before = self._groups()
        touched: dict[_GroupKey, list[Delivery]] = {}
        for delivery in changes:
            member = _member_key(delivery)
            previous = self._members.get(member)
            if isinstance(delivery, Notification):
                group_id = group_ids[(delivery.episode_id, delivery.route)]
                current = _group_key(group_id, delivery)
                if previous is not None:
                    old = _group_key(*previous)
                    if old != current:
                        touched.setdefault(old, [])
                self._members[member] = (group_id, delivery)
                touched.setdefault(current, []).append(delivery)
            elif previous is not None:
                del self._members[member]
                touched.setdefault(_group_key(*previous), []).append(delivery)
        return self._updates(before, touched)

    def deactivate(
        self, *, routes: Collection[str] | None = None
    ) -> list[DeliveryGroup]:
        """End selected route delivery without claiming that a problem cleared."""
        before = self._groups()
        touched: dict[_GroupKey, list[Delivery]] = {}
        for key, (group_id, member) in tuple(self._members.items()):
            if routes is None or member.route in routes:
                del self._members[key]
                touched.setdefault(_group_key(group_id, member), [])
        return self._updates(before, touched)

    def snapshot(self) -> JSONObject:
        """Return JSON-compatible delivered membership, with no transport state."""
        return {
            "schema_version": 1,
            "members": [
                {"group_id": group_id, "notification": _notification_json(member)}
                for group_id, member in self._members.values()
            ],
        }

    def restore(self, state: Mapping[str, JSONValue]) -> None:
        """Replace membership from a snapshot without producing delivery."""
        if state.get("schema_version") != 1:
            raise ValueError("unsupported delivery groups snapshot")
        members: dict[_MemberKey, tuple[str, Notification]] = {}
        for row in as_list(state["members"]):
            data = as_object(row)
            group_id = _string(data["group_id"])
            if not group_id:
                raise ValueError("a delivery group needs a nonempty string id")
            member = _notification_from_json(as_object(data["notification"]))
            key = _member_key(member)
            if key in members:
                raise ValueError("duplicate delivered member")
            members[key] = (group_id, member)
        self._members = members

    def _groups(self) -> dict[_GroupKey, tuple[Notification, ...]]:
        groups: dict[_GroupKey, list[Notification]] = {}
        for group_id, member in self._members.values():
            groups.setdefault(_group_key(group_id, member), []).append(member)
        return {key: tuple(members) for key, members in groups.items()}

    def _updates(
        self,
        before: Mapping[_GroupKey, tuple[Notification, ...]],
        touched: Mapping[_GroupKey, list[Delivery]],
    ) -> list[DeliveryGroup]:
        current = self._groups()
        return [
            DeliveryGroup(
                group_id=key[0],
                recipient=key[1],
                channels=key[2],
                members=current.get(key, ()),
                changes=tuple(changes),
                silent=not any(
                    isinstance(change, Notification)
                    and not change.silent
                    and _member_key(change) in self._members
                    and _group_key(*self._members[_member_key(change)]) == key
                    for change in changes
                ),
            )
            for key, changes in touched.items()
            if key in before or key in current
        ]


def _member_key(delivery: Delivery) -> _MemberKey:
    return delivery.episode_id, delivery.route, delivery.recipient


def _group_key(group_id: str, member: Notification) -> _GroupKey:
    return group_id, member.recipient, member.channels


def _notification_json(member: Notification) -> JSONObject:
    return {
        "episode_id": member.episode_id,
        "recipient": member.recipient,
        "channels": list(member.channels),
        "loudness": member.loudness.value,
        "digest": member.digest,
        "silent": member.silent,
        "cause": member.cause,
        "previously_reported": member.previously_reported,
        "route": member.route,
        "replaces": list(member.replaces),
    }


def _notification_from_json(data: JSONObject) -> Notification:
    return Notification(
        episode_id=_string(data["episode_id"]),
        recipient=_string(data["recipient"]),
        channels=tuple(_string(value) for value in as_list(data["channels"])),
        loudness=Loudness(_string(data["loudness"])),
        digest=None if data["digest"] is None else _string(data["digest"]),
        silent=_boolean(data["silent"]),
        cause=_string(data["cause"]),
        previously_reported=_boolean(data["previously_reported"]),
        route=_string(data["route"]),
        replaces=tuple(_string(value) for value in as_list(data.get("replaces", []))),
    )


def _string(value: JSONValue) -> str:
    if not isinstance(value, str):
        raise TypeError("expected a string in delivery groups snapshot")
    return value


def _boolean(value: JSONValue) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected a boolean in delivery groups snapshot")
    return value
