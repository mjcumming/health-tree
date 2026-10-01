# Ordered observation runtime

Measured 2026-09-29 with Python 3.14.7 on WSL2. The baseline is health-tree `2035c1c` (0.5.0). The candidate is the same checkout with the local graph-index changes. These are synthetic engine measurements. They don't guarantee anything about Home Assistant or the appliance it runs on.

## Workload and results

Ten passing owner nodes have either 300 or 6,000 checked dependents between them. Each of three cycles applies 60 independent failures followed by 60 independent recoveries, one observation per call, with explicit, increasing UTC timestamps. Holds are zero, expiry is off, and the grouping threshold is larger than the graph. Setup sets every check to passing before any burst is timed. No observation is folded into a later state or combined with another call.

| Measurement | 310 nodes, baseline | 310 nodes, candidate | 6,010 nodes, baseline | 6,010 nodes, candidate |
| --- | ---: | ---: | ---: | ---: |
| Mean 60-transition burst | 164 ms | 40 ms | 3,041 ms | 557 ms |
| Longest individual ingestion | 5.30 ms | 1.21 ms | 93.35 ms | 15.70 ms |
| Opening/clearing events | 360 | 360 | 360 | 360 |

The hashes of the event sequence (kind, anchor and id) match before and after. Two episodes opened afterward keep their complete persisted records across restore. The full engine suite also passes, including atomic rewiring, missing targets, shared dependencies, group dissolution, deadlines and restore scenarios. Validation: 376 tests, 99.77% statement and 98.11% branch coverage, all repository hooks, strict typing, wheel/sdist builds and strict package metadata checks.

A separate instrumented run spent 11.55 of 16.84 seconds finding dependents. When the graph changes, the candidate indexes registered forward and reverse edges and their ordering. It then traverses only reachable dependents, reuses the affecting check lists within one frame, and scans only muted nodes when it records an episode's explained symptoms. It doesn't cache every transitive closure, because that could use quadratic memory on long chains. A rejected graph change never replaces the indexes. Public behavior and the snapshot schema are unchanged, so this needs no new RFP rule or architecture decision.

## Reproduce

```bash
uv sync --locked
uv run python -m tests.runtime_profile --output build/runtime-profile/result.json
uv run python -m tests.runtime_profile --sizes 6000 --cycles 1 \
  --output build/runtime-profile/instrumented.json \
  --profile build/runtime-profile/engine.prof
```

The harness uses only public engine operations. Timers, profiling and file writes live in the opt-in test harness, outside `src/`. The timings are reports. They aren't pass/fail assertions, because they depend on the machine. The local evidence files are `build/runtime-profile/before.json`, `after.json`, and `before.prof`.

The library still evaluates every check on each call, including time-dependent holds and expiry. These changes don't set a hard limit on execution time. Homeostatic owns event-loop yielding, catalog transport and persistence, and its [known limitations](https://github.com/mjcumming/homeostatic/blob/main/docs/troubleshooting.md#known-limitations) cover what large installs can expect.
