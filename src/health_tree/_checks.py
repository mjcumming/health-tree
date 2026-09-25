"""The state of one check over time: holds, `ttl`, and staleness (rules 2 to 5).

A check has an effective status, the one the engine acts on, and at most one
pending status waiting out its hold. Every transition is applied at the time it
takes effect, so `since` is exact even when `advance` is called late.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from health_tree.types import Check, Finding, Observation, Status

_ZERO = timedelta(0)


@dataclass(slots=True, kw_only=True)
class CheckState:
    """Mutable state of one registered check. Internal to the engine."""

    node_id: str
    check: Check
    effective: Status
    since: datetime
    reason: str | None = None
    message: str | None = None
    due_at: datetime | None = None
    pending: Status | None = None
    pending_since: datetime | None = None
    observation: Observation | None = None
    expired: bool = False
    problem_known: bool = False
    stale_at: datetime | None = None

    @classmethod
    def registered(cls, node_id: str, check: Check, now: datetime) -> CheckState:
        """A new check starts `unknown`, and its unknown hold starts now (ADR 0026)."""
        return cls(
            node_id=node_id,
            check=check,
            effective=Status.UNKNOWN,
            since=now,
            stale_at=now + check.unknown_hold,
        )

    def observe(self, observation: Observation, now: datetime) -> None:
        """Apply a new observation at `now`."""
        self.advance(now)
        self.observation = observation
        self.expired = False
        self._raw(observation.status, now)

    def advance(self, now: datetime) -> None:
        """Apply every hold and expiry due at or before `now`, in time order."""
        while True:
            hold_due = self._hold_due()
            expiry = self._expiry()
            due = min(
                (time for time in (hold_due, expiry) if time is not None),
                default=None,
            )
            if due is None or due > now:
                return
            if due == hold_due:
                assert self.pending is not None
                self._set(
                    self.pending, due, from_observation=True, since=self.pending_since
                )
            else:
                self.expired = True
                self._set(Status.UNKNOWN, due, from_observation=False)

    def rejoin(self, now: datetime) -> None:
        """Restart the stale clock after a muting dependency recovers (rule 19)."""
        if self.effective is Status.UNKNOWN:
            ttl = self.check.ttl or _ZERO
            self.stale_at = now + ttl + self.check.unknown_hold

    def is_stale(self, now: datetime) -> bool:
        """Unknown for longer than `unknown_hold`."""
        return (
            self.effective is Status.UNKNOWN
            and self.stale_at is not None
            and now >= self.stale_at
        )

    def worsening_pending(self) -> bool:
        """A worse status is waiting out `raise_hold`: the check is in doubt."""
        return self.pending is not None and self.pending > self.effective

    def finding(self, now: datetime) -> Finding | None:
        """The episode reason this check contributes now, if any (ADR 0026)."""
        if self.effective in {Status.WARN, Status.FAIL}:
            return self._finding(self.effective, self.reason or "", self.since)
        if self.is_stale(now):
            assert self.stale_at is not None
            return self._finding(Status.UNKNOWN, "stale", self.stale_at)
        return None

    def next_deadline(self, now: datetime) -> datetime | None:
        """The next time this check changes on its own, after `now`."""
        times = [self._hold_due(), self._expiry()]
        if self.effective is Status.UNKNOWN:
            times.append(self.stale_at)
        return min(
            (time for time in times if time is not None and time > now), default=None
        )

    def _finding(self, status: Status, reason: str, since: datetime) -> Finding:
        return Finding(
            node_id=self.node_id,
            check_id=self.check.check_id,
            status=status,
            reason=reason,
            since=since,
            message=self.message,
            due_at=self.due_at,
            labels=self.check.labels,
            annotations=self.check.annotations,
        )

    def _hold_due(self) -> datetime | None:
        if self.pending is None or self.pending_since is None:
            return None
        hold = (
            self.check.clear_hold
            if self.pending is Status.PASS
            else self.check.raise_hold
        )
        return self.pending_since + hold

    def _expiry(self) -> datetime | None:
        if self.check.ttl is None or self.observation is None or self.expired:
            return None
        return self.observation.observed_at + self.check.ttl

    def _raw(self, status: Status, at: datetime) -> None:
        if status is self.effective:
            self.pending = self.pending_since = None
            self._take_details()
            return
        if status is Status.PASS:
            if self.effective is Status.UNKNOWN and not (
                self.problem_known or self.is_stale(at)
            ):
                self._set(Status.PASS, at, from_observation=True)
            elif self.pending is not Status.PASS:
                self.pending, self.pending_since = Status.PASS, at
            return
        if status > self.effective:
            if self.check.raise_hold == _ZERO:
                self._set(status, at, from_observation=True)
            elif not self.worsening_pending():
                self.pending, self.pending_since = status, at
            else:
                self.pending = status
            return
        self._set(status, at, from_observation=True)

    def _set(
        self,
        status: Status,
        at: datetime,
        *,
        from_observation: bool,
        since: datetime | None = None,
    ) -> None:
        """Make `status` effective at `at`. It began at `since`, before its hold."""
        began = at if since is None else since
        if status is Status.UNKNOWN and self.effective is not Status.UNKNOWN:
            self.stale_at = began + self.check.unknown_hold
        if status is not self.effective:
            self.since = began
        self.effective = status
        self.pending = self.pending_since = None
        if status in {Status.WARN, Status.FAIL}:
            self.problem_known = True
        elif status is Status.PASS:
            self.problem_known = False
        if from_observation:
            self._take_details()
        else:
            self.reason = self.message = self.due_at = None

    def _take_details(self) -> None:
        observation = self.observation
        assert observation is not None
        self.reason = observation.reason
        self.message = observation.message
        self.due_at = observation.due_at
