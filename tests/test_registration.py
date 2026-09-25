"""Atomic registration contracts and large graph safety (ADR 0033)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

import pytest

from health_tree.engine import Engine
from health_tree.types import Edge, Node, Status
from tests.engine_helpers import (
    SETTINGS,
    T0,
    at,
    check,
    counting_ids,
    node,
    obs,
    summary,
)


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        pytest.param([], "at least one node", id="empty"),
        pytest.param([node("new"), node("new")], "twice", id="duplicate"),
        pytest.param([node("a", "b"), node("b", "a")], "cycle", id="cycle"),
        pytest.param([node("waiting", "a")], "cycle", id="forward-cycle"),
        pytest.param(
            [
                node("new"),
                Node(node_id="bad", depends_on=(Edge(to="a", group="group"),)),
            ],
            "redundancy",
            id="reserved-group",
        ),
    ],
)
def test_rejected_batch_preserves_all_state(
    nodes: Sequence[Node], message: str
) -> None:
    """A late invalid item cannot register an early item or move engine time."""
    engine = Engine(SETTINGS, new_id=counting_ids())
    engine.register_many([node("a", "waiting", checks=[check()]), node("b")], T0)
    engine.ingest(obs("a", Status.FAIL, T0), T0)
    before, deadline = engine.snapshot(), engine.next_deadline()
    with pytest.raises(ValueError, match=message):
        engine.register_many(nodes, at(600))
    assert engine.snapshot() == before
    assert engine.next_deadline() == deadline
    assert engine.register(node("still_valid"), at(1)) == []


@pytest.mark.parametrize(
    "now",
    [
        pytest.param(at(-1), id="backwards"),
        pytest.param(T0.replace(tzinfo=None), id="naive"),
    ],
)
def test_invalid_time_preserves_graph(now: datetime) -> None:
    """Graph validation must not commit replacements before the time check."""
    engine = Engine(SETTINGS)
    engine.register(node("a", checks=[check()]), T0)
    before = engine.snapshot()
    with pytest.raises(ValueError):
        engine.register_many([node("a"), node("new")], now)
    assert engine.snapshot() == before
    assert engine.coverage().no_checks == ()


def test_batch_keeps_holds_and_starts_new_checks_unknown() -> None:
    """Replacing a node preserves pending evidence and untouched nodes."""
    engine = Engine(SETTINGS, new_id=counting_ids())
    engine.register_many(
        [node("a", checks=[check(raise_hold=30)]), node("untouched")], T0
    )
    engine.ingest(obs("a", Status.FAIL, T0), T0)
    assert (
        engine.register_many(
            [node("a", checks=[check(raise_hold=30), check("new")]), node("added")],
            at(20),
        )
        == []
    )
    assert summary(engine.advance(at(30))) == [("opened", "a")]
    assert engine.coverage().no_checks == ("untouched", "added")
    assert [
        (item.node_id, item.check_id) for item in engine.coverage().never_observed
    ] == [("a", "new")]


def test_batch_emits_no_intermediate_failure() -> None:
    """A check due to fail is removed in the same registration as another node."""
    engine = Engine(SETTINGS)
    engine.register(node("a", checks=[check(raise_hold=30)]), T0)
    engine.ingest(obs("a", Status.FAIL, T0), T0)
    assert engine.register_many([node("new"), node("a")], at(30)) == []
    assert engine.explain("a").findings == ()


def test_ten_thousand_node_forward_chain() -> None:
    """A complete deep graph is registered without depending on Python recursion."""
    engine = Engine(SETTINGS)
    nodes = [node(f"n{index}", f"n{index + 1}") for index in range(9999)]
    nodes.append(node("n9999", checks=[check()]))
    assert engine.register_many(nodes, T0) == []
    assert engine.ingest(obs("n9999", Status.PASS, T0), T0) == []
    assert engine.readiness(["n0"]).answer == "ready"
    assert len(engine.coverage().no_checks) == 9999
    with pytest.raises(ValueError, match="cycle"):
        engine.register_many([replace(nodes[-1], depends_on=(Edge(to="n0"),))], at(1))
    assert engine.readiness(["n0"]).answer == "ready"
