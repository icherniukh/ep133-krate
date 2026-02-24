# AGENTS.md

## 📊 Project Status (as of 2026-02-24)

**Current Milestone:** Phase 1 (CLI) Completion & Robustness
- **Protocol Understanding**: ~80% (Core ops confirmed; Playback/Audition unknown).
- **Core Features**: `ls`, `get`, `put`, `rm`, `info`, `optimize-all` are fully functional.
- **Recent Wins**: Fixed Big-Endian audio alignment and 7-bit page encoding bugs.
- **Primary Gaps**: Playback protocol (0x76), accurate memory reporting, TUI (Phase 2).

---

## 🛠 Active Task Backlog

1. **Refactor `ko2_protocol.py`**: ✅ Done. Renamed `DeviceId` to `SysExCmd`.
2. **Implement Wire-Format Layer**: 🟡 In progress. Created `ko2_wire.py` with `U7`, `U14`, `BE16`, and `Packed7`.
3. **Pathlib Migration**: Transition from `os.path` to `pathlib` for all file operations.
4. **Research Playback Protocol**: Capture SysEx to enable `ko2 play`.

---

## 🏛 Architectural Decisions

### 2026-02-24: Declarative Protocol Architecture
**Context**: 
The current procedural approach (manually shifting bits in every `build_*` function) is prone to 7-bit MIDI constraint violations and makes the code hard to audit against `PROTOCOL.md`.

**Decision**:
We will implement a layered protocol architecture:
- **Wire Layer**: Atomic MIDI-safe types (`U7`, `U14`, `BE16`) that handle their own validation.
- **Message Layer**: Dataclasses defining command structures.
- **Codec Layer**: A bridge that automates serialization based on type hints.

**Consequences**:
- **Pro**: High reliability, self-documenting code, easier testing.
- **Con**: Initial overhead of building the codec layer.
