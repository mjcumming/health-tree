"""Every story and scenario fixture passes against the engine (ADRs 0012, 0027).

`PENDING` is the scoreboard. A pending fixture is expected to fail with
`NotImplementedError` until the engine or the policy implements it. Because
`xfail_strict` is on, a pending fixture that starts passing fails the run until
it is taken off the list.
"""

from pathlib import Path

import pytest

from tests.runner import load_fixture, run_fixture

FIXTURES = Path(__file__).parent / "fixtures"
PATHS = sorted(FIXTURES.glob("*.yaml"))

PENDING = frozenset(
    {
        "scenario-14-parent-confirmed-inside-settle",
        "scenario-19-restore-open-episode",
        "scenario-24-coalesce-onto-open-episode",
        "scenario-36-readiness-answers",
        "scenario-43-maintenance-node-is-separate",
        "scenario-44-loudest-reason-wins",
        "scenario-45-group-dissolves-below-count",
        "scenario-47-group-absorbed-by-failing-anchor",
        "scenario-48-fresh-pass-does-not-gate",
        "scenario-49-readiness-ignores-quiet-window",
        "scenario-50-readiness-own-fault",
        "scenario-51-readiness-nothing-watched",
        "scenario-52-sibling-joins-open-group",
        "scenario-53-atomic-observation-batch",
        "scenario-54-staggered-failures-notify",
        "scenario-54-staggered-failures-urgent",
        "scenario-55-readiness-mixed-coverage",
        "scenario-56-command-initially-unknown",
        "story-04-battery-digest",
        "story-08-garage-door",
    }
)
_NOT_WRITTEN = pytest.mark.xfail(
    raises=NotImplementedError, strict=True, reason="the engine is not written yet"
)


def test_pending_names_only_real_fixtures() -> None:
    """The scoreboard cannot hide a typo or a deleted fixture."""
    assert {path.stem for path in PATHS} >= PENDING


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
