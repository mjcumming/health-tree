# ADR 0028: Engine and policy semantics the RFP left open

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The first engine and policy pass every fixture. Writing them forced decisions that the RFP, ADRs 0021 to 0027, and the fixtures do not pin down. Each one below is in the code and covered by a fixture, a unit test, or a Hypothesis property. They are recorded here so that each can be accepted or changed on purpose.

## Decision

**Time and checks**

- A worsening's onset, and its reason's `since`, is when the worse status was first observed, not when `raise_hold` ended. Absorption (rule 16) compares these onsets. Scenario 15 depends on this.
- An expired `ttl` makes a check `unknown` at once, whether its last observation passed or failed. An expired `fail` therefore stops muting its dependents (rules 4 and 8 together). A catalog that wants a failed host to stay failed gives its check a `ttl` longer than its probe interval.
- "A problem is known" (ADR 0026) starts when a check becomes `warn` or `fail`, or goes stale. It ends when the check becomes `pass`. Only an effective `pass` resets it.
- An explicit `unknown` observation is a worsening from `pass`, so it waits out `raise_hold`. An expiry does not.

**Graph**

- An edge may name a node that is not registered yet. It is ignored until that node arrives, and cycle detection applies when it does. Removing a node leaves the edges to it dangling, and the dependents rejoin (rule 23).
- Rule 19's rejoin happens when a node stops having a direct dependency whose `own` is `fail`. That includes nodes that are not failing themselves, whose `unknown` checks also restart their stale clocks.

**Episodes**

- `recorded` is the current set: coalesced members, plus failing nodes muted by the anchor or by a member. A recorded node that recovers leaves it, and the episode is updated.
- Coalesced members sit on an episode only while its anchor's `own` is not `fail`. When the anchor fails and opens its own episode, it absorbs the group, and the members are then recorded as muted nodes. If the anchor only warns, its new root episode takes over the members and `dependents_failing`.
- When a root episode's anchor recovers while nodes it recorded as muted still fail, it stays open and holds them through their rejoin grace. Held nodes count toward its status, reasons, and `recorded`. At the end of the grace, `coalesce_count` or more still failing become members. Fewer are released, the episode clears, and each opens its own episode. Michael chose this over an immediate all-clear followed by a new alert (scenario 4).
- A call returns its openings first, then its updates, then its resolutions, and last any probes. Within each kind the order is dependencies first, then the order of registration. An episode opened and resolved within one call is never emitted.
- The engine refuses an id from `new_id` that is already open, rather than merging two episodes.

**Queries**

- `explain` lists the node's own reasons (`warn`, `fail`, or stale), then every watched dependency whose `own` is not `pass`, roots first. Unwatched nodes carry no evidence and are left out.
- `readiness` names only causes, roots first: nodes that are not `ready` and have no direct dependency whose `own` is `fail`. A dead Eero node does not prove the speakers behind it are dead, so they are not named. `blocked_by` is `own` only when a requested function is itself one of the causes. Michael chose this (scenarios 34 and 49).

**Policy**

- A reason that matches no rule contributes nothing. An episode none of whose reasons match is `record`.
- An update that does not raise loudness goes as a silent `Notification`, at the current loudness, to each recipient who already has the episode. It goes nowhere when the loudness is now `record`.
- Lowering to `digest` puts the episode back in its digest, and lowering drops any pending `notify`.
- Escalation raises one level only when the higher level has somewhere to go: a digest for `digest`, or recipients for `notify` and `urgent`. The recipients of a digest rule are its digest's recipient.
- A digest that was missed because `advance` was not called at its time goes out once, at the next `advance`.
- A reminder repeats a sent `notify` or `urgent` message. For `digest`, it puts the episode back in its next digest.
- An `EpisodeUpdated` for an episode the policy has not seen is handled as an opening.

## Options considered

- **Onset when the hold ends.** Simpler, but then a parent confirmed after its `raise_hold` could never absorb a child that opened in the meantime. The detection race of scenario 15 would be lost.
- **Keep an expired `fail` failing.** Rule 4 says an expired check is `unknown`. Keeping it `fail` would make the engine invent evidence.
- **A `recorded` set that only grows.** It is closer to a history, but then an episode could never report that a muted node came back.
- **Resolve the recovered anchor's episode at once.** It follows rule 15 as first written, but it sends an all-clear that is false while devices still fail, and then a new alert a minute later.
- **Name every node that is not ready.** It is complete, but it names hardware that may be fine as if it had failed. `explain` already shows the chain.

## Consequences

- These choices are in the code, and changing one means changing its fixture or test.
- Rule 15 and scenarios 4, 34, and 49 are restated in the RFP to match.
