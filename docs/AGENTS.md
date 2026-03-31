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

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Version-controlled: Built on Dolt with cell-level merge
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs with git:

- Exports to `.beads/issues.jsonl` after changes (5s debounce)
- Imports from JSONL when newer (e.g., after `git pull`)
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- END BEADS INTEGRATION -->

## Key architectural decisions

### Project layout (post ARCH-001 restructure)

```
src/cli/    — CLI layer: cli_main.py, parser.py, display.py, cmd_audio.py,
              cmd_slots.py, cmd_system.py, cmd_transfer.py, formatters.py,
              naming.py, prompts.py, sysinfo.py
src/core/   — Core layer: client.py, models.py, types.py, operations.py,
              ops.py, audio.py, backup.py
src/tui/    — TUI layer: app.py, ui.py, worker.py, waveform_widget.py,
              waveform_store.py, actions.py, selectors.py, state.py
krate.py    — thin entry-point shim → src/cli/cli_main.main()
```

### View protocol for CLI output

All `cmd_*` functions receive `view: View` (from `src/cli/display.py`).
Never use bare `print()` in command functions. Use `view.success()`, `view.error()`,
`view.kv()`, etc. Three implementations: `TerminalView`, `SilentView`, `JsonView`.
Tests use `Mock(spec=View)` — no stdout patching.

### Descriptor DSL for protocol messages

- `src/core/types.py` — wire primitives (`U7`, `BE16`, `Packed7`)
- `src/core/models.py` — declarative message definitions
- `src/core/operations.py` — multi-step transactions
- `src/core/client.py` — transport only, no protocol knowledge

Build raw payload first, then apply packed7. Never pre-split values before packed7.
Slot/node fields are BE16 inside the raw payload.


--- MOBILE APP AGENT INSTRUCTIONS ---

# Mobile App — Agent Instructions

## Overview

The mobile app provides direct MIDI communication with the EP-133 KO-II from iOS (and later Android). It reuses `src/core/` (models, Packed7, protocol logic) rather than reimplementing in Swift/Kotlin.

**Stack:** BeeWare (Toga + Briefcase) for cross-platform Python GUI.

## Key Decision: Direct MIDI, Not HTTP Bridge

The original `src/app/` code uses an HTTP bridge (`httpx` → `localhost:8765`). We are replacing that with direct MIDI transport so the phone talks to the EP-133 over USB/BLE MIDI without a middleman.

Rationale:
- Eliminates the need to run a bridge service on a separate machine
- Reuses `src/core/` protocol stack directly (Packed7, SysExCmd, message descriptors)
- Real-time bidirectional MIDI (receive device responses, hotplug events)

## Architecture

```
src/app/
├── AGENTS.md              ← this file
├── __init__.py
├── app.py                 ← Toga app entry point (device picker, INIT, screen nav)
├── screens/
│   ├── slot_list.py       ← slot browser via EP133Client.list_sounds() + audition
│   └── upload_queue.py    ← upload queue via EP133Client.put()
├── transport/
│   ├── __init__.py        ← re-exports create_transport()
│   ├── base.py            ← MIDITransport ABC + EP133Client compatibility shim
│   ├── ios.py             ← iOS: ObjC MIDIBridge via rubicon-objc
│   ├── android.py         ← Android: java.midi via rubicon-java (future)
│   └── desktop.py         ← Desktop/dev: mido + rtmidi (for testing on macOS)
└── bridge/
    ├── MIDIBridge.h       ← ObjC header — public API for rubicon-objc
    └── MIDIBridge.m       ← ObjC impl — CoreMIDI lifecycle, UMP SysEx7, receive buffer
```

### Transport Abstraction (`transport/base.py`)

```python
class MIDITransport(ABC):
    """Platform-agnostic MIDI transport."""

    @abstractmethod
    def discover_devices(self) -> list[MIDIDevice]: ...

    @abstractmethod
    def connect(self, device: MIDIDevice) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_sysex(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_sysex(self, timeout: float = 1.0) -> Optional[bytes]: ...

    # EP133Client compatibility (built into base class):
    def send(self, msg) -> None: ...       # adapts mido.Message → send_sysex()
    def receive(self, timeout) -> msg: ...  # adapts receive_sysex() → mido-like msg
    def close(self) -> None: ...            # calls disconnect()
```

The screens depend only on `EP133Client` (injected by `app.py`), never on transport or platform APIs directly.

### How `src/core/` Plugs In

`EP133Client` already supports transport injection (`transport=` parameter). The `MIDITransport` base class includes a compatibility shim that translates `send(mido.Message)` / `receive(timeout)` calls to `send_sysex(bytes)` / `receive_sysex(timeout)`.

