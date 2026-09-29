"""Reproducible ordered-burst benchmark: python -m tests.runtime_profile.

Wall-clock measurements belong in this opt-in harness, never in the engine or
pass/fail timing assertions. Every run checks event history and restart identity.
"""

import argparse
import cProfile
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from health_tree.engine import Engine
from health_tree.types import EpisodeOpened, EpisodeResolved, Status
from tests.engine_helpers import SETTINGS, T0, at, check, counting_ids, node, obs


def measure(size: int, cycles: int) -> dict[str, object]:
    """Exercise independent failures and recoveries under ten passing owners."""
    settings = replace(SETTINGS, coalesce_count=size + 1)
    engine = Engine(settings, new_id=counting_ids())
    nodes = [node(f"owner-{i}", checks=[check(ttl=None)]) for i in range(10)]
    nodes.extend(
        node(
            f"device-{i}",
            f"owner-{i % 10}",
            checks=[check(clear_hold=0, ttl=None)],
        )
        for i in range(size)
    )
    started = perf_counter()
    engine.register_many(nodes, T0)
    engine.ingest_many([obs(n.node_id, Status.PASS, T0) for n in nodes], T0)
    setup = perf_counter() - started
    history: list[tuple[str, str, str]] = []
    bursts: list[dict[str, object]] = []
    for cycle in range(cycles):
        for status in (Status.FAIL, Status.PASS):
            calls: list[float] = []
            started = perf_counter()
            for index in range(60):
                now = at(1 + cycle * 120 + (60 if status is Status.PASS else 0) + index)
                before = perf_counter()
                events = engine.ingest(obs(f"device-{index}", status, now), now)
                calls.append(perf_counter() - before)
                assert len(events) == 1
                event = events[0]
                if status is Status.FAIL:
                    assert isinstance(event, EpisodeOpened)
                else:
                    assert isinstance(event, EpisodeResolved)
                    assert event.resolution == "cleared"
                history.append(
                    (
                        type(event).__name__,
                        event.episode.anchor,
                        event.episode.episode_id,
                    )
                )
            bursts.append(
                {
                    "status": status.value,
                    "seconds": perf_counter() - started,
                    "max_call_seconds": max(calls),
                }
            )
    now = at(cycles * 120 + 1)
    engine.ingest_many([obs(f"device-{i}", Status.FAIL, now) for i in range(2)], now)
    saved = engine.snapshot()
    restored = Engine(settings, new_id=counting_ids())
    restored.register_many(nodes, now)
    assert restored.restore(saved, now) == []
    assert restored.snapshot()["episodes"] == saved["episodes"]
    return {
        "nodes": len(nodes),
        "cycles": cycles,
        "setup_seconds": setup,
        "bursts": bursts,
        "events": len(history),
        "history_sha256": hashlib.sha256(json.dumps(history).encode()).hexdigest(),
        "restart_identity_preserved": True,
    }


def main() -> None:
    """Write measurements and optional profiling data outside timed sections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[300, 6000])
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    if args.cycles < 1 or min(args.sizes) < 60:
        parser.error("cycles must be positive and sizes at least 60")
    profiler = cProfile.Profile() if args.profile else None
    if profiler:
        profiler.enable()
    results = [measure(size, args.cycles) for size in args.sizes]
    if profiler:
        profiler.disable()
        args.profile.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(args.profile)
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
