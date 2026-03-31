# ep133-krate

A sample manager for the Teenage Engineering EP-133 KO-II, built on a fully
reverse-engineered MIDI SysEx protocol. There is no official API. Everything
here was derived from USB traffic captures of the official app.

```bash
krate ls --all          # browse all 999 sample slots
krate put kick.wav 43   # upload to slot 43
krate tui               # terminal UI: browse, upload, preview waveforms
```

---

## The Problem

The EP-133 KO-II exposes no public API and no documented SysEx spec. The only
way to manage samples programmatically is to reverse-engineer the MIDI traffic
the official tool sends over USB — opcodes, byte encoding, message sequencing,
error recovery — and reimplement it from scratch.

This project is that reimplementation: a full sample management CLI and
terminal UI, built against a hand-documented protocol spec derived from raw
packet captures.

---

## Install

```bash
pip install mido[ports-rtmidi] textual
brew install sox        # macOS
apt install sox         # Linux / WSL
```

Connect the EP-133 via USB, then verify it's visible:

```bash
python -c "import mido; print(mido.get_input_names())"
```

If the port name differs from the default, pass it explicitly:

```bash
krate --device "EP-133 KO II" ls
```

---

## Command Reference

### Listing and inspecting

```bash
krate ls              # first 99 slots
krate ls --page 2     # slots 100–199
krate ls --all        # all 999 slots
krate info 43         # name, size, duration for slot 43
krate info 1-50       # range query
```

### Transferring samples

```bash
krate get 43 ./kick.wav
krate put ./kick.wav 43
krate put ./kick.wav 43 --name "afterparty kick"
```

### Managing slots

```bash
krate mv 43 50
krate cp 43 50
krate rm 43
krate rename 43 "new name"
```

### Optimizing memory

The EP-133 native sample rate is 46875 Hz (24 MHz / 512, Cirrus Logic CS42L52
codec). Stereo files and files above that rate waste flash storage.

```bash
krate optimize 43       # convert slot 43: stereo → mono, downsample if needed
krate optimize-all      # optimize every stereo sample in place
krate squash            # dry run: show how slot gaps would be filled
krate squash --execute  # execute the gap-fill sequence
```

### Terminal UI

```bash
krate tui
```

Arrow keys navigate slots. `Enter` opens the action menu. `?` shows all
keybindings. Waveforms are rendered in braille characters using a SHA-256
fingerprint cache — already-loaded waveforms skip the MIDI round-trip.

---

## Under the Hood

### Reverse-engineered protocol

Every operation (upload, download, rename, delete, metadata query) is
implemented against a hand-written protocol spec (`PROTOCOL.md`) derived from
USB captures of the official EP Sample Tool. The spec documents each SysEx
opcode, byte offset, encoding, and message sequencing — including confirmed
findings, speculative inferences, and known unknowns.

Notable findings from the capture analysis:

- The device stays in download-mode after a completed transfer and silently
  drops the next command. Every `get()` call issues a re-initialization
  sequence to reset state.
- `GET_META (0x75)` returns stale metadata for deleted slots. Runtime slot
  inventory bypasses it entirely, querying the `/sounds` filesystem node
  directly.
- Page pagination for metadata queries is stateless and index-based — each
  `page=N` request independently returns the Nth chunk of the JSON response.
  The official app sends page=0 and page=1 simultaneously without waiting.
- Upload audio format is little-endian s16 verbatim — no byte swap. This was
  confirmed by byte-for-byte comparison against a real USB capture.

### 7-bit MIDI encoding (Packed7)

MIDI SysEx payloads cannot contain bytes with the high bit set. Binary data
(PCM audio, JSON metadata) is encoded with a custom `Packed7` scheme: every
8 bytes of input become 9 bytes of output, with the high bits packed into a
leading byte. Decoding is the exact inverse. This is implemented in
`src/core/types.py` and round-trip verified in the test suite.

### Descriptor DSL for protocol messages

Protocol messages are defined declaratively using field descriptors:

