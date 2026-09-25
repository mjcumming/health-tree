"""Engine behavior the fixtures cannot express: the API contract and edges."""

from collections.abc import Callable
from datetime import timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from health_tree._ids import UUIDv7Factory
from health_tree.engine import Engine
from health_tree.types import (
    Edge,
    EpisodeOpened,
    EpisodeResolved,
    Node,
    QuietWindow,
    Status,
)
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

FAIL, PASS, WARN, UNKNOWN = Status.FAIL, Status.PASS, Status.WARN, Status.UNKNOWN


def _engine(*nodes: Node) -> Engine:
    engine = Engine(SETTINGS, new_id=counting_ids())
    for item in nodes:
        assert engine.register(item, T0) == []
    return engine


def _controller_and_devices(count: int = 3) -> Engine:
    devices = [
        node(f"d{i}", "controller", checks=[check()]) for i in range(1, count + 1)
    ]
    engine = _engine(node("controller", checks=[check()]), *devices)
    engine.ingest_many(
        [obs("controller", PASS, T0), *(obs(d.node_id, PASS, T0) for d in devices)], T0
    )
    return engine


def test_register_rejects_a_redundancy_group() -> None:
    """Scenario 26: edge groups are reserved in version 1."""
    engine = _engine(node("a"))
    grouped = Node(node_id="b", depends_on=(Edge(to="a", group="uplinks"),))
    with pytest.raises(ValueError, match="redundancy"):
        engine.register(grouped, T0)


def test_register_rejects_a_cycle() -> None:
    """Scenario 12: an edge that would close a cycle is rejected, even on replace."""
    engine = _engine(node("a"), node("b", "a"), node("c", "b"))
    with pytest.raises(ValueError, match="cycle"):
        engine.register(node("a", "c"), T0)
    assert engine.readiness(["c"]).answer == "unknown"


def test_an_edge_waits_for_its_target() -> None:
    """An edge to a node not registered yet is ignored until it arrives."""
    engine = _engine(node("child", "parent", checks=[check()]))
    events = engine.ingest(obs("child", FAIL, T0), T0)
    assert summary(events) == [("opened", "child")]
    assert engine.register(node("parent", checks=[check()]), at(1)) == []
    assert engine.explain("child").nodes[0].node_id == "parent"


def test_replacing_a_node_keeps_its_check_state() -> None:
    """Re-registering keeps observed checks; a new check starts unknown."""
    engine = _engine(node("device", checks=[check()]))
    assert summary(engine.ingest(obs("device", FAIL, T0), T0)) == [("opened", "device")]
    replaced = node("device", checks=[check(), check("battery")])
    assert engine.register(replaced, at(1)) == []
    assert engine.explain("device").findings[0].reason == "reason"


def test_removing_an_anchor_resolves_and_rejoins_its_dependents() -> None:
    """Scenario 21: `removed`, then the dependents wait out rejoin grace."""
    engine = _engine(
        node("host", checks=[check()]), node("device", "host", checks=[check()])
    )
    engine.ingest_many([obs("host", FAIL, T0), obs("device", FAIL, T0)], T0)
    events = engine.remove("host", at(10))
    assert summary(events) == [("removed", "host")]
    assert engine.advance(at(69)) == []
    assert summary(engine.advance(at(70))) == [("opened", "device")]


def test_removing_a_member_can_dissolve_a_group() -> None:
    """A removed member leaves; below `coalesce_count` the group clears."""
    engine = _controller_and_devices()
    opened = engine.ingest_many([obs(f"d{i}", FAIL, at(60)) for i in (1, 2, 3)], at(60))
    assert summary(opened) == [("opened", "controller")]
    assert summary(engine.remove("d1", at(70))) == [("cleared", "controller")]
    assert summary(engine.advance(at(130))) == [("opened", "d2"), ("opened", "d3")]


