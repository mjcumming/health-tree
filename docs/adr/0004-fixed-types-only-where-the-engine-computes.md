# ADR 0004: Fixed types only where the engine computes

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The natural first move is to enumerate everything: device types, failure types, warning types, error types, notification types. A catalog of faults in the core forces every system to translate itself into one vocabulary, and forces a core change for every new fault.

Some values must be ordered, or the engine cannot do its job. Kubernetes conditions show the balance: `status` is True, False, or Unknown, while `reason` is any CamelCase string.

## Decision

Exactly three closed, ordered enums:

| Type | Order | Used for |
| --- | --- | --- |
| `Status` | `pass` < `unknown` < `warn` < `fail` | Worst-of for `own` |
| `Importance` | `low` < `normal` < `high` < `critical` | Maximum over an episode's impact |
| `Loudness` | `record` < `digest` < `notify` < `urgent` | Quiet hours lower it; escalation raises it |

Everything else is an open string:

- node `kind`
- `reason`
- `category`
- labels
- annotations
- recipient and channel ids

`health_tree.conventions` publishes well-known names as constants with documentation. The library never branches on them. The engine produces two reasons itself: `stale` and `dependents_failing`.

"Warning" and "error" are statuses of one problem, not two type lists. `battery_low` is `warn` at 20 percent. The same sensor going quiet is `stale`.

Adding a closed type needs a new ADR.

## Options considered

- **Rich enums for kinds and reasons.** Every new device or fault edits the core and forces a release of the integration.
- **Everything open, status included.** The engine could not compute worst-of or importance, and each adapter would invent its own order.

## Consequences

- New faults and device types are catalog data.
- Types do not catch a typo in an open string. The catalog validates its own vocabulary, and conventions give shared names.
- Policy rules match strings.
