"""Independent timing preserves shared controls and stable route identity."""

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from health_tree.types import EpisodeOpened, Loudness, Match, Rule
from tests.engine_helpers import T0, at
from tests.test_policy import CONTEXT, _episode, _policy

IMMEDIATE = Rule(
    route="phone",
    match=Match(),
    loudness=Loudness.URGENT,
    to=("resident",),
    remind_every=timedelta(minutes=5),
    require_acknowledgment=True,
)
REPORT = Rule(
    route="report",
    match=Match(),
    loudness=Loudness.DIGEST,
    digest="morning",
)


def test_queries_keep_independent_choices_and_global_rule_indices() -> None:
    """An overview remains useful while the complete routes expose both decisions."""
    policy = _policy(IMMEDIATE, REPORT)
    assert policy.next_deadline() is None
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    detail = policy.explain("e1")
    assert detail["loudness"] == "urgent"
    assert detail["sent_to"] == ["resident"]
    assert detail["recipients"] == ["resident"]
    assert detail["require_acknowledgment"] is True
    routes = detail["routes"]
    assert isinstance(routes, dict)
    report = routes["report"]
    assert isinstance(report, dict)
    assert report["rule_index"] == 1
    assert policy.reports(T0)[0]["route"] == "report"
    assert policy.reports(T0)[0]["episodes"] == ["e1"]
    assert policy.next_deadline() == at(300)


def test_shelf_and_unshelve_cover_all_routes() -> None:
    """An episode shelf holds every route without merging reminder state."""
    policy = _policy(IMMEDIATE, replace(IMMEDIATE, route="backup"))
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.shelve("e1", at(600), at(1)) == []
    assert policy.advance(at(300), CONTEXT) == []
    assert policy.explain("e1")["pending"] == {"resident": at(600).isoformat()}
    restored = _policy(IMMEDIATE, replace(IMMEDIATE, route="backup"))
    restored.restore(json.loads(json.dumps(policy.snapshot())), at(301))
    assert [item.route for item in restored.unshelve("e1", at(302), CONTEXT)] == [
        "phone",
        "backup",
    ]
    assert restored.unshelve("e1", at(303), CONTEXT) == []


@pytest.mark.parametrize(
    "old_route", [pytest.param("", id="legacy"), pytest.param("old", id="named")]
)
def test_new_routes_preserve_awareness_and_do_not_inherit_delivery_history(
    old_route: str,
) -> None:
    """Changing routes carries controls forward and activation respects awareness."""
    old = _policy(replace(IMMEDIATE, route=old_route))
    old.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    old.acknowledge("e1", at(1), actor_id="owner")
    new = _policy(IMMEDIATE, REPORT)
    new.restore(old.snapshot(), at(2))
    assert new.acknowledgment("e1") == old.acknowledgment("e1")
    assert new.explain("e1")["sent_to"] == []
    assert new.activate(at(3), CONTEXT) == []
    assert new.acknowledge("e1", at(4), actor_id="second") == []


def test_routes_can_be_removed_or_reordered_after_restart() -> None:
    """A route is restored by id rather than its position in configuration."""
    old = _policy(IMMEDIATE, REPORT)
    old.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    reordered = _policy(REPORT, IMMEDIATE)
    reordered.restore(old.snapshot(), at(1))
    assert [item.route for item in reordered.advance(at(300), CONTEXT)] == ["phone"]
    removed = _policy(REPORT)
    removed.restore(reordered.snapshot(), at(301))
    assert removed.advance(at(600), CONTEXT) == []
    assert removed.explain("e1")["loudness"] == "digest"
    routes = removed.explain("e1")["routes"]
    assert isinstance(routes, dict)
    report = routes["report"]
    assert isinstance(report, dict)
    assert report["rule_index"] == 0


def test_new_route_can_activate_an_existing_unacknowledged_episode() -> None:
    """An explicit reporting change starts a fresh immediate request."""
    old = _policy(REPORT)
    old.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    new = _policy(IMMEDIATE, REPORT)
    new.restore(old.snapshot(), at(1))
    assert [item.route for item in new.activate(at(2), CONTEXT)] == ["phone"]


def test_empty_route_snapshot_is_rejected() -> None:
    """Missing route state cannot silently discard shared episode controls."""
    with pytest.raises(ValueError, match="at least one route"):
        _policy(IMMEDIATE).restore({"schema_version": 4, "routes": {}}, T0)


@pytest.mark.parametrize(
    "selected", [pytest.param([], id="none"), pytest.param(["missing"], id="removed")]
)
def test_activation_without_matching_routes_preserves_pending_reminders(
    selected: list[str],
) -> None:
    """An empty or removed route selection cannot reset other delivery clocks."""
    policy = _policy(IMMEDIATE, replace(IMMEDIATE, route="backup"))
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    before = policy.snapshot()
    assert policy.activate(at(100), CONTEXT, routes=selected) == []
    assert policy.snapshot() == before
    assert [item.route for item in policy.advance(at(300), CONTEXT)] == [
        "phone",
        "backup",
    ]


def test_selected_activation_preserves_unrelated_reminder_clock() -> None:
    """Editing one route starts its attention without re-alerting another route."""
    policy = _policy(IMMEDIATE, replace(IMMEDIATE, route="backup"))
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert [
        item.route for item in policy.activate(at(100), CONTEXT, routes={"backup"})
    ] == ["backup"]
    assert [item.route for item in policy.advance(at(300), CONTEXT)] == ["phone"]
    assert [item.route for item in policy.advance(at(400), CONTEXT)] == ["backup"]


@pytest.mark.parametrize(
    ("immediate_route", "report_route"),
    [
        pytest.param("", "report", id="default-immediate"),
        pytest.param("phone", "", id="default-report"),
    ],
)
def test_mixed_routes_report_only_their_own_schedules(
    immediate_route: str,
    report_route: str,
) -> None:
    """A default route keeps its identity without duplicating another schedule."""
    policy = _policy(
        replace(IMMEDIATE, route=immediate_route),
        replace(REPORT, route=report_route),
    )
    policy.handle(EpisodeOpened(episode=_episode()), T0, CONTEXT)
    assert policy.reports(T0) == [
        {
            "name": "morning",
            "next_at": (T0 + timedelta(days=1)).replace(hour=8).isoformat(),
            "episodes": ["e1"],
            "recipients": ["resident"],
            "route": report_route,
        }
    ]
    restored = _policy(
        replace(IMMEDIATE, route=immediate_route),
        replace(REPORT, route=report_route),
    )
    restored.restore(json.loads(json.dumps(policy.snapshot())), at(1))
    assert restored.reports(at(1)) == policy.reports(T0)