def test_quiet_window_can_cover_everything() -> None:
    """A global quiet window holds every opening until it ends (rule 22)."""
    engine = _engine(node("a", checks=[check()]))
    window = QuietWindow(scope="all", until=at(60))
    assert engine.quiet(window, T0) == []
    assert engine.ingest(obs("a", FAIL, at(1)), at(1)) == []
    assert engine.next_deadline() == at(60)
    assert summary(engine.advance(at(60))) == [("opened", "a")]


@pytest.mark.parametrize(
    ("call", "error"),
    [
        pytest.param(lambda e: e.ingest_many([], at(1)), ValueError, id="empty-batch"),
        pytest.param(
            lambda e: e.ingest(obs("a", PASS, at(1), check_id="nope"), at(1)),
            ValueError,
            id="unknown-check",
        ),
        pytest.param(
            lambda e: e.ingest_many(
                [obs("a", PASS, at(1)), obs("a", FAIL, at(1))], at(1)
            ),
            ValueError,
            id="duplicate-in-batch",
        ),
        pytest.param(lambda e: e.advance(at(-1)), ValueError, id="backwards"),
        pytest.param(
            lambda e: e.advance(T0.replace(tzinfo=None)), ValueError, id="naive"
        ),
        pytest.param(
            lambda e: e.advance(T0.astimezone(ZoneInfo("America/Chicago"))),
            ValueError,
            id="not-utc",
        ),
        pytest.param(
            lambda e: e.quiet(QuietWindow(scope="all", until=T0), T0),
            ValueError,
            id="window-already-over",
        ),
        pytest.param(
            lambda e: e.quiet(QuietWindow(scope="node", node_id="x", until=at(9)), T0),
            KeyError,
            id="window-on-unknown-node",
        ),
        pytest.param(lambda e: e.remove("x", T0), KeyError, id="remove-unknown"),
        pytest.param(lambda e: e.explain("x"), KeyError, id="explain-unknown"),
        pytest.param(lambda e: e.readiness(["x"]), KeyError, id="readiness-unknown"),
    ],
)
def test_bad_calls_change_nothing(
    call: Callable[[Engine], object], error: type[Exception]
) -> None:
    """A rejected call raises and leaves the engine as it was."""
    engine = _engine(node("a", checks=[check()]))
    with pytest.raises(error):
        call(engine)
    assert engine.readiness(["a"]).answer == "unknown"


def test_next_deadline_tracks_holds_gates_and_grace() -> None:
    """The adapter needs one timer: the earliest thing that can change."""
    assert Engine(SETTINGS).next_deadline() is None
    engine = _engine(
        node("parent", checks=[check(raise_hold=20)]),
        node("child", "parent", checks=[check()]),
    )
    assert engine.next_deadline() == at(900)
    engine.ingest(obs("child", FAIL, T0), T0)
    assert engine.next_deadline() == at(120)
    engine.ingest(obs("parent", FAIL, at(10)), at(10))
    assert engine.next_deadline() == at(30)
    assert summary(engine.advance(at(30))) == [("opened", "parent")]
    engine.ingest(obs("parent", PASS, at(40)), at(40))
    assert engine.next_deadline() == at(70)
    assert summary(engine.advance(at(70))) == [("updated", "parent")]
    assert engine.next_deadline() == at(130)
    assert summary(engine.advance(at(130))) == [
        ("opened", "child"),
        ("cleared", "parent"),
    ]


def test_checks_follow_the_status_rules() -> None:
    """Rules 3 to 5: improvements at once, worsenings held, unknown reported."""
    engine = _engine(node("device", checks=[check(raise_hold=30)]))
    engine.ingest(obs("device", PASS, T0), T0)
    engine.ingest(obs("device", FAIL, at(10)), at(10))
    engine.ingest(obs("device", WARN, at(20)), at(20))
    assert engine.advance(at(39)) == []
    opened = engine.advance(at(40))
    assert isinstance(opened[0], EpisodeOpened)
    assert opened[0].episode.status is WARN
    assert opened[0].episode.reasons[0].since == at(10)
    engine.ingest(obs("device", FAIL, at(50)), at(50))
    assert engine.advance(at(80))[0].episode.status is FAIL  # type: ignore[union-attr]
    updated = engine.ingest(obs("device", WARN, at(90)), at(90))
    assert updated[0].episode.status is WARN  # type: ignore[union-attr]
    unknown = engine.ingest(obs("device", UNKNOWN, at(100)), at(100))
    assert unknown[0].episode.status is UNKNOWN  # type: ignore[union-attr]
    assert engine.readiness(["device"]).answer == "unknown"


