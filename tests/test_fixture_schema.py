"""The fixture schema catches malformed fixtures before they run (ADR 0024)."""

from pathlib import Path

import pytest
import yaml

from tests.fixture_schema import (
    FixtureSchemaError,
    validate_directory,
    validate_fixture,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_checked_in_fixtures_match_the_schema() -> None:
    """The checked-in fixtures are valid."""
    validate_directory(FIXTURES)
    names = sorted(path.name for path in FIXTURES.glob("*.yaml"))
    assert names == [
        "scenario-01-host-down-records-its-dependents.yaml",
        "scenario-02-device-fault-after-raise-hold.yaml",
        "scenario-03-controller-down-records-devices.yaml",
        "scenario-04-stragglers-held-through-rejoin.yaml",
        "scenario-05-unknown-parent-gates-then-opens.yaml",
        "scenario-06-warn-parent-does-not-mute.yaml",
        "scenario-07-healthy-parent-leaves-child-as-root.yaml",
        "scenario-08-two-reasons-one-episode.yaml",
        "scenario-09-evidence-check-leaves-own-alone.yaml",
        "scenario-10-expired-check-is-unknown.yaml",
        "scenario-11-startup-grace-covers-a-wave.yaml",
        "scenario-13-flap-inside-raise-hold.yaml",
        "scenario-14-parent-confirmed-inside-settle.yaml",
        "scenario-15-late-parent-absorbs-child.yaml",
        "scenario-16-older-child-episode-stays.yaml",
        "scenario-17-warn-fail-warn-pass.yaml",
        "scenario-19-restore-open-episode.yaml",
        "scenario-20-restored-episode-clears.yaml",
        "scenario-21-remove-and-replace-at-runtime.yaml",
        "scenario-22-two-roots-record-one-device.yaml",
        "scenario-23-importance-flows-up.yaml",
        "scenario-24-coalesce-onto-open-episode.yaml",
        "scenario-25-scoped-quiet-window.yaml",
        "scenario-28-quiet-hours-and-urgency.yaml",
        "scenario-29-resolved-before-digest.yaml",
        "scenario-30-maintenance-reminded-then-escalated.yaml",
        "scenario-31-due-within-matches-warn.yaml",
        "scenario-32-shelved-episode-waits.yaml",
        "scenario-34-readiness-names-causes.yaml",
        "scenario-35-coverage-evidence-gaps.yaml",
        "scenario-36-readiness-answers.yaml",
        "scenario-37-rejoin-restarts-stale-clocks.yaml",
        "scenario-40-critical-failure-with-deadline-pages.yaml",
        "scenario-41-stale-routing.yaml",
        "scenario-42-readiness-looks-through-to-a-sensor.yaml",
        "scenario-43-maintenance-node-is-separate.yaml",
        "scenario-44-loudest-reason-wins.yaml",
        "scenario-45-group-dissolves-below-count.yaml",
        "scenario-47-group-absorbed-by-failing-anchor.yaml",
        "scenario-48-fresh-pass-does-not-gate.yaml",
        "scenario-49-readiness-ignores-quiet-window.yaml",
        "scenario-50-readiness-own-fault.yaml",
        "scenario-51-readiness-nothing-watched.yaml",
        "scenario-52-sibling-joins-open-group.yaml",
        "scenario-53-atomic-observation-batch.yaml",
        "scenario-54-staggered-failures-notify.yaml",
        "scenario-54-staggered-failures-urgent.yaml",
        "scenario-55-readiness-mixed-coverage.yaml",
        "scenario-56-command-initially-unknown.yaml",
        "scenario-57-potential-impact.yaml",
        "scenario-58-view-rollup.yaml",
        "scenario-59-group-rollup.yaml",
        "scenario-61-situation-outside-the-cause-graph.yaml",
        "scenario-62-situation-survives-restart.yaml",
        "scenario-63-situations-never-coalesce.yaml",
        "scenario-64-situation-waits-for-quiet-hours.yaml",
        "scenario-72-reminders-respect-quiet-hours.yaml",
        "scenario-73-activation-restarts-attention.yaml",
        "scenario-74-atomic-graph-registration.yaml",
        "scenario-75-group-rejoin-final-evidence.yaml",
        "story-02-detector-hangs.yaml",
        "story-04-battery-digest.yaml",
        "story-06-ai-box.yaml",
        "story-07-eero-node-down.yaml",
        "story-08-garage-door.yaml",
        "story-09-insteon-controller-chokes.yaml",
        "story-10-front-door-open-overnight.yaml",
    ]


def test_schema_accepts_disabled_observation_expiry() -> None:
    """Null `ttl` disables observation expiry (ADRs 0018 and 0026)."""
    document = yaml.safe_load(
        (FIXTURES / "scenario-14-parent-confirmed-inside-settle.yaml").read_text(
            encoding="utf-8"
        )
    )
    document["graph"][0]["checks"][0]["ttl"] = None
    validate_fixture(
        document, filename="scenario-14-parent-confirmed-inside-settle.yaml"
    )


@pytest.mark.parametrize(
    ("query", "spec", "message"),
    [
        pytest.param("coverage", [], "must be a mapping", id="coverage-shape"),
        pytest.param("coverage", {}, "missing", id="coverage-fields"),
        pytest.param(
            "coverage",
            {"no_checks": ["missing"], "never_observed": [], "stale": []},
            "registered node ids",
            id="coverage-unknown-node",
        ),
        pytest.param(
            "coverage",
            {
                "no_checks": [],
                "never_observed": [{"node": "a", "check": "absent"}],
                "stale": [],
            },
            "registered checks",
            id="coverage-unknown-check",
        ),
        pytest.param("impact", [], "must be a mapping", id="impact-shape"),
        pytest.param(
            "impact",
            {"missing": {"nodes": [], "importance": "normal"}},
            "not a node",
            id="impact-unknown-node",
        ),
        pytest.param(
            "impact",
            {"a": {"nodes": [], "importance": "urgent"}},
            "not an importance",
            id="impact-loudness",
        ),
        pytest.param(
            "impact",
            {"a": {"nodes": [{"node": "device"}], "importance": "normal"}},
            "node and importance",
            id="impact-incomplete-member",
        ),
        pytest.param("rollup", [], "must be a mapping", id="rollup-shape"),
        pytest.param(
            "rollup",
            {"absent": {}},
            "must name a view",
            id="rollup-unknown-view",
        ),
        pytest.param(
            "rollup",
            {"location": {"absent": {"total": 0, "counts": {}}}},
            "not a group",
            id="rollup-unknown-group",
        ),
        pytest.param(
            "rollup",
            {"location": {"all": {"total": True, "counts": {}}}},
            "non-negative integer",
            id="rollup-boolean-total",
        ),
        pytest.param(
            "rollup",
            {"location": {"all": {"total": 5, "counts": {"fail": {"recorded": -1}}}}},
            "non-negative integer",
            id="rollup-negative-count",
        ),
        pytest.param(
            "rollup",
            {"location": {"all": {"total": 5, "counts": {"healthy": {"clear": 5}}}}},
            "unknown keys healthy",
            id="rollup-unknown-status",
        ),
    ],
)
def test_schema_rejects_invalid_summary_queries(
    query: str, spec: object, message: str
) -> None:
    """Malformed expected results cannot silently weaken a query fixture."""
    filename = "scenario-58-view-rollup.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][0]["expect"]["queries"] = {query: spec}
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    "views",
    [
        pytest.param([], id="not-a-mapping"),
        pytest.param({"location": []}, id="groups-not-a-mapping"),
        pytest.param({"location": {"all": ["absent"]}}, id="unknown-member"),
    ],
)
def test_schema_rejects_invalid_views(views: object) -> None:
    """Fixture views must declare groups of known node ids."""
    filename = "scenario-58-view-rollup.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["views"] = views
    with pytest.raises(FixtureSchemaError, match="views"):
        validate_fixture(document, filename=filename)


