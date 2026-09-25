# ADR 0020: The policy matches each reason; the loudest wins

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

Refines ADR 0010. Rules stay ordered, and the first match still wins, but per reason instead of per episode.

## Context

RFP 0.2 merges an episode's labels from its anchor and its non-pass checks, and then matches policy rules once per episode. Labels are a mapping, so two checks with different categories collide on the `category` key. Which one survives decides whether the episode pages or waits for the digest.

ADR 0019 removes most mixed episodes by splitting nodes. Some remain by design. A lock can report `battery_low` (`maintenance`, `warn`) and `command_failed` (`operation`, `fail`) on the same capability. The example policy puts the maintenance rule first so a dead battery never pages at night. Matched per episode, that rule would also swallow the command failure.

## Decision

- Each reason keeps its own check's labels and annotations. An episode's `labels` and `annotations` are its anchor node's only. Nothing is merged across checks.
- Rules are matched once for each reason of an episode, in order, and the first match wins for that reason. A reason is matched on:
  - its own status, reason, `due_at`, and labels (the check's labels laid over the anchor node's)
  - the episode's importance and age
- The episode takes the loudest result over its reasons. Recipients, digest, reminder, and escalation come from the rule that produced it. On a tie, the rule that appears first wins.
- A reason that clears can only lower loudness, and lowering never makes noise.

## Options considered

- **Merge labels, with a fixed order of categories.** Puts a ranking of open strings in the library, which ADR 0004 rules out.
- **Match the episode on its worst reason only.** A `warn` with a near `due_at` can matter more than an old `fail` of low importance. Status alone is the wrong key.
- **Leave it to rule order.** Every configuration would have to anticipate every combination, and the example policy's own ordering already fails.

## Consequences

- A policy's rule order still reads the same way, one reason at a time.
- `policy.handle` does a little more work per event: one pass over the rules for each reason.
- Group episodes are matched on their members' reasons, plus `dependents_failing`, which carries the anchor's labels.