def test_a_fail_that_goes_stale_still_needs_its_clear_hold() -> None:
    """A problem once known clears only through `clear_hold` (ADR 0026)."""
    engine = _engine(node("device", checks=[check(ttl=60, unknown_hold=60)]))
    engine.ingest(obs("device", FAIL, T0), T0)
    assert summary(engine.advance(at(120))) == [("updated", "device")]
    assert engine.ingest(obs("device", PASS, at(130)), at(130)) == []
    assert summary(engine.advance(at(160))) == [("cleared", "device")]


def test_explain_lists_findings_then_non_pass_dependencies() -> None:
    """`explain` names the node's reasons, then its troubled dependencies."""
    engine = _engine(
        node("hub", checks=[check()]),
        node("relay", "hub"),
        node("device", "relay", checks=[check()]),
    )
    engine.ingest_many([obs("hub", WARN, T0), obs("device", FAIL, T0)], T0)
    explanation = engine.explain("device")
    assert [f.reason for f in explanation.findings] == ["reason"]
    assert [(n.node_id, n.own, n.watched) for n in explanation.nodes] == [
        ("hub", WARN, True)
    ]


def test_readiness_names_causes_not_their_consequences() -> None:
    """ADR 0028: a failure a failed dependency explains is not named."""
    engine = _engine(
        node("hub", checks=[check()]),
        node("bridge", checks=[check()]),
        node("fn_a", "bridge", checks=[check()]),
        node("fn_b", "hub"),
        node("fn_c", "hub", checks=[check()]),
    )
    engine.ingest_many(
        [
            obs("hub", FAIL, T0),
            obs("bridge", PASS, T0),
            obs("fn_a", FAIL, T0),
            obs("fn_c", FAIL, T0),
        ],
        T0,
    )
    several = engine.readiness(["fn_a", "fn_b"])
    assert (several.answer, several.blocked_by) == ("blocked", "own")
    assert [n.node_id for n in several.nodes] == ["hub", "fn_a"]
    explained = engine.readiness(["fn_c"])
    assert explained.blocked_by == "dependency"
    assert [n.node_id for n in explained.nodes] == ["hub"]
    shared = engine.readiness(["fn_b", "fn_c"])
    assert [n.node_id for n in shared.nodes] == ["hub"]


def test_snapshot_restores_state_through_json() -> None:
    """Rule 24: a restored engine carries on exactly where the old one stopped."""
    graph = [node("host", checks=[check()]), node("device", "host", checks=[check()])]
    old = _engine(*graph)
    old.ingest_many([obs("host", FAIL, T0), obs("device", FAIL, T0)], T0)
    old.quiet(QuietWindow(scope="node", node_id="device", until=at(600)), at(1))
    state = json.loads(json.dumps(old.snapshot()))
    new = Engine(SETTINGS, new_id=counting_ids())
    for item in graph:
        new.register(item, at(5))
    assert new.restore(state, at(5)) == []
    assert new.snapshot() == old.snapshot() | {"now": new.snapshot()["now"]}
    old.ingest(obs("host", PASS, at(10)), at(10))
    new.ingest(obs("host", PASS, at(10)), at(10))
    assert summary(old.advance(at(40))) == summary(new.advance(at(40)))


def test_restore_resolves_episodes_whose_anchor_is_gone() -> None:
    """Rule 24: an episode without its anchor resolves as `removed`."""
    old = _engine(node("host", checks=[check()]))
    old.ingest(obs("host", FAIL, T0), T0)
    new = Engine(SETTINGS)
    events = new.restore(old.snapshot(), at(5))
    assert isinstance(events[0], EpisodeResolved)
    assert events[0].resolution == "removed"
    with pytest.raises(ValueError, match="schema"):
        new.restore({"schema_version": 99}, at(6))