**Flow:** `app.py` creates `EP133Client(transport=MIDITransport)` on connect. The client runs its INIT handshake through the transport. Screens call `client.list_sounds()`, `client.audition()`, `client.put()` — all protocol logic in `src/core/` is used as-is.

### iOS Transport (`transport/ios.py`)

**Problem:** CoreMIDI uses C callbacks. On iOS, ctypes callbacks are risky due to W^X (write-xor-execute) restrictions — libffi cannot always generate trampolines.

**Solution:** ObjC wrapper class (`MIDIBridge`) that:
1. Manages CoreMIDI lifecycle (client, input port, output port)
2. Exposes simple methods callable via rubicon-objc
3. Handles callbacks in ObjC land, buffers received data
4. Python polls or gets notified via a simpler mechanism

```
┌─────────────┐     rubicon-objc     ┌──────────────┐     CoreMIDI
│  Python      │ ──────────────────► │  MIDIBridge   │ ──────────────► EP-133
│  transport/  │ ◄────────────────── │  (.m / .swift)│ ◄──────────────
│  ios.py      │   method calls      │               │   callbacks
└─────────────┘                      └──────────────┘
```

The ObjC `MIDIBridge` class source lives in `bridge/MIDIBridge.{h,m}` and gets compiled into the Briefcase iOS app bundle. It provides:
- `discoverDevices` → NSArray of NSDictionary (name, hasInput, hasOutput, sourceRef, destRef)
- `connectToDevice:` → matches by name, opens ports, connects source
- `sendSysEx:` → strips F0/F7, fragments into UMP SysEx7, sends via `MIDISendEventList`
- `drainReceivedMessages` → atomically returns and clears buffered NSArray of NSData (with F0/F7)
- `isConnected` → BOOL property
- Receive: CoreMIDI callback reassembles SysEx across UMP start/continue/end packets, buffers complete messages with thread-safe locking
- Filters out Apple's "Session 1" / "Network Session 1" virtual ports

### Android Transport (`transport/android.py`) — Future

Android MIDI API (`android.media.midi`) accessed via rubicon-java. Similar pattern: Java wrapper class for callbacks, Python drives the transport.

### Desktop Transport (`transport/desktop.py`)

Wraps `mido` + `rtmidi` for development/testing on macOS/Linux. This lets us iterate on the Toga UI without needing a physical iOS device.

## POC Milestones

- [x] Transport abstraction (`base.py`, `desktop.py`, `ios.py`)
- [x] EP133Client compatibility shim (send/receive/close on MIDITransport base)
- [x] ObjC MIDIBridge implementation (`bridge/MIDIBridge.{h,m}`)
- [x] Refactored screens (slot_list, upload_queue use EP133Client, not httpx)
- [x] App.py with device picker, connect/disconnect, INIT via EP133Client
- [x] Locale fix for iOS launch crash in krate/__main__.py
- [x] Added std-nslog for better logging
- [ ] **Briefcase project setup** — `pyproject.toml` [tool.briefcase] config, iOS template with MIDIBridge compiled; desktop-only `python-rtmidi` kept out of iOS build requirements
- [ ] **Deploy to iOS device** — `briefcase build iOS && briefcase open iOS`, Xcode deploy
- [ ] **End-to-end verification** — INIT handshake → device responds → list_sounds() → audition(3)

## Wire Format Reference

See `PROTOCOL.md` for full details. Key points for transport implementers:

- **INIT sequence** (raw, NOT packed7):
  - `F0 7E 7F 06 01 F7` — Identity Request
  - `F0 00 20 76 33 40 61 17 01 F7` — TE INIT 1
  - `F0 00 20 76 33 40 61 18 05 00 01 01 00 40 00 00 F7` — TE INIT 2
- **File operations** use packed7 payloads: build raw payload, then `Packed7.pack()`, then wrap in SysEx
- **TE manufacturer ID:** `00 20 76`, device family: `33 40`
- **UMP SysEx7** (iOS `MIDISendEventList`): strip F0/F7, fragment into 6-byte chunks with status nibbles (0x1=start, 0x2=continue, 0x3=end, 0x0=complete)

## Existing Swift Reference

`src/ios-native/KrateCore/` contains a Swift Package with `SysEx`, `Packed7`, and `KrateProtocol` types. These were built during the native iOS probe (`ios-midi-probe/`). The Swift code is reference material — the mobile app uses the Python equivalents from `src/core/`.

## Conventions

- Python 3.11+ (BeeWare Briefcase 0.4.x supports 3.10–3.14)
- Follow `src/` module layout: `src/app/` is a peer of `src/cli/`, `src/core/`, `src/tui/`
- Transport methods are synchronous — screens use `asyncio.to_thread()` for non-blocking UI
- No bare `print()` in screen code — use Toga widgets for output
- Tests: `tests/unit/test_mobile_*.py` with mocked transport