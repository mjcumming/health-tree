"""Every story and scenario fixture passes against the engine (ADRs 0012, 0027).

`PENDING` is the scoreboard. It is empty: every fixture passes. A new fixture
that the engine or policy does not satisfy yet goes on the list, and is expected
to fail with `FixtureMismatch`. Because `xfail_strict` is on, a pending fixture
that starts passing fails the run until it is taken off the list.
"""

from pathlib import Path

import pytest

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
