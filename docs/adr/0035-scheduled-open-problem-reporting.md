# ADR 0035: Schedule open-problem reports and match affected nodes

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Michael Cumming

## Context

Consumers need daily and weekly reports, explicit device reporting preferences,
and an honest preview of the next report. Notification scheduling must remain
in the pure policy rather than being independently implemented by each adapter.

## Decision

Extend `Digest` with `weekdays` (Monday 0 through Sunday 6, all by default) and
`repeat_open` (false by default). A repeating digest includes still-open eligible
episodes at each scheduled occurrence. It never emits an empty or resolved entry.
Use a digest rule's explicit recipients, falling back to the digest's recipient.
The output's `previously_reported` flag distinguishes each recipient's ongoing
problem from a first report. Existing digest behavior remains the default.

Expose `Policy.reports(now)` as a read-only forecast: schedule, next occurrence,
eligible episode ids, and recipient ids. Shelving and acknowledgment apply.
The forecast is provisional and does not reserve or send a message.

Extend `Match` with optional `nodes`, `checks`, and `excluded_checks`. Nodes match
the union of anchor, recorded nodes and impact. Checks match finding check ids;
exclusions let an adapter compile condition exceptions without masking them with
a device default. Strings remain opaque; the core recognizes no device kinds or
reporting profile names. Ordered rule precedence and loudest-reason selection
remain unchanged. Adapters must explicitly order conflicts.

Use local wall-clock schedule dates. On a nonexistent clock time, use its forward
UTC round trip; on a repeated clock time use the first occurrence, once per date.
After an overdue occurrence send at most one current report and move into the
future. Preserve next occurrences through restart.

## Options considered

- Adapter timers would duplicate lifecycle and scheduling state.
- Repeated reminders cannot express selected weekdays or separate report times.
- New urgency enums would mix household choices with generic attention mechanics.

## Consequences

Old configuration and snapshots keep their behavior. Applications can build a
small reporting interface using these generic fields without modifying evidence,
importance, or the engine's episode lifecycle.
