# ADR 0031: Situation alerts are in scope, and the library never detects them

**Status:** Accepted
**Date:** 2026-09-25
**Deciders:** Michael Cumming

## Context

RFP 0.5 left situation alerts out of the first version: the garage open at night, a water leak, a door unlocked while away. The house has not failed. The world is in a state the owner does not like.

The owner needs them anyway, and everything after detection is what this library already does:

- one problem, one episode, updated in place
- importance, quiet hours, digests, reminders, escalation, and shelving
- ids and state that survive a restart
- an answer to "who heard, and why"

Leaving them out means two alert systems in one house, each with its own quiet hours and its own idea of who hears what. The UI worksheet (`docs/ideas/homeostatic-ui.md`, sections 14 and 16) records the requirement.

Detection is a different job. "Open for three hours, and it is between 22:00 and 07:00" needs states, durations, schedules, presence, and thresholds. Home Assistant automations, templates, and binary sensors already do that, and the owner already writes them. A condition language in the library would copy Home Assistant, badly, and would bring clock and schedule rules into a core that reads no clock (ADR 0003).

## Decision

- Situation alerts are in scope. They share the episode lifecycle and the attention policy with failures.
- The library never decides whether a situation holds. A reporter outside the library evaluates the condition and sends an ordinary observation on the situation's check:

  | Status | Meaning |
  | --- | --- |
  | `fail` | The situation holds |
  | `pass` | It has ended |
  | `unknown` | The reporter cannot tell |
  | `warn` | Optional: a lesser form of the same situation, if the reporter has one |

- The reporter owns the condition's timing: its durations, schedules, and hysteresis. The check's `raise_hold` is zero, and so is its `clear_hold` unless the reporter has no hysteresis of its own. Durations stay required (ADR 0018), so the zero is written, never assumed. The zero stops the library from adding a second delay on top of the rule's.
- `unknown` never clears a situation. Only `pass` does (rules 2 and 15, unchanged). A situation that stays `unknown` past its `unknown_hold` gains the reason `stale`, as any check does.
- In the Home Assistant integration, the reporter is an entity the owner builds: a template, a binary sensor, or a helper an automation keeps up to date. `on` is `fail`, `off` is `pass`, and `unavailable` or `unknown` is `unknown`. The integration ships no condition builder.
- The reporting entity must turn `unavailable` when its source is unavailable. If it turns `off` instead, a dead sensor reads as a clear. The integration documents this and warns about a bound template that declares no availability.
- This is not a life-safety system. Smoke, carbon monoxide, and flood alarms keep their own alarm path. Homeostatic is an additional way to hear about them, never the only one.

## Options considered

- **Keep situations out of scope.** The owner keeps two systems with different quiet hours, and the one without episodes pages again on every flap.
- **A condition language in the library.** Copies Home Assistant, needs clock and schedule semantics in the core, and still cannot see presence or other context without new inputs.
- **A condition builder in the integration**, the simple form in the worksheet's section 14. Needs its own restart continuity, schedule edges, and hysteresis for each pattern, which is a second rule engine next to Home Assistant's. It was dropped on 2026-09-25.
- **Reports from automations through a service call, with no bound entity.** Needs leases, ordering, deduplication, and replay after a restart. A stateful entity can simply be read again.

## Consequences

- RFP section 2 moves situation alerts from out of scope to in scope, and adds "evaluating conditions" to out of scope. Story 10 and scenarios 61 to 64 describe the behavior.
- The engine and the policy do not change. ADR 0032 says how a situation is shaped so that existing rules give the right answers.
- The owner writes the condition once, in Home Assistant, where it can also drive other automations.
- A restart inside the reporter's own delay can restart that delay. Home Assistant resets `for` and `delay_on` when it restarts. That limit belongs to the rule, and the integration must not claim continuity it did not observe.
- An existing Alert or Alert2 notification for the same condition would duplicate these messages. Migrating it is the owner's choice. The integration never disables another integration's notifications.
