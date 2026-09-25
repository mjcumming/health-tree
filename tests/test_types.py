"""Public records hold their own invariants (RFP 5, ADR 0027)."""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from health_tree.types import (
    Check,
    Digest,
    Edge,
    EngineSettings,
    Episode,
    EpisodeResolved,
    Importance,
    Loudness,
    Match,
    Node,
    Notification,
    Observation,
    PolicyConfig,
    QuietHours,
    QuietWindow,
    Readiness,
    Recipient,
    Rule,
    Status,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)


def _settings(**changes: object) -> EngineSettings:
    values: dict[str, object] = {
        "settle": 2 * MINUTE,
        "rejoin_grace": MINUTE,
        "startup_grace": MINUTE,
        "coalesce_count": 3,
        "coalesce_window": MINUTE,
        **changes,
    }
    return EngineSettings(**values)  # type: ignore[arg-type]


def _check(**changes: object) -> Check:
    values: dict[str, object] = {
        "check_id": "link",
        "raise_hold": MINUTE,
        "clear_hold": MINUTE,
        "ttl": MINUTE,
        "unknown_hold": MINUTE,
        **changes,
    }
    return Check(**values)  # type: ignore[arg-type]


def _episode() -> Episode:
    return Episode(
        episode_id="e1",
        form="root",
        anchor="host",
        status=Status.FAIL,
        reasons=(),
        recorded=frozenset(),
        impact=frozenset(),
        importance=Importance.NORMAL,
        opened_at=NOW,
        updated_at=NOW,
    )


def _policy(**changes: object) -> PolicyConfig:
    values: dict[str, object] = {
        "batch": MINUTE,
        "timezone": UTC,
        "recipients": {"michael": Recipient(channels=("phone",))},
        "digests": {"morning": Digest(at=time(8), to="michael")},
        "rules": (Rule(match=Match(), loudness=Loudness.NOTIFY, to=("michael",)),),
        **changes,
    }
    return PolicyConfig(**values)  # type: ignore[arg-type]


def test_fixed_types_order_as_declared() -> None:
    """Worst-of and loudest-of are plain `max` (RFP 5)."""
    assert max(Status) is Status.FAIL
    assert max(Status.PASS, Status.UNKNOWN) is Status.UNKNOWN
    assert sorted([Importance.CRITICAL, Importance.LOW]) == [
        Importance.LOW,
        Importance.CRITICAL,
    ]
    assert Loudness.DIGEST <= Loudness.NOTIFY < Loudness.URGENT
    assert Status("warn") is Status.WARN


@pytest.mark.parametrize(
    "other",
    [
        pytest.param(Importance.LOW, id="another-enum"),
        pytest.param("warn", id="a-string"),
    ],
)
def test_fixed_types_do_not_compare_across_types(other: object) -> None:
    """A status is never ordered against an importance or a bare string."""
    with pytest.raises(TypeError):
        _ = other > Status.PASS


def test_valid_records_build() -> None:
    """The happy path for every validated record."""
    node = Node(
        node_id="device",
        depends_on=(Edge(to="hub"),),
        checks=(_check(ttl=None), _check(check_id="battery")),
    )
    assert node.importance is Importance.NORMAL
    assert _settings().coalesce_count == 3
    assert QuietWindow(scope="all", until=NOW).node_id is None
    assert QuietWindow(scope="node", node_id="device", until=NOW).scope == "node"
    resolved = EpisodeResolved(
        episode=_episode(), resolution="absorbed", absorbed_into="e2"
    )
    assert resolved.absorbed_into == "e2"
    assert Readiness(answer="blocked", nodes=(), blocked_by="own").answer == "blocked"
    assert Readiness(answer="ready", nodes=()).blocked_by is None
    assert QuietHours(start=time(22, 30), end=time(7)).end == time(7)
    assert _policy(timezone=ZoneInfo("America/Chicago")).batch == MINUTE
    assert (
        Notification(
            episode_id="e1",
            recipient="michael",
            channels=("phone",),
            loudness=Loudness.DIGEST,
            digest="morning",
        ).digest
        == "morning"
    )
    assert (
        Observation(
            node_id="device",
            check_id="link",
            status=Status.FAIL,
            reason="unreachable",
            observed_at=NOW,
            due_at=NOW + MINUTE,
        ).status
        is Status.FAIL
    )


