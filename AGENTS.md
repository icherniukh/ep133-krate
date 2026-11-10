# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking.

- Run `bd prime` for the current workflow context.
- Core commands: `bd ready`, `bd show <id>`, `bd update <id> --claim`, `bd close <id>`.
- Use `bd` for persistent task tracking instead of markdown TODO lists.
- Use `bd remember` only for evergreen facts not already captured well in issue descriptions.
<!-- END BEADS INTEGRATION -->

## Key architectural decisions

### Project layout (post ARCH-001 restructure)

```
src/cli/    — CLI layer: cli_main.py, parser.py, display.py, cmd_audio.py,
              cmd_slots.py, cmd_system.py, cmd_transfer.py, formatters.py,
              naming.py, prompts.py, sysinfo.py
src/core/   — Core layer: client.py, transport.py, desktop_transport.py,
              models.py, types.py, operations.py, ops.py, audio.py, backup.py,
              waveform_store.py
src/tui/    — TUI layer: app.py, ui.py, worker.py, waveform_widget.py,
              waveform_store.py, actions.py, selectors.py, state.py
src/app/    — Primary Toga/BeeWare product surface and platform app shell;
              consumes shared core functionality; dedicated Debug UI is planned
krate.py    — thin entry-point shim → src/cli/cli_main.main()
```

### View protocol for CLI output

All `cmd_*` functions receive `view: View` (from `src/cli/display.py`).
Never use bare `print()` in command functions. Use `view.success()`, `view.error()`,
`view.kv()`, etc. If output shape is not covered cleanly by the existing methods,
extend the view layer rather than printing directly from a command. Three
implementations: `TerminalView`, `SilentView`, `JsonView`.
Tests use `Mock(spec=View)` — no stdout patching.

### Descriptor DSL for protocol messages

- `src/core/types.py` — wire primitives (`U7`, `BE16`, `Packed7`)
- `src/core/models.py` — declarative message definitions
- `src/core/operations.py` — multi-step transactions
- `src/core/client.py` — current protocol/session entry point; owns device
  conversation invariants today and is under architectural review

Build raw payload first, then apply packed7. Never pre-split values before packed7.
Slot/node fields are BE16 inside the raw payload.

### App-First Architecture

`src/app` is the primary product surface. CLI and TUI remain first-class,
maintained frontends, not secondary or legacy surfaces. Shared architecture
must serve all three, preserving CLI/TUI behavior and test coverage.

Authoritative boundary guidance lives in
`docs/architecture/ARCH-002-app-first-core-ui.md`:

- transport owns platform MIDI I/O
- protocol/session logic owns device conversation correctness
- shared application workflows sit above protocol/session logic
- UI layers bind to shared workflows rather than owning orchestration directly
