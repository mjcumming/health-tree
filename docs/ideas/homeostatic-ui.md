# Homeostatic UI: ideas worksheet

Working notes for the owner-facing surface of `homeostatic`. Not the design of record. Nothing here is accepted until it lands in the RFP or an ADR.

Expanded 2026-09-24. Layout remains open. This worksheet names owner tasks, proposes workflows and priorities, and distinguishes existing library behavior from integration work. Owner requirements include user-created alerts; section 14 explores the mechanism. Recommendations remain proposals for review, not accepted library changes. The ADR index now records ADRs 0024 through 0028 as accepted.

The UI's job is to answer: **What can my house do, what is preventing it, what am I not watching, and what should interrupt me?** Adding integrations, devices, and alerts establishes that picture. Understanding and maintaining it is the larger job.

The library already fixes the model. The integration supplies nodes, checks, observations, durations, and policy data, and it carries deliveries out. See RFP sections 7 and 11, and ADR 0010 and ADR 0018.

The original three configuration surfaces are retained below. The expanded design exploration then covers first setup, functions, daily operation, evidence, maintenance, migration, and implementation gaps. These are jobs to support, not a commitment to a particular set of tabs.

| Surface | Question it answers |
| --- | --- |
| Configuration | What timings and integration settings does the owner live with? |
| What to monitor | Which parts of the house become nodes, checks, and edges? |
| Notifications | Who hears what, how loudly, and when? |

Mark each row when we decide it: **v1**, **later**, or **not a control**.

## 1. Configuration

The library fills in no duration. The integration's settings own the ones that are not per check, and they supply fallbacks where the catalog has none (ADR 0018, RFP section 11).

Starting values already written down, all editable:

| Setting | Starting value | Owns |
| --- | --- | --- |
| `settle` | 2 minutes | Engine |
| `rejoin_grace` | 1 minute | Engine |
| startup grace | 2 minutes | Engine |
| `coalesce_count` | 3 | Engine |
| `coalesce_window` | 60 seconds | Engine |
| `batch` | 30 seconds | Policy |
| `clear_hold` fallback | 2 minutes | Check, when the catalog sets none |
| `unknown_hold` fallback | 15 minutes | Check, when the catalog sets none |

The catalog sets `raise_hold`, `clear_hold`, `ttl`, and `unknown_hold` on each check. `ttl` may be explicitly `None`.

| Requirement | Decision |
| --- | --- |
| Edit the eight values above | |
| Override one check's `raise_hold`, `clear_hold`, `ttl`, or `unknown_hold` | |
| See the catalog's value next to an override | |
| Policy time zone, used by quiet hours and digest clocks | |
| Where the watchdog heartbeat goes | |
| Anything else that is integration setup rather than health behavior | |

`batch` is policy data. It is listed here because it is one house-wide duration, in the same family as the engine settings.

Startup grace is applied when Home Assistant reports it has started, not when the integration loads. That is adapter behavior, not a second control beside the duration.

## 2. What to monitor

RFP section 11 names where nodes come from. It does not say whether the owner opts in, opts out, or gets the whole inventory.

Sources:

- Supervisor host, core, add-ons, config entries, devices, automations, scripts
- External hosts and functions the owner declares
- Maintenance nodes the catalog splits off, such as updates and backups (ADR 0019)

Edges are a separate decision from "include this thing":

- Registered directly: `config_entry_id`, `via_device_id`, `parent_device_id`
- Candidates the owner confirms: entities an automation references
- Declared by the owner: relationships Home Assistant cannot see

A wrong edge mutes a real failure. A missing edge costs at most an extra message.

Selection and the graph are different controls. Collapsing them into one picker would hide that.

| Requirement | Decision |
| --- | --- |
| Default: watch everything the catalog understands, or start from an empty selection | |
| Exclude or include a whole integration (config entry) | |
| Exclude or include an add-on | |
| Exclude or include a device | |
| Exclude or include one check on a node | |
| Declare an external host | |
| Declare a function, and what it depends on | |
| Set a node's importance (`low`, `normal`, `high`, `critical`; default `normal`) | |
| Confirm a candidate edge | |
| Reject a candidate edge | |
| Declare an edge | |
| Remove an edge the owner confirmed or declared | |
| Show what `coverage` would list: no checks, never observed, stale | |

Functions in the stories carry importance because that is what makes an episode urgent. If importance is not editable, the example policy cannot tell the garage from the backyard.

The catalog supplies built-in checks. User-defined conditions and rules are an additional required input, explored in section 14. They must report actual evidence through a defined contract; merely declaring an alert does not close a monitoring gap.

## 3. Notifications

Policy configuration is data with a fixed shape (RFP section 7, ADR 0010). ADR 0010 says YAML first, a UI later. This section scopes what that configuration has to express. It does not decide the editor.

A recipient has channels (opaque ids), optional quiet hours, and optional sites. A recipient may be dynamic, such as whoever is home, resolved from context at send time. Context has no fields yet (RFP section 13).

A digest has a clock time and one recipient.

A rule matches a reason's status, reason, category, labels, and deadline through `due_within`, and the episode's importance and age. Rules are ordered. Within one reason the first match wins, and the episode takes the loudest result across its reasons. On a tie, the earlier rule wins. Recipients and timing come from the winning rule, not a union of all matches. A rule sets loudness, recipients, digest, reminder interval, and escalation. Loudness is `record`, `digest`, `notify`, or `urgent`.

The example in RFP section 7 is the shape, not a commitment that every house starts from those six rules.

| Requirement | Decision |
| --- | --- |
| Name recipients | |
| Bind each channel id to a Home Assistant notify service | |
| Set a recipient's quiet hours | |
| Set a recipient's sites | |
| Point "whoever is home" at whatever supplies presence | |
| Name digests, with a time and a recipient | |
| Edit rules: match, loudness, recipients, digest, remind, escalate | |
| Reorder rules | |
| Ship a starting policy the owner can replace | |
| Keep the first editor as YAML | |

