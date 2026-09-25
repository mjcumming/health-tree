"""The fixture schema holds before any engine code exists (ADR 0012)."""

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
        "scenario-50-readiness-own-fault.yaml",
        "scenario-51-readiness-nothing-watched.yaml",
        "scenario-52-sibling-joins-open-group.yaml",
        "story-04-battery-digest.yaml",
        "story-08-garage-door.yaml",
    ]


def test_schema_accepts_a_check_that_never_goes_stale() -> None:
    """`ttl` may be null, said explicitly (ADR 0018)."""
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
