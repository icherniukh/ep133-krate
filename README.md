# ep133-krate

The EP-133 KO-II has no public API and no documented protocol. Managing
samples means using the official EP Sample Tool — until now.

**krate** is a full sample manager for the EP-133. The BeeWare app in
`src/app` is now the primary product under active development; the CLI and
terminal UI remain first-class, maintained frontends for automation,
reverse engineering, and power-user workflows. The [SysEx reference](PROTOCOL.md)
documents the byte layouts and device behavior established from official
Sample Tool captures and community hardware tests.

---

## Install

**Requires Python 3.11+ and sox.**

```bash
git clone https://github.com/icherniukh/ep133-krate
cd ep133-krate
python -m venv .venv && source .venv/bin/activate   # uv: uv venv && source .venv/bin/activate
pip install -e '.[desktop]'
brew install sox    # macOS
apt install sox     # Linux
```

Connect the EP-133 via USB, then verify it's visible:

```bash
python -c "import mido; print(mido.get_input_names())"
# e.g. ['EP-133 KO II MIDI 1']
```

If the port name differs, pass it explicitly: `krate --device "EP-133 KO II" ls`

---

## Quick Start

```bash
krate tui                               # interactive browser
krate put kick.wav 43 --name "kick"     # upload to slot 43
```

<!-- TODO: demo.gif -->

---

## Terminal UI

```bash
krate tui
```

Arrow keys navigate slots. Single-key shortcuts for every operation:
upload, download, move, copy, rename, delete, optimize, squash, and
audition. Multi-select with `Space`, bulk operations on selections.
`?` shows all keybindings. Waveforms render in braille using a SHA-256
fingerprint cache — previously viewed slots skip the MIDI round-trip.

<!-- TODO: screenshot.png -->

---

## CLI Reference

All commands accept `--device <name>`, `--quiet`, and `--json`. Run `krate --help` for the full list.

```bash
# inspect
krate ls                                # slots 1–99
krate ls --page 2                       # slots 100–199
krate ls --all                          # all 999 slots
krate info 43                           # name, size, duration
krate info 1-50                         # range

# transfer
krate get 43 ./kick.wav
krate put ./kick.wav 43
krate put ./kick.wav 43 --name "afterparty kick"

# manage
krate mv 43 50
krate cp 43 50
krate rm 43
krate rename 43 "new name"

# optimize (native rate: 46875 Hz — stereo and higher-rate files waste flash)
krate optimize 43                       # stereo → mono, downsample if needed
krate optimize-all                      # optimize every stereo sample in place
krate squash                            # dry run: show how gaps would be filled
krate squash --execute
```

---

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | CLI — full sample management | ✅ complete |
| 2 | Terminal UI — interactive browser with all operations | ✅ complete |
| 3 | BeeWare/Toga app (`src/app`) for iOS/macOS | 🚧 primary product in progress |

The protocol specification in PROTOCOL.md is the foundation for all of it.

---

## How It Works

### Descriptor DSL for protocol messages

Protocol messages are defined declaratively using field descriptors:

- `src/core/types.py` — primitive wire types: `U7`, `BE16`, `Packed7`
- `src/core/models.py` — message structures composed from typed field descriptors
- `src/core/operations.py` — multi-step transactions such as sample upload
- `src/core/client.py` — current protocol/session entry point; owns initialization,
  response matching, and recovery, alongside workflow/file policy being reviewed

The transport handles platform MIDI I/O.

### Testable CLI output (View protocol)

All CLI functions receive `view: View` as an injected parameter — a structural
protocol with 10 domain-semantic methods: `section`, `step`, `success`,
`error`, `warn`, `info`, `kv`, `progress`, `render_samples`, `sample_detail`.

| Implementation | Use |
|---|---|
| `TerminalView` | Colored ANSI output (default) |
| `SilentView` | All no-ops — `--quiet` and as test double |
| `JsonView` | Structured output for `--json` |

Every command function is unit-testable via `Mock(spec=View)` — no stdout
patching, no subprocess, no fixture complexity.

### Frontend execution model

`EP133Client` is synchronous and blocking. The Textual TUI runs on an async
event loop. All device I/O goes through `DeviceWorker`, which runs client
calls in a background thread. The worker
accepts a `waveform_cache_checker` callback — if the fingerprint is already
cached, the MIDI round-trip is skipped entirely.

The app in `src/app` is the primary product surface. The current repository is
in the middle of an app-first architecture shift: protocol/session invariants
remain concentrated in `src/core`, while reusable user-facing workflows are
planned for extraction from TUI-specific execution code so the app, TUI, and CLI
can share them without regressing existing frontend behavior or test coverage.
See [`docs/architecture/ARCH-002-app-first-core-ui.md`](docs/architecture/ARCH-002-app-first-core-ui.md).

### Test suite

The unit suite runs without a device; hardware end-to-end tests are separate.

- Capture-based tests check specific request layouts and uploaded PCM bytes
  against recorded USB traffic
- Encoding tests exercise `U7`, `BE16`, `Packed7` and slot encoding variants
- CLI tests use `Mock(spec=View)` to check command output
- Dedicated modules for waveform fingerprinting, squash algorithm, and
  optimize flow
- Fuzz tests (`test_protocol_fuzz.py`) exercise response parsers against
  malformed payloads

---

## Protocol coverage

Krate's version-stamped captures cover OS **2.0.5**. Community hardware
results cover **2.5.1**, including project TAR reads and writes. The
[operation matrix](docs/protocol-evidence.md#operation-coverage) tracks
evidence and implementation for each operation.

See [what changed from 2.0.5 to 2.5.1](docs/protocol-evidence.md#firmware-changes-from-205-to-251)
and the [capture scenarios for remaining gaps](docs/capture-wishlist.md).

---

## Architecture

```
src/
  app/        # Primary Toga/BeeWare product surface
  cli/        # Command-line frontend and automation surface
  core/       # Transport, protocol/session logic, shared device operations,
              # audio helpers, waveform cache
  tui/        # Textual frontend and power-user tooling
krate.py      # Entry point
PROTOCOL.md   # Reverse-engineered protocol specification
```

Dependencies: mido (MIDI I/O), textual (TUI), sox (audio conversion via
subprocess). The core layer is intended to own transport, protocol/session
behavior, and shared workflows without depending on the CLI, TUI, or app UI
layers.

---

## Contributing

Protocol reverse-engineering is ongoing. Useful contributions:

- USB traffic captures from the official EP Sample Tool
- Tests and analysis for the protocol gaps listed above
- App, CLI, and TUI feature work

The project tracks issues with beads <!-- TODO: link beads repo -->. Core
contributors: `bd list` for the full backlog, `bd ready` for unblocked work.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, capture
instructions, and architecture decision log. The current app-first boundary
decision is documented in
[`docs/architecture/ARCH-002-app-first-core-ui.md`](docs/architecture/ARCH-002-app-first-core-ui.md).

---

## License

Copyright (c) 2026, Ivan Cherniukh. [MIT](LICENSE)
