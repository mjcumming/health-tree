"""Validate health-tree YAML fixtures against the RFP 0.5 draft and ADR 0024.

It checks structure only. `tests/runner.py` runs the fixtures against the engine.
"""

from collections.abc import Set as AbstractSet
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Any

import yaml

FIXTURES = Path(__file__).parent / "fixtures"

_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
_BIND = re.compile(r"^[a-z][a-z0-9_]*$")
_DURATION = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")
_CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_QUIET = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$")
_SETTINGS = (
    "settle",
    "rejoin_grace",
    "startup_grace",
    "coalesce_count",
    "coalesce_window",
)
_CHECK_DURATIONS = ("raise_hold", "clear_hold", "ttl", "unknown_hold")
_IMPORTANCE = frozenset({"low", "normal", "high", "critical"})
_STATUS = frozenset({"pass", "unknown", "warn", "fail"})
_LOUDNESS = frozenset({"record", "digest", "notify", "urgent"})
_RESOLUTION = frozenset({"cleared", "removed", "absorbed"})
_QUIET_SCOPES = frozenset({"all", "node", "node_and_dependents"})
_MATCH_KEYS = frozenset(
    {"status", "importance", "reason", "category", "labels", "age", "due_within"}
)
_EVENT_KINDS = frozenset({"probe", "opened", "updated", "resolved"})
_EPISODE_FIELDS = frozenset(
    {
        "anchor",
        "episode",
        "form",
        "status",
        "importance",
        "reasons",
        "recorded",
        "absorbed",
    }
)
_READINESS = frozenset({"ready", "degraded", "blocked", "unknown"})
_BLOCKED_BY = frozenset({"own", "dependency"})


class FixtureSchemaError(ValueError):
    """A fixture does not match the current design's schema."""


def parse_duration(value: str) -> timedelta:
    """Parse a fixture duration such as `90s`, `15m`, or `1d2h`."""
    match = _DURATION.fullmatch(value)
    if not value or match is None:
        raise FixtureSchemaError(f"{value!r} is not a duration")
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def validate_directory(path: Path = FIXTURES) -> None:
    """Validate every YAML fixture in `path`."""
    files = sorted(path.glob("*.yaml"))
    if not files:
        raise FixtureSchemaError(f"{path} has no fixtures")
    errors: list[str] = []
    for fixture in files:
        try:
            document = yaml.safe_load(fixture.read_text(encoding="utf-8"))
            validate_fixture(document, filename=fixture.name)
        except FixtureSchemaError as exc:
            errors.append(str(exc))
    if errors:
        raise FixtureSchemaError("\n".join(errors))


def validate_fixture(document: object, *, filename: str) -> None:
    """Validate one fixture document."""
    problems: list[str] = []
    if not isinstance(document, dict):
        raise FixtureSchemaError(f"{filename}: fixture must be a mapping")
    data: dict[str, Any] = document
    _require_keys(
        data,
        {"id", "title", "covers", "start", "settings", "graph", "steps"},
        filename,
        problems,
    )
    _reject_unknown(
        data,
        {
            "id",
            "title",
            "covers",
            "start",
            "settings",
            "policy",
            "graph",
            "views",
            "steps",
        },
        filename,
        problems,
    )
    stem = filename.removesuffix(".yaml")
    if data.get("id") != stem:
        problems.append(f"{filename}: id {data.get('id')!r} does not match {stem}")
    _string(data.get("title"), f"{filename}: title", problems)
    _covers(data.get("covers"), filename, problems)
    start = _datetime(data.get("start"), f"{filename}: start", problems)
    _settings(data.get("settings"), filename, problems)
    if "policy" in data:
        _policy(data.get("policy"), filename, problems)
    nodes = _graph(data.get("graph"), filename, problems)
    views = _views(data.get("views", {}), nodes, f"{filename}: views", problems)
    _steps(
        data.get("steps"),
        filename=filename,
        start=start,
        nodes=nodes,
        views=views,
        has_policy="policy" in data,
        problems=problems,
    )
    if problems:
        raise FixtureSchemaError("\n".join(problems))


def _require_keys(
    data: dict[str, Any],
    required: set[str],
    filename: str,
    problems: list[str],
) -> None:
    missing = required - data.keys()
    if missing:
        problems.append(f"{filename}: missing {', '.join(sorted(missing))}")


