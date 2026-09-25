# Health Tree

A platform-agnostic library for health across a dependency graph.

- A node reports only what its own checks saw.
- A failed dependency mutes notifications for the nodes that depend on it, and it does not rewrite their status.
- An episode is as important as the most important thing its root takes down.
- An attention policy decides who hears what, how loudly, and when.

Home Assistant is the planned first consumer. Its integration is not part of this package.

**Status: design.**

- The design of record is [docs/rfp.md](docs/rfp.md) (version 0.2).
- Decisions are in [docs/adr](docs/adr/README.md).
- No engine code will be written until the types, stories, and scenarios in the RFP are accepted.

## What the library will contain

| Part | Module | Owns |
| --- | --- | --- |
| Engine | `health_tree` | Graph, checks, episodes, importance, quiet windows, snapshots, queries |
| Attention policy | `health_tree.policy` | Rules, recipients, loudness, quiet hours, digests, reminders |
| Conventions | `health_tree.conventions` | Standard reasons, categories, and label names |

The library is pure Python 3.14. It does no I/O, uses no threads or event loop, reads no clock, and has no runtime dependencies. The integration supplies observations and the current time, and carries out deliveries.

## Development

```bash
uv sync
uv run prek install
make check
```

See [CONTRIBUTING.md](CONTRIBUTING.md). AI agents: see [AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE)
