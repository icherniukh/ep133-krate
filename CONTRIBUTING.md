# Contributing

This is a reverse-engineering project. Protocol understanding is incomplete —
contributions in the form of device captures, protocol analysis, tests, and
CLI/TUI features are all welcome.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
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

The authoritative gap list lives in [PROTOCOL.md § Known Issues](PROTOCOL.md#known-issues).
See `docs/capture-wishlist.md` for capture scenarios and exact commands needed to fill them.

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

`main()` constructs the view from flags. All `cmd_*` functions are unit-testable
via `Mock(spec=View)` — no stdout patching needed.

### Descriptor DSL for protocol messages (2026-02-24)

Protocol messages are defined declaratively using field descriptors:
- `src/core/types.py` — primitive types (`U7`, `BE16`, `Packed7`)
- `src/core/models.py` — message structures using `U7Field`, `BE16Field`, `JsonField`
- `src/core/operations.py` — stateful multi-step operations (e.g., `UploadTransaction`)
- `src/core/client.py` — thin transport layer, knows nothing about `Packed7` or JSON packing

This gives 100% serialization/deserialization symmetry with no transport leakage.