def _reject_unknown(
    data: dict[str, Any],
    allowed: AbstractSet[str],
    where: str,
    problems: list[str],
) -> None:
    extra = set(data) - allowed
    if extra:
        problems.append(f"{where}: unknown keys {', '.join(sorted(extra))}")


def _string(value: object, where: str, problems: list[str]) -> None:
    if not isinstance(value, str) or not value:
        problems.append(f"{where} must be a non-empty string")


def _covers(value: object, filename: str, problems: list[str]) -> None:
    if not isinstance(value, list) or not value:
        problems.append(f"{filename}: covers must be a non-empty list")
        return
    problems.extend(
        f"{filename}: bad covers entry {item!r}"
        for item in value
        if not isinstance(item, str)
        or re.fullmatch(r"(story|scenario)-\d+", item) is None
    )


def _datetime(value: object, where: str, problems: list[str]) -> datetime | None:
    parsed = value if isinstance(value, datetime) else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            problems.append(f"{where} is not a timestamp")
            return None
    if parsed is None:
        problems.append(f"{where} must be a UTC timestamp")
        return None
    if parsed.tzinfo is None:
        problems.append(f"{where} must include a timezone")
        return None
    return parsed


def _duration(value: object, where: str, problems: list[str]) -> None:
    if not isinstance(value, str) or not value or _DURATION.fullmatch(value) is None:
        problems.append(f"{where} must be a duration such as 2m or 30s")


