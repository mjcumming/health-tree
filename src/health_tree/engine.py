"""The engine: graph, evaluation, inhibition, episodes, windows, and queries.

Every call takes `now`, brings each check up to date, and evaluates the whole
graph once (ADR 0024). The events a call returns are the difference between the
episodes before and after it: a new episode is `opened`, a changed one is
`updated`, and a closed one is `resolved`. Nothing inside a call is emitted.
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import cast

from health_tree._checks import CheckState
from health_tree._codec import (
    JSONObject,
    as_list,
    as_object,
    episode_from_json,
    episode_to_json,
    observation_from_json,
    observation_to_json,
    required_time,
    strings_list,
    time_from_json,
    time_to_json,
)
from health_tree._ids import UUIDv7Factory
from health_tree.types import (
    BlockedBy,
    CheckReference,
    Coverage,
    EngineSettings,
    Episode,
    EpisodeForm,
    EpisodeOpened,
    EpisodeResolved,
    EpisodeUpdated,
    Event,
    Explanation,
    Finding,
    Impact,
    ImpactNode,
    JSONValue,
    Node,
    NodeCondition,
    Observation,
    ProbeRequested,
    QuietScope,
    QuietWindow,
    Readiness,
    ReadinessAnswer,
    Resolution,
    Rollup,
    RollupCounts,
    Status,
    View,
)

SCHEMA_VERSION = 1
"""The version of the data `Engine.snapshot` returns."""

_ZERO = timedelta(0)
_ANSWER_RANK: dict[ReadinessAnswer, int] = {
    "ready": 0,
    "unknown": 1,
    "degraded": 2,
    "blocked": 3,
}
_ANSWER: dict[Status, ReadinessAnswer] = {
    Status.PASS: "ready",
    Status.UNKNOWN: "unknown",
    Status.WARN: "degraded",
    Status.FAIL: "blocked",
}


@dataclass(slots=True, kw_only=True)
class _Window:
    scope: QuietScope
    node_id: str | None
    start: datetime
    until: datetime


@dataclass(slots=True, kw_only=True)
class _NodeState:
    onset: datetime | None = None
    probed: set[str] = field(default_factory=set)
    grace_until: datetime | None = None
    dependency_failed: bool = False


@dataclass(slots=True, kw_only=True)
class _EpisodeState:
    episode_id: str
    form: EpisodeForm
    anchor: str
    opened_at: datetime
    members: dict[str, datetime] = field(default_factory=dict)
    members_since: datetime | None = None
    absorbed: list[str] = field(default_factory=list)
    holding: set[str] = field(default_factory=set)
    holding_until: datetime | None = None
    view: Episode | None = None


@dataclass(slots=True, kw_only=True)
class _Closing:
    state: _EpisodeState
    resolution: Resolution
    into: str | None = None


@dataclass(slots=True, kw_only=True)
class _Frame:
    """What the graph looks like at `now`. Rebuilt by every evaluation."""

    now: datetime
    own: dict[str, Status]
    watched: dict[str, bool]
    findings: dict[str, list[Finding]]
    muted: dict[str, bool]
    roots: dict[str, frozenset[str]]
    gated: dict[str, bool] = field(default_factory=dict)


class Engine:
    """A state machine over the cause graph. It never reads a clock (ADR 0003).

    Args:
        settings: Engine-wide durations, all required (ADR 0018).
        new_id: Builds an episode id from `now`. The default builds a UUIDv7
            with random low bits (ADR 0017). Tests may pass their own.
    """

    __slots__ = (
        "_checks",
        "_closing",
        "_episodes",
        "_frame",
        "_ids",
        "_last",
        "_new_id",
        "_node_states",
        "_nodes",
        "_order",
        "_settings",
        "_windows",
    )

    def __init__(
        self,
        settings: EngineSettings,
        new_id: Callable[[datetime], str] | None = None,
    ) -> None:
        """Create an engine. Startup grace begins at the first call's `now`."""
        self._settings = settings
        self._ids = UUIDv7Factory()
        self._new_id: Callable[[datetime], str] = new_id or self._ids
        self._nodes: dict[str, Node] = {}
        self._checks: dict[str, dict[str, CheckState]] = {}
        self._node_states: dict[str, _NodeState] = {}
        self._episodes: dict[str, _EpisodeState] = {}
        self._closing: list[_Closing] = []
        self._windows: list[_Window] = []
        self._order: list[str] = []
        self._last: datetime | None = None
        self._frame: _Frame | None = None

    def register(self, node: Node, now: datetime) -> list[Event]:
        """Add or replace a node and its checks. A cycle is rejected (rule 23).

        An edge may name a node that is not registered yet. It takes effect
        when that node is registered.
        """
        return self.register_many([node], now)

    def register_many(self, nodes: Sequence[Node], now: datetime) -> list[Event]:
        """Add or replace nodes atomically, then evaluate once (ADR 0033).

        Validate the final graph before changing state or time. Unmentioned nodes
        remain registered. Retained checks keep their observations and holds.
        """
        if not nodes:
            raise ValueError("a batch needs at least one node")
        graph = self._nodes.copy()
        seen: set[str] = set()
        for node in nodes:
            if node.node_id in seen:
                raise ValueError(f"{node.node_id} appears twice in one batch")
            if any(edge.group is not None for edge in node.depends_on):
                raise ValueError("redundancy groups are reserved and rejected in v1")
            seen.add(node.node_id)
            graph[node.node_id] = node
        order = self._topological(graph)
        self._tick(now)
        for node in nodes:
            previous = self._checks.get(node.node_id, {})
            states: dict[str, CheckState] = {}
            for check in node.checks:
                state = previous.get(check.check_id)
                if state is None:
                    state = CheckState.registered(node.node_id, check, now)
                state.check = check
                states[check.check_id] = state
            self._checks[node.node_id] = states
            self._node_states.setdefault(node.node_id, _NodeState())
        self._nodes = graph
        self._order = order
        return self._evaluate(now)

    def remove(self, node_id: str, now: datetime) -> list[Event]:
        """Remove a node. Its open episode resolves as `removed` (rule 23)."""
        self._require_node(node_id)
        self._tick(now)
        del self._nodes[node_id], self._checks[node_id], self._node_states[node_id]
        for state in list(self._episodes.values()):
            if state.anchor == node_id:
                self._close(state, "removed")
            else:
                state.members.pop(node_id, None)
        self._windows = [w for w in self._windows if w.node_id != node_id]
        self._order = self._topological()
        return self._evaluate(now)

    def ingest(self, observation: Observation, now: datetime) -> list[Event]:
        """Apply one observation. The same as a one-observation batch (ADR 0024)."""
        return self.ingest_many([observation], now)

    def ingest_many(
        self, observations: Sequence[Observation], now: datetime
    ) -> list[Event]:
        """Apply a batch atomically, then evaluate once (ADR 0024).

        The whole batch is checked before any of it is applied.
        """
        if not observations:
            raise ValueError("a batch needs at least one observation")
        seen: set[tuple[str, str]] = set()
        for observation in observations:
            key = (observation.node_id, observation.check_id)
            if observation.check_id not in self._checks.get(observation.node_id, {}):
                raise ValueError(f"{key} is not a registered check")
            if key in seen:
                raise ValueError(f"{key} appears twice in one batch")
            seen.add(key)
        self._tick(now)
        for observation in observations:
            state = self._checks[observation.node_id][observation.check_id]
            state.observe(observation, now)
        return self._evaluate(now)

    def quiet(self, window: QuietWindow, now: datetime) -> list[Event]:
        """Open a quiet window from `now` until `window.until` (rules 21 and 22)."""
        if window.node_id is not None:
            self._require_node(window.node_id)
        if window.until <= now:
            raise ValueError("a quiet window must end after it starts")
        self._tick(now)
        self._windows.append(
            _Window(
                scope=window.scope,
                node_id=window.node_id,
                start=now,
                until=window.until,
            )
        )
        return self._evaluate(now)

    def advance(self, now: datetime) -> list[Event]:
        """Apply holds, `ttl`, gates, grace, and windows due at or before `now`."""
        self._tick(now)
        return self._evaluate(now)

    def next_deadline(self) -> datetime | None:
        """The next time `advance` would change anything, for the adapter's timer."""
        if self._last is None or self._frame is None:
            return None
        now = self._last
        times: list[datetime | None] = [
            state.next_deadline(now) for state in self._all_checks()
        ]
        times.extend(window.until for window in self._windows)
        times.extend(state.grace_until for state in self._node_states.values())
        for node_id, gated in self._frame.gated.items():
            onset = self._node_states[node_id].onset
            if gated and onset is not None:
                times.append(onset + self._settings.settle)
        return min(
            (time for time in times if time is not None and time > now), default=None
        )

    def snapshot(self) -> dict[str, JSONValue]:
        """All state, as JSON-compatible data with a schema version (rule 24)."""
        millis, counter = self._ids.state
        return {
            "schema_version": SCHEMA_VERSION,
            "now": time_to_json(self._last),
            "ids": [millis, counter],
            "windows": [
                {
                    "scope": window.scope,
                    "node_id": window.node_id,
                    "start": time_to_json(window.start),
                    "until": time_to_json(window.until),
                }
                for window in self._windows
            ],
            "checks": [_check_to_json(state) for state in self._all_checks()],
            "nodes": [
                {
                    "node_id": node_id,
                    "onset": time_to_json(state.onset),
                    "probed": strings_list(state.probed),
                    "grace_until": time_to_json(state.grace_until),
                    "dependency_failed": state.dependency_failed,
                }
                for node_id, state in self._node_states.items()
            ],
            "episodes": [
                _episode_state_to_json(state) for state in self._episodes.values()
            ],
        }

    def restore(self, state: Mapping[str, JSONValue], now: datetime) -> list[Event]:
        """Restore a snapshot after the graph is registered (rule 24, ADR 0011).

        Episodes whose anchor no longer exists resolve as `removed`. The others
        keep their ids and continue without a new `opened` event. Startup grace
        starts again at `now`.
        """
        if state.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"cannot restore schema {state.get('schema_version')!r}")
        first_call = self._last is None
        self._tick(now)
        if not first_call:
            self._start_grace(now)
        millis, counter = (int(cast(int, item)) for item in as_list(state["ids"]))
        self._ids.state = max(self._ids.state, (millis, counter))
        for item in as_list(state["windows"]):
            window = _window_from_json(item)
            if window.until > now and (
                window.node_id is None or window.node_id in self._nodes
            ):
                self._windows.append(window)
        for item in as_list(state["checks"]):
            _restore_check(self._checks, as_object(item))
        for item in as_list(state["nodes"]):
            data = as_object(item)
            node_id = str(data["node_id"])
            if node_id in self._node_states:
                self._node_states[node_id] = _NodeState(
                    onset=time_from_json(data["onset"]),
                    probed={str(name) for name in as_list(data["probed"])},
                    grace_until=time_from_json(data["grace_until"]),
                    dependency_failed=bool(data["dependency_failed"]),
                )
        for item in as_list(state["episodes"]):
            episode = _episode_state_from_json(as_object(item))
            episode.members = {
                name: since
                for name, since in episode.members.items()
                if name in self._nodes
            }
            episode.holding &= set(self._nodes)
            if episode.anchor in self._nodes:
                self._episodes[episode.episode_id] = episode
            else:
                self._closing.append(_Closing(state=episode, resolution="removed"))
        return self._evaluate(now)

    def explain(self, node_id: str) -> Explanation:
        """Why a node is not working: its findings, then its dependencies.

        `nodes` lists every watched dependency, direct or not, whose `own` is not
        `pass`, roots first. Unwatched nodes carry no evidence and are skipped.
        """
        self._require_node(node_id)
        frame = self._current_frame()
        above = self._ancestors([node_id])
        return Explanation(
            node_id=node_id,
            findings=tuple(frame.findings[node_id]),
            nodes=tuple(
                self._condition(name, frame)
                for name in self._order
                if name in above
                and frame.watched[name]
                and frame.own[name] is not Status.PASS
            ),
        )

    def readiness(self, node_ids: Collection[str]) -> Readiness:
        """Whether these functions can perform, from `own` status only (ADR 0025).

        Episodes, muting, quiet windows, and shelving never change the answer.
        Only causes are named: a node whose state a failed dependency explains
        is left out, because its own hardware may be fine (ADR 0028).
        """
        for node_id in node_ids:
            self._require_node(node_id)
        frame = self._current_frame()
        involved = set(node_ids) | self._ancestors(node_ids)
        if not any(frame.watched[name] for name in involved):
            return Readiness(
                answer="unknown",
                nodes=tuple(
                    self._condition(name, frame)
                    for name in self._order
                    if name in involved
                ),
            )
        answers: dict[str, ReadinessAnswer] = {}
        visited: set[str] = set()

        stack = [(node_id, True) for node_id in reversed(tuple(node_ids))]
        while stack:
            name, requested = stack.pop()
            if name in visited:
                continue
            visited.add(name)
            dependencies = self._dependencies(name)
            if frame.watched[name]:
                answers[name] = _ANSWER[frame.own[name]]
            elif not dependencies and not requested:
                answers[name] = "unknown"
            stack.extend((dependency, False) for dependency in reversed(dependencies))
        answer: ReadinessAnswer = "ready"
        for found in answers.values():
            if _ANSWER_RANK[found] > _ANSWER_RANK[answer]:
                answer = found
        causes = [
            name
            for name in self._order
            if answers.get(name, "ready") != "ready"
            and not any(frame.own[d] is Status.FAIL for d in self._dependencies(name))
        ]
        blocked_by: BlockedBy | None = None
        if answer == "blocked":
            own_fault = any(answers.get(name) == "blocked" for name in node_ids)
            blocked_by = (
                "own" if own_fault and set(causes) & set(node_ids) else "dependency"
            )
        return Readiness(
            answer=answer,
            nodes=tuple(self._condition(name, frame) for name in causes),
            blocked_by=blocked_by,
        )

    def impact(self, node_id: str) -> Impact:
        """Return potential dependents and importance, even when all are healthy.

        The requested node is excluded from `nodes` but included in the
        maximum importance. Each transitive dependent appears once.
        """
        self._require_node(node_id)
        dependents = self._dependents(node_id)
        return Impact(
            node_id=node_id,
            nodes=tuple(
                ImpactNode(node_id=name, importance=self._nodes[name].importance)
                for name in self._order
                if name in dependents
            ),
            importance=max(
                self._nodes[name].importance for name in {node_id, *dependents}
            ),
        )

    def coverage(self) -> Coverage:
        """Return missing checks, never-observed checks, and stale checks.

        Evidence-only checks are included. Never-observed checks may also be
        stale. Quiet windows and inhibition do not hide evidence gaps.
        """
        never_observed: list[CheckReference] = []
        stale: list[CheckReference] = []
        for node_id in self._order:
            for check_id, state in self._checks[node_id].items():
                reference = CheckReference(node_id=node_id, check_id=check_id)
                if state.observation is None:
                    never_observed.append(reference)
                assert self._last is not None
                if state.is_stale(self._last):
                    stale.append(reference)
        return Coverage(
            no_checks=tuple(name for name in self._order if not self._checks[name]),
            never_observed=tuple(never_observed),
            stale=tuple(stale),
        )

    def rollup(self, view: View, group: str) -> Rollup:
        """Count each selected node by its own status and episode membership.

        Anchoring an open episode takes precedence over being recorded on
        another. Unknown groups or selected members raise `KeyError`.
        """
        selected = view.groups[group]
        for node_id in sorted(selected):
            self._require_node(node_id)
        by_status: dict[Status, set[str]] = {status: set() for status in Status}
        if selected:
            frame = self._current_frame()
            for node_id in selected:
                by_status[frame.own[node_id]].add(node_id)
        anchors = {state.anchor for state in self._episodes.values()}
        recorded = {
            node_id
            for state in self._episodes.values()
            if state.view is not None
            for node_id in state.view.recorded
        }
        return Rollup(
            view_id=view.view_id,
            group=group,
            counts=tuple(
                RollupCounts(
                    own=status,
                    clear=len(members - anchors - recorded),
                    own_episode=len(members & anchors),
                    recorded=len((members & recorded) - anchors),
                )
                for status, members in by_status.items()
            ),
        )

    def _tick(self, now: datetime) -> None:
        if now.utcoffset() != _ZERO:
            raise ValueError("now must be a timezone-aware UTC datetime")
        if self._last is not None and now < self._last:
            raise ValueError("now must not go backwards")
        if self._last is None:
            self._start_grace(now)
        self._last = now

    def _start_grace(self, now: datetime) -> None:
        if self._settings.startup_grace > _ZERO:
            self._windows.append(
                _Window(
                    scope="all",
                    node_id=None,
                    start=now,
                    until=now + self._settings.startup_grace,
                )
            )

    def _require_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            raise KeyError(node_id)

    def _current_frame(self) -> _Frame:
        assert self._frame is not None
        return self._frame

    def _all_checks(self) -> Iterable[CheckState]:
        for states in self._checks.values():
            yield from states.values()

    def _dependencies(self, node_id: str) -> list[str]:
        return [
            edge.to
            for edge in self._nodes[node_id].depends_on
            if edge.to in self._nodes
        ]

    def _topological(self, nodes: Mapping[str, Node] | None = None) -> list[str]:
        graph = self._nodes if nodes is None else nodes
        order: list[str] = []
        placed: set[str] = set()
        visiting: set[str] = set()
        for root in graph:
            stack = [(root, False)]
            while stack:
                name, expanded = stack.pop()
                if name in placed:
                    continue
                if expanded:
                    visiting.remove(name)
                    placed.add(name)
                    order.append(name)
                    continue
                if name in visiting:
                    raise ValueError(f"an edge from {name} would close a cycle")
                visiting.add(name)
                stack.append((name, True))
                stack.extend(
                    (edge.to, False)
                    for edge in reversed(graph[name].depends_on)
                    if edge.to in graph
                )
        return order

    def _ancestors(self, node_ids: Iterable[str]) -> set[str]:
        found: set[str] = set()
        stack = [dep for name in node_ids for dep in self._dependencies(name)]
        while stack:
            name = stack.pop()
            if name not in found:
                found.add(name)
                stack.extend(self._dependencies(name))
        return found

    def _dependents(self, node_id: str) -> set[str]:
        found: set[str] = set()
        for name in self._order:
            if any(dep == node_id or dep in found for dep in self._dependencies(name)):
                found.add(name)
        return found

    def _condition(self, node_id: str, frame: _Frame) -> NodeCondition:
        return NodeCondition(
            node_id=node_id,
            own=frame.own[node_id],
            reasons=tuple(finding.reason for finding in frame.findings[node_id]),
            watched=frame.watched[node_id],
        )

    def _affecting(self, node_id: str) -> list[CheckState]:
        return [s for s in self._checks[node_id].values() if s.check.affects_own]

    def _evaluate(self, now: datetime) -> list[Event]:
        for state in self._all_checks():
            state.advance(now)
        self._windows = [window for window in self._windows if window.until > now]
        frame = self._build_frame(now)
        if self._update_members(frame):
            frame = self._build_frame(now)
        self._frame = frame
        self._resolve_recovered(frame)
        probes = self._gate(frame)
        self._open(frame)
        return self._emit(frame, probes)

    def _build_frame(self, now: datetime) -> _Frame:
        own: dict[str, Status] = {}
        watched: dict[str, bool] = {}
        for name in self._order:
            affecting = self._affecting(name)
            watched[name] = bool(affecting)
            own[name] = max((s.effective for s in affecting), default=Status.UNKNOWN)
        for name in self._order:
            state = self._node_states[name]
            failed = any(own[dep] is Status.FAIL for dep in self._dependencies(name))
            if state.dependency_failed and not failed:
                self._rejoin(name, now)
            state.dependency_failed = failed
        findings: dict[str, list[Finding]] = {}
        muted: dict[str, bool] = {}
        roots: dict[str, frozenset[str]] = {}
        for name in self._order:
            found = [
                f for s in self._affecting(name) if (f := s.finding(now)) is not None
            ]
            findings[name] = found
            failed_deps = [
                dep for dep in self._dependencies(name) if own[dep] is Status.FAIL
            ]
            muted[name] = bool(found) and bool(failed_deps)
            roots[name] = (
                frozenset(
                    root
                    for dep in failed_deps
                    for root in (roots[dep] if muted[dep] else {dep})
                )
                if muted[name]
                else frozenset()
            )
            state = self._node_states[name]
            if not found:
                state.onset = None
                state.probed.clear()
            elif state.onset is None:
                state.onset = min(finding.since for finding in found)
        return _Frame(
            now=now,
            own=own,
            watched=watched,
            findings=findings,
            muted=muted,
            roots=roots,
        )

    def _rejoin(self, node_id: str, now: datetime) -> None:
        """Rule 19: wait out `rejoin_grace`, and restart the stale clocks."""
        self._node_states[node_id].grace_until = now + self._settings.rejoin_grace
        for state in self._checks[node_id].values():
            state.rejoin(now)

    def _close(
        self, state: _EpisodeState, resolution: Resolution, into: str | None = None
    ) -> None:
        del self._episodes[state.episode_id]
        self._closing.append(_Closing(state=state, resolution=resolution, into=into))

    def _absorb(self, state: _EpisodeState, into: _EpisodeState) -> None:
        into.absorbed.append(state.episode_id)
        self._close(state, "absorbed", into.episode_id)

    def _update_members(self, frame: _Frame) -> bool:
        """Dissolve undersized groups; report whether stale clocks restarted."""
        rejoined = False
        for state in self._episodes.values():
            self._update_holding(state, frame)
        for state in list(self._episodes.values()):
            if not state.members:
                continue
            for member in list(state.members):
                if frame.own[member] is Status.PASS:
                    del state.members[member]
            failing = [m for m in state.members if frame.findings[m]]
            if len(failing) >= self._settings.coalesce_count:
                continue
            for member in state.members:
                self._rejoin(member, frame.now)
                rejoined = True
            state.members.clear()
            state.members_since = None
            if state.form == "group":
                self._close(state, "cleared")
        return rejoined

    def _update_holding(self, state: _EpisodeState, frame: _Frame) -> None:
        """Rule 15: stragglers held through rejoin grace become members, or go.

        Held nodes that recover simply leave. When the grace ends, the ones
        still failing become members if there are at least `coalesce_count`.
        Otherwise they are released, the episode can clear, and each one opens
        its own episode.
        """
        if not state.holding:
            return
        state.holding = {
            n for n in state.holding if n in self._nodes and frame.findings[n]
        }
        assert state.holding_until is not None
        if frame.now < state.holding_until:
            return
        still = sorted(state.holding, key=self._order.index)
        state.holding.clear()
        state.holding_until = None
        if len(still) >= self._settings.coalesce_count:
            for name in still:
                state.members[name] = frame.now
            state.members_since = frame.now

    def _resolve_recovered(self, frame: _Frame) -> None:
        """Rule 15: a root episode clears when its anchor passes and holds no one.

        When the anchor passes while nodes it muted still fail, the episode
        stays open and holds them through their rejoin grace.
        """
        for state in list(self._episodes.values()):
            if (
                state.form != "root"
                or state.members
                or state.holding
                or frame.own[state.anchor] is not Status.PASS
            ):
                continue
            recorded = state.view.recorded if state.view is not None else frozenset()
            stragglers = {
                name: grace
                for name in recorded
                if name in self._nodes
                and frame.findings[name]
                and not frame.muted[name]
                and (grace := self._node_states[name].grace_until) is not None
                and grace > frame.now
            }
            if stragglers:
                state.holding = set(stragglers)
                state.holding_until = max(stragglers.values())
            else:
                self._close(state, "cleared")

    def _has_episode(self, node_id: str) -> bool:
        return any(
            (state.form == "root" and state.anchor == node_id)
            or node_id in state.members
            or node_id in state.holding
            for state in self._episodes.values()
        )

    def _may_open(self, node_id: str, now: datetime) -> bool:
        grace = self._node_states[node_id].grace_until
        if grace is not None and now < grace:
            return False
        return not any(self._covers(window, node_id) for window in self._windows)

    def _covers(self, window: _Window, node_id: str) -> bool:
        if window.scope == "all" or window.node_id == node_id:
            return True
        assert window.node_id is not None
        return window.scope == "node_and_dependents" and node_id in self._dependents(
            window.node_id
        )

    def _in_doubt(self, node_id: str, frame: _Frame) -> bool:
        """ADR 0022: a watched dependency that is unknown, worsening, or gated."""
        return frame.watched[node_id] and (
            frame.own[node_id] is Status.UNKNOWN
            or frame.gated[node_id]
            or any(s.worsening_pending() for s in self._affecting(node_id))
        )

    def _gate(self, frame: _Frame) -> list[Event]:
        """Rule 13: hold a node while a dependency is in doubt, up to `settle`."""
        probes: list[Event] = []
        for name in self._order:
            frame.gated[name] = False
            state = self._node_states[name]
            if (
                not frame.findings[name]
                or frame.muted[name]
                or self._has_episode(name)
                or state.onset is None
                or frame.now >= state.onset + self._settings.settle
            ):
                continue
            doubtful = [d for d in self._dependencies(name) if self._in_doubt(d, frame)]
            frame.gated[name] = bool(doubtful)
            if not self._may_open(name, frame.now):
                continue
            for dependency in doubtful:
                if dependency not in state.probed:
                    state.probed.add(dependency)
                    probes.append(ProbeRequested(node_id=dependency))
        return probes

    def _open(self, frame: _Frame) -> None:
        now = frame.now
        candidates = [
            name
            for name in self._order
            if frame.findings[name]
            and not frame.muted[name]
            and not frame.gated[name]
            and not self._has_episode(name)
            and self._may_open(name, now)
        ]
        remaining: list[str] = []
        for name in candidates:
            group = self._joinable(name, frame)
            if group is None:
                remaining.append(name)
            else:
                group.members[name] = now
        remaining = self._coalesce(remaining, frame)
        for name in remaining:
            self._open_root(name, frame)

    def _joinable(self, node_id: str, frame: _Frame) -> _EpisodeState | None:
        """ADR 0021: a failing sibling joins an episode that holds members."""
        dependencies = self._dependencies(node_id)
        return next(
            (
                state
                for state in self._episodes.values()
                if state.members
                and state.anchor in dependencies
                and frame.own[state.anchor] is not Status.FAIL
            ),
            None,
        )

    def _coalesce(self, candidates: list[str], frame: _Frame) -> list[str]:
        """Rule 18: enough failures under one dependency become one episode."""
        now = frame.now
        window_start = now - self._settings.coalesce_window
        for anchor in self._order:
            new = [c for c in candidates if anchor in self._dependencies(c)]
            if not new:
                continue
            recent = [
                state
                for state in self._episodes.values()
                if state.form == "root"
                and not state.members
                and anchor in self._dependencies(state.anchor)
                and state.opened_at >= window_start
                and frame.findings[state.anchor]
                and not frame.muted[state.anchor]
            ]
            if len(new) + len(recent) < self._settings.coalesce_count:
                continue
            target = next(
                (s for s in self._episodes.values() if s.anchor == anchor),
                None,
            ) or self._new_episode("group", anchor, now)
            for name in [*new, *(state.anchor for state in recent)]:
                target.members[name] = now
            if target.members_since is None:
                target.members_since = now
            for state in recent:
                self._absorb(state, target)
            candidates = [c for c in candidates if c not in new]
        return candidates

    def _open_root(self, node_id: str, frame: _Frame) -> None:
        episode = self._new_episode("root", node_id, frame.now)
        failed = frame.own[node_id] is Status.FAIL
        for group in [
            s
            for s in self._episodes.values()
            if s.form == "group" and s.anchor == node_id
        ]:
            if not failed:
                episode.members.update(group.members)
                episode.members_since = group.members_since
            self._absorb(group, episode)
        onset = self._node_states[node_id].onset
        if not failed or onset is None:
            return
        earliest = onset - self._settings.settle
        for state in list(self._episodes.values()):
            child = state.anchor
            child_onset = self._node_states[child].onset
            if (
                state.form == "root"
                and frame.muted[child]
                and node_id in frame.roots[child]
                and child_onset is not None
                and child_onset >= earliest
            ):
                self._absorb(state, episode)

    def _new_episode(
        self, form: EpisodeForm, anchor: str, now: datetime
    ) -> _EpisodeState:
        episode_id = self._new_id(now)
        if episode_id in self._episodes:
            raise ValueError(f"new_id returned {episode_id}, which is already open")
        state = _EpisodeState(
            episode_id=episode_id, form=form, anchor=anchor, opened_at=now
        )
        self._episodes[state.episode_id] = state
        return state

    def _emit(self, frame: _Frame, probes: list[Event]) -> list[Event]:
        opened: list[Event] = []
        updated: list[Event] = []
        for state in self._episodes.values():
            view = self._view(state, frame)
            if state.view is None:
                state.view = view
                opened.append(EpisodeOpened(episode=view))
            elif replace(state.view, updated_at=view.updated_at) != view:
                state.view = replace(view, updated_at=frame.now)
                updated.append(EpisodeUpdated(episode=state.view))
        resolved: list[Event] = [
            EpisodeResolved(
                episode=replace(closing.state.view, updated_at=frame.now),
                resolution=closing.resolution,
                absorbed_into=closing.into,
            )
            for closing in self._closing
            if closing.state.view is not None
        ]
        self._closing.clear()
        return [*opened, *updated, *resolved, *probes]

    def _view(self, state: _EpisodeState, frame: _Frame) -> Episode:
        anchor = state.anchor
        members = [name for name in self._order if name in state.members]
        held = [name for name in self._order if name in state.holding]
        reasons = [*frame.findings[anchor]]
        for member in [*members, *held]:
            reasons.extend(frame.findings[member])
        if members:
            reasons.append(
                Finding(
                    node_id=anchor,
                    check_id=None,
                    status=max(frame.own[m] for m in members),
                    reason="dependents_failing",
                    since=state.members_since or state.opened_at,
                )
            )
        sources = {anchor, *members, *held}
        recorded = {*members, *held} | {
            name
            for name in self._order
            if frame.muted[name]
            and frame.roots[name] & sources
            and not self._has_episode(name)
        }
        impact = self._dependents(anchor)
        return Episode(
            episode_id=state.episode_id,
            form=state.form,
            anchor=anchor,
            status=max(frame.own[name] for name in [anchor, *members, *held]),
            reasons=tuple(reasons),
            recorded=frozenset(recorded),
            impact=frozenset(impact),
            importance=max(self._nodes[name].importance for name in {anchor, *impact}),
            opened_at=state.opened_at,
            updated_at=frame.now if state.view is None else state.view.updated_at,
            due_at=min(
                (f.due_at for f in reasons if f.due_at is not None), default=None
            ),
            absorbed=frozenset(state.absorbed),
            labels=self._nodes[anchor].labels,
        )


