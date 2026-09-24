# Health Tree

A platform-agnostic library for health across a dependency tree.

A node reports only what its own checks saw. A failed dependency mutes notifications for the nodes that depend on it, and it does not rewrite their status. Home Assistant is the planned first adapter. It is not part of this package.

The design of record is [docs/rfp.md](docs/rfp.md). The package is a scaffold until the scenarios in that document are accepted.

## Development

```bash
pip install -e ".[dev]"
pytest
```
