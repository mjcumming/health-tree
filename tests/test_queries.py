"""Public query contracts around inventory changes and immutable results."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from health_tree.engine import Engine
from health_tree.types import (
    CheckReference,
    Coverage,
    ImpactNode,
    Importance,
    RollupCounts,
    Status,
    View,
)
from tests.engine_helpers import SETTINGS, T0, at, check, node, obs


def test_empty_queries_need_no_clock_or_initial_advance() -> None:
    """An empty group and empty inventory have useful answers before startup."""
    engine = Engine(SETTINGS)
    before = engine.snapshot()
    result = engine.rollup(
        View(view_id="rooms", groups={"empty": frozenset()}), "empty"
    )
    assert result.total == 0
    assert result.counts == tuple(
        RollupCounts(own=status, clear=0, own_episode=0, recorded=0)
        for status in Status
    )
    assert engine.coverage() == Coverage(no_checks=(), never_observed=(), stale=())
    assert engine.snapshot() == before
    assert engine.next_deadline() is None


def test_impact_tracks_registration_removal_and_declared_importance() -> None:
    """Dangling edges do not bridge missing nodes; replacing nodes updates impact."""
    engine = Engine(SETTINGS)
    engine.register(node("leaf", "bridge", importance=Importance.HIGH), T0)
    engine.register(node("root", importance=Importance.CRITICAL), T0)
    assert engine.impact("root").nodes == ()
    engine.register(node("bridge", "root"), T0)
    original = engine.impact("root")
    assert original.nodes == (
        ImpactNode(node_id="bridge", importance=Importance.NORMAL),
        ImpactNode(node_id="leaf", importance=Importance.HIGH),
    )
    assert original.importance is Importance.CRITICAL
    engine.register(node("leaf", "bridge", importance=Importance.LOW), at(1))
    assert engine.impact("root").nodes[-1].importance is Importance.LOW
    assert original.nodes[-1].importance is Importance.HIGH
    engine.remove("bridge", at(2))
    assert engine.impact("root").nodes == ()
    assert engine.impact("root").importance is Importance.CRITICAL


def test_coverage_tracks_check_replacement_and_removal() -> None:
    """Retained observations survive replacement; added checks have no evidence."""
    engine = Engine(SETTINGS)
    engine.register(node("device", checks=[check(clear_hold=0)]), T0)
    engine.ingest(obs("device", Status.PASS, T0), T0)
    engine.register(node("device", checks=[check(), check("battery")]), at(1))
    assert engine.coverage().never_observed == (
        CheckReference(node_id="device", check_id="battery"),
    )
    engine.register(node("device"), at(2))
    assert engine.coverage() == Coverage(
        no_checks=("device",), never_observed=(), stale=()
    )
    engine.remove("device", at(3))
    assert engine.coverage() == Coverage(no_checks=(), never_observed=(), stale=())


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(lambda e: e.impact("missing"), id="missing-node"),
        pytest.param(
            lambda e: e.rollup(View(view_id="v", groups={}), "missing"),
            id="missing-group",
        ),
        pytest.param(
            lambda e: e.rollup(
                View(view_id="v", groups={"all": frozenset({"a", "missing"})}), "all"
            ),
            id="missing-member",
        ),
    ],
)
def test_invalid_query_does_not_change_state(query: Callable[[Engine], object]) -> None:
    """Invalid references fail without advancing time or changing episodes."""
    engine = Engine(SETTINGS)
    engine.register(node("a", checks=[check()]), T0)
    before = engine.snapshot()
    deadline = engine.next_deadline()
    with pytest.raises(KeyError, match="missing"):
        query(engine)
    assert engine.snapshot() == before
    assert engine.next_deadline() == deadline


def test_rollup_requires_only_selected_members_and_keeps_previous_results() -> None:
    """Adapters may keep unrelated groups while reconciling removed devices."""
    engine = Engine(SETTINGS)
    engine.register(node("a", checks=[check()]), T0)
    view = View(
        view_id="v",
        groups={"selected": frozenset({"a"}), "unrelated": frozenset({"missing"})},
    )
    original = engine.rollup(view, "selected")
    assert original.counts[1].clear == 1
    engine.ingest(obs("a", Status.WARN, at(1)), at(1))
    assert engine.rollup(view, "selected").counts[2].own_episode == 1
    assert original.counts[1].clear == 1
    engine.remove("a", at(2))
    with pytest.raises(KeyError, match="a"):
        engine.rollup(view, "selected")


def test_view_detaches_membership_from_adapter_configuration() -> None:
    """Mutating adapter configuration cannot silently change an existing view."""
    groups = {"room": frozenset({"a"})}
    view = View(view_id="v", groups=groups)
    groups["room"] = frozenset({"b"})
    assert view.groups["room"] == frozenset({"a"})
    with pytest.raises(TypeError):
        view.groups["room"] = frozenset()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        view.view_id = "changed"  # type: ignore[misc]
