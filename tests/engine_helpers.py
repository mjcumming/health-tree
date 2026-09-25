"""Small builders for engine and policy unit tests."""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from health_tree.types import (
    Check,
    Edge,
    EngineSettings,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Event,
    Importance,
    Node,
    Observation,
    ProbeRequested,
    Status,
)

T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
SETTINGS = EngineSettings(
    settle=timedelta(minutes=2),
    rejoin_grace=timedelta(minutes=1),
    startup_grace=timedelta(0),
    coalesce_count=3,
    coalesce_window=timedelta(seconds=60),
)


def at(seconds: float) -> datetime:
    """`T0` plus some seconds."""
    return T0 + timedelta(seconds=seconds)


def check(
    check_id: str = "state",
    *,
    raise_hold: float = 0,
    clear_hold: float = 30,
    ttl: float | None = 3600,
    unknown_hold: float = 900,
    affects_own: bool = True,
    labels: dict[str, str] | None = None,
) -> Check:
    """A check with durations in seconds."""
    return Check(
        check_id=check_id,
        raise_hold=timedelta(seconds=raise_hold),
        clear_hold=timedelta(seconds=clear_hold),
        ttl=None if ttl is None else timedelta(seconds=ttl),
        unknown_hold=timedelta(seconds=unknown_hold),
        affects_own=affects_own,
        labels=labels or {},
    )


def node(
    node_id: str,
    *depends_on: str,
    checks: Iterable[Check] = (),
    importance: Importance = Importance.NORMAL,
) -> Node:
    """A node with edges to `depends_on`."""
    return Node(
        node_id=node_id,
        depends_on=tuple(Edge(to=target) for target in depends_on),
        checks=tuple(checks),
        importance=importance,
    )


def obs(
    node_id: str,
    status: Status,
    when: datetime,
    *,
    check_id: str = "state",
    reason: str = "reason",
    due_at: datetime | None = None,
) -> Observation:
    """An observation made at `when`."""
    return Observation(
        node_id=node_id,
        check_id=check_id,
        status=status,
        reason=reason,
        observed_at=when,
        due_at=due_at,
    )


def counting_ids() -> Callable[[datetime], str]:
    """Predictable episode ids: e1, e2, and so on."""
    count = 0

    def new_id(_: datetime) -> str:
        nonlocal count
        count += 1
        return f"e{count}"

    return new_id


def summary(events: Iterable[Event]) -> list[tuple[str, str]]:
    """Each event as (kind, anchor or node), for compact assertions."""
    result: list[tuple[str, str]] = []
    for event in events:
        match event:
            case EpisodeOpened(episode=episode):
                result.append(("opened", episode.anchor))
            case EpisodeUpdated(episode=episode):
                result.append(("updated", episode.anchor))
            case EpisodeResolved(episode=episode, resolution=resolution):
                result.append((resolution, episode.anchor))
            case ProbeRequested(node_id=node_id):
                result.append(("probe", node_id))
    return result
