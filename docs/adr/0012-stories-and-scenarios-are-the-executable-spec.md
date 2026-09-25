# ADR 0012: Stories and scenarios are the executable spec

**Status:** Superseded by 0024
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The RFP says the library is done when its stories and scenarios pass. In prose, the scenarios hid real gaps: the detection race was invisible until someone asked about exact timing.

A fixture forces exact times and event shapes, and freezes the contract before any engine code exists. The engine is then written to the spec, instead of the spec drifting to match the engine.

## Decision

- **One fixture per story or scenario.** Each is a YAML file under `tests/fixtures/`. The file's `id` matches its name. The first three are the detection race (scenario 14), the restart (scenario 19), and the 03:58 battery through the policy (story 4).
- **A fixture states every duration it uses.** The runner fills nothing in.
- **`start` is when the engine is created,** and startup grace begins then. Each step has an `at` time in UTC, strictly increasing and not before `start`. The runner calls `advance(at)` and then applies the step. A step may ingest, restart, or only expect. It does not call `advance` at times that have no step.
- **Expectations are exact about which events happened and partial about their fields.** When `events` or `deliveries` is present, it is the complete list for that step. Each mapping must match on the keys it names. Unlisted labels, evidence, and other fields are not frozen. `open` is the complete set of episodes still open.
- **Episode ids are bound, not predicted.** `bind` names the UUIDv7 of the episode that opened on an anchor in that step. Later steps refer to it as `$name`. A fixture asserts the anchor, the onset, and that the id survives update and restore.
- **One runner** feeds every fixture to the engine and the policy. The schema test is in place first. The runner arrives with the engine.
- **Hypothesis property tests** check invariants over random graphs and timelines:
  - A node with a failed hard dependency does not open an episode.
  - An anchor has at most one open episode.
  - Nothing opens inside a quiet window.
  - Every episode resolves once all checks pass and the holds have elapsed.
  - `restore(snapshot())` loses nothing.

## Options considered

- **Plain pytest code per scenario.** Fine for engineers, harder to review as a spec, and it drifts.
- **Prose until the engine exists.** Defers every exact decision into code.
- **Snapshot tests with syrupy.** Good for checking outputs, not for writing inputs. They may complement fixtures later.

## Consequences

- PyYAML is a development dependency.
- Changing the fixture format means editing fixtures.
- A reviewer can read a fixture next to its story.
