"""Every story and scenario fixture passes against the engine (ADRs 0012, 0027).

`PENDING` lists fixtures the engine or policy does not satisfy yet, expected
to fail with `FixtureMismatch`. Because `xfail_strict` is on, a pending fixture
that starts passing fails the run until it is taken off the list.
"""

from pathlib import Path
import re

import pytest
import yaml

from tests.runner import FixtureMismatch, load_fixture, run_fixture

FIXTURES = Path(__file__).parent / "fixtures"
PATHS = sorted(FIXTURES.glob("*.yaml"))

PENDING: frozenset[str] = frozenset()
_NOT_WRITTEN = pytest.mark.xfail(
    raises=FixtureMismatch, strict=True, reason="the engine does not do this yet"
)


def test_pending_names_only_real_fixtures() -> None:
    """The scoreboard cannot hide a typo or a deleted fixture."""
    assert {path.stem for path in PATHS} >= PENDING


def test_rfp_stories_and_scenarios_have_tests() -> None:
    """Specification ids and fixture coverage stay in agreement."""
    rfp = (FIXTURES.parents[1] / "docs" / "rfp.md").read_text(encoding="utf-8")
    stories = rfp.split("## 9. Stories\n", 1)[1].split("\n## ", 1)[0]
    scenarios = rfp.split("## 10. Scenarios the library must pass\n", 1)[1].split(
        "\n## ", 1
    )[0]
    required = [
        f"story-{number}" for number in re.findall(r"^(\d+)\. ", stories, re.MULTILINE)
    ] + [
        f"scenario-{number}"
        for number in re.findall(r"^(\d+)\. ", scenarios, re.MULTILINE)
    ]
    covered: set[str] = {
        requirement
        for path in PATHS
        for requirement in yaml.safe_load(path.read_text(encoding="utf-8"))["covers"]
    }
    # Rejected registrations and generated-id ordering use test_engine.py.
    unit_tested = {"scenario-12", "scenario-26", "scenario-38"}
    assert len(required) == len(set(required))
    assert unit_tested <= set(required)
    assert covered == set(required) - unit_tested


@pytest.mark.parametrize("path", [pytest.param(path, id=path.stem) for path in PATHS])
def test_fixture_builds_records(path: Path) -> None:
    """Every fixture describes records that hold their own invariants."""
    assert load_fixture(path).fixture_id == path.stem


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            path, id=path.stem, marks=[_NOT_WRITTEN] if path.stem in PENDING else []
        )
        for path in PATHS
    ],
)
def test_fixture_passes(path: Path) -> None:
    """The engine and the policy do what the fixture says."""
    run_fixture(load_fixture(path))
