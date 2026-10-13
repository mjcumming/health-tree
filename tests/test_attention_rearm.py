"""Explicit renewed awareness retains route identity and episode pauses."""

from datetime import timedelta

import pytest

from health_tree.types import EpisodeOpened
from tests.engine_helpers import T0, at
from tests.test_attention_routes import IMMEDIATE, REPORT
from tests.test_policy import CONTEXT, _episode, _policy


def test_rearm_retains_shared_identity_and_reports_after_restart() -> None:
    """A new round clears acknowledgment across routes without ending the issue."""
    policy = _policy(IMMEDIATE, REPORT)
    event = EpisodeOpened(episode=_episode())
    policy.handle(event, T0, CONTEXT)
    policy.acknowledge(event.episode.episode_id, at(60), actor_id="owner")
    restored = _policy(IMMEDIATE, REPORT)
    restored.restore(policy.snapshot(), at(120))
    deliveries = restored.rearm(event.episode.episode_id, at(180), CONTEXT)
    assert restored.acknowledgment(event.episode.episode_id) is None
    assert [item.route for item in deliveries] == ["phone"]
    assert restored.rearm(event.episode.episode_id, at(240), CONTEXT) == []
    assert len(restored.reports(at(240))) == 1


def test_rearm_keeps_shelf_and_unknown_ids_fail() -> None:
    """A new awareness round cannot bypass a delivery pause."""
    policy = _policy(IMMEDIATE, REPORT)
    event = EpisodeOpened(episode=_episode())
    policy.handle(event, T0, CONTEXT)
    policy.acknowledge(event.episode.episode_id, at(60))
    policy.shelve(event.episode.episode_id, T0 + timedelta(hours=1), at(120))
    assert policy.rearm(event.episode.episode_id, at(180), CONTEXT) == []
    assert policy.acknowledgment(event.episode.episode_id) is None
    with pytest.raises(KeyError):
        policy.rearm("missing", at(240), CONTEXT)
