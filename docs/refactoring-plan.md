# Repo structure plan

> **Planning document.** The source tree has not been refactored yet. This describes the intended direction, not the current state.

This plan is based on what the repo actually does today, not on an idealized library architecture.

## What the project really is

The project has four real concerns:

1. EP-133 device workflows
2. User interfaces on top of those workflows
3. Reverse-engineering tooling
4. Tests and documentation

That means the source tree should be organized around product areas, not around every internal implementation concept.

## What should not drive the top-level layout

These distinctions are useful inside code, but not as repo-defining product areas:

- `protocol` versus `device`
- `transfer` as a standalone subsystem
- generic `backup` as a catch-all name

`transfer` is part of device behavior. `protocol` is a layer inside device-facing code, but the repo is not primarily a reusable protocol library.

## Recommended direction

If the repo is later packaged, a reasonable shape is:

```text
ko2/
  device/
    protocol.py
    client.py
    operations.py
    safety_backup.py
  cli/
  tui/
  tooling/
    capture/
    emulator/
tests/
docs/
scripts/
```

This reflects current responsibilities without inventing future placeholders.

## Backup reconsidered

The current file `ko2_backup.py` is not a backup subsystem in the user-facing sense.

It only creates local rollback snapshots in `.ko2-backups/` before destructive device operations.

So the current naming should be reconsidered as:

- `device/safety_backup.py`, or
- `device/snapshots.py`

## What to avoid

- Do not add `web/`, `mobile/`, or `services/` directories before they exist.
- Do not create a vague `core/` bucket unless a clear dependency boundary actually emerges.
- Do not publish internal agent-configuration notes as first-class project docs.

## Documentation layout

```
README.md          — setup, CLI reference, troubleshooting (user-facing)
PROTOCOL.md        — protocol specification + slot/node addressing
CONTRIBUTING.md    — dev setup, protocol gaps, architecture decisions
AGENTS.md          — agent rules, issue tracking, architectural decisions
docs/
  protocol-evidence.md  — forensic captures and wire validation
  capture-wishlist.md   — scenarios for filling protocol gaps
  capture-format.md     — midi_proxy.py capture format reference
  refactoring-plan.md   — this file
```