def _check_to_json(state: CheckState) -> JSONObject:
    return {
        "node_id": state.node_id,
        "check_id": state.check.check_id,
        "effective": state.effective.value,
        "since": time_to_json(state.since),
        "reason": state.reason,
        "message": state.message,
        "due_at": time_to_json(state.due_at),
        "pending": None if state.pending is None else state.pending.value,
        "pending_since": time_to_json(state.pending_since),
        "observation": (
            None
            if state.observation is None
            else observation_to_json(state.observation)
        ),
        "expired": state.expired,
        "problem_known": state.problem_known,
        "stale_at": time_to_json(state.stale_at),
    }


def _restore_check(checks: dict[str, dict[str, CheckState]], data: JSONObject) -> None:
    state = checks.get(str(data["node_id"]), {}).get(str(data["check_id"]))
    if state is None:
        return
    pending = data["pending"]
    observation = data["observation"]
    reason = data["reason"]
    message = data["message"]
    state.effective = Status(data["effective"])
    state.since = required_time(data["since"])
    state.reason = None if reason is None else str(reason)
    state.message = None if message is None else str(message)
    state.due_at = time_from_json(data["due_at"])
    state.pending = None if pending is None else Status(pending)
    state.pending_since = time_from_json(data["pending_since"])
    state.observation = (
        None if observation is None else observation_from_json(observation)
    )
    state.expired = bool(data["expired"])
    state.problem_known = bool(data["problem_known"])
    state.stale_at = time_from_json(data["stale_at"])


