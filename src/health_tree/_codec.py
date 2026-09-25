"""JSON-compatible encodings of records, for snapshots (rule 24, ADR 0011)."""

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import cast

from health_tree.types import (
    Episode,
    EpisodeForm,
    Finding,
    Importance,
    JSONValue,
    Observation,
    Status,
)

type JSONObject = dict[str, JSONValue]


def strings_list(values: Iterable[str]) -> list[JSONValue]:
    """Encode strings as a JSON list, sorted for a stable snapshot."""
    return [str(value) for value in sorted(values)]


def time_to_json(value: datetime | None) -> str | None:
    """Encode a UTC time, or `None`."""
    return None if value is None else value.isoformat()


def time_from_json(value: JSONValue) -> datetime | None:
    """Decode a time encoded by `time_to_json`."""
    return None if value is None else datetime.fromisoformat(str(value))


def required_time(value: JSONValue) -> datetime:
    """Decode a time that must be present."""
    decoded = time_from_json(value)
    if decoded is None:
        raise ValueError("snapshot is missing a required time")
    return decoded


def strings_to_json(value: Mapping[str, str]) -> JSONObject:
    """Encode a string mapping."""
    return dict(value)


def strings_from_json(value: JSONValue) -> dict[str, str]:
    """Decode a string mapping."""
    return {key: str(item) for key, item in _object(value).items()}


def finding_to_json(finding: Finding) -> JSONObject:
    """Encode a finding."""
    return {
        "node_id": finding.node_id,
        "check_id": finding.check_id,
        "status": finding.status.value,
        "reason": finding.reason,
        "since": time_to_json(finding.since),
        "message": finding.message,
        "due_at": time_to_json(finding.due_at),
        "labels": strings_to_json(finding.labels),
        "annotations": strings_to_json(finding.annotations),
    }


def finding_from_json(value: JSONValue) -> Finding:
    """Decode a finding."""
    data = _object(value)
    check_id = data["check_id"]
    message = data["message"]
    return Finding(
        node_id=str(data["node_id"]),
        check_id=None if check_id is None else str(check_id),
        status=Status(data["status"]),
        reason=str(data["reason"]),
        since=required_time(data["since"]),
        message=None if message is None else str(message),
        due_at=time_from_json(data["due_at"]),
        labels=strings_from_json(data["labels"]),
        annotations=strings_from_json(data["annotations"]),
    )


def episode_to_json(episode: Episode) -> JSONObject:
    """Encode an episode."""
    return {
        "episode_id": episode.episode_id,
        "form": episode.form,
        "anchor": episode.anchor,
        "status": episode.status.value,
        "reasons": [finding_to_json(finding) for finding in episode.reasons],
        "recorded": strings_list(episode.recorded),
        "impact": strings_list(episode.impact),
        "importance": episode.importance.value,
        "opened_at": time_to_json(episode.opened_at),
        "updated_at": time_to_json(episode.updated_at),
        "due_at": time_to_json(episode.due_at),
        "absorbed": strings_list(episode.absorbed),
        "labels": strings_to_json(episode.labels),
        "annotations": strings_to_json(episode.annotations),
    }


def episode_from_json(value: JSONValue) -> Episode:
    """Decode an episode."""
    data = _object(value)
    return Episode(
        episode_id=str(data["episode_id"]),
        form=cast(EpisodeForm, data["form"]),
        anchor=str(data["anchor"]),
        status=Status(data["status"]),
        reasons=tuple(finding_from_json(item) for item in _list(data["reasons"])),
        recorded=frozenset(str(item) for item in _list(data["recorded"])),
        impact=frozenset(str(item) for item in _list(data["impact"])),
        importance=Importance(data["importance"]),
        opened_at=required_time(data["opened_at"]),
        updated_at=required_time(data["updated_at"]),
        due_at=time_from_json(data["due_at"]),
        absorbed=frozenset(str(item) for item in _list(data["absorbed"])),
        labels=strings_from_json(data["labels"]),
        annotations=strings_from_json(data["annotations"]),
    )


def observation_to_json(observation: Observation) -> JSONObject:
    """Encode an observation."""
    return {
        "node_id": observation.node_id,
        "check_id": observation.check_id,
        "status": observation.status.value,
        "reason": observation.reason,
        "observed_at": time_to_json(observation.observed_at),
        "message": observation.message,
        "evidence": dict(observation.evidence),
        "due_at": time_to_json(observation.due_at),
    }


def observation_from_json(value: JSONValue) -> Observation:
    """Decode an observation."""
    data = _object(value)
    message = data["message"]
    return Observation(
        node_id=str(data["node_id"]),
        check_id=str(data["check_id"]),
        status=Status(data["status"]),
        reason=str(data["reason"]),
        observed_at=required_time(data["observed_at"]),
        message=None if message is None else str(message),
        evidence=_object(data["evidence"]),
        due_at=time_from_json(data["due_at"]),
    )


def _object(value: JSONValue) -> JSONObject:
    if not isinstance(value, dict):
        raise TypeError("snapshot expected an object")
    return value


def _list(value: JSONValue) -> list[JSONValue]:
    if not isinstance(value, list):
        raise TypeError("snapshot expected a list")
    return value


def as_object(value: JSONValue) -> JSONObject:
    """Narrow a snapshot value to an object."""
    return _object(value)


def as_list(value: JSONValue) -> list[JSONValue]:
    """Narrow a snapshot value to a list."""
    return _list(value)
