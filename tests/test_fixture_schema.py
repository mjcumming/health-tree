"""The fixture schema holds before any engine code exists (proposed ADR 0024)."""

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
        "scenario-14-parent-confirmed-inside-settle.yaml",
        "scenario-19-restore-open-episode.yaml",
        "scenario-24-coalesce-onto-open-episode.yaml",
        "scenario-36-readiness-answers.yaml",
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
        "story-04-battery-digest.yaml",
        "story-08-garage-door.yaml",
    ]


def test_schema_accepts_disabled_observation_expiry() -> None:
    """Null `ttl` disables observation expiry (ADR 0018 and proposed ADR 0026)."""
    document = yaml.safe_load(
        (FIXTURES / "scenario-14-parent-confirmed-inside-settle.yaml").read_text(
            encoding="utf-8"
        )
    )
    document["graph"][0]["checks"][0]["ttl"] = None
    validate_fixture(
        document, filename="scenario-14-parent-confirmed-inside-settle.yaml"
    )


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
    """A readiness expectation names a real answer and real nodes (ADR 0023)."""
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
