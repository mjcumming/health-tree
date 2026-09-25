"""The engine: graph, evaluation, inhibition, episodes, windows, and queries.

Only the interface exists so far (RFP 8, ADR 0027). Every method raises
`NotImplementedError` until the engine is written against the fixtures.
"""

from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime

from health_tree.types import (
    EngineSettings,
    Event,
    Explanation,
    JSONValue,
    Node,
    Observation,
    QuietWindow,
    Readiness,
)


class Engine:
    """A state machine over the cause graph. It never reads a clock (ADR 0003).

    Args:
        settings: Engine-wide durations, all required (ADR 0018).
        new_id: Builds an episode id from `now`. The default builds a UUIDv7
            with random low bits (ADR 0017). Tests may pass their own.
    """

    __slots__ = ("_new_id", "_settings")

    def __init__(
        self,
        settings: EngineSettings,
        new_id: Callable[[datetime], str] | None = None,
    ) -> None:
        """Create an engine. Startup grace begins at the first call's `now`."""
        self._settings = settings
        self._new_id = new_id

    def register(self, node: Node, now: datetime) -> list[Event]:
        """Add or replace a node and its checks. A cycle is rejected (rule 23)."""
        raise NotImplementedError

    def remove(self, node_id: str, now: datetime) -> list[Event]:
        """Remove a node. Its open episode resolves as `removed` (rule 23)."""
        raise NotImplementedError

    def ingest(self, observation: Observation, now: datetime) -> list[Event]:
        """Apply one observation. The same as a one-observation batch (ADR 0024)."""
        raise NotImplementedError

    def ingest_many(
        self, observations: Sequence[Observation], now: datetime
    ) -> list[Event]:
        """Apply a batch atomically, then evaluate once (ADR 0024)."""
        raise NotImplementedError

    def quiet(self, window: QuietWindow, now: datetime) -> list[Event]:
        """Open a quiet window from `now` until `window.until` (rules 21 and 22)."""
        raise NotImplementedError

    def advance(self, now: datetime) -> list[Event]:
        """Apply holds, `ttl`, gates, grace, and windows due at or before `now`."""
        raise NotImplementedError

    def next_deadline(self) -> datetime | None:
        """The next time `advance` would change anything, for the adapter's timer."""
        raise NotImplementedError

    def snapshot(self) -> dict[str, JSONValue]:
        """All state, as JSON-compatible data with a schema version (rule 24)."""
        raise NotImplementedError

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> list[Event]:
        """Restore a snapshot after the graph is registered (rule 24)."""
        raise NotImplementedError

    def explain(self, node_id: str) -> Explanation:
        """Why a node is not working: its findings, then its dependencies."""
        raise NotImplementedError

    def readiness(self, node_ids: Collection[str]) -> Readiness:
        """Whether these functions can perform, from `own` status only (ADR 0023)."""
        raise NotImplementedError