- `src/core/types.py` — primitive wire types: `U7`, `BE16`, `Packed7`
- `src/core/models.py` — message structures composed from `U7Field`,
  `BE16Field`, `JsonField`, etc.
- `src/core/operations.py` — stateful multi-step transactions (e.g.,
  `UploadTransaction`: PUT_INIT → data chunks → sentinel → VERIFY → METADATA_SET → VERIFY)
- `src/core/client.py` — thin transport layer, no knowledge of `Packed7` or
  JSON packing

Serialization and deserialization are symmetric by construction. The transport
layer is completely isolated from encoding concerns.

### View protocol for testable CLI output

All 16 CLI command functions receive `view: View` as an injected parameter.
`View` is a structural protocol (Python `typing.Protocol`) with 10
domain-semantic methods: `section`, `step`, `success`, `error`, `warn`,
`info`, `kv`, `progress`, `render_samples`, `sample_detail`.

Three implementations ship:

| Implementation | Use |
|---|---|
| `TerminalView` | Colored ANSI output (default) |
| `SilentView` | All no-ops — used for `--quiet` and as test double |
| `JsonView` | Structured output for `--json` |

Because output is injected rather than printed, every `cmd_*` function is unit
testable via `Mock(spec=View)` — no stdout patching, no subprocess, no
fixture complexity.

### TUI threading model

`EP133Client` is synchronous and blocking. The Textual TUI runs on an async
event loop. All device I/O goes through `DeviceWorker`, which runs client
calls in a background thread via `run_worker(fn, thread=True)`. The worker
accepts a `waveform_cache_checker` callback — if the waveform fingerprint is
already cached locally, the MIDI round-trip is skipped entirely.

### Test suite

379 unit tests. No device required for any of them.

- Capture-based protocol tests verify serialized bytes against real USB
  traffic (`tests/unit/test_upload_capture.py`)
- Encoding tests assert round-trip symmetry for `U7`, `BE16`, `Packed7`, and
  slot encoding variants
- CLI tests use `Mock(spec=View)` — all 16 command functions covered
- Waveform fingerprinting, squash algorithm, and optimize flow each have
  dedicated test modules
- Adversarial inputs (`test_protocol_fuzz.py`) exercise `parse_file_list_response`
  and `_parse_json_tolerant` against malformed payloads

---

## Protocol Gaps

These are the remaining unknowns. They are documented here because honest
accounting of what is confirmed vs. speculative is part of the engineering
discipline, not a gap to paper over.

1. **Playback (0x76)** — TX format unknown. Audition in TUI uses a
   workaround; true playback triggering is not yet implemented.
2. **Memory statistics TX** — the device sends `free_space_in_bytes` in a
   known RX payload, but the command that triggers it is not identified.
   `krate` falls back to 64 MB.
3. **Device info (0x77/0x78)** — RX response format is known; TX request
   format is not confirmed. `device_info()` always returns `None`.
4. **Pad mapping (Groups B/C/D)** — Group A fully captured and implemented.
   Groups B/C/D are partially reverse-engineered.
5. **Project listing (0x7C)** — project switching is documented; listing
   available projects is not yet captured.

Contributions in the form of USB captures are welcome. See `CONTRIBUTING.md`
for capture setup instructions.

---

## Architecture

```
src/
  cli/        # Argument parsing, view construction, 16 cmd_* functions
  core/       # EP133Client, wire types, protocol models, operations
  tui/        # Textual app, DeviceWorker, waveform cache and rendering
krate.py      # Entry point shim
PROTOCOL.md   # Hand-written protocol specification (source of truth)
```

No framework magic. Dependencies are mido (MIDI I/O), textual (TUI), and sox
(audio conversion via subprocess). The core layer has no knowledge of the CLI
or TUI layers.

---

## Contributing

Protocol reverse-engineering is ongoing. Useful contributions:

- USB traffic captures from the official EP Sample Tool (see `CONTRIBUTING.md`)
- Tests against the confirmed unknowns listed above
- CLI and TUI feature work

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, protocol capture
instructions, and the architecture decision log.