def test_schema_requires_unknown_hold() -> None:
    """`unknown_hold` is always a duration, never null (ADR 0018)."""
    document = yaml.safe_load(
        (FIXTURES / "scenario-14-parent-confirmed-inside-settle.yaml").read_text(
            encoding="utf-8"
        )
    )
    document["graph"][0]["checks"][0]["unknown_hold"] = None
    with pytest.raises(FixtureSchemaError, match="unknown_hold"):
        validate_fixture(
            document, filename="scenario-14-parent-confirmed-inside-settle.yaml"
        )


def test_schema_rejects_a_naive_clock() -> None:
    """A timestamp without a timezone is not a fixture time."""
    document = yaml.safe_load(
        (FIXTURES / "scenario-14-parent-confirmed-inside-settle.yaml").read_text(
            encoding="utf-8"
        )
    )
    document["start"] = "2026-09-24T02:40:00"
    with pytest.raises(FixtureSchemaError, match="timezone"):
        validate_fixture(
            document, filename="scenario-14-parent-confirmed-inside-settle.yaml"
        )


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        pytest.param(
            {"answer": "maybe", "names": ["f_own"]},
            "not a readiness answer",
            id="unknown-answer",
        ),
        pytest.param(
            {"answer": "unknown", "names": ["f_own"], "by": "own"},
            "for blocked only",
            id="by-without-blocked",
        ),
        pytest.param(
            {"answer": "blocked", "names": ["f_own"], "by": "someone"},
            "for blocked only",
            id="by-not-own-or-dependency",
        ),
        pytest.param(
            {"answer": "blocked", "names": ["nowhere"]},
            "names must be node ids",
            id="unknown-name",
        ),
    ],
)
def test_schema_rejects_a_bad_readiness_query(
    spec: dict[str, object], message: str
) -> None:
    """A readiness expectation names a real answer and real nodes (ADR 0025)."""
    filename = "scenario-50-readiness-own-fault.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][0]["expect"]["queries"]["readiness"]["f_own"] = spec
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    "status",
    [pytest.param("warn", id="repeated"), pytest.param("fail", id="conflicting")],
)
def test_schema_rejects_duplicate_checks_in_a_batch(status: str) -> None:
    """An atomic batch cannot depend on the order of repeated check observations."""
    filename = "scenario-24-coalesce-onto-open-episode.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    observation = document["steps"][0]["ingest"][0]
    document["steps"][0]["ingest"].append({**observation, "status": status})
    with pytest.raises(FixtureSchemaError, match="duplicate check observation"):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        pytest.param("form", "cluster", "not an episode form", id="bad-form"),
        pytest.param("status", "broken", "not a status", id="bad-status"),
        pytest.param("recorded", ["missing"], "registered node ids", id="bad-member"),
        pytest.param("absorbed", ["$missing"], "unbound", id="bad-absorption"),
        pytest.param("reasons", [False], "list of strings", id="bad-reason"),
    ],
)
def test_schema_rejects_bad_episode_update_fields(
    field: str, value: object, message: str
) -> None:
    """Grouping assertions must refer to valid episode fields and bound ids."""
    filename = "scenario-24-coalesce-onto-open-episode.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][1]["expect"]["events"][0]["updated"][field] = value
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        pytest.param({"resolution": "gone"}, "not a resolution", id="bad-resolution"),
        pytest.param({"loudness": "urgent"}, "no loudness or digest", id="noisy-clear"),
        pytest.param({"digest": "morning"}, "no loudness or digest", id="digest-clear"),
        pytest.param({"silent": True}, "always silent", id="silent-clear"),
        pytest.param({"to": ""}, "non-empty string", id="missing-recipient"),
    ],
)
def test_schema_rejects_bad_resolution_deliveries(
    change: dict[str, object], message: str
) -> None:
    """A resolution updates an existing recipient's message without another alert."""
    filename = "scenario-54-staggered-failures-urgent.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][3]["expect"]["deliveries"][1].update(change)
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)


