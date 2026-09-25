"""The attention policy: who hears what, how loudly, and when (ADR 0010).

The policy tracks every open episode it has seen. Each reason is matched on its
own, and the loudest result wins (ADR 0020). Loudness decides delivery:

- `record`: nothing is sent.
- `digest`: the episode waits for its digest.
- `notify`: sent after `batch`, or when the recipient's quiet hours end.
- `urgent`: sent at once, through quiet hours.

A rise in loudness makes noise. Anything else only replaces the message the
recipient already has, silently. A resolution goes silently to whoever received
the episode. An episode resolved before it was delivered is simply dropped.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from health_tree._codec import (
    JSONObject,
    as_list,
    as_object,
    episode_from_json,
    episode_to_json,
    required_time,
    strings_list,
    time_from_json,
    time_to_json,
)
from health_tree.types import (
    Delivery,
    Episode,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Event,
    Finding,
    JSONValue,
    Loudness,
    Match,
    Notification,
    PolicyConfig,
    PolicyContext,
    QuietHours,
    ResolutionNotice,
    Rule,
)

SCHEMA_VERSION = 2
"""The version of the data `Policy.snapshot` returns."""

_ZERO = timedelta(0)
_DAY = timedelta(days=1)
_LADDER = list(Loudness)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Decision:
    loudness: Loudness
    rule: Rule | None
    recipients: tuple[str, ...]
    digest: str | None


_SILENT = _Decision(loudness=Loudness.RECORD, rule=None, recipients=(), digest=None)


@dataclass(slots=True, kw_only=True)
class _Pending:
    recipient: str
    due: datetime
    cause: str = "open"


@dataclass(slots=True, kw_only=True)
class _Tracked:
    episode: Episode
    decision: _Decision
    sent_to: dict[str, None] = field(default_factory=dict)
    pending: list[_Pending] = field(default_factory=list)
    digested: bool = False
    last_sent: datetime | None = None
    attention_since: datetime | None = None
    sent_at: dict[str, datetime] = field(default_factory=dict)


class Policy:
    """A pure state machine from engine events to deliveries.

    Args:
        config: Recipients, digests, rules, and the batch delay.
    """

    __slots__ = ("_config", "_last", "_next_digest", "_shelves", "_tracked")

    def __init__(self, config: PolicyConfig) -> None:
        """Create a policy from its configuration."""
        self._config = config
        self._tracked: dict[str, _Tracked] = {}
        self._shelves: dict[str, datetime] = {}
        self._next_digest: dict[str, datetime] = {}
        self._last: datetime | None = None

    def handle(
        self, event: Event, now: datetime, context: PolicyContext
    ) -> list[Delivery]:
        """Turn one engine event into the deliveries it causes now."""
        self._tick(now)
        match event:
            case EpisodeOpened(episode=episode):
                tracked = _Tracked(episode=episode, decision=self._decide(episode, now))
                self._tracked[episode.episode_id] = tracked
                return self._announce(tracked, now)
            case EpisodeUpdated(episode=episode):
                known = self._tracked.get(episode.episode_id)
                if known is None:
                    return self.handle(EpisodeOpened(episode=episode), now, context)
                known.episode = episode
                return self._redecide(known, now, changed=True)
            case EpisodeResolved(episode=episode, resolution=resolution):
                gone = self._tracked.pop(episode.episode_id, None)
                self._shelves.pop(episode.episode_id, None)
                if gone is None:
                    return []
                return [
                    ResolutionNotice(
                        episode_id=episode.episode_id,
                        recipient=recipient,
                        channels=self._channels(recipient),
                        resolution=resolution,
                    )
                    for recipient in gone.sent_to
                ]
        return []

    def advance(self, now: datetime, context: PolicyContext) -> list[Delivery]:
        """Deliver what is due: batches, digests, reminders, ends of quiet hours."""
        self._tick(now)
        deliveries: list[Delivery] = []
        for tracked in list(self._tracked.values()):
            deliveries.extend(self._redecide(tracked, now, changed=False))
        for tracked in self._tracked.values():
            deliveries.extend(self._release(tracked, now))
        for tracked in self._tracked.values():
            deliveries.extend(self._remind(tracked, now))
        for name in self._config.digests:
            if self._next_digest[name] <= now:
                deliveries.extend(self._digest(name, now))
                self._next_digest[name] = self._occurrence(
                    self._config.digests[name].at, now, after=True
                )
        return deliveries

    def activate(self, now: datetime, context: PolicyContext) -> list[Delivery]:
        """Start attention afresh for tracked episodes, preserving their history."""
        self._tick(now)
        self._next_digest = {
            name: self._occurrence(digest.at, now, after=False)
            for name, digest in self._config.digests.items()
        }
        deliveries: list[Delivery] = []
        for tracked in self._tracked.values():
            tracked.attention_since = now
            tracked.last_sent = None
            tracked.sent_to.clear()
            tracked.sent_at.clear()
            tracked.digested = False
            tracked.decision = self._decide(tracked.episode, now, now)
            deliveries.extend(self._announce(tracked, now, cause="activate"))
        return deliveries

    def explain(self, episode_id: str) -> dict[str, JSONValue]:
        """Return a detached explanation of the last evaluated attention state."""
        tracked = self._tracked[episode_id]
        decision = tracked.decision
        return {
            "episode_id": episode_id,
            "opened_at": time_to_json(tracked.episode.opened_at),
            "attention_since": time_to_json(
                tracked.attention_since or tracked.episode.opened_at
            ),
            "loudness": decision.loudness.value,
            "rule_index": (
                self._config.rules.index(decision.rule)
                if decision.rule is not None
                else None
            ),
            "recipients": strings_list(decision.recipients),
            "digest": decision.digest,
            "sent_to": strings_list(tracked.sent_to),
            "pending": {p.recipient: time_to_json(p.due) for p in tracked.pending},
            "last_sent": time_to_json(tracked.last_sent),
        }

    def shelve(self, episode_id: str, until: datetime, now: datetime) -> list[Delivery]:
        """Hold deliveries for one episode until `until`. An operator action."""
        self._tick(now)
        self._shelves[episode_id] = until
        return []

    def next_deadline(self) -> datetime | None:
        """The next time `advance` would deliver anything or change a decision."""
        if self._last is None:
            return None
        now = self._last
        times: list[datetime] = [*self._next_digest.values()]
        for tracked in self._tracked.values():
            times.extend(pending.due for pending in tracked.pending)
            rule = tracked.decision.rule
            if rule is not None and rule.remind_every:
                if tracked.decision.loudness is Loudness.DIGEST and tracked.last_sent:
                    times.append(tracked.last_sent + rule.remind_every)
                elif tracked.decision.loudness in {Loudness.NOTIFY, Loudness.URGENT}:
                    waiting = {p.recipient for p in tracked.pending}
                    times.extend(
                        sent + rule.remind_every
                        for recipient, sent in tracked.sent_at.items()
                        if recipient in tracked.decision.recipients
                        and recipient not in waiting
                    )
            times.extend(self._thresholds(tracked))
        return min((t for t in times if t > now), default=None)

    def snapshot(self) -> dict[str, JSONValue]:
        """All state, as JSON-compatible data with a schema version."""
        return {
            "schema_version": SCHEMA_VERSION,
            "now": time_to_json(self._last),
            "next_digest": {
                name: time_to_json(at) for name, at in self._next_digest.items()
            },
            "shelves": {
                episode_id: time_to_json(until)
                for episode_id, until in self._shelves.items()
            },
            "tracked": [
                _tracked_to_json(tracked) for tracked in self._tracked.values()
            ],
        }

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> None:
        """Restore a snapshot taken by `snapshot`. Decisions are made afresh."""
        if state.get("schema_version") not in {1, SCHEMA_VERSION}:
            raise ValueError(f"cannot restore schema {state.get('schema_version')!r}")
        self._tick(now)
        for name, at in as_object(state["next_digest"]).items():
            if name in self._config.digests:
                self._next_digest[name] = required_time(at)
        self._shelves = {
            episode_id: required_time(until)
            for episode_id, until in as_object(state["shelves"]).items()
        }
        for item in as_list(state["tracked"]):
            data = as_object(item)
            episode = episode_from_json(data["episode"])
            attention_since = time_from_json(data.get("attention_since"))
            self._tracked[episode.episode_id] = _Tracked(
                episode=episode,
                attention_since=attention_since,
                sent_at={
                    name: required_time(at)
                    for name, at in as_object(
                        data.get(
                            "sent_at",
                            {
                                str(name): data["last_sent"]
                                for name in as_list(data["sent_to"])
                                if data["last_sent"] is not None
                            },
                        )
                    ).items()
                    if name in self._config.recipients
                },
                decision=self._decide(
                    episode, required_time(state["now"]), attention_since
                ),
                sent_to={
                    str(name): None
                    for name in as_list(data["sent_to"])
                    if name in self._config.recipients
                },
                pending=[
                    _Pending(
                        recipient=str(as_object(p)["recipient"]),
                        due=required_time(as_object(p)["due"]),
                        cause=str(as_object(p).get("cause", "open")),
                    )
                    for p in as_list(data["pending"])
                    if as_object(p)["recipient"] in self._config.recipients
                ],
                digested=bool(data["digested"]),
                last_sent=time_from_json(data["last_sent"]),
            )

    def _tick(self, now: datetime) -> None:
        if now.utcoffset() != _ZERO:
            raise ValueError("now must be a timezone-aware UTC datetime")
        if self._last is not None and now < self._last:
            raise ValueError("now must not go backwards")
        if self._last is None:
            for name, digest in self._config.digests.items():
                self._next_digest[name] = self._occurrence(digest.at, now, after=False)
        self._last = now

    def _channels(self, recipient: str) -> tuple[str, ...]:
        return self._config.recipients[recipient].channels

    def _decide(
        self, episode: Episode, now: datetime, attention_since: datetime | None = None
    ) -> _Decision:
        """ADR 0020: match each reason, first rule wins; the loudest reason wins."""
        best = _SILENT
        best_index = len(self._config.rules)
        for finding in episode.reasons:
            for index, rule in enumerate(self._config.rules):
                if not _matches(rule.match, finding, episode, now):
                    continue
                decision = self._outcome(rule, episode, now, attention_since)
                if decision.loudness > best.loudness or (
                    decision.loudness == best.loudness and index < best_index
                ):
                    best, best_index = decision, index
                break
        return best

    def _outcome(
        self,
        rule: Rule,
        episode: Episode,
        now: datetime,
        attention_since: datetime | None,
    ) -> _Decision:
        recipients = rule.to
        if not recipients and rule.digest is not None:
            recipients = (self._config.digests[rule.digest].to,)
        loudness = rule.loudness
        if (
            rule.escalate_after is not None
            and now - (attention_since or episode.opened_at) >= rule.escalate_after
        ):
            raised = _LADDER[min(_LADDER.index(loudness) + 1, len(_LADDER) - 1)]
            deliverable = (
                raised is not Loudness.DIGEST or rule.digest is not None
            ) and bool(recipients)
            if deliverable:
                loudness = raised
        return _Decision(
            loudness=loudness, rule=rule, recipients=recipients, digest=rule.digest
        )

    def _announce(
        self, tracked: _Tracked, now: datetime, *, cause: str = "open"
    ) -> list[Delivery]:
        """A new episode, or a louder one: this is the noise."""
        decision = tracked.decision
        tracked.pending.clear()
        if decision.loudness is Loudness.DIGEST:
            tracked.digested = False
            return []
        if decision.loudness is Loudness.URGENT:
            until = self._shelves.get(tracked.episode.episode_id)
            if until is not None and until > now:
                tracked.pending = [
                    _Pending(recipient=r, due=until, cause=cause)
                    for r in decision.recipients
                ]
                return []
            return [self._send(tracked, r, now, cause) for r in decision.recipients]
        if decision.loudness is Loudness.NOTIFY:
            due = now + self._config.batch
            tracked.pending = [
                _Pending(recipient=r, due=due, cause=cause) for r in decision.recipients
            ]
        return []

    def _redecide(
        self, tracked: _Tracked, now: datetime, *, changed: bool
    ) -> list[Delivery]:
        """Match again. Louder makes noise; otherwise refresh silently if changed."""
        before = tracked.decision
        tracked.decision = after = self._decide(
            tracked.episode, now, tracked.attention_since
        )
        if after.loudness > before.loudness:
            return self._announce(tracked, now, cause="escalate")
        if after.loudness < before.loudness:
            tracked.pending.clear()
            if after.loudness is Loudness.DIGEST:
                tracked.digested = False
        elif not changed:
            return []
        return self._replace(tracked)

    def _replace(self, tracked: _Tracked) -> list[Delivery]:
        """Silently refresh the message recipients already have."""
        decision = tracked.decision
        if decision.loudness is Loudness.RECORD:
            return []
        digest = decision.digest if decision.loudness is Loudness.DIGEST else None
        return [
            Notification(
                episode_id=tracked.episode.episode_id,
                recipient=recipient,
                channels=self._channels(recipient),
                loudness=decision.loudness,
                digest=digest,
                silent=True,
                cause="update",
            )
            for recipient in tracked.sent_to
        ]

    def _release(self, tracked: _Tracked, now: datetime) -> list[Delivery]:
        """Send batched `notify` deliveries, holding them through quiet hours."""
        deliveries: list[Delivery] = []
        shelf = self._shelves.get(tracked.episode.episode_id)
        for pending in list(tracked.pending):
            if pending.due > now:
                continue
            if shelf is not None and shelf > now:
                pending.due = shelf
                continue
            quiet = self._config.recipients[pending.recipient].quiet_hours
            if (
                tracked.decision.loudness is Loudness.NOTIFY
                and quiet is not None
                and self._in_quiet_hours(quiet, now)
            ):
                pending.due = self._occurrence(quiet.end, now, after=True)
                continue
            tracked.pending.remove(pending)
            deliveries.append(
                self._send(tracked, pending.recipient, now, pending.cause)
            )
        return deliveries

    def _remind(self, tracked: _Tracked, now: datetime) -> list[Delivery]:
        """Repeat each recipient's message without bypassing their holds."""
        rule = tracked.decision.rule
        if rule is None or rule.remind_every is None:
            return []
        if tracked.decision.loudness is Loudness.DIGEST:
            if (
                tracked.last_sent is not None
                and now >= tracked.last_sent + rule.remind_every
            ):
                tracked.digested = False
                tracked.last_sent = now
            return []
        if tracked.decision.loudness is Loudness.RECORD:
            return []
        waiting = {p.recipient for p in tracked.pending}
        tracked.pending.extend(
            _Pending(recipient=recipient, due=now, cause="remind")
            for recipient in tracked.decision.recipients
            if recipient not in waiting
            and recipient in tracked.sent_at
            and now >= tracked.sent_at[recipient] + rule.remind_every
        )
        return self._release(tracked, now)

    def _digest(self, name: str, now: datetime) -> list[Delivery]:
        recipient = self._config.digests[name].to
        deliveries: list[Delivery] = []
        for tracked in self._tracked.values():
            decision = tracked.decision
            shelf = self._shelves.get(tracked.episode.episode_id)
            if (
                decision.loudness is not Loudness.DIGEST
                or decision.digest != name
                or tracked.digested
                or (shelf is not None and shelf > now)
            ):
                continue
            tracked.digested = True
            tracked.sent_to[recipient] = None
            tracked.sent_at[recipient] = now
            tracked.last_sent = now
            deliveries.append(
                Notification(
                    episode_id=tracked.episode.episode_id,
                    recipient=recipient,
                    channels=self._channels(recipient),
                    loudness=Loudness.DIGEST,
                    digest=name,
                    cause="digest",
                )
            )
        return deliveries

    def _send(
        self, tracked: _Tracked, recipient: str, now: datetime, cause: str
    ) -> Notification:
        tracked.sent_to[recipient] = None
        tracked.sent_at[recipient] = now
        tracked.last_sent = now
        return Notification(
            episode_id=tracked.episode.episode_id,
            recipient=recipient,
            channels=self._channels(recipient),
            loudness=tracked.decision.loudness,
            cause=cause,
        )

    def _thresholds(self, tracked: _Tracked) -> Iterable[datetime]:
        """Times at which a rule's age or deadline starts to match."""
        episode = tracked.episode
        for rule in self._config.rules:
            if rule.match.age is not None:
                yield episode.opened_at + rule.match.age
            if rule.escalate_after is not None:
                yield (
                    tracked.attention_since or episode.opened_at
                ) + rule.escalate_after
            if rule.match.due_within is not None:
                for finding in episode.reasons:
                    if finding.due_at is not None:
                        yield finding.due_at - rule.match.due_within

    def _occurrence(self, clock: time, now: datetime, *, after: bool) -> datetime:
        """The next time the policy's clock shows `clock`, in UTC."""
        zone = self._config.timezone
        local = now.astimezone(zone)
        candidate = datetime.combine(local.date(), clock, tzinfo=zone)
        if candidate < now or (after and candidate == now):
            candidate = datetime.combine(local.date() + _DAY, clock, tzinfo=zone)
        return candidate.astimezone(now.tzinfo)

    def _in_quiet_hours(self, quiet: QuietHours, now: datetime) -> bool:
        clock = now.astimezone(self._config.timezone).time()
        if quiet.start < quiet.end:
            return quiet.start <= clock < quiet.end
        return clock >= quiet.start or clock < quiet.end


def _matches(match: Match, finding: Finding, episode: Episode, now: datetime) -> bool:
    labels = {**episode.labels, **finding.labels}
    due_within = match.due_within
    return (
        (match.status is None or finding.status in match.status)
        and (match.importance is None or episode.importance in match.importance)
        and (match.reason is None or finding.reason in match.reason)
        and (match.category is None or labels.get("category") in match.category)
        and all(labels.get(key) == value for key, value in match.labels.items())
        and (match.age is None or now - episode.opened_at >= match.age)
        and (
            due_within is None
            or (finding.due_at is not None and finding.due_at - now <= due_within)
        )
    )


def _tracked_to_json(tracked: _Tracked) -> JSONObject:
    return {
        "episode": episode_to_json(tracked.episode),
        "sent_to": strings_list(tracked.sent_to),
        "pending": [
            {"recipient": p.recipient, "due": time_to_json(p.due), "cause": p.cause}
            for p in tracked.pending
        ],
        "digested": tracked.digested,
        "last_sent": time_to_json(tracked.last_sent),
        "attention_since": time_to_json(tracked.attention_since),
        "sent_at": {name: time_to_json(at) for name, at in tracked.sent_at.items()},
    }
