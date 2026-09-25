"""Public records: the shapes the engine and the policy take and return.

RFP sections 5, 7 and 8 define the fields. ADR 0027 settles the shapes the RFP
leaves open. Records are immutable, times are timezone-aware UTC, and durations
are `timedelta`. A record checks only its own invariants. Rules that depend on
the graph or on time belong to the engine.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo
from enum import Enum
from functools import total_ordering
from typing import Literal

type JSONValue = (
    str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None
)
"""A value that survives `json.dumps` and `json.loads` unchanged."""

type EpisodeForm = Literal["root", "group"]
"""`root` for a failing anchor, `group` for coalesced members (rule 18)."""

type Resolution = Literal["cleared", "removed", "absorbed"]
"""Why an episode resolved (rules 15, 16, 18 and 23)."""

type QuietScope = Literal["all", "node", "node_and_dependents"]
"""What a quiet window covers (rule 22)."""

type ReadinessAnswer = Literal["ready", "degraded", "unknown", "blocked"]
"""The answer to a readiness query (ADR 0023)."""

type BlockedBy = Literal["own", "dependency"]
"""Whether a blocked function fails on its own checks or through a dependency."""

_ZERO = timedelta(0)


@total_ordering
class _Ordered(Enum):
    """An enum whose members compare in the order they are declared."""

    @property
    def rank(self) -> int:
        """Position in declaration order, lowest first."""
        return list(type(self)).index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.rank < other.rank


class Status(_Ordered):
    """Observed condition of a check or a node. `own` is the worst (RFP 5)."""

    PASS = "pass"
    UNKNOWN = "unknown"
    WARN = "warn"
    FAIL = "fail"


class Importance(_Ordered):
    """How much a node matters. An episode takes the maximum over its impact."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Loudness(_Ordered):
    """How a delivery reaches a person. Quiet hours lower it; escalation raises it."""

    RECORD = "record"
    DIGEST = "digest"
    NOTIFY = "notify"
    URGENT = "urgent"


def _require_utc(name: str, value: datetime | None) -> None:
    if value is not None and value.utcoffset() != _ZERO:
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")


def _require_non_negative(name: str, value: timedelta | None) -> None:
    if value is not None and value < _ZERO:
        raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class EngineSettings:
    """Engine-wide durations. All are required (ADR 0018)."""

    settle: timedelta
    rejoin_grace: timedelta
    startup_grace: timedelta
    coalesce_count: int
    coalesce_window: timedelta

    def __post_init__(self) -> None:
        """Reject negative durations and a count that cannot coalesce."""
        _require_non_negative("settle", self.settle)
        _require_non_negative("rejoin_grace", self.rejoin_grace)
        _require_non_negative("startup_grace", self.startup_grace)
        _require_non_negative("coalesce_window", self.coalesce_window)
        if self.coalesce_count < 2:
            raise ValueError("coalesce_count must be at least 2")


