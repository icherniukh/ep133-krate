# AGENTS.md

## 📊 Project Status (as of 2026-02-24)

**Current Milestone:** Phase 1 (CLI) Completion & Robustness
- **Protocol Understanding**: ~80% (Core ops confirmed; Playback/Audition unknown).
- **Core Features**: `ls`, `get`, `put`, `rm`, `info`, `optimize-all` are fully functional.
- **Recent Wins**: Fixed Big-Endian audio alignment and 7-bit page encoding bugs.
- **Primary Gaps**: Playback protocol (0x76), accurate memory reporting, TUI (Phase 2).

---

## 🛠 Active Task Backlog

1. **Refactor `ko2_models.py`**: ✅ Done. Renamed `DeviceId` to `SysExCmd`.
2. **Implement Wire-Format Layer**: ✅ Done. Created `ko2_types.py`, refactored `ko2_models.py` to use declarative types, and deleted `ko2_encoding.py`.
3. **Pathlib Migration**: ✅ Done. Standardized on `pathlib.Path` across all active scripts.
4. **Research Playback Protocol**: Capture SysEx to enable `ko2 play`.

---

## 🏛 Architectural Decisions

### 2026-02-24: "Golden Standard" Descriptor DSL Architecture
**Context**: 
The procedural approach (manually shifting bits) was replaced by a `dataclass`-based layer. However, that layer still suffered from asymmetry (manual unpacking on receive) and anti-patterns (overriding pack methods for variable-length strings).

**Decision**:
We implemented a true **Descriptor-based Domain Specific Language (DSL)** natively in Python (similar to SQLAlchemy/Django ORM) for the entire protocol.
- **`ko2_types.py`**: Minimal, primitive types (`U7`, `BE16`, `Packed7`).
- **`ko2_models.py`**: The Domain Layer. It contains all Opcodes, Message structures, and Logical Parsers. Messages are defined using declarative fields (`U7Field`, `BE16Field`, `JsonField`).
- **`ko2_operations.py`**: Stateful operations (e.g., `UploadTransaction`).
- **`ko2_client.py`**: Thin transport interface speaking the `Message` domain.

**Consequences**:
- **Pro**: 100% symmetry for serialization/deserialization. Zero transport leakage (`ko2_client` knows nothing about `Packed7` or JSON byte-packing). Thread-safe for future Textual TUI integration.
- **Con**: Higher cognitive load for developers unfamiliar with Python descriptors.