def _window_from_json(value: JSONValue) -> _Window:
    data = as_object(value)
    node_id = data["node_id"]
    return _Window(
        scope=cast(QuietScope, data["scope"]),
        node_id=None if node_id is None else str(node_id),
        start=required_time(data["start"]),
        until=required_time(data["until"]),
    )


def _episode_state_to_json(state: _EpisodeState) -> JSONObject:
    return {
        "episode_id": state.episode_id,
        "form": state.form,
        "anchor": state.anchor,
        "opened_at": time_to_json(state.opened_at),
        "members": {name: time_to_json(since) for name, since in state.members.items()},
        "members_since": time_to_json(state.members_since),
        "absorbed": [str(item) for item in state.absorbed],
        "holding": strings_list(state.holding),
        "holding_until": time_to_json(state.holding_until),
        "view": None if state.view is None else episode_to_json(state.view),
    }


def _episode_state_from_json(data: JSONObject) -> _EpisodeState:
    view = data["view"]
    return _EpisodeState(
        episode_id=str(data["episode_id"]),
        form=cast(EpisodeForm, data["form"]),
        anchor=str(data["anchor"]),
        opened_at=required_time(data["opened_at"]),
        members={
            name: required_time(since)
            for name, since in as_object(data["members"]).items()
        },
        members_since=time_from_json(data["members_since"]),
        absorbed=[str(item) for item in as_list(data["absorbed"])],
        holding={str(item) for item in as_list(data["holding"])},
        holding_until=time_from_json(data["holding_until"]),
        view=None if view is None else episode_from_json(view),
    )