@dataclass(frozen=True, slots=True, kw_only=True)
class Edge:
    """A hard dependency. `group` is reserved; version 1 rejects any value."""

    to: str
    group: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Check:
    """One way a node can fail, with the holds that time it (RFP 5).

    `ttl` of `None`, said explicitly, disables observation expiry. It does not
    disable `unknown_hold` (ADR 0026).
    """

    check_id: str
    raise_hold: timedelta
    clear_hold: timedelta
    ttl: timedelta | None
    unknown_hold: timedelta
    affects_own: bool = True
    labels: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject negative holds and a `ttl` that expires at once."""
        _require_non_negative("raise_hold", self.raise_hold)
        _require_non_negative("clear_hold", self.clear_hold)
        _require_non_negative("unknown_hold", self.unknown_hold)
        if self.ttl is not None and self.ttl <= _ZERO:
            raise ValueError("ttl must be positive or None")


@dataclass(frozen=True, slots=True, kw_only=True)
class Node:
    """One capability: one thing that works or does not (ADR 0019)."""

    node_id: str
    kind: str | None = None
    depends_on: tuple[Edge, ...] = ()
    importance: Importance = Importance.NORMAL
    labels: Mapping[str, str] = field(default_factory=dict)
    checks: tuple[Check, ...] = ()

    def __post_init__(self) -> None:
        """Reject repeated check ids and repeated or self edges."""
        check_ids = [check.check_id for check in self.checks]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError(f"{self.node_id} repeats a check id")
        targets = [edge.to for edge in self.depends_on]
        if len(set(targets)) != len(targets):
            raise ValueError(f"{self.node_id} repeats a dependency")
        if self.node_id in targets:
            raise ValueError(f"{self.node_id} depends on itself")


@dataclass(frozen=True, slots=True, kw_only=True)
class Observation:
    """One check result, produced by the adapter (RFP 5)."""

    node_id: str
    check_id: str
    status: Status
    reason: str
    observed_at: datetime
    message: str | None = None
    evidence: Mapping[str, JSONValue] = field(default_factory=dict)
    due_at: datetime | None = None

    def __post_init__(self) -> None:
        """Require UTC times."""
        _require_utc("observed_at", self.observed_at)
        _require_utc("due_at", self.due_at)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuietWindow:
    """No episode opens in scope until `until` (rules 21 and 22).

    The window starts at the `now` of the `quiet` call. `node_id` names the
    node for the scoped forms and is `None` when the scope is `all`.
    """

    scope: QuietScope
    until: datetime
    node_id: str | None = None

    def __post_init__(self) -> None:
        """Require a node exactly when the scope names one."""
        _require_utc("until", self.until)
        if (self.scope == "all") != (self.node_id is None):
            raise ValueError("node_id is required for a scoped window, and only then")


@dataclass(frozen=True, slots=True, kw_only=True)
class Finding:
    """A non-pass check on an episode, or a reason the engine produced.

    `check_id` is `None` for `dependents_failing`, which no check reports.
    `labels` are the check's own. They are never merged with the node's
    (ADR 0020).
    """

    node_id: str
    check_id: str | None
    status: Status
    reason: str
    since: datetime
    message: str | None = None
    due_at: datetime | None = None
    labels: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class Episode:
    """One problem, from onset to resolution, anchored on one node (RFP 5).

    `episode_id` is a UUIDv7 string built from `now` (ADR 0017).
    """

    episode_id: str
    form: EpisodeForm
    anchor: str
    status: Status
    reasons: tuple[Finding, ...]
    recorded: frozenset[str]
    impact: frozenset[str]
    importance: Importance
    opened_at: datetime
    updated_at: datetime
    due_at: datetime | None = None
    absorbed: frozenset[str] = frozenset()
    labels: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeOpened:
    """An episode opened. It carries the whole episode as it now stands."""

    episode: Episode


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeUpdated:
    """An open episode changed (rule 14). It carries the episode as it now stands."""

    episode: Episode


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeResolved:
    """An episode resolved. `absorbed_into` names the absorbing episode."""

    episode: Episode
    resolution: Resolution
    absorbed_into: str | None = None

    def __post_init__(self) -> None:
        """Name the absorbing episode exactly when the resolution is absorbed."""
        if (self.resolution == "absorbed") != (self.absorbed_into is not None):
            raise ValueError(
                "absorbed_into is required for an absorption, and only then"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProbeRequested:
    """The engine wants a fresh observation of a node. The adapter decides."""

    node_id: str


type Event = EpisodeOpened | EpisodeUpdated | EpisodeResolved | ProbeRequested
"""What the engine emits."""


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeCondition:
    """A node named by a query, with the reasons that put it there.

    `watched` is false for a node with no affecting checks. Such a node has
    no reasons of its own.
    """

    node_id: str
    own: Status
    reasons: tuple[str, ...] = ()
    watched: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class Explanation:
    """Why a node is not working: its own findings, then its dependencies.

    `nodes` lists every non-pass node it depends on, roots first. It never
    includes the node asked about.
    """

    node_id: str
    findings: tuple[Finding, ...]
    nodes: tuple[NodeCondition, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Readiness:
    """Whether functions can perform as required (ADR 0023).

    `nodes` names the nodes responsible for the answer, roots first.
    """

    answer: ReadinessAnswer
    nodes: tuple[NodeCondition, ...]
    blocked_by: BlockedBy | None = None

    def __post_init__(self) -> None:
        """Say what blocks exactly when the answer is blocked."""
        if (self.answer == "blocked") != (self.blocked_by is not None):
            raise ValueError("blocked_by is required when blocked, and only then")


@dataclass(frozen=True, slots=True, kw_only=True)
class QuietHours:
    """A recipient's daily quiet hours, in the policy's time zone.

    `end` before `start` wraps past midnight, as in 22:30 to 07:00.
    """

    start: time
    end: time

    def __post_init__(self) -> None:
        """Reject an empty span and clock times that carry their own zone."""
        if self.start == self.end:
            raise ValueError("quiet hours must not start and end at the same time")
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("quiet hours use the policy's time zone")


@dataclass(frozen=True, slots=True, kw_only=True)
class Recipient:
    """Someone deliveries go to, through opaque channel ids."""

    channels: tuple[str, ...]
    quiet_hours: QuietHours | None = None
    sites: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True, kw_only=True)
class Digest:
    """A scheduled summary for one recipient, at a clock time in the policy's zone."""

    at: time
    to: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Match:
    """What a rule matches, per reason (ADR 0020). `None` matches anything.

    `labels` must all be present with the given values, on the check's labels
    laid over the anchor node's. `age` is a minimum episode age. `due_within`
    matches a reason whose `due_at` is at most that far from `now`.
    """

    status: frozenset[Status] | None = None
    importance: frozenset[Importance] | None = None
    reason: frozenset[str] | None = None
    category: frozenset[str] | None = None
    labels: Mapping[str, str] = field(default_factory=dict)
    age: timedelta | None = None
    due_within: timedelta | None = None

    def __post_init__(self) -> None:
        """Reject negative ages and windows."""
        _require_non_negative("age", self.age)
        _require_non_negative("due_within", self.due_within)


