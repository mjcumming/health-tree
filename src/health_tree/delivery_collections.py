"""Fixed-window collection of accepted requests with exact retained targets."""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

from health_tree._codec import (
    JSONObject,
    as_list,
    as_object,
    required_time,
    time_to_json,
)
from health_tree.delivery_groups import (
    DeliveryGroup,
    DeliveryGroups,
    _notification_from_json,
    _notification_json,
)
from health_tree.policy import Policy
from health_tree.types import JSONValue, Notification, QuietHours, ResolutionNotice

type _Member = tuple[str, str, str, str]
type _Window = tuple[str, str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionRequest:
    """An accepted request, its timing, and opaque rendering instructions.

    The caller resolves channels before submission. Each channel is an exact
    destination and receives its own collection. Group identity must include
    the saved notification identity. Instructions additionally partition it.
    """

    notification: Notification
    group_id: str
    delay: timedelta
    instructions: Mapping[str, JSONValue] = field(default_factory=dict)
    content: Mapping[str, JSONValue] = field(default_factory=dict)
    quiet_hours: QuietHours | None = None
    timezone: str = "UTC"
    resume_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate explicit timing and detach accepted JSON from caller edits."""
        if not self.group_id:
            raise ValueError("a collection needs a nonempty group id")
        if self.delay < timedelta(0):
            raise ValueError("collection delay must be nonnegative")
        ZoneInfo(self.timezone)
        if self.resume_at is not None and self.resume_at.utcoffset() != timedelta(0):
            raise ValueError("resume_at must be a timezone-aware UTC datetime")
        object.__setattr__(self, "instructions", _copy(self.instructions))
        object.__setattr__(self, "content", _copy(self.content))


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectedGroup:
    """An exact delivery replacement and its accepted presentation data."""

    group: DeliveryGroup
    instructions: Mapping[str, JSONValue]
    contents: Mapping[tuple[str, str], Mapping[str, JSONValue]]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Transfer:
    pending: CollectionRequest | None
    presented: CollectionRequest | None
    due: datetime | None
    pending_id: str | None
    presented_id: str | None


class DeliveryCollections:
    """Collect policy-authorized requests after eligibility, without I/O.

    Persist this snapshot together with the adapter's transport outbox. Calls
    take UTC time. Restoring never requests delivery or restarts a deadline.
    """

    __slots__ = (
        "_due",
        "_groups",
        "_instructions",
        "_last",
        "_message_ids",
        "_pending",
        "_presented",
        "_presented_ids",
        "_sequence",
        "_transfers",
        "_waiting",
    )

    def __init__(self) -> None:
        """Start without pending or presented messages."""
        self._pending: dict[_Member, CollectionRequest] = {}
        self._presented: dict[_Member, CollectionRequest] = {}
        self._due: dict[_Member, datetime] = {}
        self._groups: dict[str, DeliveryGroups] = {}
        self._last: datetime | None = None
        self._message_ids: dict[_Member, str] = {}
        self._presented_ids: dict[_Member, str] = {}
        self._instructions: dict[_Window, JSONObject] = {}
        self._sequence = 0
        self._transfers: dict[_Member, _Transfer] = {}
        self._waiting: set[_Member] = set()

    def pending(self) -> tuple[CollectionRequest, ...]:
        """Return detached accepted requests, including their exact targets."""
        return tuple(replace(request) for request in self._pending.values())

    def apply(
        self,
        requests: Iterable[CollectionRequest],
        resolutions: Iterable[ResolutionNotice],
        now: datetime,
        policy: Policy,
        *,
        held: bool = False,
        flush: bool = True,
    ) -> list[CollectedGroup]:
        """Apply a captured batch and release due collections atomically.

        A caller-owned startup hold retains requests without starting their
        window. Passing ``held=False`` starts their collection at that time.
        """
        self._tick(now)
        incoming = tuple(
            replace(
                request, notification=replace(request.notification, channels=(channel,))
            )
            for request in requests
            for channel in self._targets(request)
        )
        outgoing: list[CollectedGroup] = []
        later: list[CollectionRequest] = []
        for request in incoming:
            outgoing.extend(self._transfer(request))
            key = _member(request.notification)
            previous = self._pending.get(key)
            if previous is None and any(
                member[:3] == key[:3] for member in self._pending
            ):
                continue
            if previous is not None:
                self._pending[key] = replace(
                    previous,
                    content=request.content,
                    notification=replace(
                        previous.notification,
                        replaces=request.notification.replaces,
                    ),
                )
            if key in self._presented and (
                request.notification.silent or request.notification.cause == "open"
            ):
                accepted = replace(
                    self._presented[key],
                    content=request.content,
                    notification=replace(
                        self._presented[key].notification,
                        silent=True,
                        cause=request.notification.cause,
                        replaces=request.notification.replaces,
                    ),
                )
                outgoing.extend(self._emit([accepted], presented=True))
            elif previous is None and not request.notification.silent:
                later.append(request)
        for resolution in resolutions:
            for key in tuple(self._pending):
                if key[:3] == (
                    resolution.episode_id,
                    resolution.route,
                    resolution.recipient,
                ):
                    del self._pending[key]
            outgoing.extend(self._resolve(resolution))
        if flush:
            outgoing.extend(self.advance(now, policy, held=held))
        cohort = set(self._message_ids.values())
        for request in later:
            if not policy.delivery_eligibility(request.notification, now).eligible:
                continue
            self._pending[_member(request.notification)] = request
            if not held:
                self._start(request, now, cohort=cohort)
        if flush:
            outgoing.extend(self.advance(now, policy, held=held))
        return outgoing

    def advance(
        self, now: datetime, policy: Policy, *, held: bool = False
    ) -> list[CollectedGroup]:
        """Release due eligible members, retaining shelves and accepted hours."""
        self._tick(now)
        for key, request in tuple(self._pending.items()):
            eligibility = policy.delivery_eligibility(request.notification, now)
            if not eligibility.eligible:
                del self._pending[key]
                continue
            resume_at = eligibility.resume_at
            if request.notification.replaces and request.resume_at is not None:
                resume_at = max(request.resume_at, resume_at or request.resume_at)
            if request.resume_at != resume_at:
                self._pending[key] = replace(request, resume_at=resume_at)
        self._prune_windows()
        if held:
            return []
        for request in self._pending.values():
            self._start(request, now)
        ready: list[CollectionRequest] = []
        for key, deadline in tuple(self._due.items()):
            request = self._pending[key]
            deadline = max(deadline, request.resume_at or deadline)
            if deadline > now:
                continue
            eligibility = policy.delivery_eligibility(request.notification, now)
            permitted = _permitted_at(request, now)
            resume = max(permitted, eligibility.resume_at or now)
            if resume > now:
                self._due[key] = resume
            else:
                ready.append(request)
                del self._pending[key]
                del self._due[key]
        return self._emit(ready)

    def next_deadline(self) -> datetime | None:
        """Return the next collection deadline, excluding startup-held requests."""
        deadlines = [
            max(due, self._pending[key].resume_at or due)
            for key, due in self._due.items()
        ]
        deadlines.extend(
            request.resume_at
            for key in self._waiting
            if (request := self._pending[key]).resume_at is not None
        )
        return min(deadlines, default=None)

    def deactivate(
        self, *, routes: Collection[str] | None = None, preserve_pending: bool = False
    ) -> list[CollectedGroup]:
        """Cancel selected pending requests and silently withdraw their messages."""
        for key, request in tuple(self._pending.items()):
            if not preserve_pending and (
                routes is None or request.notification.route in routes
            ):
                del self._pending[key]
        result: list[CollectedGroup] = []
        for groups in self._groups.values():
            result.extend(
                self._result(group) for group in groups.deactivate(routes=routes)
            )
        for key, request in tuple(self._presented.items()):
            if routes is None or request.notification.route in routes:
                del self._presented[key]
        self._prune_windows()
        return result

    def snapshot(self) -> JSONObject:
        """Return durable membership, deadlines and accepted instructions."""
        return {
            "schema_version": 1,
            "sequence": self._sequence,
            "message_ids": [
                {
                    "episode": key[0],
                    "route": key[1],
                    "recipient": key[2],
                    "channel": key[3],
                    "id": identity,
                }
                for key, identity in self._message_ids.items()
            ],
            "presented_ids": [
                {"key": list(key), "id": identity}
                for key, identity in self._presented_ids.items()
            ],
            "instructions": [
                {
                    "group": key[0],
                    "recipient": key[1],
                    "channel": key[2],
                    "value": value,
                }
                for key, value in self._instructions.items()
            ],
            "pending": [_request_json(value) for value in self._pending.values()],
            "waiting": [list(key) for key in sorted(self._waiting)],
            "presented": [_request_json(value) for value in self._presented.values()],
            "deadlines": [
                {
                    "episode": key[0],
                    "route": key[1],
                    "recipient": key[2],
                    "channel": key[3],
                    "due": time_to_json(due),
                }
                for key, due in self._due.items()
            ],
            "groups": {
                channel: groups.snapshot() for channel, groups in self._groups.items()
            },
            "transfers": [
                {
                    "key": list(key),
                    "pending": None
                    if value.pending is None
                    else _request_json(value.pending),
                    "presented": None
                    if value.presented is None
                    else _request_json(value.presented),
                    "due": time_to_json(value.due),
                    "pending_id": value.pending_id,
                    "presented_id": value.presented_id,
                }
                for key, value in self._transfers.items()
            ],
        }

    def restore(self, state: Mapping[str, JSONValue]) -> None:
        """Atomically restore accepted requests without producing delivery."""
        if state.get("schema_version") != 1:
            raise ValueError("unsupported delivery collections snapshot")
        pending = _requests_from_json(state["pending"])
        waiting = {_key_from_json(value) for value in as_list(state["waiting"])}
        if not waiting <= pending.keys():
            raise ValueError("invalid collection eligibility wait")
        presented = _requests_from_json(state["presented"])
        deadlines: dict[_Member, datetime] = {}
        for value in as_list(state["deadlines"]):
            row = as_object(value)
            key = (
                str(row["episode"]),
                str(row["route"]),
                str(row["recipient"]),
                str(row["channel"]),
            )
            if key in deadlines or key not in pending:
                raise ValueError("invalid collection deadline")
            deadlines[key] = required_time(row["due"])
        groups: dict[str, DeliveryGroups] = {}
        for channel, value in as_object(state["groups"]).items():
            groups[channel] = reducer = DeliveryGroups()
            reducer.restore(as_object(value))
        sequence = state["sequence"]
        if type(sequence) is not int or sequence < 0:
            raise ValueError("invalid collection sequence")
        message_ids: dict[_Member, str] = {}
        for value in as_list(state["message_ids"]):
            row = as_object(value)
            message_ids[
                (
                    str(row["episode"]),
                    str(row["route"]),
                    str(row["recipient"]),
                    str(row["channel"]),
                )
            ] = str(row["id"])
        presented_ids = {
            _key_from_json(as_object(value)["key"]): str(as_object(value)["id"])
            for value in as_list(state["presented_ids"])
        }
        instructions = {
            (str(row["group"]), str(row["recipient"]), str(row["channel"])): as_object(
                row["value"]
            )
            for value in as_list(state["instructions"])
            for row in [as_object(value)]
        }
        transfers: dict[_Member, _Transfer] = {}
        for value in as_list(state["transfers"]):
            row = as_object(value)
            transfers[_key_from_json(row["key"])] = _Transfer(
                pending=None
                if row["pending"] is None
                else next(iter(_requests_from_json([row["pending"]]).values())),
                presented=None
                if row["presented"] is None
                else next(iter(_requests_from_json([row["presented"]]).values())),
                due=None if row["due"] is None else required_time(row["due"]),
                pending_id=None
                if row["pending_id"] is None
                else str(row["pending_id"]),
                presented_id=None
                if row["presented_id"] is None
                else str(row["presented_id"]),
            )
        if (
            not deadlines.keys() <= message_ids.keys()
            or not presented.keys() <= presented_ids.keys()
        ):
            raise ValueError("collection membership is missing a message identity")
        self._pending, self._presented = pending, presented
        self._waiting = waiting
        self._due, self._groups = deadlines, groups
        self._sequence, self._message_ids, self._transfers = (
            sequence,
            message_ids,
            transfers,
        )
        self._presented_ids, self._instructions = presented_ids, instructions
        self._last = None

    def _tick(self, now: datetime) -> None:
        if now.utcoffset() != timedelta(0):
            raise ValueError("now must be a timezone-aware UTC datetime")
        if self._last is not None and now < self._last:
            raise ValueError("now must not go backwards")
        self._last = now

    def _start(
        self,
        request: CollectionRequest,
        now: datetime,
        *,
        cohort: Collection[str] | None = None,
    ) -> None:
        key = _member(request.notification)
        if key in self._due:
            return
        if request.resume_at is not None and request.resume_at > now:
            self._waiting.add(key)
            return
        self._waiting.discard(key)
        delay = (
            timedelta(0) if request.notification.digest is not None else request.delay
        )
        compatible = [
            (due, member)
            for member, due in self._due.items()
            if member in self._pending
            and _window(self._pending[member]) == _window(request)
            and (
                due > now
                or (
                    due == now
                    and cohort is not None
                    and self._message_ids[member] not in cohort
                )
            )
        ]
        if compatible:
            due, previous = min(compatible)
            self._due[key] = due
            self._message_ids[key] = self._message_ids[previous]
        else:
            self._sequence += 1
            self._due[key] = now + delay
            self._message_ids[key] = f"{_identity(request)}:{self._sequence}"

    def _prune_windows(self) -> None:
        self._waiting.intersection_update(self._pending)
        self._due = {key: due for key, due in self._due.items() if key in self._pending}
        retained = (
            self._pending.keys() | self._presented.keys() | self._transfers.keys()
        )
        self._message_ids = {
            key: identity
            for key, identity in self._message_ids.items()
            if key in retained
        }
        self._presented_ids = {
            key: identity
            for key, identity in self._presented_ids.items()
            if key in self._presented
        }

    def _targets(self, request: CollectionRequest) -> tuple[str, ...]:
        notification = request.notification
        current = (notification.episode_id, notification.route, notification.recipient)
        continuing = dict.fromkeys(
            key[3] for key in self._pending if key[:3] == current
        )
        if notification.silent or notification.cause == "open":
            continuing.update(
                dict.fromkeys(key[3] for key in self._presented if key[:3] == current)
            )
        accepted = dict.fromkeys(
            key[3]
            for key in self._pending.keys()
            | self._presented.keys()
            | self._transfers.keys()
            if key[0] in notification.replaces
            and key[1:3] == (notification.route, notification.recipient)
        )
        return tuple(accepted or continuing or dict.fromkeys(notification.channels))

    def _transfer(self, request: CollectionRequest) -> list[CollectedGroup]:
        notification = request.notification
        key = _member(notification)
        result: list[CollectedGroup] = []
        for identity in notification.replaces:
            old_key = (identity, *key[1:])
            pending = self._pending.pop(old_key, None)
            due = self._due.pop(old_key, None)
            presented = self._presented.get(old_key)
            if pending is not None or presented is not None:
                self._transfers[old_key] = _Transfer(
                    pending=pending,
                    presented=presented,
                    due=due,
                    pending_id=self._message_ids.get(old_key),
                    presented_id=self._presented_ids.get(old_key),
                )
            previous = self._transfers.get(old_key)
            if previous is not None:
                pending, presented, due = (
                    previous.pending,
                    previous.presented,
                    previous.due,
                )
            if pending is not None and not (
                key in self._presented
                and pending.notification.cause in {"open", "activate"}
            ):
                replacement = replace(
                    pending,
                    notification=replace(
                        pending.notification,
                        episode_id=notification.episode_id,
                        replaces=notification.replaces,
                    ),
                    content=request.content,
                )
                current = self._pending.setdefault(key, replacement)
                if (
                    due is not None
                    and _window(current) == _window(replacement)
                    and due <= self._due.get(key, due)
                ):
                    self._due[key] = due
                    assert previous is not None and previous.pending_id is not None
                    self._message_ids[key] = previous.pending_id
            if presented is not None:
                pending_open = self._pending.get(key)
                if pending_open is not None and pending_open.notification.cause in {
                    "open",
                    "activate",
                }:
                    self._pending.pop(key)
                    self._due.pop(key, None)
                accepted = self._presented.get(key, presented)
                replacement = replace(
                    accepted,
                    notification=replace(
                        accepted.notification,
                        episode_id=notification.episode_id,
                        silent=True,
                        cause="update",
                        replaces=notification.replaces,
                    ),
                    content=request.content,
                )
                self._presented[key] = replacement
                assert previous is not None and previous.presented_id is not None
                self._presented_ids.setdefault(key, previous.presented_id)
                self._instructions[(self._presented_ids[key], key[2], key[3])] = _copy(
                    replacement.instructions
                )
                reducer = self._groups[key[3]]
                updates = reducer.apply(
                    [
                        ResolutionNotice(
                            episode_id=identity,
                            route=key[1],
                            recipient=key[2],
                            channels=(key[3],),
                            resolution="absorbed",
                        ),
                        replacement.notification,
                    ],
                    {(key[0], key[1]): self._presented_ids[key]},
                )
                result.extend(self._result(group) for group in updates)
                self._presented.pop(old_key, None)
                self._presented_ids.pop(old_key, None)
        return result

    def _emit(
        self, requests: list[CollectionRequest], *, presented: bool = False
    ) -> list[CollectedGroup]:
        channels: dict[str, list[CollectionRequest]] = {}
        for request in requests:
            key = _member(request.notification)
            self._presented[key] = request
            if not presented:
                self._presented_ids[key] = self._message_ids[key]
            self._instructions[(self._presented_ids[key], key[2], key[3])] = _copy(
                request.instructions
            )
            channels.setdefault(key[3], []).append(request)
        result: list[CollectedGroup] = []
        for channel, members in channels.items():
            reducer = self._groups.setdefault(channel, DeliveryGroups())
            updates = reducer.apply(
                [request.notification for request in members],
                {
                    (
                        request.notification.episode_id,
                        request.notification.route,
                    ): self._presented_ids[_member(request.notification)]
                    for request in members
                },
            )
            result.extend(self._result(group) for group in updates)
        return result

    def _resolve(self, resolution: ResolutionNotice) -> list[CollectedGroup]:
        result: list[CollectedGroup] = []
        for channel, reducer in self._groups.items():
            updates = reducer.apply([replace(resolution, channels=(channel,))], {})
            result.extend(self._result(group) for group in updates)
        for key in tuple(self._presented):
            if key[:3] == (
                resolution.episode_id,
                resolution.route,
                resolution.recipient,
            ):
                del self._presented[key]
        for key in tuple(self._transfers):
            if key[:3] == (
                resolution.episode_id,
                resolution.route,
                resolution.recipient,
            ):
                del self._transfers[key]
        self._prune_windows()
        return result

    def _result(self, group: DeliveryGroup) -> CollectedGroup:
        key = (group.group_id, group.recipient, group.channels[0])
        instructions = _copy(self._instructions[key])
        if group.closed:
            del self._instructions[key]
        return CollectedGroup(
            group=group,
            instructions=instructions,
            contents={
                (member.episode_id, member.route): _copy(
                    self._presented[_member(member)].content
                )
                for member in group.members
            },
        )


def _member(notification: Notification) -> _Member:
    return (
        notification.episode_id,
        notification.route,
        notification.recipient,
        notification.channels[0],
    )


def _key_from_json(value: JSONValue) -> _Member:
    values = as_list(value)
    if len(values) != 4 or any(not isinstance(item, str) for item in values):
        raise ValueError("invalid collection member identity")
    return str(values[0]), str(values[1]), str(values[2]), str(values[3])


def _identity(request: CollectionRequest) -> str:
    compatible = {
        "instructions": dict(request.instructions),
        "delay": request.delay.total_seconds(),
        "quiet": _quiet_json(request.quiet_hours),
        "timezone": request.timezone,
    }
    fingerprint = hashlib.sha256(
        json.dumps(compatible, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"{request.group_id}:{fingerprint}"


def _window(request: CollectionRequest) -> _Window:
    return (
        _identity(request),
        request.notification.recipient,
        request.notification.channels[0],
    )


def _permitted_at(request: CollectionRequest, now: datetime) -> datetime:
    quiet = request.quiet_hours
    if quiet is None or request.notification.digest is not None:
        return now
    zone = ZoneInfo(request.timezone)
    local = now.astimezone(zone)
    clock = local.time()
    inside = (
        quiet.start <= clock < quiet.end
        if quiet.start < quiet.end
        else clock >= quiet.start or clock < quiet.end
    )
    if not inside:
        return now
    day = local.date()
    candidate = datetime.combine(day, quiet.end, zone).astimezone(UTC)
    if candidate <= now:
        candidate = datetime.combine(
            day + timedelta(days=1), quiet.end, zone
        ).astimezone(UTC)
    return candidate


def _copy(value: Mapping[str, JSONValue]) -> JSONObject:
    return as_object(json.loads(json.dumps(dict(value))))


def _quiet_json(value: QuietHours | None) -> JSONObject | None:
    return (
        None
        if value is None
        else {"start": value.start.isoformat(), "end": value.end.isoformat()}
    )


def _request_json(request: CollectionRequest) -> JSONObject:
    return {
        "notification": _notification_json(request.notification),
        "group_id": request.group_id,
        "delay": request.delay.total_seconds(),
        "instructions": _copy(request.instructions),
        "content": _copy(request.content),
        "quiet_hours": _quiet_json(request.quiet_hours),
        "timezone": request.timezone,
        "resume_at": time_to_json(request.resume_at),
    }


def _requests_from_json(value: JSONValue) -> dict[_Member, CollectionRequest]:
    result: dict[_Member, CollectionRequest] = {}
    for item in as_list(value):
        row = as_object(item)
        quiet = row["quiet_hours"]
        hours = None if quiet is None else as_object(quiet)
        request = CollectionRequest(
            notification=_notification_from_json(as_object(row["notification"])),
            group_id=str(row["group_id"]),
            delay=timedelta(seconds=float(str(row["delay"]))),
            instructions=as_object(row["instructions"]),
            content=as_object(row["content"]),
            timezone=str(row["timezone"]),
            resume_at=None
            if row["resume_at"] is None
            else required_time(row["resume_at"]),
            quiet_hours=None
            if hours is None
            else QuietHours(
                start=time.fromisoformat(str(hours["start"])),
                end=time.fromisoformat(str(hours["end"])),
            ),
        )
        if len(request.notification.channels) != 1:
            raise ValueError("a stored collection member needs exactly one destination")
        key = _member(request.notification)
        if key in result:
            raise ValueError("duplicate collection member")
        result[key] = request
    return result
