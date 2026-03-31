# ko2-tools Project Instructions

## Task Folder Pattern
Use **type-first** pattern: `type_MMDDYY_codename/`

---

## Protocol and Hardware Rules (ENFORCE EVERY SESSION)

Before making any protocol claim, constant reference, or code change touching the device wire format:

1. Read `PROTOCOL.md` — primary source for all SysEx opcodes, byte formats, slot encoding
2. Read `docs/PROTOCOL_EVIDENCE.md` — forensic notes, confirmed vs speculative findings

**Never guess.** If a value is not in the docs, say "I cannot find this in PROTOCOL.md — please verify."
For every protocol constant or hardware behavior, cite the exact file and approximate location.
If you cannot find a source, say explicitly: "I am assuming this — please verify."

Do NOT trial-and-error on the device. Unknown behavior means capture first.

---

## Source of Truth Hierarchy

| Question | Source |
|----------|--------|
| Protocol opcodes, byte offsets | `PROTOCOL.md` |
| Phase status, what's done | Beads (`bd list`) |
| Forensic/capture evidence | `docs/PROTOCOL_EVIDENCE.md` |
| Slot/node addressing | `ep133-device` skill |
| Wire format details | `ep133-protocol` skill |
| TUI threading patterns | `.claude/skills/ko2-tui-threading.md` |

Do NOT infer project status from `git status` or recent file timestamps. Use `bd list` (Beads).

---

## Audio Format Facts (Do Not Guess These)

- Sample rate: **46875 Hz** (24 MHz / 512, Cirrus Logic CS42L52)
- OS 2.0+: sub-46875 Hz samples stored at original rate — do NOT upsample
- Upload audio format: **LE s16 as-is** — WAV frames sent unchanged, no byte swap
- Download: device sends raw LE s16 PCM, NOT a RIFF WAV
- Slot encoding varies by operation — always check PROTOCOL.md first

---

## Fabrication Policy

Never fabricate data, ratings, or metrics. If you cannot access real data, say so.
When corrected on an approach, fully internalize the correction. Do not revert in the same session.

---

## Architecture (post ARCH-001 src/ restructure)

### CLI layer — `src/cli/`
- `cli_main.py` — `main()` entry point, view construction, dispatch
- `parser.py` — `build_parser()`, `validate_slot()`, `parse_range()`; mv/cp/rm use `aliases=[]`
- `display.py` — `View` protocol + `TerminalView`/`SilentView`/`JsonView`/`SampleFormat`
- `cmd_audio.py` — `cmd_optimize`, `cmd_optimize_all`, `cmd_audition`, `cmd_play`
- `cmd_slots.py` — `cmd_ls`, `cmd_mv`, `cmd_cp`, `cmd_rm`, `cmd_rename`, `cmd_squash`
- `cmd_system.py` — `cmd_info`, `cmd_backup`, `cmd_fingerprint`, plus others
- `cmd_transfer.py` — `cmd_put`, `cmd_get`
- `formatters.py`, `naming.py`, `prompts.py`, `sysinfo.py` — shared CLI helpers

### Core layer — `src/core/`
- `client.py` — `EP133Client` context manager, synchronous/blocking, uses mido
- `models.py` — protocol message descriptors
- `types.py` — wire-level types and constants
- `operations.py` — multi-step transaction operations
- `ops.py` — device operations (mv/cp/rm at protocol level)
- `audio.py` — DSP/analysis utilities (pure functions, no device I/O)
- `backup.py` — backup copy helper

### TUI layer — `src/tui/`
- `app.py` — `TUIApp` (~1041 lines), main Textual app
- `ui.py` — `DetailsWidget`, `HelpModal`
- `worker.py` — `DeviceWorker`, threaded MIDI ops
- `waveform_widget.py`, `waveform_store.py` — waveform rendering pipeline

### Entry point
- `krate.py` — thin shim, calls `src/cli/cli_main.main()`

**View protocol rule:** All CLI output goes through `view: View`. No bare `print()` in `cmd_*`.
**TUI threading rule:** `EP133Client` is synchronous. Always `run_worker(fn, thread=True)`.

---

## Test Suite

Run with: `python3 -m pytest tests/unit/ -v`
Run after any functional change. Do not proceed past a regression.

---

## Mobile / iOS Build (BeeWare + Briefcase)

### Source of truth hierarchy (mobile layer)
| Question | Source |
|----------|--------|
| Briefcase config | `src/ios/pyproject.toml` |
| App entry point | `src/app/__main__.py` → `src/app/app.py` |
| iOS transport | `src/app/transport/ios.py` (rubicon-objc) |
| Source symlinks | `src/ios/src/{core,app}` → `src/{core,app}` |

### Build venv
- Location: `.venv-mobile/` (Python 3.12, **not** the project root venv)
- Create: `python3.12 -m venv .venv-mobile && .venv-mobile/bin/pip install briefcase toga rubicon-objc`
- Never use the root `.venv` for mobile builds — it may contain desktop-only extensions that break Briefcase

### Build commands (run from repo root)

```bash
make ios-create   # briefcase create iOS  — scaffold Xcode project
make ios-build    # briefcase build iOS   — compile
make ios-run      # briefcase run iOS -d 446DA412-2BE7-43A6-BA99-26B85E010A93
make ios          # all three in sequence
```

Manual equivalents (cd into `src/ios/` first):
```bash
cd src/ios
../../.venv-mobile/bin/briefcase create iOS
../../.venv-mobile/bin/briefcase build iOS
../../.venv-mobile/bin/briefcase run iOS -d 446DA412-2BE7-43A6-BA99-26B85E010A93
```

### Simulator
- UUID: `446DA412-2BE7-43A6-BA99-26B85E010A93` — use this exact UUID every time
- Logs: `make ios-logs` (streams NSLog output from the simulator for the Krate process)

### rubicon-objc correctness rules (iOS transport layer)
- `NSData → bytes`: use `py_from_ns(ns_data)` — never `ns_data.bytes[:n]` (c_void_p not subscriptable)
- `bytes → NSData`: use `ns_from_py(data)` — never `ObjCClass("NSData").dataWithBytes_length_()`
- `NSNumber bool`: call `.boolValue` — `bool(NSNumber(0))` is always `True`
- `NSArray iteration`: plain `for item in ns_array:` or `ns_array[i]` — `ObjCListInstance` supports both
- `NSString → str`: `str(ns_str)` or `py_from_ns(ns_str)`
- `asyncio.to_thread`: safe for pure data operations; avoid for UI mutations or run-loop-sensitive ObjC calls
