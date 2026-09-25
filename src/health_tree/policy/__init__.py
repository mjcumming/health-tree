"""The attention policy: who hears what, how loudly, and when (ADR 0010).

Only the interface exists so far (RFP 8, ADR 0027). Every method raises
`NotImplementedError` until the policy is written against the fixtures.
"""

from collections.abc import Mapping
from datetime import datetime

from health_tree.types import Delivery, Event, JSONValue, PolicyConfig, PolicyContext


class Policy:
    """A pure state machine from engine events to deliveries.

    Args:
        config: Recipients, digests, rules, and the batch delay.
    """

    __slots__ = ("_config",)

    def __init__(self, config: PolicyConfig) -> None:
        """Create a policy from its configuration."""
        self._config = config

    def handle(
        self, event: Event, now: datetime, context: PolicyContext
    ) -> list[Delivery]:
        """Turn one engine event into the deliveries it causes now."""
        raise NotImplementedError

    def advance(self, now: datetime, context: PolicyContext) -> list[Delivery]:
        """Deliver what is due: batches, digests, reminders, ends of quiet hours."""
        raise NotImplementedError

    def shelve(self, episode_id: str, until: datetime, now: datetime) -> list[Delivery]:
        """Hold deliveries for one episode until `until`."""
        raise NotImplementedError

    def next_deadline(self) -> datetime | None:
        """The next time `advance` would deliver anything."""
        raise NotImplementedError

    def snapshot(self) -> dict[str, JSONValue]:
        """All state, as JSON-compatible data with a schema version."""
        raise NotImplementedError

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> None:
        """Restore a snapshot taken by `snapshot`."""
        raise NotImplementedError
