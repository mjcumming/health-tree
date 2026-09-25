# ADR 0021: One anchor, one episode; coalesced members decide recovery

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Refines the coalescing and recovery rules of ADR 0007.

## Context

RFP 0.2 anchors a group episode on the shared dependency of the nodes it coalesces, and resolves every episode when its anchor's `own` stays `pass` through `clear_hold`. The anchor of a group is usually not failing, so its recovery says nothing about the group:

- Scenario 4. The controller has already recovered when the group opens. By rule 15 the group resolves at once, while three devices still fail.
- Scenario 24. The parent stays `warn`. The group never resolves, even after every member recovers.

Story 9 has a second problem. The Insteon controller is `warn`, so by rule 12 it has its own episode. Coalescing then opens a group episode on the same controller: two episodes on one anchor, which breaks the Hypothesis invariant in ADR 0012.

Three more cases have no rule:

- a sibling that fails after the group opened
- a group whose anchor then fails outright
- a group that shrinks to a few members that have their own, unrelated faults

## Decision

- **One anchor, one episode.** If the shared dependency already has an open episode, coalesced nodes are recorded on it, and `dependents_failing` is added to its reasons. A `group` episode opens only when the anchor has none.
- **Members join while it is open.** A direct dependent of the anchor that fails while the episode holds coalesced members joins it, and the episode is updated. It does not open its own.
- **A member that recovers leaves.** Its `own` has stayed `pass` through `clear_hold`, or it was removed. The episode is updated.
- **Members decide recovery.** Coalescing holds while at least `coalesce_count` members still fail. When fewer remain:
  - `dependents_failing` is dropped.
  - A `group` episode resolves as `cleared`. A `root` episode continues on its anchor's own status.
  - The remaining members are treated as after a rejoin (rule 19). They wait out `rejoin_grace`, and then those still failing open their own episodes.
- **A failing anchor absorbs its group.** When a group's anchor opens its own episode, the group resolves as `absorbed`, and its members are recorded on the anchor's episode.
- An episode's `status` is the worst over its anchor's `own` and its members' `own`.

## Options considered

- **Resolve a group when its anchor passes.** Wrong in both directions, as scenarios 4 and 24 show.
- **Resolve a group only when every member passes.** One device with an unrelated fault would hold the controller's group open indefinitely, blaming the controller.
- **Allow a root episode and a group episode on one anchor.** Two messages about one controller, and the invariant has to be weakened.
- **Close the group to new members once it opens.** The thirty-first Insteon device would open its own episode a minute later.

## Consequences

- Scenario 24 is restated. Scenarios 45 to 47 and 52 cover the new rules.
- A few members still failing after most recover become their own episodes, one `rejoin_grace` later. That is a new message, and it is the true one: those devices are broken on their own.
- The invariant "an anchor has at most one open episode" holds again.
