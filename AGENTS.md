# Agent instructions

This file is for AI coding agents: Claude Code, Cursor, Copilot, Codex. Humans read [CONTRIBUTING.md](CONTRIBUTING.md). The rules are the same.

health-tree is a platform-agnostic Python library for health across a dependency graph: nodes, checks, dependency-aware episodes, and an attention policy. Home Assistant is the first consumer, in a separate repository.

## Read first

- [docs/rfp.md](docs/rfp.md) is the design of record. Behavior is whatever the RFP says. Change the RFP before changing behavior.
- [docs/adr/README.md](docs/adr/README.md) lists the decisions and why they were made. Do not reverse an accepted ADR. Propose a new one that supersedes it.
- Read only the sections a task needs. The RFP's table of contents and the ADR index are enough to find them.

## Hard rules

- No Home Assistant imports and no runtime dependencies (ADR 0002).
- No I/O, threads, asyncio, sleeping, or clock reads in `src/`. Anything that depends on time takes `now`, a timezone-aware UTC `datetime` (ADR 0003). Ruff's banned-API list enforces this. Do not silence it.
- `Status`, `Importance`, and `Loudness` are the only closed enums. Kinds, reasons, categories, labels, annotations, and recipient and channel ids are strings, and the library never branches on them. A new closed type needs an ADR (ADR 0004).
- Never rewrite a node's `own` status because of its dependencies (ADR 0005).
- Every behavior change comes with a story or scenario fixture. If a rule is new, update the RFP too.
- Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change.
- Do not commit, push, tag, publish, or open issues or pull requests unless the maintainer asks. The maintainer reviews every change and must be able to explain it (ADR 0016).
- Take today's date from the system (`date`). Never guess dates in ADRs or the changelog.

## Commands

```bash
uv sync                          # environment, including Python 3.14
uv run prek install              # once per clone
uv run prek run --all-files      # ruff, format, codespell, yamllint, zizmor, mypy, hygiene
uv run pytest                    # tests
make check                       # everything CI runs
```

## Python

- Python 3.14 only (ADR 0013). Annotations are evaluated lazily (PEP 649). Do not quote forward references, and do not add `from __future__ import annotations`.
- Python 3.14 allows `except A, B:` without parentheses. Do not flag it.
- Records are `@dataclass(frozen=True, slots=True, kw_only=True)`.
- Type hints everywhere. mypy runs in strict mode. Prefer concrete types to `Any`.
- Google-style docstrings on public modules, classes, and functions.

## Style

These follow Home Assistant core.

- Comments explain why, never what. No section or divider comments. Never justify a change by describing the old code.
- Keep `try` blocks small, and catch only exceptions you expect.
- When a key is guaranteed to exist, use `data["key"]`, not `data.get("key")`.
- No `print`. The core logs nothing above DEBUG. State is visible through events and queries.

## Tests

- Stories and scenarios are YAML fixtures under `tests/fixtures/`, run by one runner (ADRs 0024 and 0027).
- Annotate the types of test parameters.
- Merge near-duplicate tests with `pytest.mark.parametrize` and `pytest.param(..., id=...)`.
- No branching inside tests.
- Invariants use Hypothesis. `HYPOTHESIS_PROFILE=ci` runs more examples.
- Never sleep in a test. Pass times.
- Story and scenario numbers are ids that fixtures cite. Never renumber them. A new one takes the next number.
- Branch coverage stays at or above 95 percent.

## Layout

```text
src/health_tree/            engine (and, as they land, policy/ and conventions.py)
tests/                      unit tests, property tests, fixtures
docs/rfp.md                 design of record
docs/adr/                   decisions
```

## Commits

Use Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`. One logical change per commit. The maintainer may commit small documentation and repository housekeeping changes directly on `main` after reviewing the diff. Changes to behavior, APIs, dependencies, or release contents use a branch and pull request. The authorization rule above still applies to every commit and push.

## Writing docs

Docs are for people, not for the next agent.

- Start from the reader's questions: what does it do, what would I use it for, why does it exist, how does it work, how do I set it up, and what doesn't it do. Get the answers from the code. Other docs may be stale.
- One page, one job: a tutorial, a how-to, reference, or an explanation (Diátaxis). The README is the front door: what it is, why you'd want it, how to install it, and where to go next.
- Write in a plain, professional voice. Never use the first person (no "I" or "my house"), and never name the maintainer in the docs. The product is the subject ("Homeostatic watches..."), and guides talk to the reader as "you". Contractions are fine where they read naturally. No hype, no slogans, no jokes.
- Say each thing once. Caveats go in one limitations section, not in every paragraph.
- Keep these out of user docs: inline ADR, rule or scenario numbers; version history ("since 0.3.0"); test counts and coverage; hard-wrapped prose.
- Cut the AI tells: "X, not Y" contrasts, a bold label on every bullet, lists of three for rhythm, noun piles, passive voice that hides who does what, and stock words like robust, seamless, comprehensive, leverage and ensure.
- When behavior changes, edit the section that owns it rather than bolting a new section on wherever is handy.
- Don't invent facts. If something needs the maintainer's knowledge, ask before writing it.
