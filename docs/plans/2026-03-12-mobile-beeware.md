# BeeWare Mobile Frontend — Research & Design Overview

## Context

ko2-tools Phase 3 (Mobile) needs a plan. The goal is an iOS app for managing EP-133 KO-II samples. This document captures research findings, workflow requirements, and the recommended architecture for adding a BeeWare mobile frontend to the existing repo.

Goals:
- Phase 1: core operations (browse slots, upload/download, audition/play)
- Architectural baseline: full TUI parity is the floor; mobile will extend beyond it
- Platform: iOS first (easier with macOS dev environment + CoreMIDI reliability)
- Approach: transport abstraction (Approach C) — keep one repo, make EP133Client platform-agnostic

---

## Key Research Findings

### BeeWare Status (2025–2026)
- Functional but not production-ready. Tier 3 CPython support for iOS/Android since Python 3.13.
- Pure-Python dependencies: work fine. C extensions: need iOS wheels (sparse but growing).
- Toga 0.5.x + Briefcase 0.3.26+ are current stable versions.
- Briefcase CLI cannot deploy to physical iOS devices yet (Issue #860). Must use Xcode.

### Critical Blockers
1. **mido won't run on iOS** — all backends are C extensions without iOS wheels. Need Rubicon-ObjC → CoreMIDI bridge written from scratch (~500–1000 lines).
2. **Textual TUI is a full rewrite** — Toga uses native widgets, not terminal/ANSI. All `src/tui/` code must be rewritten. Architecture (worker thread, event queue, state model) carries over conceptually.
3. **sox not available on iOS** — `optimize_sample()` shells out to sox; needs replacement with a Python audio library or CoreAudio.

### What IS Reusable
| Module | Reusable? | Notes |
|--------|-----------|-------|
| `src/core/ops.py` | Yes | Pure logic |
| `src/core/audio.py` | Yes | Pure DSP |
| `src/core/models.py`, `types.py` | Yes | Wire format, no platform deps |
| `src/core/client.py` | Partial | Needs pluggable transport |
| `src/core/backup.py` | Yes | File I/O only |
| `src/tui/state.py` (SlotRow, TuiState) | Yes | Clean data model |
| All `src/tui/` UI code | No | Full rewrite in Toga |
| View Protocol concept | Yes | New MobileView implementation needed |
| WorkerRequest/Event pattern | Yes | Swap Textual event loop for Toga's |

---

## Recommended Architecture: Approach C (Transport Abstraction)

### Core Idea
Define a `MIDITransport` protocol. `EP133Client` becomes transport-agnostic. Desktop uses the existing mido backend. iOS uses a new Rubicon-ObjC → CoreMIDI backend.

```
src/core/transport.py
  ├── class MIDITransport(Protocol)   ← send(bytes), receive() -> bytes, open/close
  ├── class MidoTransport             ← wraps existing mido code (desktop, no behavior change)
  └── class CoreMIDITransport         ← Rubicon-ObjC bridge to iOS CoreMIDI (new)

src/core/client.py
  └── EP133Client(transport: MIDITransport)  ← transport injected, no platform logic here

src/mobile/                           ← new BeeWare Toga app
  ├── app.py                          ← toga.App subclass
  ├── screens/
  │   ├── slot_browser.py             ← DetailedList of 999 slots
  │   ├── slot_detail.py              ← sample metadata + waveform
  │   └── transfer.py                 ← upload/download UI
  ├── worker.py                       ← mobile DeviceWorker (same pattern as src/tui/worker.py)
  └── views.py                        ← MobileView implementing View protocol
```

### Implementation Phases

**Phase 0 — Transport abstraction (prerequisite)**
1. Define `MIDITransport` protocol in `src/core/transport.py`
2. Refactor `EP133Client` to accept transport (default: `MidoTransport`)
3. `MidoTransport` wraps existing mido code — zero behavioral change for desktop
4. All existing tests continue to pass (`python3 -m pytest tests/unit/ -v`)

**Phase 1 — CoreMIDI bridge**
1. `CoreMIDITransport` in `src/core/midi_ios.py` using Rubicon-ObjC
2. APIs: `MIDIClientCreate`, `MIDIOutputPortCreate`, `MIDIInputPortCreate`, `MIDISysExSendRequest`
3. USB MIDI port discovery (`MIDIGetNumberOfDevices`, `MIDIGetDevice`)
4. Sync wrapper: CoreMIDI uses callbacks → wrap with `threading.Event` for blocking semantics
5. Validate with a real device before proceeding to UI

**Phase 2 — BeeWare project setup**
1. `briefcase new` (or manual `pyproject.toml` config) for iOS target
2. Bundle pure-Python deps: `src/core/` works as-is; confirm `mido` not included for iOS build
3. Toga app skeleton runs in `briefcase dev`

**Phase 3 — Toga UI (Phase 1 scope)**
- Slot browser: `toga.DetailedList` or `toga.Table` of SlotRow data
- Slot detail: metadata panel + waveform canvas (`toga.Canvas`)
- Actions: audition/play, download to Files app, upload from Files app
- Device connect flow: scan for MIDI ports, select EP-133

---

## Dev Workflow Requirements

### Minimum Setup
- macOS 14 (Sonoma) or later
- Xcode 16+ (free from App Store)
- 16 GB RAM recommended for iOS builds
- Python 3.13 recommended
- `pip install briefcase toga` (Toga 0.5.x, Briefcase 0.3.26+)

### Development Loop
1. `briefcase dev` — runs Toga app in local Python, no packaging, fastest iteration
2. `briefcase run iOS` — runs in iOS Simulator (no device needed)
3. `briefcase build iOS && briefcase open iOS` → deploy from Xcode for physical device

### Apple Developer Account
- **Free Apple ID**: sufficient for personal device testing via Xcode
  - Certificates expire every 7 days (must re-sign weekly)
  - Limited to 3 registered devices
- **Paid ($99/year)**: required for App Store, TestFlight, push notifications
- **Verdict**: Free account is sufficient for development. Pay only when distributing.

---

## BeeWare Skill: Yes, Create One

A `beeware-ios` (or `toga-ios-midi`) skill is needed. Without it, every session requires re-researching Rubicon-ObjC patterns, Toga widget APIs, and Briefcase config.

**Skill should cover:**
1. Toga widget system — Box layout, Table, DetailedList, Canvas, NavigationView
2. Briefcase dev workflow — `briefcase dev` / `build` / `run` / `open` lifecycle
3. **Rubicon-ObjC bridge patterns** — calling ObjC APIs, handling callbacks, retain/release
4. iOS CoreMIDI API — `MIDIClientCreate`, port creation, SysEx send/receive, device discovery
5. `Info.plist` customization via `pyproject.toml` (background modes, MIDI entitlements)
6. Threading model: `app.add_background_task()` vs threads for the MIDI worker

---

## Files to Create / Modify

| File | Action | Notes |
|------|--------|-------|
| `src/core/transport.py` | Create | `MIDITransport` protocol + `MidoTransport` |
| `src/core/midi_ios.py` | Create | `CoreMIDITransport` via Rubicon-ObjC |
| `src/core/client.py` | Modify | Inject transport; keep `MidoTransport` as default |
| `src/mobile/` | Create | Toga app (briefcase project) |
| `pyproject.toml` | Modify | Add Briefcase iOS configuration |
| `tests/unit/test_transport.py` | Create | Transport protocol compliance tests |

---

## Verification

1. `python3 -m pytest tests/unit/ -v` — all 374 tests pass (no regression from transport refactor)
2. `briefcase dev` — Toga app launches on macOS desktop
3. `briefcase run iOS` — app runs in iOS Simulator
4. Physical device (free Apple ID): `briefcase open iOS` → deploy from Xcode
5. CoreMIDI bridge: connects to EP-133 via USB, sends `_initialize()` SysEx, receives valid response
6. Phase 1 E2E: list slots → select slot → audition plays on device

---

## Open Questions (Pre-Implementation)

- **sox replacement for optimize_sample on iOS**: `pydub` (pure Python + ffmpeg)? native CoreAudio? or defer optimize to Phase 2?
- **File import/export on iOS**: `UIDocumentPickerViewController` via Rubicon-ObjC for loading WAV files from Files app.
- **BLE MIDI**: out of scope for Phase 1 (too low bandwidth for sample transfers), but architecture should not preclude it.