@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(lambda: _settings(settle=-MINUTE), "settle", id="negative-settle"),
        pytest.param(
            lambda: _settings(coalesce_count=1), "coalesce_count", id="count-of-one"
        ),
        pytest.param(lambda: _check(clear_hold=-MINUTE), "clear_hold", id="bad-hold"),
        pytest.param(lambda: _check(ttl=timedelta(0)), "ttl", id="zero-ttl"),
        pytest.param(
            lambda: Node(node_id="n", checks=(_check(), _check())),
            "repeats a check",
            id="repeated-check",
        ),
        pytest.param(
            lambda: Node(node_id="n", depends_on=(Edge(to="a"), Edge(to="a"))),
            "repeats a dependency",
            id="repeated-edge",
        ),
        pytest.param(
            lambda: Node(node_id="n", depends_on=(Edge(to="n"),)),
            "depends on itself",
            id="self-edge",
        ),
        pytest.param(
            lambda: Observation(
                node_id="n",
                check_id="c",
                status=Status.PASS,
                reason="ok",
                observed_at=NOW.replace(tzinfo=None),
            ),
            "observed_at",
            id="naive-observation",
        ),
        pytest.param(
            lambda: Observation(
                node_id="n",
                check_id="c",
                status=Status.PASS,
                reason="ok",
                observed_at=NOW.astimezone(ZoneInfo("America/Chicago")),
            ),
            "UTC",
            id="local-observation",
        ),
        pytest.param(
            lambda: QuietWindow(scope="all", node_id="n", until=NOW),
            "node_id",
            id="node-on-global-window",
        ),
        pytest.param(
            lambda: QuietWindow(scope="node_and_dependents", until=NOW),
            "node_id",
            id="scoped-window-without-node",
        ),
        pytest.param(
            lambda: EpisodeResolved(episode=_episode(), resolution="absorbed"),
            "absorbed_into",
            id="absorption-without-target",
        ),
        pytest.param(
            lambda: EpisodeResolved(
                episode=_episode(), resolution="cleared", absorbed_into="e2"
            ),
            "absorbed_into",
            id="clear-with-target",
        ),
        pytest.param(
            lambda: Readiness(answer="blocked", nodes=()),
            "blocked_by",
            id="blocked-without-cause",
        ),
        pytest.param(
            lambda: Readiness(answer="unknown", nodes=(), blocked_by="own"),
            "blocked_by",
            id="cause-without-blocked",
        ),
        pytest.param(
            lambda: QuietHours(start=time(7), end=time(7)),
            "same time",
            id="empty-quiet-hours",
        ),
        pytest.param(
            lambda: QuietHours(start=time(22, tzinfo=UTC), end=time(7)),
            "time zone",
            id="zoned-quiet-hours",
        ),
        pytest.param(lambda: Match(age=-MINUTE), "age", id="negative-age"),
        pytest.param(
            lambda: Rule(match=Match(), loudness=Loudness.DIGEST),
            "digest",
            id="digest-rule-without-digest",
        ),
        pytest.param(
            lambda: Rule(match=Match(), loudness=Loudness.URGENT),
            "recipients",
            id="urgent-rule-without-recipients",
        ),
        pytest.param(
            lambda: Rule(
                match=Match(),
                loudness=Loudness.RECORD,
                remind_every=timedelta(0),
            ),
            "remind_every",
            id="zero-reminder",
        ),
        pytest.param(lambda: _policy(rules=()), "at least one rule", id="no-rules"),
        pytest.param(
            lambda: _policy(digests={"morning": Digest(at=time(8), to="nobody")}),
            "unknown nobody",
            id="digest-to-nobody",
        ),
        pytest.param(
            lambda: _policy(
                rules=(Rule(match=Match(), loudness=Loudness.NOTIFY, to=("nobody",)),)
            ),
            "unknown",
            id="rule-to-nobody",
        ),
        pytest.param(
            lambda: _policy(
                rules=(Rule(match=Match(), loudness=Loudness.DIGEST, digest="evening"),)
            ),
            "unknown digest",
            id="rule-to-missing-digest",
        ),
        pytest.param(
            lambda: Notification(
                episode_id="e1",
                recipient="michael",
                channels=(),
                loudness=Loudness.RECORD,
            ),
            "never delivered",
            id="record-delivered",
        ),
        pytest.param(
            lambda: Notification(
                episode_id="e1",
                recipient="michael",
                channels=(),
                loudness=Loudness.NOTIFY,
                digest="morning",
            ),
            "digest",
            id="notify-with-digest",
        ),
    ],
)
def test_records_reject_broken_invariants(
    build: Callable[[], object], message: str
) -> None:
    """A record that cannot be true is never built."""
    with pytest.raises(ValueError, match=message):
        build()