def test_startup_grace_starts_again_on_restore() -> None:
    """ADR 0011: nothing new opens during grace after a restore."""
    settings = SETTINGS.__class__(
        settle=SETTINGS.settle,
        rejoin_grace=SETTINGS.rejoin_grace,
        startup_grace=timedelta(minutes=2),
        coalesce_count=3,
        coalesce_window=SETTINGS.coalesce_window,
    )
    old = Engine(settings)
    old.register(node("a", checks=[check()]), T0)
    new = Engine(settings)
    new.register(node("a", checks=[check()]), at(300))
    assert new.restore(old.snapshot(), at(400)) == []
    assert new.ingest(obs("a", FAIL, at(401)), at(401)) == []
    assert summary(new.advance(at(520))) == [("opened", "a")]


def test_default_ids_sort_in_the_order_episodes_open() -> None:
    """Scenario 38: two episodes from one call have ids in opening order."""
    engine = Engine(SETTINGS)
    engine.register(node("a", checks=[check()]), T0)
    engine.register(node("b", checks=[check()]), T0)
    events = engine.ingest_many([obs("a", FAIL, T0), obs("b", FAIL, T0)], T0)
    ids = [e.episode.episode_id for e in events if isinstance(e, EpisodeOpened)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 2


def test_uuidv7_ids_are_version_7_and_never_go_backwards() -> None:
    """ADR 0017: the counter orders one millisecond; overflow moves time on."""
    factory = UUIDv7Factory(random_bits=lambda bits: 0)
    first = factory(T0)
    assert first[14] == "7"
    factory.state = (int(T0.timestamp() * 1000), 0xFFF)
    overflow = factory(T0)
    assert overflow > first
    assert factory.state == (int(T0.timestamp() * 1000) + 1, 0)
    assert factory(T0) > overflow


def test_a_warning_anchor_takes_over_its_group() -> None:
    """ADR 0021: the anchor's own episode absorbs the group and keeps its members."""
    engine = _controller_and_devices()
    engine.ingest_many([obs(f"d{i}", FAIL, at(60)) for i in (1, 2, 3)], at(60))
    events = engine.ingest(obs("controller", WARN, at(70)), at(70))
    assert summary(events) == [("opened", "controller"), ("absorbed", "controller")]
    opened = events[0]
    assert isinstance(opened, EpisodeOpened)
    assert opened.episode.form == "root"
    assert opened.episode.recorded == {"d1", "d2", "d3"}
    assert "dependents_failing" in {f.reason for f in opened.episode.reasons}


@pytest.mark.parametrize(
    ("change", "error"),
    [
        pytest.param({"ids": "none"}, TypeError, id="ids-not-a-list"),
        pytest.param({"windows": [["all"]]}, TypeError, id="window-not-an-object"),
        pytest.param(
            {
                "windows": [
                    {"scope": "all", "node_id": None, "start": None, "until": None}
                ]
            },
            ValueError,
            id="window-without-times",
        ),
    ],
)
def test_restore_rejects_malformed_snapshots(
    change: dict[str, object], error: type[Exception]
) -> None:
    """A damaged snapshot fails loudly instead of restoring half a state."""
    state = _engine(node("a", checks=[check()])).snapshot() | change
    with pytest.raises(error):
        Engine(SETTINGS).restore(state, T0)  # type: ignore[arg-type]


def test_an_id_factory_may_not_reuse_an_open_id() -> None:
    """A custom `new_id` that repeats itself is caught, not silently merged."""
    engine = Engine(SETTINGS, new_id=lambda _: "same")
    engine.register(node("a", checks=[check()]), T0)
    engine.register(node("b", checks=[check()]), T0)
    engine.ingest(obs("a", FAIL, T0), T0)
    with pytest.raises(ValueError, match="already open"):
        engine.ingest(obs("b", FAIL, at(1)), at(1))
