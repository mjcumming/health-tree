# Ordered observation runtime

Measured 2026-09-29 with Python 3.14.7 on WSL2. The baseline is health-tree
`2035c1c` (0.5.0); the candidate is that checkout with the local graph-index
changes. These are synthetic engine measurements, not Home Assistant or target
appliance guarantees.

## Workload and results

Ten passing owners have either 300 or 6,000 checked dependents. Each of three
cycles applies 60 independent failures followed by 60 independent recoveries,
one observation per call with explicit, increasing UTC timestamps. Holds are
zero, expiry is disabled, and the grouping threshold exceeds the graph size.
Setup initializes every check to passing before timing bursts. No observations
are collapsed into a later state or combined across calls.

| Measurement | 310 nodes, baseline | 310 nodes, candidate | 6,010 nodes, baseline | 6,010 nodes, candidate |
| --- | ---: | ---: | ---: | ---: |
| Mean 60-transition burst | 164 ms | 40 ms | 3,041 ms | 557 ms |
| Longest individual ingestion | 5.30 ms | 1.21 ms | 93.35 ms | 15.70 ms |
| Opening/clearing events | 360 | 360 | 360 | 360 |

The event-kind/anchor/id sequence hashes match before and after. Two later open
episodes retain their complete persisted episode records across restore. The
full engine suite also passes, including atomic rewiring, missing targets,
shared dependencies, group dissolution, deadlines and restore scenarios.
Validation: 376 tests, 99.77% statement and 98.11% branch coverage, all repository
hooks, strict typing, wheel/sdist builds and strict package metadata checks.

A separate instrumented run attributed 11.55 of 16.84 seconds to finding
dependents. The candidate indexes registered forward/reverse edges and ordering
when a graph changes, traverses only reachable dependents, reuses the affecting
check lists within one frame, and scans only muted nodes when recording an
episode's explained symptoms. It does not cache every transitive closure, which
would risk quadratic memory use on long chains. Rejected graph changes never
replace the indexes. Public behavior and snapshot schema are unchanged, so no
new RFP rule or architecture decision is introduced.

## Reproduce

```bash
uv sync --locked
uv run python -m tests.runtime_profile --output build/runtime-profile/result.json
uv run python -m tests.runtime_profile --sizes 6000 --cycles 1 \
  --output build/runtime-profile/instrumented.json \
  --profile build/runtime-profile/engine.prof
```

The harness uses only public engine operations. Timers, profiling and file writes
live in the opt-in test harness, outside `src/`. Timings are reports, not
machine-dependent pass/fail assertions. The local evidence files are
`build/runtime-profile/before.json`, `after.json`, and `before.prof`.

The library still evaluates every check on each call, including time-dependent
holds and expiry. These changes do not establish a hard execution-time limit.
Homeostatic owns event-loop yielding, catalog transport and persistence; its
[runtime assessment](https://github.com/mjcumming/homeostatic/blob/main/docs/testing/runtime-scaling.md)
records the separate adapter measurements and remaining qualification limits.
