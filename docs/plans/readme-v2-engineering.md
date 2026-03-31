# ep133-krate

A sample manager for the Teenage Engineering EP-133 KO-II — built on a fully
reverse-engineered MIDI SysEx protocol. No official API exists. All opcodes,
encoding schemes, and session state machine were discovered by capturing USB
traffic from the official app and working backward from raw bytes.

## How It Works

### The protocol problem

The EP-133 communicates via MIDI SysEx. The official EP Sample Tool provides no
documentation, no SDK, and no public wire format. Everything here was derived by:

1. Running `midi_proxy.py` as a man-in-the-middle between the official app and the device
2. Capturing bidirectional traffic to `.jsonl` files
3. Correlating request/response pairs to identify opcodes and field layouts
4. Writing tests that replay real captures to lock in the understanding

Known opcodes (partial list):

| Opcode | Direction | Status     | Purpose                         |
|--------|-----------|------------|---------------------------------|
| `0x6C` | TX        | Confirmed  | Data chunk (upload)             |
| `0x6D` | TX        | Confirmed  | End-of-transfer sentinel        |
| `0x75` | TX        | Confirmed  | `GET_META` — stale for deleted slots |
| `0x76` | TX        | **Unknown**| Audition/playback               |
| `0x7C` | TX        | Confirmed  | Project switch                  |
| `0x0B` | TX        | Confirmed  | VERIFY — metadata doesn't persist without it |

The slot encoding varies by operation type: upload/download/delete use raw 16-bit
big-endian; metadata queries use little-endian. Slots are 1–999. All binary
payloads use Packed7 (7-bit clean) encoding because MIDI reserves the high bit.

### Audio format

Native sample rate: **46875 Hz** (24 MHz / 512, Cirrus Logic CS42L52 codec).
Upload format: LE s16 PCM, sent as-is. The device does not want a RIFF header.
Download returns the same raw LE s16 — not a WAV. OS 2.0+ stores sub-46875 Hz
files at their original rate; `krate optimize` only downsamples when needed.

### Architecture

Three layers with hard boundaries:

```
src/cli/       View protocol + 16 cmd_* functions (display, dispatch, argument handling)
src/core/      Protocol implementation (client, models, types, operations) — zero UI leakage
src/tui/       Textual app + threaded DeviceWorker (EP133Client is synchronous)
```

**View protocol** (`src/cli/display.py`): all 16 `cmd_*` functions receive
`view: View` — a protocol with 10 domain-semantic methods (`section`, `step`,
`success`, `error`, `kv`, `render_samples`, ...). Three implementations:
`TerminalView` (ANSI output), `SilentView` (no-ops, used for `--quiet`),
`JsonView` (structured output for `--json`). Unit tests use `Mock(spec=View)` —
no stdout patching required.

**Descriptor DSL** (`src/core/`): protocol messages are defined declaratively.
`types.py` defines primitive types (`U7`, `BE16`, `Packed7`). `models.py` builds
message structures from `U7Field`, `BE16Field`, `JsonField` descriptors.
`operations.py` wraps stateful multi-step transactions (upload, download).
`client.py` is a thin transport — knows nothing about Packed7 or JSON packing.
Serialization and deserialization are symmetric by construction.

**TUI threading**: `EP133Client` is blocking/synchronous (mido constraint). The
Textual app dispatches all device I/O through `DeviceWorker` with
`run_worker(fn, thread=True)`. The waveform pipeline (`waveform_widget.py`,
`waveform_store.py`) skips MIDI entirely on cache hits via a
`waveform_cache_checker` callback injected into the worker.

### Test strategy

379 unit tests. No device required for the full suite.

- **Capture-based protocol tests**: `test_upload_capture.py` replays a real USB
  capture byte-for-byte to verify the upload sequence against ground truth.
- **Fixture-based audio tests**: `tests/fixtures/kick-46875hz.wav` (synthetic,
  copyright-free) drives encode/decode tests without device dependency.
- **View protocol tests**: all `cmd_*` functions tested via `Mock(spec=View)`.
- **Wire robustness**: parametrized boundary tests for U7/U14 encoding.

Run tests:

```bash
pytest tests/unit/
```

## Install

```bash
pip install mido[ports-rtmidi] textual
brew install sox   # macOS
apt install sox    # Linux
```

Clone and run directly (packaging in progress):

```bash
git clone https://github.com/ivankovnatsky/ep133-krate
cd ep133-krate
python krate.py --help
```

## Usage

### TUI

```bash
krate tui
```

Arrow keys to navigate. `?` for keybindings. All operations available
interactively: move, copy, rename, optimize, squash, audition.

### CLI

```bash
krate ls                              # list first 99 slots
krate ls --all                        # all 999 slots
krate info 43                         # name, size, duration
krate info 1-50                       # range

krate get 43 ./kick.wav               # download slot 43
krate put ./kick.wav 43               # upload to slot 43
krate put ./kick.wav 43 --name "kick"

krate mv 43 50
krate cp 43 50
krate rm 43
krate rename 43 "new name"

krate optimize 43                     # stereo→mono, downsample if needed
krate optimize-all                    # all stereo samples
krate squash                          # preview gap-fill
krate squash --execute
```

Pass `--device <port>` to target a specific MIDI port. List available ports:

```bash
python -c "import mido; print(mido.get_input_names())"
```

## Protocol gaps

Several operations are still unknown. See `CONTRIBUTING.md` for the full list
and `docs/capture-wishlist.md` for exact capture steps. Short version:

- **0x76 (audition)** — TX format entirely unknown
- **Project listing** — switching documented; listing available projects is not
- **Memory statistics** — device reports `free_space_in_bytes` but the TX trigger is unknown
- **Pad mapping (Groups B/C/D)** — Group A fully captured; B/C/D partial

Captures go in `captures/`. The MIDI proxy handles both directions:

```bash
python midi_proxy.py --proxy --spoof captures/sniffer-<name>.jsonl
python midi_proxy.py --pretty captures/sniffer-<name>.jsonl
```

## Documentation

- [Protocol Specification](PROTOCOL.md)
- [Protocol Evidence](docs/PROTOCOL_EVIDENCE.md)
- [Contributing](CONTRIBUTING.md)
