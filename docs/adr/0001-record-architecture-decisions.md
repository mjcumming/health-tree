# ADR 0001: Record architecture decisions

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

The RFP says what the library does. The reasons behind it need a home that survives the conversation that produced them, so a later change does not reverse a decision by accident.

home-topology kept every decision in one log file and ended up with duplicate numbers (two ADR-007s, two 011s, two 012s). pywiim kept one file per decision with an index, and did not.

## Decision

- One Markdown file per decision in `docs/adr/`, named `NNNN-short-slug.md`, numbered in order. Numbers are never reused.
- Sections: Status, Date, Deciders, Context, Decision, Options considered, Consequences.
- Status is `Proposed`, `Accepted`, `Deprecated`, or `Superseded by NNNN`.
- An accepted ADR is not edited for substance. A new ADR supersedes it, and the old one's status changes.
- [README.md](README.md) indexes every ADR.
- The RFP says what. ADRs say why. When a rule in the RFP changes, the ADR that explains it changes or is superseded in the same pull request.

Write an ADR when a decision changes the public interface or a rule in the RFP, would be easy to reverse by mistake, or picks between real alternatives. Do not write one for details that are clear from the code.

## Options considered

- **One log file.** Easy to skim. Numbering collides and merges conflict, as home-topology showed.
- **The RFP alone.** One document, but it loses the alternatives and churns every time a reason is added.
- **Issues or discussions.** Not versioned with the code, and invisible to an agent working in a checkout.

## Consequences

- One more file per decision.
- Reviewers and agents can trace a rule to its reason by reading the index.