Channels stay opaque in the library. The binding to a notify service is integration configuration.

Order carries meaning. The maintenance rule sits above the urgent rule so a dead battery does not page at night. A UI that adds a rule at the bottom changes who gets woken up.

Shelving, quiet windows, and repairs are not notification settings. They are listed below.

## Adjacent, not one of these three

| Verb | What it does | Why it is separate |
| --- | --- | --- |
| Shelve an episode until a time | Holds deliveries for that episode | Operator action on one open episode |
| Quiet a node until a time | Stops episodes from opening | Engine window, including its dependents or the whole house |
| `explain`, `impact`, `readiness`, `coverage`, `rollup` | Read the house | Services and Assist tools (RFP section 11) |
| Function health entity | Lets an automation fall back | An entity, not a setting |
| Repair | A fixable problem, such as a new login | Home Assistant repairs, from the catalog's remedy |

## Still to argue

- Per-check duration overrides, or only the two fallbacks.
- Opt in, opt out, or the whole inventory.
- Whether importance is edited with the function, or left at `normal` until a later pass.
- Whether notification configuration is YAML only in the first integration, with the table above as the later UI's contents.

## 4. Start with the owner's model

Use familiar Home Assistant things as entry points, and reveal engine concepts when they help a decision.

| Owner's concept | What the UI needs to make clear |
| --- | --- |
| Integration | A specific configured instance. Two instances of one integration can fail independently |
| Device | One recognizable physical thing, potentially containing several monitored capabilities |
| Function | A job the house should perform, such as basement motion lighting or garage operation |
| Check | Specific evidence about one capability, with a source and limits |
| Dependency | Something a capability always requires, whose failure can suppress duplicate episodes |
| View | A room, integration, site, or label grouping; membership never creates a dependency |
| Problem | An episode that persists while its evidence, impact, and urgency change |
| Attention | What the policy and delivery system are doing about that problem |

A Frigate device page can collect detection, recording, and updates. Underneath, detection and recording are distinct capability nodes; updates are a separate maintenance node. A full recording disk must not make motion lighting appear broken. The UI can hide the node count while preserving these distinctions (ADR 0019).

Keep three answers distinct: **observed condition**, **function readiness**, and **notification state**. A device recorded under its failed controller still has its own observed failure. A function can be blocked without having a failed check of its own. Shelving changes delivery, not health. These are presentation distinctions, not new core enums.

## 5. First setup should produce useful coverage

**Recommendation:** discover broadly, offer supported passive monitoring with a scope preview, and activate outbound notifications separately. The owner should not have to create hundreds of nodes or tune every duration. Discovery alone should not start costly or active external probes.

1. **Discover the existing installation.** Show integration instances, devices, automations, scripts, and available host/add-on information. Unsupported sources stay visible as coverage gaps. An installation without Supervisor should explain the unavailable host/add-on evidence.
2. **Review monitoring scope.** Show supported checks, setup requirements, exclusions, and whether future discoveries inherit inclusion. Allow bulk selection by integration, device, area, or label.
3. **Name important functions.** Offer relevant starting points from actual inventory: motion lighting, garage operation, backyard music. This can be postponed, with importance remaining `normal` until configured.
4. **Choose and test recipients.** Distinguish a transport test that sends a message from a policy preview that sends nothing.
5. **Review and activate alerts.** Show day/night examples, maintenance handling, and current problems that would be delivered on activation.
6. **Show remaining gaps and watchdog setup.** Finish with an honest coverage picture and the status of external monitoring of HA itself.

Notification activation is a proposed adapter workflow, not an existing engine feature. Before implementation, specify how already-open episodes, pending messages, and policy state transition into live delivery. Do not mark unsent openings as delivered or replay a backlog blindly.

## 6. Adding integrations and devices

### Integrations

Separate two intents:

- **Connect something new to Home Assistant.** Open native integration setup, then return to monitoring review after discovery. HA's [config flows](https://developers.home-assistant.io/docs/core/integration/config_flow/) own setup, discovery, reconfiguration, and reauthentication.
- **Monitor something already connected.** Select the configured instance, inspect supported checks and devices, review inherited settings and gaps, apply, and see first observations.

An integration detail needs instance identity, observed setup/authentication state, supported checks, supplied capabilities/devices, affected functions, and coverage. Link to its original HA page and available repair/reauthentication flow. Setup should show an already-failing integration rather than require a healthy baseline.

Monitoring the integration itself and monitoring its devices are separate choices. Excluding a controller check must not silently exclude all device checks. Including an integration should offer a bulk action for current devices and an explicit setting for future discoveries.

### Devices and external services

| Owner intent | Proposed workflow |
| --- | --- |
| Monitor an existing HA device | Search by name, integration, area, or label; inspect current coverage; select supported checks |
| Add a new physical device | Hand off to the owning integration's pairing/setup flow where supported, then review discovered monitoring |
| Monitor an entity without a device | Let a supported catalog check use the entity directly |
| Add an external host/service | Select a catalog-supported probe, enter connection details, preview frequency/cost, test, and declare dependents |
| Monitor an unsupported device | Show available evidence and missing capabilities; do not imply full coverage |

Homeostatic should not invent universal device pairing. Nor should successful ping imply the service on a host works. The device page should collect health, maintenance, last verified evidence, checks, dependencies, functions served, and recent problems. Before saving, an owner should understand what the selected checks actually detect.

Use stable source identities. Renaming or moving a device preserves settings and history. Replacing hardware or re-adding an integration needs deliberate remapping; matching display names are not sufficient.

### Inclusion and inheritance

