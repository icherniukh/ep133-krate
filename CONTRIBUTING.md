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

### iOS app

On macOS, install Xcode 26 or later with an iOS 26+ simulator runtime. From
the repository root, install the Briefcase version declared in
[`src/ios/pyproject.toml`](src/ios/pyproject.toml) and build the app.

```bash
python3.12 -m venv .venv-mobile
.venv-mobile/bin/python -m pip install --upgrade pip
.venv-mobile/bin/python -m pip install --group src/ios/pyproject.toml:ios-build
make ios
```

When the iOS template or deployment target changes, run `make ios-create` and
confirm replacement of the generated Xcode project. Use `make ios-run
IOS_SIM=<UDID>` to select a specific iOS 26+ simulator.

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

## Protocol research

See the [wire reference](PROTOCOL.md), [firmware and evidence matrix](docs/protocol-evidence.md),
and [open capture scenarios](docs/capture-wishlist.md). Follow the
[capture guide](docs/capture-format.md) to record both directions and stamp
the device model and firmware.

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

The descriptors handle wire encoding and decoding. The transport sends and
receives the resulting frames.
