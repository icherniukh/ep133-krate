# Contributing

This is a reverse-engineering project. Protocol understanding is incomplete —
contributions in the form of device captures, protocol analysis, tests, and
CLI/TUI features are all welcome.

## Development setup

```bash
pip install mido[ports-rtmidi] textual
brew install sox  # macOS
apt install sox   # Linux
```

Run tests:

```bash
# Unit tests (no device required)
pytest

# End-to-end tests (requires a connected EP-133)
pytest -m e2e --device "EP-133"
```

## What's working

- Sample listing and inspection
- Upload and download
- Rename and delete
- Move/copy and squash flows
- Optimize and optimize-all flows
- Fingerprint and waveform cache operations
- SysEx capture proxy with pretty-printing and filtering

## Protocol gaps

These are the remaining unknowns that require further reverse-engineering.
See `docs/capture-wishlist.md` for capture scenarios and exact commands.

1. **Playback/audition (0x76)** — TX format, parameters, and device response all unknown.
   Blocking TUI audition (Tab key) and Phase 3.
2. **Project listing (0x7C)** — switching is documented, listing available projects is not captured.
3. **Memory statistics** — device returns `free_space_in_bytes` in a known RX payload,
   but the TX command that triggers it is not identified. `cmd_status` falls back to 64 MB.
4. **Pad mapping (Groups B/C/D)** — Group A fully captured (`9201–9212`).
   Groups B/C/D partial. See `docs/capture-wishlist.md` for capture steps.
5. **GET_META (0x75) reliability** — known to return stale data for deleted slots.
   Runtime inventory now uses `/sounds` + node metadata instead. Retained for audit only.
6. **Device info (0x77/0x78)** — `device_info()` always returns None. RX response is known
   but TX request format is not confirmed.

## Capturing protocol traffic

Protocol gaps are filled by sniffing traffic from the official EP Sample Tool.
See `docs/capture-wishlist.md` for specific scenarios, steps, and commands.

Quick reference:

```bash
# Intercept both directions
python midi_proxy.py --proxy --spoof captures/sniffer-<name>.jsonl

# Replay/inspect a capture
python midi_proxy.py --pretty captures/sniffer-<name>.jsonl
```

## Architecture decisions

### View-oriented CLI output (2026-03-02)

`krate` commands receive `view: View` as an injected parameter. `View` is a protocol
in `src/cli/display.py` with 10 domain-semantic methods: `section`, `step`, `success`,
`error`, `warn`, `info`, `kv`, `progress`, `render_samples`, `sample_detail`.

Three implementations:
- `TerminalView` — colored ANSI output (default)
- `SilentView` — all no-ops, used for `--quiet` and as test double
- `JsonView` — structured output for `--json`

`main()` constructs the view from flags. All 16 `cmd_*` functions are unit-testable
via `Mock(spec=View)` — no stdout patching needed.

### Descriptor DSL for protocol messages (2026-02-24)

Protocol messages are defined declaratively using field descriptors:
- `src/core/types.py` — primitive types (`U7`, `BE16`, `Packed7`)
- `src/core/models.py` — message structures using `U7Field`, `BE16Field`, `JsonField`
- `src/core/operations.py` — stateful multi-step operations (e.g., `UploadTransaction`)
- `src/core/client.py` — thin transport layer, knows nothing about `Packed7` or JSON packing

This gives 100% serialization/deserialization symmetry with no transport leakage.