Recommend **inherit / include / exclude**, displaying the effective choice and its source. Proposed precedence: explicit check choice, then device choice, then integration enrollment choice, then installation default. Areas/labels can select bulk operations without becoming competing inheritance rules. The cause graph is not an inheritance tree.

Persist exclusions across rediscovery. Distinguish new devices from new catalog checks on existing devices. Preview catalog changes that add probe cost, change thresholds, or alter routing labels, and preserve explicit overrides.

An excluded capability that a monitored function requires must remain an explicit evidence gap. Recommendation: retain its identity as an unwatched requirement. Simply deleting it can make readiness falsely reassuring. Registration details and existing-episode handling need integration scenarios before adopting this behavior.

## 7. Functions and dependencies deserve first-class editing

A function needs a name, purpose, importance, optional area/site, and required capabilities. Functions can depend on other functions while keeping the graph acyclic. For basement motion lighting, choose detection and the lighting control path; recording is not required merely because the same computer provides it.

Make **importance editable in the first usable release**, especially on functions. Otherwise the policy cannot distinguish the consequences of a failed garage command from unavailable backyard music. Explain importance with consequences, and preview its upstream effect: a controller's episode can become high importance because Garage operation depends on it. Importance is not a direct alert setting; policy still chooses loudness.

A function with no checks of its own can be ready when all required branches are watched and passing. An unwatched terminal requirement makes readiness unknown. A known warning can coexist with an unknown branch, so a degraded summary must not hide missing evidence. This follows the RFP and ADR 0025.

Distinguish **depends on** from **observed failing now**. Episode importance uses all dependents in its impact, not just devices that have already reported failure.

For each dependency, show direction (“A requires B”), capability required, provenance, reason for the suggestion, affected functions, and the separate reports a failed dependency could suppress. Show whether it is active, suggested, rejected, or references something missing.

Preserve the RFP's distinction between registered HA relationships, owner-confirmed candidates, and declared external edges. Automation references are candidates: conditions, optional scene members, and notification targets are not always required. Add/remove actions need an impact preview. Reject cycles with a readable explanation. Preserve rejected candidates across refreshes.

For automatic edges, show provenance and a correction path. Overriding one needs an ownership/reconciliation rule so discovery does not restore it immediately. A wrong edge can hide an independent failure, so bulk confirmation needs more than an unexplained checkbox list.

There is a design tension to resolve carefully: HA association does not establish failure of every physical capability. An integration can fail while a wall switch still operates locally. Apply RFP section 11 to the capability represented by the node and validate mappings against ADR 0019. Broader changes to automatic-edge semantics need an RFP change first. HA's current [device registry documentation](https://developers.home-assistant.io/docs/device_registry_index/) marks child-device APIs as evolving; check the adapter's target version.

Areas, floors, and labels are views. Moving a device into Garage must not create a dependency or silently change importance. If a policy explicitly matches an area label, preview changed rule coverage. Do not offer “either dependency is sufficient” in v1: redundancy groups are reserved and rejected. Fallback automations can consume readiness without inventing redundancy semantics.

## 8. Checks and coverage must expose the quality of evidence

Each check detail should explain:

- What it establishes, and what it does not establish.
- Evidence source, last source timestamp, and adapter receipt time where available.
- Latest observation versus effective state after holds/expiry.
- Why it is unknown, waiting, or stale, and its next relevant deadline.
- Supported configuration, current values, catalog defaults, overrides, and reset action.
- Affected capability, dependent functions, and alert-policy consequences.

The catalog owns built-in check meaning. Threshold controls require defined parameters, units, and validation. User-authored rules can supply additional conditions through the reporting contract in section 14, without requiring a second general automation language inside Homeostatic. Advanced timing overrides should preview detection latency and survive catalog upgrades while showing changed recommendations.

Freshness needs particular care. An unchanged value can be healthy; repeated cached writes can be stale evidence. HA's [`last_reported`](https://developers.home-assistant.io/blog/2024/03/20/state_reported_timestamp/) records state writes. The RFP requires proof that the observation reflects physical-device communication. Show “device freshness unavailable” when that proof is absent. Shortening `ttl` cannot create evidence.

A command check should show target, command time, deadline, and fresh resulting state. “No command outstanding” does not prove reachability. “Check again” requests a supported observation and reports when unavailable; it must not unexpectedly operate a door or lock.

Coverage should remain visible even when there are no open problems. Useful categories include active observation, awaiting first observation, stale/checker unavailable, unsupported, excluded, disabled at source, missing requirement, and partial coverage. These are adapter presentation categories, not new engine enums.

The planned `coverage()` query identifies no checks, never observed, and stale checks. Unsupported inventory and deliberate exclusions also need adapter data. Avoid a percentage that omits unsupported devices from its denominator. Prefer “42 discovered; 30 with supported monitoring; 7 unsupported; 5 excluded,” with capability gaps still available inside the 30.

Each gap should lead to an action: enable a supported check, restore a source, configure a probe, correct a mapping, or accept an uncovered requirement. Accepting the gap records a decision; it does not turn the requirement green.

## 9. Alerts must be explainable before and after delivery

### Recipients and transport

Start with static recipients, selected channels, quiet hours, and digests. Recipients need not be administrators. Enforce permissions for settings and notification actions in the backend, not just by hiding controls.

