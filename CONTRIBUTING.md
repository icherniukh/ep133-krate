# Contributing

This is a reverse-engineering project. Protocol understanding is incomplete —
contributions in the form of device captures, protocol analysis, tests, and
app, CLI, and TUI features are all welcome.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[desktop]'
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

## Releases

1. Set the release version in `pyproject.toml`, run the unit suite, and merge
   the release commit to `main`.
2. Tag that commit `v<version>` (for example, `v0.1.0`) and push that tag.
3. The release workflow verifies main ancestry and the tag/version match, runs
   unit tests, builds/checks Python wheel and source packages, and smoke-tests
   the installed wheel before creating a GitHub Release with generated notes.

PyPI publishing is optional: configure the repository secret `PYPI_TOKEN` to
publish there too. No `ENABLE_RELEASE` variable is required. This workflow does
not build native iOS apps or prove device/firmware compatibility.

Desktop CLI/TUI users install `ep133-krate[desktop]` (or `.[desktop]` from source)
to include the MIDI backend. The base package omits desktop-only dependencies
so shared core code can be used by other platforms.

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

### App-first core/UI boundaries (2026-04-02)

`src/app` is the primary product surface. The repository is being reorganized
around an app-first boundary model. CLI and TUI remain first-class,
maintained frontends; shared changes must preserve their behavior and test
coverage as well as support the app:

- transport owns platform MIDI I/O only
- protocol/session logic owns device conversation correctness
- shared application workflows sit above protocol/session logic
- UI layers bind to shared workflows instead of owning orchestration

`EP133Client` should be treated as the current protocol/session entry point,
not as a thin transport-only wrapper. `DeviceWorker` should be treated as the
current execution adapter, not as the permanent home of shared business
workflows.

See [`docs/architecture/ARCH-002-app-first-core-ui.md`](docs/architecture/ARCH-002-app-first-core-ui.md).

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
- `src/core/client.py` — current protocol/session entry point

This gives 100% serialization/deserialization symmetry with no transport leakage.
