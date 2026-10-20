# ADR 0043: Keep continuous qualification through affected-node reporting

**Status:** Accepted
**Date:** 2026-10-19

## Context

An application can give dependent equipment a longer qualification hold than its integration. Existing affected-node matching includes every potential dependent, so an integration failure can authorize that equipment's route before its own check qualifies. A recorded dependent's findings are deliberately absent from the root's reasons; filtering those reasons by node would never authorize its route.

Some checks also require a continuous interval of observed worsening. The existing hold can span an unknown report or a stopped process. Neither gap establishes continuous evidence.

## Decision

Add optional `Check.continuous`, defaulting to false. For an opted-in check, an unknown report immediately interrupts an incomplete worsening and follows normal unknown-evidence rules. A later worsening starts a full new hold. Restore discards a pending worsening for these checks; fresh evidence starts qualification again. Effective warnings and failures, pending recovery, episode identities and ordinary checks retain their existing behavior. Observation expiry also interrupts qualification through the existing unknown transition.

A fresh known worsening waiting for its continuous hold is current evidence, so the preceding unknown interval cannot open a stale finding while that hold runs. Another unknown report or expiry interrupts that evidence and starts its own unknown hold; repeated unknown reports do not extend it.

Add `Episode.qualified_nodes`, the affected nodes whose own effective checks contribute a warning or failure, or whose continuous check already qualified and has not effectively recovered. The scope includes anchor, recorded nodes and impact. An initial pending worsening and stale unknown findings do not earn qualification. Once a continuous check qualifies, unknown evidence cannot revoke that qualification or replay the shared problem's opening when warning evidence resumes. Effective pass through the normal clear hold or removal ends that qualification. Its changes update the episode. This leaves the existing reasons, status, impact and dependency lifecycle unchanged.

Add optional `Match.qualified_nodes`. When supplied, it must intersect the episode's qualified scope. This predicate is independent of `nodes` and the finding's check, status and labels; those retain their established meanings. Applications with one check per independently configured condition can require that condition's qualified node while matching its shared root's finding.

Episode snapshot decoding defaults a missing qualified scope to empty. Engine evaluation rebuilds it from effective checks and emits an update when needed; it never infers qualification from potential impact. Existing snapshots keep their identities and delivery history. The new check and match settings are configuration, outside the snapshot.

## Options considered

- Adapter timers would duplicate engine deadlines and qualification state.
- Requiring a finding's node to match would exclude recorded dependent findings from shared root episodes.
- Adding recorded findings to reasons would change existing attention precedence and shared problem summaries.
- Changing ordinary hold semantics would alter existing consumers; continuous evidence is explicit.

## Consequences

Applications can preserve independent waits when dependencies absorb problems without inventing additional episodes or delivery timers. Existing callers retain affected-node behavior until they opt into the new predicate and continuous check setting.