def test_schema_rejects_a_non_boolean_silent() -> None:
    """`silent` says whether a notification replaces an earlier one quietly."""
    filename = "story-10-front-door-open-overnight.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][1]["expect"]["deliveries"][0]["silent"] = "no"
    with pytest.raises(FixtureSchemaError, match="silent must be true or false"):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    ("quiet", "message"),
    [
        pytest.param(
            {"scope": "house", "until": "2026-09-24T07:00:00Z"},
            "scope must be",
            id="unknown-scope",
        ),
        pytest.param(
            {"scope": "all", "node": "device", "until": "2026-09-24T07:00:00Z"},
            "not allowed when scope is all",
            id="node-with-all",
        ),
        pytest.param(
            {"scope": "node_and_dependents", "until": "2026-09-24T07:00:00Z"},
            "must name a node",
            id="scoped-without-node",
        ),
        pytest.param(
            {"scope": "node", "node": "device", "until": "2026-09-24T06:02:00Z"},
            "after the step",
            id="ends-at-the-step",
        ),
        pytest.param(
            {"scope": "node", "node": "device", "until": "2026-09-24T07:00:00"},
            "timezone",
            id="naive-until",
        ),
        pytest.param(["device"], "must be a mapping", id="not-a-mapping"),
    ],
)
def test_schema_rejects_a_bad_quiet_window(quiet: object, message: str) -> None:
    """A quiet window names a scope, a node when scoped, and a later end (rule 22)."""
    filename = "scenario-49-readiness-ignores-quiet-window.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][2]["quiet"] = quiet
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)


