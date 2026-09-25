# ADR 0010: The attention policy is a pure library module; its content is configuration

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Who hears what, how loudly, and when is the part the owner feels most:

- no battery messages at 4 AM
- the garage failure at once
- chores in a digest

The mechanism is generic: matching, schedules, escalation. The content is specific to one house.

ISA-18.2 separates three kinds of suppression:

- suppressed by design, which is the engine's inhibition here
- out of service, which is a quiet window
- shelved, which is an operator action

Alertmanager separates routing labels from human annotations, and waits briefly before a first notification.

## Decision

- `health_tree.policy` is part of this library.
- It is pure, like the engine. Events, `now`, and context go in. Deliveries and `next_deadline()` come out.
- Configuration is data with a fixed shape:
  - Recipients, with channels, quiet hours, and dynamic recipients such as whoever is home.
  - Digests.
  - Rules in order, first match wins. A rule matches on status, importance, reason, category, labels, age, and `due_within`. It sets loudness, recipients, digest, reminders, and escalation.
- The loudness ladder is closed (ADR 0004).
- A new `notify` delivery waits `batch` so absorption and coalescing land first.
- Rules are matched again when an episode changes, and when its age or `due_at` crosses a threshold that a rule names. Those times feed `next_deadline()`.
- Shelving lives here. Quiet windows live in the engine.
- Channels are opaque ids that the adapter maps to Home Assistant notify services.

## Options considered

- **The policy in the Home Assistant adapter.** Untestable without Home Assistant, and rebuilt for any other consumer.
- **Alertmanager's routing tree.** Proven, but it matches labels only, has no importance, deadlines, or age, and needs a server.
- **Home Assistant automations and blueprints.** No awareness of episodes, and scattered.

## Consequences

- Preferences change by configuration alone, which is an acceptance criterion in the RFP.
- The integration needs a configuration surface: YAML first, a UI later.
- The adapter supplies presence as context.