Choose explicit destinations. HA supports notify entities through `notify.send_message` as well as other notification actions; do not assume all targets are phone-specific service names. Generic `notify.notify` is unsuitable when destination must be predictable. See [HA notifications](https://www.home-assistant.io/integrations/notify/).

For each channel, show target, availability, last test, and capabilities: ordinary/urgent delivery, replacement, clearing, and actionable responses. A missing channel is a configuration problem. Keep credentials in appropriate HA configuration and redact diagnostic exports.

`urgent` bypasses Homeostatic quiet hours; it does not prove a phone will sound through its own settings. Test transport behavior separately. Companion documentation describes [critical notifications](https://companion.home-assistant.io/docs/notifications/critical-notifications/) and [replacement/clearing limitations](https://companion.home-assistant.io/docs/notifications/notifications-basic/#replacing). Do not promise silent replacement on transports that cannot support it.

“Whoever is home,” sites, absence, unknown presence, and fallback when nobody qualifies need defined semantics and fixtures. `PolicyContext` currently has no fields. Do not ship a presence selector that looks effective while routing statically.

### Editing and preview

Keep ADR 0010's YAML-first direction. A read-only explanation and preview can arrive before a complete visual editor. A later guided editor should use the same policy data with one authoritative configuration and lossless round trips for supported fields.

Offer a starting policy with concrete examples: maintenance in the morning digest, important operation failures immediately, ordinary failures according to quiet hours. It remains a replaceable proposal, not a universal household preference. Rules must expose order, matching fields, loudness, recipients/digest, reminders, and escalation.

For a lock with battery warning plus failed close command, preview each reason's first match and the urgent winning result. When the command clears, maintenance can remain without another noisy notification. Show that tied results use the earlier rule; recipients are not combined across losing rules (ADR 0020).

If a future “change alerts for this device” shortcut creates a policy rule, expose its scope and position. Do not create a hidden override system outside policy. Reordering needs before/after examples and warnings about plainly shadowed rules.

Separate **Preview policy** from **Send test notification**. Preview accepts time, sample reasons, importance, and supported context, and predicts delivery/reminder/escalation where calculable. Predictions depend on unchanged evidence and configuration. Use isolated state; never advance the live policy's counters to preview tomorrow.

Current escalation raises loudness one level; it is not an unlimited ladder or automatic reassignment to another person. Richer escalation needs policy work.

### Explain silence as well as alerts

Every problem should answer both “Why did this alert?” and “Why didn't this alert?” Show evidence, matched rules, winning reason, loudness, recipients, and delay/suppression with expiry. Distinguish:

- A check inside its raise hold.
- Settling while a dependency is in doubt.
- Symptoms recorded under another episode.
- Startup/rejoin grace or maintenance window.
- Record-only policy, digest, batch delay, or recipient quiet hours.
- Shelving until a specific time.
- Policy delivery requested but transport failed.

Policy output is not proof of delivery or reading. Track requested, accepted by channel, failed, and confirmed only where supported. Ordinary alerts may coalesce before sending; urgent messages already sent cannot be unsent when a late cause appears.

## 10. Everyday use and incident handling

The landing experience should prioritize blocked/degraded functions, actionable problems, maintenance due, and coverage gaps. A graph helps explain relationships but should not be the only way to navigate. “Requires” and “used by” lists must work on phones, with keyboards, and without color. Filter large inventories; avoid redrawing the entire topology for every observation.

A useful problem summary would read:

> Basement motion lighting is blocked. The Frigate host is unreachable. Four functions depend on it; three sensors also report failures. One problem is tracking the outage. A notification was requested for Michael at 02:40.

Problem detail needs first observation and opening times, evidence, confirmed versus suspected cause, potential impact versus observed symptoms, independent problems, delivery decisions/attempts, a short timeline, remedies, and scoped operator actions.

When siblings fail under a passing controller, say that several devices sharing the controller are failing and its own checks still pass. Coalescing suggests a shared cause; it does not prove controller failure. Explain remaining independent failures when a group dissolves.

Keep absorbed-episode links navigable with “merged into this problem.” Distinguish `removed`, `absorbed`, and `cleared`. Removing monitoring is not recovery. Explain clear holds and rejoin handling rather than show a stuck alert or premature all-clear.

Dismissing a phone notification must not clear the problem. “Fixed” must not fabricate a passing observation. Offer the actual remedy and supported recheck. Use HA [Repairs](https://developers.home-assistant.io/docs/core/platform/repairs/) for actionable repair flows rather than duplicate every fault there. Automatic remediation remains outside the RFP's first version.

### Quiet controls need different names

| Action | Meaning | Still visible |
| --- | --- | --- |
| Shelve this problem until a time | Hold policy deliveries for one episode | Evidence, health, impact, expiry |
| Start maintenance for a scope until a time | Prevent new episodes there | Observations, readiness, existing episodes |
| Set a recipient's quiet hours | Ordinary notifications wait; urgent bypasses the policy delay | Problems and other recipients' delivery state |
| Record only through policy | Keep problems without outbound messages | Evidence and history |
| Exclude a check | Stop monitoring that source | Coverage gap and effects on required functions |

Avoid one “mute” action covering all five. Shelving is episode-wide in the current API, not “silence only my phone.” Maintenance scope is one node, node plus dependents, or everything. Preview scope, show expiry, and make active windows/shelves easy to find after restart.

Maintenance does not silence already-open episodes. A combined action must show both the window and episodes being shelved. Quiet actions never make readiness healthy. Early cancellation of maintenance, window inspection, and durable acknowledgement (“I am handling this”) require API/semantic work. Do not disguise acknowledgement as shelving.

## 11. Configuration and lifecycle details that are easy to miss

Keep the eight starting settings in section 1, editable in an advanced surface. Recommend per-check overrides with precedence: explicit override, catalog value, then documented fallback where one exists. There is no invented universal `raise_hold` or `ttl`; missing required catalog values need correction. Explicit `ttl: None` does not disable unknown handling.

Preview a timeline for timing changes: last verified report -> expiry -> stale problem eligible -> policy delivery. Daily-reporting battery devices and frequently reporting detectors need different expectations. Display time zone with quiet hours/digests and test midnight/daylight-saving transitions. Current policy uses one zone, not one per recipient.

Validate references and values before applying; keep the last working configuration on failure. Bulk changes need an affected-item preview. Detect concurrent edits. Specify how changes affect open episodes and pending deliveries; blind reconstruction risks duplicates or lost continuity.

| Lifecycle event | UI requirement |
| --- | --- |
| Rename or move | Retain identity/settings; preview affected label-based rules |
| Unavailable | Distinguish loss of evidence from removal |
| Deliberately disabled | Explain coverage loss and affected functions |
| Removed | Expose broken references; retain history; removal is not recovery |
| Replaced | Review mapping of former role, checks, and dependencies |
| Catalog upgraded | Show changed assumptions, new checks, migrations, retained overrides |
| Restart | Restore episode identity and policy state; show grace and observation recovery |
| Restore failed | Explain continuity limits and actionable configuration/storage failure |
| Notification target lost | Show failure and offer remapping without claiming delivery |
| HA process died | Outside watchdog alerts independently of HA |

A watchdog page should distinguish configured, heartbeat sent, and externally verified, with verification time. Sending a heartbeat alone does not prove failure detection or delivery. Its test should not require taking the house down.

History is adapter work. Retain enough to explain last night's alert: findings, episode transitions, policy/configuration version, actions, and transport outcomes. Define retention and redacted export. A current snapshot is not a historical journal. If the UI loses its live connection, label displayed data stale.

During migration, inventory existing alerts the owner identifies, map supported equivalents, compare behavior, and keep unmatched items visible. A record-only trial can reduce duplicate outbound messages, but live activation still needs specified reconciliation. Never disable existing automations merely because a similar check exists.

Situation alerts are required in the intended Homeostatic product alongside health monitoring: water detected, door unlocked while away, and garage open at night. Their condition logic can come from existing automations while Homeostatic manages the problem and attention lifecycle. Preserve the distinction between an undesirable situation and failed equipment. Migrate an existing automation's notification responsibility only after verifying equivalent opening, update, and clearing behavior. Section 14 proposes the extension; the current library RFP still excludes situation alerts from its first version.

## 12. Implementation boundaries and missing contracts

This is a source-based planning inventory, not a claim about a released integration.

| UI need | Existing foundation | Remaining work |
| --- | --- | --- |
| Explain failure/readiness | Public `explain` and `readiness` implementations | HA identities, presentation, proven observations |
| Impact, coverage, summaries | RFP specifies `impact`, `coverage`, `rollup` | Those public methods are absent from current `Engine`; settle/implement contracts |
| Current conditions and waiting times | Internal check, hold, gate, window, and episode state | Supported read model instead of private fields/snapshot internals |
| Policy explanation and preview | Per-reason decisions and delivery output | Supported decision trace and isolated preview |
| Static alerts/shelving | Current policy API | HA channels, tests, transport capabilities, authorization |
| Presence/sites | Recipient sites and empty `PolicyContext` | Context, fallback semantics, fixtures |
| Maintenance | `Engine.quiet` | Window identity/inspection and early-cancellation semantics if offered |
| Live configuration | Runtime registration/removal; immutable policy configuration | Validate/apply/reconcile open and pending state |
| Delivery activation/retry | Delivery intentions | Durable attempts, bounded retry, deduplication, truthful outcomes |
| Historical explanation | Current-state snapshots | Bounded journal and configuration versions in adapter |
| Replacement/catalog evolution | Adapter-chosen stable ids | Source mapping, provenance, migrations, broken references |
| User-created alerts and rule input | Generic observations, episodes, and attention policy | Condition registration/reporting, producer freshness, situation-alert semantics, RFP/ADR and fixtures |

The frontend must not reproduce readiness, inhibition, or policy algorithms. Engine/policy owns decisions; adapter owns discovery, mappings, history, delivery, and presentation data. New public read contracts may need an ADR.

Use native HA [options flows](https://developers.home-assistant.io/docs/core/integration/options_flow/) for ordinary settings, entities for function health, and actions for supported operations. A dedicated health view is recommended for reviewing many problems and coverage gaps; frontend technology and packaging are open. Assist can reuse read queries, with the same authorization/scope for any future mutation.

## 13. Recommended priorities and acceptance walkthroughs

These are recommendations for review, not accepted release assignments.

| Phase | Proposed scope |
| --- | --- |
| Prove inputs | Real detector, battery-freshness, and command-completion traces; demonstrate notification and watchdog paths |
| First usable release | Native setup; inventory/inclusion; catalog checks and advanced timing; functions/importance/dependencies; health/problem/coverage views; static recipients; YAML policy validation/explanation; channel test; shelving and bounded maintenance creation; restore/errors; user-defined alert registration and rule input after the required semantics are specified |
| Next | Guided policy editor with change preview; richer history; migration tools; saved readiness views; maintenance cancellation after API design; actionable phone controls |
| Later after semantics | Dynamic recipients/sites, acknowledgement/assignment, richer escalation, a general visual condition-expression builder, redundancy |

First-release hypothesis: with supported devices, an owner can enroll an integration, define one useful function, verify a channel, and understand coverage in about ten minutes without editing node definitions. Evaluate observed setup sessions; mandatory telemetry is unnecessary. Also measure duplicate messages per outage, unexplained decisions, time to locate a cause, and persistent evidence gaps.

The following are proposed integration/UI walkthroughs, not new numbered library stories or executable fixtures. Existing story/scenario ids remain unchanged.

| Walkthrough | Expected result |
| --- | --- |
| Enroll two instances of one integration | Separate identity, checks, device selection |
| Discover a new device | Visible inclusion setting applies; exclusions persist; unsupported coverage is visible |
| Function has passing and unwatched required branches | Cannot appear fully ready; missing evidence is explained |
| Frigate host fails | One problem explains symptoms and function impact without rewriting own status |
| Detection hangs while recording works | Motion readiness changes independently of recording |
| Recording disk fills while detection works | Motion lighting is not blocked by the recording capability |
| Lock battery warns and command fails | Per-reason preview explains urgent winner and later maintenance-only state |
| Several devices fail under passing controller | Shared-cause suspicion without claiming controller failure |
| Start maintenance on failing controller | Existing problems remain unless shelved; readiness stays truthful |
| Shelve and restart | Problem/expiry survive; restored policy controls delivery |
| Reorder maintenance rule | Preview shows changed outcomes and recipients |
| Cached writes continue after device disconnect | Never claim verified physical freshness |
| Remove required device | Explicit unresolved requirement, not apparent function recovery |
| Transport fails | Decision and failed attempt separate; no delivered claim |
| Recover before batch delivery | No stale opening sent; history remains understandable |
| Restart after delivery | Stable episode identity; no new page just for restarting |
| Migrate garage-open-at-night alert | Preserve condition semantics while moving its problem/notification lifecycle into Homeostatic through the specified rule interface |
| UI connection drops | Old all-clear is visibly stale |

Observation-proof walkthroughs need real traces under RFP section 11. Synthetic engine fixtures do not prove HA can produce that evidence.

The next decisions are enrollment defaults for future devices, first supported external probes, activation of already-open problems, treatment of excluded requirements, provenance/overrides of automatic edges, and the minimum read/decision APIs. Importance editing and advanced timing overrides are recommended for the first usable UI; a complete visual policy editor can follow YAML.

The product test is one understandable chain: **this part of the house matters -> these capabilities support it -> these checks provide evidence -> this problem explains failure -> this policy explains who heard -> this action helps address it**.

## 14. User-created alerts and rules as inputs

**Owner requirement:** create alerts such as “the front door has been open for three hours and it is 2 a.m.,” alongside remote-system failure, disk capacity, and other custom conditions. This belongs in the product scope. The design recommendation is to separate **detecting a condition** from **managing a problem and delivering attention**.

The current RFP explicitly excludes situation alerts from the library's first version. Supporting them requires an explicit scope/model proposal and fixtures before implementation; this worksheet does not silently change that contract. Remote host/service failure and disk capacity already fit health monitoring. A healthy door sensor reporting an open door is a situation, not a broken sensor.

### One alert lifecycle, several sources

| Source | Responsibility | Example |
| --- | --- | --- |
| Built-in catalog check | Interpret supported device/service evidence | Remote host unreachable, detector stalled, disk nearly full |
| Simple user-created condition | Evaluate a supported state/duration/threshold pattern | Door open too long during specified hours |
| Existing HA automation, template, or other rule producer | Evaluate custom logic and report current condition | Windows open while heating, abnormal freezer temperature, missed scheduled job |

All sources should use shared problem identity, evidence, history, notification policy, reminders, shelving, and recovery handling. The producer should not need to reproduce recipients, quiet hours, repeated notifications, or escalation logic. Use different names for **condition rules**, which establish a problem, and **notification rules**, which decide who hears about it.

Prefer a HA action for registered rule producers to report a condition, plus an optional binding to a stateful entity that Homeostatic can evaluate on setup/restart. Exact action names and arguments are not yet an API. Do not accept arbitrary prebuilt engine events or let an automation fabricate episode identities; the problem owner manages those.

### Create alert: simple form and advanced rule entry

The UI should offer common patterns first: state persists too long, measurement crosses a threshold, heartbeat is missing, expected result/deadline is missed, or an existing entity represents a problem. An advanced path lets an existing automation report the condition through the same lifecycle.

For the door example, an illustrative form would say:

| Field | Example choice |
| --- | --- |
| Name | Front door open overnight |
| Source | Front door contact sensor |
| Problem condition | Open continuously for at least three hours |
| When it applies | Between 22:00 and 07:00 in the home's time zone |
| Condition ends | Verified closed, or the overnight rule no longer applies |
| Importance | Owner-selected consequence, such as high |
| Attention | Preview the notification rule; optionally create an explicit urgent exception |
| Missing evidence | Unknown, with source-health/freshness monitoring; never assume closed |

Those hours and importance are examples, not inferred preferences or defaults. If the intent is instead “check specifically at 02:00,” the form must express that different schedule. High importance alone does not guarantee an urgent delivery.

Trigger reevaluation when the door changes, the three-hour threshold arrives, the time window opens/closes, configuration changes, and HA restarts. A door open since 18:00 must qualify when the overnight window begins, even without another sensor transition. A door opened at 23:00 qualifies at 02:00. Do not restart the open-duration clock at bedtime unless explicitly requested.

The rule's clear semantics must also be explicit. At 07:00, “overnight condition no longer applies” does not mean “door closed.” Owners may instead choose to keep a raised problem active until verified closure, but that latching behavior needs a specified lifecycle. Disabling/deleting a rule is administrative removal, not observed recovery.

### Rules report state, not a stream of new messages

A proposed reporting contract needs:

| Information | Why it matters |
| --- | --- |
| Stable definition/condition key and subject | Repeated evaluations update one active occurrence; two doors remain independent |
| Producer identity and authorized ownership | One rule cannot accidentally clear a different rule's problem |
| Active, clear, or unknown result | Lack of evidence is distinct from verified recovery; these are adapter concepts, not new core enums |
| Occurrence start and observation time | Duration of the condition is distinct from episode opening and message delivery |
| Reason, measured evidence, and readable message | Explain the condition and show what changed |
| Importance and routing labels on the registered definition | Keep policy configurable and reports scoped to their intended meaning |
| Freshness/renewal contract | Detect a producer that stopped reporting without falsely clearing its problem |
| Clear semantics and optional clear hold | Define what ends this condition, including hysteresis for numeric thresholds |

Repeated active reports should update the same occurrence. Verified clearing ends it; a later recurrence starts a new one. Reject or ignore stale/out-of-order reports under a documented ordering rule. Deduplicate retries. An unknown report or expired producer lease must not become a clear, and lost evidence must not erase a previously active condition from the UI.

Separate an externally monitored heartbeat from the health of the monitoring producer. “Remote service missed its heartbeat” can be a problem even when the remote service cannot report its own death. “The checker stopped running” is unknown coverage, not proof the remote service died. `ttl` alone expresses expired evidence; the catalog/producer must decide whether a missed expected heartbeat establishes failure or only uncertainty.

Stateful bindings are useful because current truth can be reconciled after restart. Action-only producers must define how they report initial state, renew evidence, and clear. Persist verified condition start times/deadlines when needed. Do not claim uninterrupted physical state during an observation gap without evidence. HA documents that automation `for` waits reset on restart/reload, so a naive three-hour wait is insufficient for continuity. See [automation trigger timing](https://www.home-assistant.io/docs/automation/trigger/#template-trigger).

For thresholds, define units, missing-value handling, and distinct raise/clear criteria where appropriate. A disk might warn above a chosen utilization and clear below a lower threshold; an absent measurement must not be converted to zero usage. Assign each duration to one layer so producer timing and engine holds do not accidentally double the delay.

### Share attention without inventing health dependencies

A situation's subject and evidence source are associations, not automatically cause edges. Losing a door sensor must not suppress or clear an already-known open-door situation. An open-door situation must not make the contact sensor or unrelated door functions appear broken. A shared area or source does not justify coalescing two independent situations.

The first implementation option to evaluate is a separately registered condition node/check, isolated from equipment dependency inhibition and unrelated function readiness, while reusing episode and policy mechanics. Kind/category names can remain open strings. This is a proposed use of the model: it needs RFP/ADR review against the one-capability rule, unknown handling, and quiet-window scope. Do not silently label the physical device failed just to obtain a notification.

If the condition lifecycle cannot fit the engine without distorting those rules, use a dedicated condition-to-episode adapter that feeds the shared attention policy. That adapter would own identity, opening/update/resolution, restore, and unknown semantics explicitly; it should not become a second notification engine. Choose between these implementations with the walkthroughs below, rather than exposing either internal model in the alert form.

Global maintenance scope deserves a deliberate decision when situations are included: maintenance for a controller or host should not accidentally suppress a door-open situation merely because it uses that device's evidence. Shared recipients and policy do not imply shared suppression scope.

### Other useful alert patterns

| Pattern | Example | Evidence/clear requirement |
| --- | --- | --- |
| State persists | Door open too long; water flowing too long | Verified duration and explicit end condition |
| Threshold | Freezer warm; disk nearly full; UPS battery low | Valid units, current samples, suitable clear threshold/hold |
| Missing heartbeat | Remote service silent; scheduled telemetry missing | Independent observer and expected reporting interval |
| Deadline missed | Backup/job did not finish; expected device did not reconnect | Known schedule/command and evidence of completion |
| End-to-end failure | Host responds but remote inference or recording fails | Probe the required service, not only the host |
| Combined condition | Heating with windows open; unlocked while away | Defined behavior for unknown source/presence and condition transitions |
| Growing risk | Storage expected to fill soon | Producer-supplied projection/deadline; no invented core prediction |

HA already has an [Alert integration](https://www.home-assistant.io/integrations/alert/) for repeating alerts and acknowledgement. Existing setups are migration candidates, not a reason to create duplicate notification loops. Homeostatic's proposed value is shared health context, episode handling, policy, evidence, and explanation. Preserve an existing alert until its replacement's opening, reminder, clear, and acknowledgement differences have been reviewed; acknowledgement is still a separate open design item here.

### Required walkthroughs before implementing the extension

- Door opens at 23:00: one problem becomes eligible at 02:00; repeated evaluations do not create repeated openings.
- Door already exceeded three hours before the overnight window starts: it is evaluated at window start.
- HA restarts near the deadline: reconcile persisted evidence and current state; do not claim continuity that was not observed.
- Door source becomes unavailable: show unknown evidence and preserve the unresolved situation without declaring closure.
- Schedule ends while door remains open: follow the selected semantics and never say the door physically closed.
- Two doors match one reusable rule: independent keys, clear actions, and histories.
- A delayed active report arrives after verified clearing: it cannot resurrect the old occurrence.
- Remote service dies while the reporting adapter stays healthy: the independent observer raises the expected problem.
- Reporting adapter dies: expose freshness/coverage loss rather than invent remote failure or recovery.
- Disk readings oscillate near a threshold: use the defined hysteresis/holds without notification storms.
- A condition producer is disabled or removed: expose lost coverage/administrative removal rather than a false all-clear.
- Controller maintenance starts during an open-door situation: suppression follows explicit situation scope, not an accidental source association.

The minimum product path is **register a user alert -> bind a condition source or report from a rule -> preview shared policy -> manage one ongoing problem**. A sophisticated expression editor can come later; user-defined alerts should not depend on building one.

## 15. Follow Home Assistant's existing error and repair patterns

**Owner requirement:** follow and reuse HA's design patterns for integration and device errors. Verified 2026-09-24 against current official documentation, Core release `2026.9.3`, and frontend release `20260826.7`. These release sources establish the baseline; this is not an inspection of the owner's running HA instance. The local `C:/GitHub/core` checkout identifies itself as `2025.11.0.dev0`, so it was not used as the current reference.

### Existing surfaces and their intended meaning

| Situation | HA's existing mechanism | Homeostatic's proposed use |
| --- | --- | --- |
| Integration cannot finish setup | Config-entry states distinguish retry, setup error, migration error, and other lifecycle states; retry can recover automatically | Preserve the native state/reason, apply catalog timing, show function impact, link to the original entry |
| Credentials expired | Reauthentication flow; current Core also creates a related repair issue | Point to that flow and correlate the existing issue instead of creating another login form or duplicate issue |
| Entity cannot be read/controlled | Entity availability; missing values can instead be unknown | Retain the source distinction and evaluate the particular capability; do not mark a whole device failed indiscriminately |
| Integration exposes a specific fault | Problem-class binary sensor or other integration-provided diagnostic entity | Reuse the structured signal and its documented meaning |
| User intervention is required | Repairs issue with explanation and supported fix/help path | Reuse an existing issue; create our own only when Homeostatic owns an actionable problem |
| An action fails | Validation/runtime exception returned to the action caller | Return a useful translated error for our actions; separately track persistent failure where warranted |
| Troubleshooting needs detail | Integration logs, debug logging, diagnostics when supported | Link to these tools and offer redacted Homeostatic evidence |

The [config-entry lifecycle](https://developers.home-assistant.io/docs/config_entries_index/) and [setup-failure guidance](https://developers.home-assistant.io/docs/integration_setup_failures/) distinguish recoverable setup delay from failure. The [released integration row](https://github.com/home-assistant/frontend/blob/20260826.7/src/panels/config/integrations/ha-config-entry-row.ts) renders a status icon, localized state, explanatory reason, and context-dependent actions including logs, reload, reconfigure, and diagnostics. Follow this pattern of a specific problem plus a useful next action.

HA's [availability guidance](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-unavailable/) distinguishes inability to fetch from a temporarily missing value. The catalog must interpret those signals: unavailable can establish failure of an HA control path without proving physical hardware is dead. An integration being loaded likewise does not establish that every device or service operation works. Avoid parsing log text as the primary source of structured health.

A [problem binary sensor](https://www.home-assistant.io/integrations/binary_sensor/#device-class) represents a detected problem, while [entity categories](https://developers.home-assistant.io/docs/core/entity/#registry-properties) distinguish configuration and diagnostics. Use standard entities, device classes, names, and categories where the meaning fits. A readiness entity must remain available to report “blocked”; its own availability indicates whether Homeostatic can supply that answer. Do not compress ready/degraded/blocked/unknown into a misleading boolean without retaining those distinctions.

### Repairs are an actionable surface, not every notification

HA's [repair quality rule](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/repair-issues/) requires useful information and a problem the user can address. This includes more than configuration migrations: low disk space is explicitly an example in the [repair lifecycle documentation](https://developers.home-assistant.io/docs/core/platform/repairs/). A remote outage without a meaningful repair action need not become another Repairs entry.

Keep the native issue identity, owning integration, severity, and ignored state. Link a Homeostatic problem to it. Do not delete another integration's issue or manufacture passing evidence when its repair flow finishes. Native dismissal/ignore and temporary Homeostatic shelving are different operations; their notification interaction must be explicit.

For an issue we own, use a stable issue id, translated explanation, and the appropriate fix flow or help link. Account for HA's persistence and ignore lifecycle rather than re-creating issues on every evaluation. Native repair severity is separate from health status, function importance, and delivery loudness. In particular, HA reserves its critical repair severity for exceptional panic conditions; it is not an automatic mapping from a critical function.

Current Core's [reauthentication implementation](https://github.com/home-assistant/core/blob/2026.9.3/homeassistant/config_entries.py#L1336) supplies a concrete example of reuse: the config entry, active flow, and repair issue are manifestations of one credential problem. Correlate them using structured source identity, not matching English messages. Source-specific adapters may be required because there is not a universal foreign issue-to-device association to assume.

### Native setup, actions, and presentation

Use config/options/reconfigure flows for their existing purposes. Preserve original device and integration identities and link back to their pages. Expose our rule-reporting actions through HA's ordinary action mechanism with suitable selectors and translated field/error text. HA's [action failure rule](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-exceptions/) distinguishes invalid input from execution failure; a failed request must not appear saved successfully.

The [released device page](https://github.com/home-assistant/frontend/blob/20260826.7/src/panels/config/devices/ha-config-device-page.ts) groups entities into ordinary controls, sensors, configuration, and diagnostics, with supported diagnostic downloads. Follow those familiar groupings. A dedicated Homeostatic view adds cross-device episodes, dependency explanations, coverage, and policy decisions. It should share HA's terminology, theme, responsive behavior, and accessibility patterns. Inspecting frontend source establishes design precedent, not a guarantee that private frontend components are supported extension APIs.

Use existing HA notification transports for outbound delivery. A [persistent notification](https://www.home-assistant.io/integrations/persistent_notification/) is an in-app message that can be updated or dismissed; it is neither a repair workflow nor proof of physical recovery. Avoid putting the same episode into Repairs, a persistent notification, and a phone alert by default without a defined purpose for each. Our policy controls our deliveries; it does not silently disable another integration's notifications.

Respect HA's [log-on-transition guidance](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/log-when-unavailable/) for adapter connectivity, rather than logging every retry as a new error. The health-tree library retains its own no-I/O and DEBUG-only logging boundary.

### Concrete acceptance checks

- Expired credentials produce one correlated Homeostatic problem with a working path to native reauthentication, preserving HA's existing issue ownership.
- Temporary setup retry remains visibly different from permanent setup failure and expected startup/disabled state.
- One unavailable diagnostic entity does not automatically fail every capability of its device.
- A loaded integration with a failed end-to-end check can still produce a service-health problem.
- Native repair ignore is displayed accurately and is not treated as repair, recovery, or automatic shelving.
- A low-disk repair already raised by HA is linked rather than duplicated.
- Homeostatic cannot provide fresh readiness: its exported entity reports that limitation, rather than retaining a false current all-clear.
- A bad rule-reporting action returns the native style of actionable validation error and leaves the prior configuration intact.

The practical design rule is: **retain HA's original state and correction path; add cause, consequences, episode history, coverage, and attention decisions around it.** Changes to library semantics still require the RFP and fixtures; this section establishes integration and UI direction.