def _settings(value: object, filename: str, problems: list[str]) -> None:
    where = f"{filename}: settings"
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    _reject_unknown(value, set(_SETTINGS), where, problems)
    _require_keys(value, set(_SETTINGS), where, problems)
    for name in ("settle", "rejoin_grace", "startup_grace", "coalesce_window"):
        if name in value:
            _duration(value[name], f"{where}.{name}", problems)
    count = value.get("coalesce_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 2:
        problems.append(f"{where}.coalesce_count must be an integer >= 2")


def _policy(value: object, filename: str, problems: list[str]) -> None:
    where = f"{filename}: policy"
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    allowed = {"batch", "recipients", "digests", "rules"}
    _reject_unknown(value, allowed, where, problems)
    _require_keys(value, allowed, where, problems)
    if "batch" in value:
        _duration(value["batch"], f"{where}.batch", problems)
    recipients = value.get("recipients")
    if not isinstance(recipients, dict) or not recipients:
        problems.append(f"{where}.recipients must be a non-empty mapping")
        recipients = {}
    for name, recipient in recipients.items():
        _recipient(name, recipient, where, problems)
    digests = value.get("digests")
    if not isinstance(digests, dict):
        problems.append(f"{where}.digests must be a mapping")
        digests = {}
    for name, digest in digests.items():
        _digest(name, digest, set(recipients), where, problems)
    rules = value.get("rules")
    if not isinstance(rules, list) or not rules:
        problems.append(f"{where}.rules must be a non-empty list")
        return
    for index, rule in enumerate(rules):
        _rule(rule, set(digests), f"{where}.rules[{index}]", problems)


def _recipient(
    name: object,
    value: object,
    where: str,
    problems: list[str],
) -> None:
    path = f"{where}.recipients.{name}"
    if not isinstance(name, str) or not _ID.fullmatch(name):
        problems.append(f"{path}: bad recipient id")
    if not isinstance(value, dict):
        problems.append(f"{path} must be a mapping")
        return
    _reject_unknown(value, {"channels", "quiet_hours", "sites"}, path, problems)
    channels = value.get("channels")
    if not isinstance(channels, list) or not all(isinstance(c, str) for c in channels):
        problems.append(f"{path}.channels must be a list of strings")
    quiet = value.get("quiet_hours")
    if quiet is not None and (
        not isinstance(quiet, str) or _QUIET.fullmatch(quiet) is None
    ):
        problems.append(f"{path}.quiet_hours must look like 22:30-07:00")


def _digest(
    name: object,
    value: object,
    recipients: set[str],
    where: str,
    problems: list[str],
) -> None:
    path = f"{where}.digests.{name}"
    if not isinstance(value, dict):
        problems.append(f"{path} must be a mapping")
        return
    _reject_unknown(value, {"at", "to"}, path, problems)
    at = value.get("at")
    if not isinstance(at, str) or _CLOCK.fullmatch(at) is None:
        problems.append(f"{path}.at must be HH:MM")
    if value.get("to") not in recipients:
        problems.append(f"{path}.to is not a recipient")


def _rule(
    value: object,
    digests: set[str],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    _reject_unknown(
        value,
        {"match", "loudness", "to", "digest", "remind_every", "escalate_after"},
        where,
        problems,
    )
    match = value.get("match")
    if not isinstance(match, dict):
        problems.append(f"{where}.match must be a mapping")
    else:
        _reject_unknown(match, _MATCH_KEYS, f"{where}.match", problems)
    if value.get("loudness") not in _LOUDNESS:
        problems.append(f"{where}.loudness is not a loudness")
    if "digest" in value and value["digest"] not in digests:
        problems.append(f"{where}.digest is not a digest")
    for name in ("remind_every", "escalate_after"):
        if name in value:
            _duration(value[name], f"{where}.{name}", problems)


def _graph(value: object, filename: str, problems: list[str]) -> dict[str, set[str]]:
    """Return node id to check ids. Empty when the graph is unusable."""
    where = f"{filename}: graph"
    if not isinstance(value, list) or not value:
        problems.append(f"{where} must be a non-empty list")
        return {}
    nodes: dict[str, set[str]] = {}
    edges: dict[str, list[str]] = {}
    for index, node in enumerate(value):
        node_id, check_ids, depends = _node(node, f"{where}[{index}]", problems)
        if node_id is None:
            continue
        if node_id in nodes:
            problems.append(f"{where}: duplicate node {node_id}")
        nodes[node_id] = check_ids
        edges[node_id] = depends
    problems.extend(
        f"{filename}: {node_id} depends on unknown {target}"
        for node_id, depends in edges.items()
        for target in depends
        if target not in nodes
    )
    _cycles(edges, filename, problems)
    return nodes


def _node(
    value: object,
    where: str,
    problems: list[str],
) -> tuple[str | None, set[str], list[str]]:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return None, set(), []
    _reject_unknown(
        value,
        {"id", "kind", "importance", "depends_on", "labels", "checks"},
        where,
        problems,
    )
    node_id = value.get("id")
    if not isinstance(node_id, str) or not _ID.fullmatch(node_id):
        problems.append(f"{where}.id must be a lowercase identifier")
        node_id = None
    importance = value.get("importance", "normal")
    if importance not in _IMPORTANCE:
        problems.append(f"{where}.importance is not an importance")
    depends = value.get("depends_on", [])
    if not isinstance(depends, list) or not all(
        isinstance(item, str) for item in depends
    ):
        problems.append(f"{where}.depends_on must be a list of ids")
        depends = []
    checks = value.get("checks", [])
    check_ids: set[str] = set()
    if not isinstance(checks, list):
        problems.append(f"{where}.checks must be a list")
    else:
        for index, check in enumerate(checks):
            check_id = _check(check, f"{where}.checks[{index}]", problems)
            if check_id is None:
                continue
            if check_id in check_ids:
                problems.append(f"{where}: duplicate check {check_id}")
            check_ids.add(check_id)
    return node_id, check_ids, depends


def _check(value: object, where: str, problems: list[str]) -> str | None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return None
    _reject_unknown(
        value,
        {"id", "affects_own", "labels", "annotations", *_CHECK_DURATIONS},
        where,
        problems,
    )
    check_id = value.get("id")
    if not isinstance(check_id, str) or not _ID.fullmatch(check_id):
        problems.append(f"{where}.id must be a lowercase identifier")
        check_id = None
    for name in _CHECK_DURATIONS:
        if name not in value:
            problems.append(f"{where} missing {name}")
        elif not (name == "ttl" and value[name] is None):
            _duration(value[name], f"{where}.{name}", problems)
    if "affects_own" in value and not isinstance(value["affects_own"], bool):
        problems.append(f"{where}.affects_own must be a boolean")
    return check_id


def _cycles(
    edges: dict[str, list[str]],
    filename: str,
    problems: list[str],
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        visiting.add(node)
        for target in edges.get(node, []):
            if target in visiting:
                problems.append(f"{filename}: cycle through {node} -> {target}")
            elif target not in visited and target in edges:
                walk(target)
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        if node not in visited:
            walk(node)


def _steps(
    value: object,
    *,
    filename: str,
    start: datetime | None,
    nodes: dict[str, set[str]],
    views: dict[str, set[str]],
    has_policy: bool,
    problems: list[str],
) -> None:
    where = f"{filename}: steps"
    if not isinstance(value, list) or not value:
        problems.append(f"{where} must be a non-empty list")
        return
    bound: set[str] = set()
    previous_step: datetime | None = None
    for index, step in enumerate(value):
        path = f"{where}[{index}]"
        if not isinstance(step, dict):
            problems.append(f"{path} must be a mapping")
            continue
        _reject_unknown(
            step, {"at", "quiet", "ingest", "restart", "expect"}, path, problems
        )
        at = _datetime(step.get("at"), f"{path}.at", problems)
        if at is not None and start is not None and at < start:
            problems.append(f"{path}.at must not be before start")
        if at is not None and previous_step is not None and at <= previous_step:
            problems.append(f"{path}.at must be after the previous step")
        if at is not None:
            previous_step = at
        if step.get("restart") is True and ("ingest" in step or "quiet" in step):
            problems.append(f"{path} cannot restart and also quiet or ingest")
        if "quiet" in step:
            _quiet_window(step["quiet"], nodes, at, f"{path}.quiet", problems)
        if "ingest" in step:
            _ingest(step["ingest"], nodes, path, problems)
        if "restart" in step and step["restart"] is not True:
            problems.append(f"{path}.restart must be true")
        expect = step.get("expect")
        if not isinstance(expect, dict):
            problems.append(f"{path}.expect must be a mapping")
            continue
        _expect(expect, path, nodes, views, bound, has_policy, problems)


def _quiet_window(
    value: object,
    nodes: dict[str, set[str]],
    at: datetime | None,
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    _reject_unknown(value, {"scope", "node", "until"}, where, problems)
    scope = value.get("scope")
    if scope not in _QUIET_SCOPES:
        problems.append(f"{where}.scope must be all, node, or node_and_dependents")
    elif scope == "all" and "node" in value:
        problems.append(f"{where}.node is not allowed when scope is all")
    elif scope != "all" and value.get("node") not in nodes:
        problems.append(f"{where}.node must name a node")
    until = _datetime(value.get("until"), f"{where}.until", problems)
    if until is not None and at is not None and until <= at:
        problems.append(f"{where}.until must be after the step")


def _ingest(
    value: object,
    nodes: dict[str, set[str]],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, list) or not value:
        problems.append(f"{where}.ingest must be a non-empty list")
        return
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        path = f"{where}.ingest[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{path} must be a mapping")
            continue
        _reject_unknown(
            item,
            {"node", "check", "status", "reason", "message", "evidence", "due_at"},
            path,
            problems,
        )
        node = item.get("node")
        check = item.get("check")
        if (
            not isinstance(node, str)
            or node not in nodes
            or not isinstance(check, str)
            or check not in nodes[node]
        ):
            problems.append(f"{path} does not name a registered check")
        else:
            key = (node, check)
            if key in seen:
                problems.append(f"{path}: duplicate check observation {node}.{check}")
            seen.add(key)
        if item.get("status") not in _STATUS:
            problems.append(f"{path}.status is not a status")
        _string(item.get("reason"), f"{path}.reason", problems)
        if "due_at" in item:
            _datetime(item["due_at"], f"{path}.due_at", problems)


def _expect(
    expect: dict[str, Any],
    where: str,
    nodes: dict[str, set[str]],
    views: dict[str, set[str]],
    bound: set[str],
    has_policy: bool,
    problems: list[str],
) -> None:
    path = f"{where}.expect"
    _reject_unknown(
        expect,
        {"bind", "events", "deliveries", "open", "queries"},
        path,
        problems,
    )
    if "events" not in expect:
        problems.append(f"{path} must list events, even when the list is empty")
        events: list[Any] = []
    else:
        events = expect["events"] if isinstance(expect["events"], list) else []
        if not isinstance(expect["events"], list):
            problems.append(f"{path}.events must be a list")
    if "bind" in expect:
        _bind(expect["bind"], events, f"{path}.bind", bound, problems)
    _events(events, nodes, bound, f"{path}.events", problems)
    if "deliveries" in expect:
        if not has_policy:
            problems.append(f"{path}.deliveries requires a policy")
        _deliveries(expect["deliveries"], bound, f"{path}.deliveries", problems)
    if "open" in expect:
        _open(expect["open"], nodes, bound, f"{path}.open", problems)
    if "queries" in expect:
        _queries(expect["queries"], nodes, views, f"{path}.queries", problems)


def _bind(
    value: object,
    events: list[Any],
    where: str,
    bound: set[str],
    problems: list[str],
) -> None:
    if not isinstance(value, dict) or not value:
        problems.append(f"{where} must be a non-empty mapping")
        return
    for name, spec in value.items():
        if not isinstance(name, str) or not _BIND.fullmatch(name):
            problems.append(f"{where}: bad bind name {name!r}")
            continue
        if name in bound:
            problems.append(f"{where}: {name} is already bound")
        if not isinstance(spec, dict) or set(spec) != {"opened"}:
            problems.append(f"{where}.{name} must be {{opened: anchor}}")
            continue
        anchor = spec["opened"]
        opened = [
            event
            for event in events
            if isinstance(event, dict)
            and set(event) == {"opened"}
            and isinstance(event["opened"], dict)
            and event["opened"].get("anchor") == anchor
        ]
        if len(opened) != 1:
            problems.append(f"{where}.{name} does not match one opened event")
        bound.add(name)


def _events(
    events: list[Any],
    nodes: dict[str, set[str]],
    bound: set[str],
    where: str,
    problems: list[str],
) -> None:
    for index, event in enumerate(events):
        path = f"{where}[{index}]"
        if not isinstance(event, dict) or len(event) != 1:
            problems.append(f"{path} must name one event kind")
            continue
        kind, body = next(iter(event.items()))
        if kind not in _EVENT_KINDS:
            problems.append(f"{path} has unknown kind {kind}")
            continue
        if kind == "probe":
            if body not in nodes:
                problems.append(f"{path} probes an unknown node")
            continue
        if not isinstance(body, dict):
            problems.append(f"{path}.{kind} must be a mapping")
            continue
        _event_body(kind, body, nodes, bound, path, problems)


def _event_body(
    kind: str,
    body: dict[str, Any],
    nodes: dict[str, set[str]],
    bound: set[str],
    where: str,
    problems: list[str],
) -> None:
    if kind == "opened":
        _reject_unknown(body, _EPISODE_FIELDS, where, problems)
        if body.get("anchor") not in nodes:
            problems.append(f"{where}.anchor is not a node")
        if "episode" in body:
            _ref(body["episode"], bound, f"{where}.episode", problems)
        _episode_details(body, nodes, bound, where, problems)
        return
    episode = body.get("episode")
    _ref(episode, bound, f"{where}.episode", problems)
    if kind == "resolved":
        if body.get("resolution") not in _RESOLUTION:
            problems.append(f"{where}.resolution is not a resolution")
        _reject_unknown(body, {"episode", "resolution"}, where, problems)
    else:
        _reject_unknown(body, _EPISODE_FIELDS, where, problems)
        if "anchor" in body and body["anchor"] not in nodes:
            problems.append(f"{where}.anchor is not a node")
        _episode_details(body, nodes, bound, where, problems)


def _episode_details(
    body: dict[str, Any],
    nodes: dict[str, set[str]],
    bound: set[str],
    where: str,
    problems: list[str],
) -> None:
    if "form" in body and body["form"] not in {"root", "group"}:
        problems.append(f"{where}.form is not an episode form")
    if "status" in body and body["status"] not in _STATUS:
        problems.append(f"{where}.status is not a status")
    if "importance" in body and body["importance"] not in _IMPORTANCE:
        problems.append(f"{where}.importance is not an importance")
    if "reasons" in body:
        reasons = body["reasons"]
        if not isinstance(reasons, list) or not all(
            isinstance(reason, str) for reason in reasons
        ):
            problems.append(f"{where}.reasons must be a list of strings")
    if "recorded" in body:
        recorded = body["recorded"]
        if not isinstance(recorded, list) or not all(
            isinstance(node, str) and node in nodes for node in recorded
        ):
            problems.append(f"{where}.recorded must be registered node ids")
    if "absorbed" in body:
        absorbed = body["absorbed"]
        if not isinstance(absorbed, list):
            problems.append(f"{where}.absorbed must be a list of episode references")
        else:
            for episode in absorbed:
                _ref(episode, bound, f"{where}.absorbed", problems)


def _deliveries(
    value: object,
    bound: set[str],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, list):
        problems.append(f"{where} must be a list")
        return
    for index, delivery in enumerate(value):
        path = f"{where}[{index}]"
        if not isinstance(delivery, dict):
            problems.append(f"{path} must be a mapping")
            continue
        _reject_unknown(
            delivery,
            {"loudness", "digest", "episode", "to", "resolution"},
            path,
            problems,
        )
        if "resolution" in delivery:
            if delivery["resolution"] not in _RESOLUTION:
                problems.append(f"{path}.resolution is not a resolution")
            if "loudness" in delivery or "digest" in delivery:
                problems.append(
                    f"{path}: a resolution delivery has no loudness or digest"
                )
            _string(delivery.get("to"), f"{path}.to", problems)
        elif delivery.get("loudness") not in _LOUDNESS:
            problems.append(f"{path}.loudness is not a loudness")
        _ref(delivery.get("episode"), bound, f"{path}.episode", problems)


def _open(
    value: object,
    nodes: dict[str, set[str]],
    bound: set[str],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, list):
        problems.append(f"{where} must be a list")
        return
    for index, episode in enumerate(value):
        path = f"{where}[{index}]"
        if not isinstance(episode, dict):
            problems.append(f"{path} must be a mapping")
            continue
        _reject_unknown(episode, _EPISODE_FIELDS, path, problems)
        _ref(episode.get("episode"), bound, f"{path}.episode", problems)
        if episode.get("anchor") not in nodes:
            problems.append(f"{path}.anchor is not a node")
        _episode_details(episode, nodes, bound, path, problems)


def _queries(
    value: object,
    nodes: dict[str, set[str]],
    views: dict[str, set[str]],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, dict) or not value:
        problems.append(f"{where} must be a non-empty mapping")
        return
    _reject_unknown(
        value, {"explain", "readiness", "impact", "coverage", "rollup"}, where, problems
    )
    if "explain" in value:
        _explain(value["explain"], nodes, f"{where}.explain", problems)
    if "readiness" in value:
        _readiness(value["readiness"], nodes, f"{where}.readiness", problems)
    if "impact" in value:
        _impact(value["impact"], nodes, f"{where}.impact", problems)
    if "coverage" in value:
        _coverage(value["coverage"], nodes, f"{where}.coverage", problems)
    if "rollup" in value:
        _rollup(value["rollup"], views, f"{where}.rollup", problems)


def _node_ids(
    value: object, nodes: dict[str, set[str]], where: str, problems: list[str]
) -> None:
    if not isinstance(value, list) or any(
        not isinstance(name, str) or name not in nodes for name in value
    ):
        problems.append(f"{where} must be registered node ids")


def _views(
    value: object, nodes: dict[str, set[str]], where: str, problems: list[str]
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return result
    for name, groups in value.items():
        _string(name, where, problems)
        if not isinstance(name, str) or not isinstance(groups, dict):
            problems.append(f"{where}.{name} must be a mapping of groups")
            continue
        result[name] = set()
        for group, members in groups.items():
            _string(group, f"{where}.{name}", problems)
            if isinstance(group, str):
                result[name].add(group)
            _node_ids(members, nodes, f"{where}.{name}.{group}", problems)
    return result


def _impact(
    value: object, nodes: dict[str, set[str]], where: str, problems: list[str]
) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    for name, spec in value.items():
        path = f"{where}.{name}"
        if name not in nodes:
            problems.append(f"{path} is not a node")
        if not isinstance(spec, dict):
            problems.append(f"{path} must be a mapping")
            continue
        _reject_unknown(spec, {"nodes", "importance"}, path, problems)
        if spec.get("importance") not in _IMPORTANCE:
            problems.append(f"{path}.importance is not an importance")
        members = spec.get("nodes")
        if not isinstance(members, list):
            problems.append(f"{path}.nodes must be a list")
            continue
        for member in members:
            if not isinstance(member, dict) or set(member) != {"node", "importance"}:
                problems.append(f"{path}.nodes must list node and importance")
                continue
            if member["node"] not in nodes or member["importance"] not in _IMPORTANCE:
                problems.append(f"{path}.nodes must name nodes with valid importance")


def _coverage(
    value: object, nodes: dict[str, set[str]], where: str, problems: list[str]
) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    fields = {"no_checks", "never_observed", "stale"}
    _require_keys(value, fields, where, problems)
    _reject_unknown(value, fields, where, problems)
    _node_ids(value.get("no_checks"), nodes, f"{where}.no_checks", problems)
    for field in ("never_observed", "stale"):
        refs = value.get(field)
        if not isinstance(refs, list):
            problems.append(f"{where}.{field} must be a list")
            continue
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"node", "check"}:
                problems.append(f"{where}.{field} must list node and check")
                continue
            node, check = ref["node"], ref["check"]
            if (
                not isinstance(node, str)
                or node not in nodes
                or not isinstance(check, str)
                or check not in nodes[node]
            ):
                problems.append(f"{where}.{field} must name registered checks")


def _rollup(
    value: object, views: dict[str, set[str]], where: str, problems: list[str]
) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    for name, groups in value.items():
        if name not in views or not isinstance(groups, dict):
            problems.append(f"{where}.{name} must name a view and map its groups")
            continue
        for group, spec in groups.items():
            path = f"{where}.{name}.{group}"
            if group not in views[name]:
                problems.append(f"{path} is not a group")
            if not isinstance(spec, dict):
                problems.append(f"{path} must be a mapping")
                continue
            _reject_unknown(spec, {"total", "counts"}, path, problems)
            _count(spec.get("total"), f"{path}.total", problems)
            counts = spec.get("counts")
            if not isinstance(counts, dict):
                problems.append(f"{path}.counts must be a mapping")
                continue
            _reject_unknown(counts, _STATUS, f"{path}.counts", problems)
            for status, row in counts.items():
                row_path = f"{path}.counts.{status}"
                if not isinstance(row, dict):
                    problems.append(f"{row_path} must be a mapping")
                    continue
                _reject_unknown(
                    row, {"clear", "own_episode", "recorded"}, row_path, problems
                )
                for key, count in row.items():
                    _count(count, f"{row_path}.{key}", problems)


def _count(value: object, where: str, problems: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        problems.append(f"{where} must be a non-negative integer")


def _explain(
    value: object,
    nodes: dict[str, set[str]],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping")
        return
    for node, spec in value.items():
        path = f"{where}.{node}"
        if node not in nodes:
            problems.append(f"{path} is not a node")
        if not isinstance(spec, dict) or set(spec) != {"names"}:
            problems.append(f"{path} must be {{names: [node ids]}}")
            continue
        names = spec["names"]
        if not isinstance(names, list) or any(name not in nodes for name in names):
            problems.append(f"{path}.names must be node ids")


def _readiness(
    value: object,
    nodes: dict[str, set[str]],
    where: str,
    problems: list[str],
) -> None:
    if not isinstance(value, dict) or not value:
        problems.append(f"{where} must be a non-empty mapping")
        return
    for node, spec in value.items():
        path = f"{where}.{node}"
        if node not in nodes:
            problems.append(f"{path} is not a node")
        if not isinstance(spec, dict):
            problems.append(f"{path} must be a mapping")
            continue
        _reject_unknown(spec, {"answer", "names", "by"}, path, problems)
        answer = spec.get("answer")
        if answer not in _READINESS:
            problems.append(f"{path}.answer is not a readiness answer")
        names = spec.get("names")
        if not isinstance(names, list) or any(name not in nodes for name in names):
            problems.append(f"{path}.names must be node ids")
        if "by" in spec and (answer != "blocked" or spec["by"] not in _BLOCKED_BY):
            problems.append(f"{path}.by must be own or dependency, for blocked only")


def _ref(value: object, bound: set[str], where: str, problems: list[str]) -> None:
    if not isinstance(value, str) or not value.startswith("$"):
        problems.append(f"{where} must be a $name bound earlier")
        return
    if value[1:] not in bound:
        problems.append(f"{where} uses unbound {value}")
