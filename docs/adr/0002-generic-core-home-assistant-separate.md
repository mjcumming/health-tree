# ADR 0002: A generic library; the Home Assistant integration in its own repository

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** Michael Cumming

## Context

Home Assistant has the inventory but no health layer. Building the model inside a Home Assistant integration would tie it to one inventory, and every new kind of failure would become a special case.

The same split already works in two of the maintainer's projects: home-topology (library) with Topomation (integration), and pywiim (library) with wiim (integration).

Home Assistant expects this shape. Its development checklist requires that "All communication to external devices or services must be wrapped in an external Python library hosted on pypi." Its dependency-transparency rule asks for an OSI-approved license, publication on PyPI from a public CI pipeline, and tagged releases that match PyPI versions.

## Decision

- `health-tree` is a platform-agnostic library published on PyPI.
- It never imports Home Assistant.
- It has no runtime dependencies.
- It ships `py.typed`.
- The Home Assistant integration, meaning the catalog and the adapter, lives in its own repository and depends on released versions of this library.

## Options considered

- **Build it inside the integration.** Fastest start. The model bends to Home Assistant, and nothing can be tested without it.
- **One repository for both.** It couples releases, and HACS expects one integration per repository.
- **Use an existing server such as Alertmanager or Icinga.** Heavy to run. Neither has episodes, importance, or views as this design needs them. See the prior-art review in the project notes.

## Consequences

- The engine can be tested in milliseconds without Home Assistant.
- With no dependencies, the library cannot conflict with Home Assistant's pinned package constraints.
- A change that needs both sides takes two pull requests: library first, release, then integration.