def test_schema_rejects_a_quiet_window_on_restart() -> None:
    """A restart step only restarts; the window belongs to its own step."""
    filename = "scenario-49-readiness-ignores-quiet-window.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][2]["restart"] = True
    with pytest.raises(FixtureSchemaError, match="cannot restart"):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    ("filename", "index", "change", "message"),
    [
        pytest.param(
            "scenario-21-remove-and-replace-at-runtime.yaml",
            2,
            {"remove": "nowhere"},
            "remove must name a node",
            id="remove-unknown-node",
        ),
        pytest.param(
            "scenario-21-remove-and-replace-at-runtime.yaml",
            3,
            {"register": {"id": "new_host", "depends_on": ["nowhere"]}},
            "depends on unknown nowhere",
            id="register-unknown-dependency",
        ),
        pytest.param(
            "scenario-21-remove-and-replace-at-runtime.yaml",
            3,
            {"restart": True},
            "cannot restart and also register",
            id="restart-with-register",
        ),
        pytest.param(
            "scenario-21-remove-and-replace-at-runtime.yaml",
            1,
            {"shelve": {"episode": "$host_ep", "until": "2026-09-24T14:00:00Z"}},
            "requires a policy",
            id="shelve-without-policy",
        ),
        pytest.param(
            "scenario-32-shelved-episode-waits.yaml",
            1,
            {"shelve": {"episode": "$other", "until": "2026-09-24T18:00:00Z"}},
            "unbound",
            id="shelve-unbound-episode",
        ),
        pytest.param(
            "scenario-32-shelved-episode-waits.yaml",
            1,
            {"shelve": {"episode": "$printer_ep", "until": "2026-09-24T14:00:10Z"}},
            "after the step",
            id="shelve-ends-at-the-step",
        ),
        pytest.param(
            "scenario-32-shelved-episode-waits.yaml",
            1,
            {"shelve": ["$printer_ep"]},
            "must be a mapping",
            id="shelve-not-a-mapping",
        ),
    ],
)
def test_schema_rejects_bad_runtime_steps(
    filename: str, index: int, change: dict[str, object], message: str
) -> None:
    """Register, remove, and shelve steps name real nodes, episodes, and times."""
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][index].update(change)
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        pytest.param({"register_many": []}, "non-empty list", id="empty"),
        pytest.param({"register_many": {}}, "non-empty list", id="not-list"),
        pytest.param({"register_many": [42]}, "must be a mapping", id="bad-node"),
        pytest.param(
            {"register_many": [{"id": "a"}, {"id": "a"}]},
            "duplicate node id",
            id="duplicate",
        ),
        pytest.param(
            {"register_many": [{"id": "a", "depends_on": ["nowhere"]}]},
            "depends on unknown",
            id="unknown-target",
        ),
        pytest.param(
            {"register": {"id": "a"}}, "cannot combine", id="single-and-batch"
        ),
        pytest.param({"restart": True}, "cannot restart", id="restart"),
    ],
)
def test_schema_rejects_bad_registration_batches(
    change: dict[str, object], message: str
) -> None:
    """Batch fixture steps cannot hide malformed or ambiguous graph changes."""
    filename = "scenario-74-atomic-graph-registration.yaml"
    document = yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8"))
    document["steps"][1].update(change)
    with pytest.raises(FixtureSchemaError, match=message):
        validate_fixture(document, filename=filename)
