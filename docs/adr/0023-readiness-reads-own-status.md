# ADR 0023: Readiness reads observed status, and stale is not a failure

**Status:** Superseded by 0025
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

RFP 0.2 answers `readiness` with `ready`, `degraded`, `blocked`, or `unknown`, and maps a stale dependency to `blocked`. Three problems remain:

- **Stale is not a failure.** A check that has gone quiet past `unknown_hold` tells us nothing new about the equipment. Calling it `blocked` claims a failure nobody observed. Missing evidence should not become reassurance, and it should not become an accusation either.
- **Nodes with no checks.** Rule 2 gives them `own == unknown`. Readiness "looks through" them, but the RFP does not say that their own `unknown` is ignored. Read literally, every function without checks would answer `unknown`.
- **What readiness reads.** Story 3 says backyard music is `blocked` "if the episode is still open." Episodes are shaped by muting, absorption, quiet windows, and holds. Readiness is a question about the equipment, not about notifications.

## Decision

- `readiness` reads `own` status only. Episodes, muting, quiet windows, and shelving do not change the answer. Checks with `affects_own` false do not count.
- For each function it considers the function's own checks and every node the function depends on, directly or not.
  - `ready`: all are `pass`.
  - `degraded`: one is `warn`.
  - `blocked`: one is `fail`.
  - `unknown`: one is `unknown`, whether or not it is stale. A stale node is named with reason `stale`.
- A node with no checks is looked through to what it depends on, and its own `unknown` does not count. When the function has no checks and nothing under it does, the answer is `unknown`, naming the unwatched nodes.
- The worst answer wins, in the order `blocked`, `degraded`, `unknown`, `ready`. The responsible nodes are named, roots first. A blocked function says whether its own checks fail or a dependency does.

## Options considered

- **Keep `stale` as `blocked`.** Simple, and often right for a dead battery, but it asserts what was not observed. It would also make `readiness` disagree with `explain`, which names the stale node as quiet, not failed.
- **A fifth answer, `unverified`.** Adds a closed value (ADR 0004) with no behavior different from `unknown`.
- **Read episodes.** Readiness would change when a quiet window opens or a failure is absorbed, although nothing about the equipment changed.

## Consequences

- An automation that falls back, such as from camera occupancy to a PIR sensor, should fall back on any answer but `ready`. The integration documents that.
- Scenario 36 is restated. Scenarios 49 to 51 cover the new rules.
- A stale dependency still opens its `stale` episode and pages under the policy. Only the readiness answer changes.
