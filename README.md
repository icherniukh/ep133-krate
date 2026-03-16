# ep133-krate

The EP-133 KO-II has no public API and no documented protocol. Managing
samples means using the official EP Sample Tool — until now.

**krate** is a full sample manager for the EP-133 — CLI and terminal UI today,
with native desktop and mobile apps on the roadmap. The MIDI SysEx protocol
was reverse-engineered from USB captures of the official app. The full
specification is published in [PROTOCOL.md](PROTOCOL.md) — opcodes, byte
layouts, session state machine, confirmed findings and honest gaps — so the
community doesn't have to start from scratch.

---

## Install

**Requires Python 3.11+ and sox.**

```bash
git clone https://github.com/icherniukh/ep133-krate
cd ep133-krate
python -m venv .venv && source .venv/bin/activate   # uv: uv venv && source .venv/bin/activate
pip install -e .
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
krate tui               # browse and manage samples interactively
krate ls                # list slots 1–99
krate put kick.wav 43   # upload to slot 43
krate get 43 kick.wav   # download slot 43
```

<!-- TODO: demo.gif -->

---

## Terminal UI

```bash
krate tui
```

Arrow keys navigate slots. `Enter` opens the action menu. `?` shows all
keybindings. Waveforms are rendered in braille using a SHA-256 fingerprint
cache — slots already loaded skip the MIDI round-trip on subsequent views.

<!-- TODO: screenshot.png -->

---

## CLI Reference

All commands accept `--device <name>`, `--quiet`, and `--json`.
Run `krate --help` for the full list.

### Inspect

```bash
krate ls              # slots 1–99
krate ls --page 2     # slots 100–199
krate ls --all        # all 999 slots
krate info 43         # name, size, duration
krate info 1-50       # range
```

### Transfer

```bash
krate get 43 ./kick.wav
krate put ./kick.wav 43
krate put ./kick.wav 43 --name "afterparty kick"
```

### Manage

```bash
krate mv 43 50
krate cp 43 50
krate rm 43
krate rename 43 "new name"
```

### Optimize

The EP-133 native sample rate is 46875 Hz (24 MHz ÷ 512, Cirrus Logic CS42L52).
Stereo files and files above that rate use more flash than necessary.

```bash
krate optimize 43       # stereo → mono, downsample if needed
krate optimize-all      # optimize every stereo sample in place
krate squash            # dry run: show how slot gaps would be filled
krate squash --execute
```

---

## Roadmap

krate is Phase 1 of a larger project.

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | CLI — full sample management | ✅ complete |
| 2 | Terminal UI — interactive browser, waveform preview | 🔧 in progress |
| 3 | Native desktop, mobile, and web apps | planned |

The protocol specification in PROTOCOL.md is the foundation for all of it.

---

## How It Works

### Reverse-engineered protocol

The EP-133 exposes no public API. Every operation — upload, download, rename,
delete, metadata query — is implemented against a hand-written spec derived
from USB captures of the official EP Sample Tool. [PROTOCOL.md](PROTOCOL.md)
documents each SysEx opcode, byte offset, encoding, and message sequence,
along with confirmation status for every finding.

Notable discoveries from the capture analysis:

- The device stays in download mode after a completed transfer and silently
  drops the next command. Every `get()` call issues a re-initialization
  sequence to reset state.
- `GET_META (0x75)` returns stale metadata for deleted slots. Runtime inventory
  bypasses it, querying the `/sounds` filesystem node directly.
- Metadata pagination is stateless: each `page=N` request independently
  returns the Nth chunk of the JSON response. The official app sends page=0
  and page=1 simultaneously without waiting for a response.
- Upload audio is little-endian s16, sent verbatim — confirmed by byte-for-byte
  comparison against a real USB capture.

### 7-bit encoding (Packed7)

MIDI SysEx is a 7-bit-clean channel — any byte with the high bit set ends the
message. Binary data (PCM audio, JSON metadata) must be re-encoded before
transmission. `Packed7` does this: every 8 bytes of input become 9 bytes of
output, high bits packed into a leading byte. Implemented in
`src/core/types.py`, round-trip verified in the test suite.

### Descriptor DSL for protocol messages

Protocol messages are defined declaratively using field descriptors:

- `src/core/types.py` — primitive wire types: `U7`, `BE16`, `Packed7`
- `src/core/models.py` — message structures composed from typed field descriptors
- `src/core/operations.py` — stateful multi-step transactions (e.g.
  `UploadTransaction`: PUT_INIT → data chunks → sentinel → VERIFY →
  METADATA_SET → VERIFY)
- `src/core/client.py` — thin transport layer, no knowledge of `Packed7`
  or JSON packing

Serialization and deserialization are symmetric by construction. The transport
layer is completely isolated from encoding concerns.

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

### TUI threading

`EP133Client` is synchronous and blocking. The Textual TUI runs on an async
event loop. All device I/O goes through `DeviceWorker`, which runs client
calls in a background thread via `run_worker(fn, thread=True)`. The worker
accepts a `waveform_cache_checker` callback — if the fingerprint is already
cached, the MIDI round-trip is skipped entirely.

### Test suite

379 unit tests. No device required for any of them.

- Capture-based protocol tests verify serialized bytes against real USB traffic
- Encoding tests assert round-trip symmetry for `U7`, `BE16`, `Packed7`, and
  slot encoding variants
- CLI tests cover all command functions via `Mock(spec=View)`
- Dedicated modules for waveform fingerprinting, squash algorithm, and
  optimize flow
- Fuzz tests (`test_protocol_fuzz.py`) exercise response parsers against
  malformed payloads

---

## Protocol Gaps

Remaining unknowns:

1. **Playback (0x76)** — TX format, parameters, and device response all
   unknown. Audition uses a workaround; true playback triggering is not
   implemented.
2. **Memory statistics** — the device sends `free_space_in_bytes` in a known
   RX payload, but the TX command that triggers it hasn't been identified.
   `krate` falls back to 64 MB.
3. **Device info (0x77/0x78)** — RX response format known; TX request not
   confirmed. `device_info()` always returns `None`.
4. **Pad mapping (Groups B/C/D)** — Group A fully captured. Groups B/C/D
   partial.
5. **Project listing (0x7C)** — project switching documented; listing
   available projects not yet captured.

Contributions in the form of USB captures are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for setup and capture workflow.

---

## Architecture

```
src/
  cli/        # Argument parsing, view construction, 16 cmd_* functions
  core/       # EP133Client, wire types, protocol models, operations
  tui/        # Textual app, DeviceWorker, waveform cache and rendering
krate.py      # Entry point
PROTOCOL.md   # Reverse-engineered protocol specification
```

Dependencies: mido (MIDI I/O), textual (TUI), sox (audio conversion via
subprocess). The core layer has no knowledge of the CLI or TUI layers.

---

## Contributing

Protocol reverse-engineering is ongoing. Useful contributions:

- USB traffic captures from the official EP Sample Tool
- Tests and analysis for the protocol gaps listed above
- CLI and TUI feature work

The project tracks issues with beads <!-- TODO: link beads repo -->. Core
contributors: `bd list` for the full backlog, `bd ready` for unblocked work.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, capture
instructions, and architecture decision log.
