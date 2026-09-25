"""Episode ids: UUIDv7 built from `now`, never from the clock (ADR 0017)."""

from collections.abc import Callable
from datetime import datetime
import secrets
import uuid

_COUNTER_MAX = 0xFFF


class UUIDv7Factory:
    """Build time-sortable ids from `now`.

    Ids made in the same millisecond keep their order through a 12-bit counter.
    If the counter runs out, the timestamp moves forward one millisecond, so ids
    never go backwards.
    """

    __slots__ = ("_counter", "_millis", "_random")

    def __init__(self, random_bits: Callable[[int], int] = secrets.randbits) -> None:
        """Create a factory. `random_bits` supplies the 62 random bits."""
        self._random = random_bits
        self._millis = -1
        self._counter = 0

    @property
    def state(self) -> tuple[int, int]:
        """The last millisecond and counter used, for snapshots."""
        return self._millis, self._counter

    @state.setter
    def state(self, value: tuple[int, int]) -> None:
        self._millis, self._counter = value

    def __call__(self, now: datetime) -> str:
        """Return the next id for `now`."""
        millis = int(now.timestamp() * 1000)
        if millis > self._millis:
            self._millis, self._counter = millis, 0
        elif self._counter < _COUNTER_MAX:
            self._counter += 1
        else:
            self._millis, self._counter = self._millis + 1, 0
        value = (
            (self._millis & 0xFFFF_FFFF_FFFF) << 80
            | 0x7 << 76
            | self._counter << 64
            | 0b10 << 62
            | self._random(62)
        )
        return str(uuid.UUID(int=value))
