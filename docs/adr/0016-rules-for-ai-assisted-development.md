# ADR 0016: Rules for AI-assisted development

**Status:** Proposed
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Much of this project will be written with AI agents such as Claude and Cursor.

home-topology recorded the ways agents go wrong:

- wrong dates
- reading too much
- coverage that decays
- platform dependencies creeping in

Home Assistant core keeps its agent instructions in `AGENTS.md`, with `CLAUDE.md` pointing to it. It follows the Open Home Foundation AI policy: a human must review, understand, and be able to explain every change, and agents do not open issues or pull requests on their own.

## Decision

- `AGENTS.md` at the root is the single source of agent instructions: hard rules, commands, style, and tests.
- `CLAUDE.md` imports it with `@AGENTS.md`. It is not a symlink, because symlinks break on Windows checkouts.
- There is no `.cursorrules` file. Cursor reads `AGENTS.md`.
- Agents follow these rules:
  - Read the relevant RFP section and ADRs before changing behavior.
  - Update the RFP, ADRs, and changelog in the same change.
  - Add a fixture for every behavior change.
  - Take dates from the system clock.
  - Never commit, push, tag, publish, or open issues or pull requests unless the maintainer asks.
- The maintainer reviews every change.

## Options considered

- **A file per tool** (`.cursorrules`, `CLAUDE.md`, Copilot instructions), each with its own content. The copies drift apart.
- **No agent file.** Agents guess at conventions.

## Consequences

- One file to maintain.
- The rules are enforced by review and, where possible, by CI: ruff's banned APIs, mypy, and tests.