@dataclass(frozen=True, slots=True, kw_only=True)
class Rule:
    """One attention rule. Rules are tried in order for each reason (RFP 7)."""

    match: Match
    loudness: Loudness
    to: tuple[str, ...] = ()
    digest: str | None = None
    remind_every: timedelta | None = None
    escalate_after: timedelta | None = None

    def __post_init__(self) -> None:
        """Give a digest rule its digest and a sending rule its recipients."""
        if self.loudness is Loudness.DIGEST and self.digest is None:
            raise ValueError("a digest rule must name its digest")
        if self.loudness in {Loudness.NOTIFY, Loudness.URGENT} and not self.to:
            raise ValueError(f"a {self.loudness.value} rule must name recipients")
        if self.remind_every is not None and self.remind_every <= _ZERO:
            raise ValueError("remind_every must be positive")
        _require_non_negative("escalate_after", self.escalate_after)


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyConfig:
    """The attention policy's configuration: data with a fixed shape (ADR 0010).

    Clock times, in quiet hours and digests, are read in `timezone`.
    """

    batch: timedelta
    timezone: tzinfo
    recipients: Mapping[str, Recipient]
    digests: Mapping[str, Digest]
    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        """Require every name a digest or rule uses to be defined."""
        _require_non_negative("batch", self.batch)
        if not self.rules:
            raise ValueError("a policy needs at least one rule")
        for name, digest in self.digests.items():
            if digest.to not in self.recipients:
                raise ValueError(f"digest {name} goes to unknown {digest.to}")
        for index, rule in enumerate(self.rules):
            unknown = set(rule.to) - set(self.recipients)
            if unknown:
                raise ValueError(f"rule {index} goes to unknown {sorted(unknown)}")
            if rule.digest is not None and rule.digest not in self.digests:
                raise ValueError(f"rule {index} names unknown digest {rule.digest}")


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyContext:
    """What the policy knows about the house at `now`, such as who is home.

    It has no fields yet. They arrive with the fixtures that need them
    (RFP 13, presence-based delivery).
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class Notification:
    """Tell a recipient about an episode, now or in a digest.

    `silent` replaces an earlier message without alerting again. That happens
    when an update does not raise loudness. `record` is never delivered.
    """

    episode_id: str
    recipient: str
    channels: tuple[str, ...]
    loudness: Loudness
    digest: str | None = None
    silent: bool = False

    def __post_init__(self) -> None:
        """Name the digest exactly for digest deliveries. Never deliver `record`."""
        if self.loudness is Loudness.RECORD:
            raise ValueError("record is stored, never delivered")
        if (self.loudness is Loudness.DIGEST) != (self.digest is not None):
            raise ValueError("digest is required for a digest delivery, and only then")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolutionNotice:
    """Silently update or withdraw a message a recipient already has (RFP 7)."""

    episode_id: str
    recipient: str
    channels: tuple[str, ...]
    resolution: Resolution


type Delivery = Notification | ResolutionNotice
"""What the policy returns. The adapter carries it out."""
