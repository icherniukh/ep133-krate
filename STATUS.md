# EP-133 KO-II Tools - Project Status

## 📊 Progress Overview (as of 2026-02-24)

**Current Milestone:** Phase 1 (CLI) Complete. Transitioning to Phase 2 (TUI).

**Protocol Understanding:** `[########--] 80%`
- Confirmed: LIST/GET/PUT/DELETE, METADATA SET, VERIFY, upload metadata fields, pad mapping A + partial B/C/D.
- Partial: Project ops, memory reporting, node hierarchy semantics.
- Unknown: PLAYBACK/AUDITION wire protocol.

**Project Phases:**
- Phase 1 (CLI): `[##########] 100% Done`
- Phase 2 (TUI): `[----------] 0% (Next Up)`
- Phase 3 (Desktop/Web/Mobile): `[----------] 0%`

---

## 🏛 Architectural Decisions

### 2026-02-24: "Golden Standard" Descriptor DSL Architecture
**Context**: 
The procedural approach (manually shifting bits) was replaced by a `dataclass`-based layer. However, that layer still suffered from asymmetry (manual unpacking on receive) and anti-patterns (overriding pack methods for variable-length strings).

**Decision**:
We implemented a true **Descriptor-based Domain Specific Language (DSL)** natively in Python (similar to SQLAlchemy/Django ORM) for the entire protocol.
- **`ko2_types.py`**: Minimal, primitive types (`U7`, `BE16`, `Packed7`).
- **`ko2_models.py`**: The Domain Layer. Contains all Opcodes, Message structures, and Logical Parsers. Messages are defined using declarative fields (`U7Field`, `BE16Field`, `JsonField`).
- **`ko2_operations.py`**: Stateful, multi-step operations (e.g., `UploadTransaction`).
- **`ko2_client.py`**: Thin transport interface speaking the `Message` domain.

**Consequences**:
- 100% symmetry for serialization/deserialization.
- Zero transport leakage (`ko2_client` knows nothing about `Packed7` or JSON byte-packing).
- Synchronous and thread-safe design, paving the way for async TUI worker threads (Textual framework).

---

## 🛠 Currently Working Operations (CLI)

| Operation | Command | Notes |
|-----------|---------|-------|
| **List Samples** | `ko2 ls [--page N] [--all]` | Scan by pages (100 slots), show size/duration |
| **Query Metadata** | `ko2 info <slot\|range>` | Get name, size, duration. Fallbacks handle `GET_META` offsets. |
| **Download Sample** | `ko2 get <slot> [file]` | Downloads to WAV (46875Hz). 7-bit page encoding fixed. |
| **Upload Sample** | `ko2 put <file> <slot>` | Audio + metadata set. Safe 44.1kHz support. |
| **Delete Sample** | `ko2 rm <slot>` | Big-endian slot formatting verified. |
| **Optimize Sample** | `ko2 optimize <slot>` | Backup + optimize + replace |
| **Optimize All** | `ko2 optimize-all [--min KB]`| Batch optimize stereo samples (downmix to mono) |
| **Squash Slots** | `ko2 squash` | Fill gaps sequentially (dry-run default) |

---

## 🔍 Technical Gaps & Investigation Priorities

These are the remaining mysteries in the EP-133 protocol that require further reverse-engineering:

1. **Playback/Audition (0x76)** 
   - Protocol unknown. We need to capture the official app triggering an audition to unblock Phase 3.
2. **Project Query & Switching (0x7C)** 
   - Switching is documented, but listing projects is not yet captured or implemented. Required for backup/restore features.
3. **Memory Statistics** 
   - No known command to query free memory. 64 MB assumed as a fallback, but newer hardware ships with 128 MB.
4. **Pad Mapping & Hierarchy Semantics** 
   - Group A mapping is fully captured (`9201-9212`). Groups B/C/D are only partially captured.
   - `META_SET` operations show `active` toggles on nodes `2000/5100/5300/5400/9100/9300/9500`, but UI semantics are still unclear.
5. **GET_META (0x75) Reliability & Corruption** 
   - `GET_META` is known to be unreliable (returns offset names or stale data for slots >127). The official app relies entirely on `/sounds` (FILE LIST) and Node `METADATA GET` instead. Our CLI mitigates this by trusting Node metadata first.
6. **Project file format (.ppak)**
   - Documented in `PPAK_FORMAT.md`, but no SysEx path for extracting it has been found. It might rely on USB Mass Storage or undocumented bulk transfers.

---

## 📅 Task List: Phase 2 (Textual TUI)

Our core objective is to wrap the robust `ko2_client` into a responsive, async-safe terminal UI using the `textual` framework.

### Step 1: TUI Foundation & Async Threading
- [ ] Initialize `textual` app structure (`app.py`, `ui/`, `workers/`).
- [ ] Implement a background MIDI polling worker (queue-based) to decouple `mido` from the async event loop.
- [ ] Design a thread-safe state container (e.g. `ko2_state_manager.py`) to hold the sample inventory without blocking the UI.

### Step 2: Core Views
- [ ] **Slot Browser**: A `DataTable` or custom list view showing all 999 slots (Slot, Name, Size, Channels, Rate).
- [ ] **Detail Pane**: A sidebar or modal showing deep metadata for the selected slot.
- [ ] **Log Console**: A built-in terminal view showing raw MIDI TX/RX and operation logs.

### Step 3: Interactive Operations
- [ ] **Download Modal**: Trigger `DownloadOperation` with progress bar feedback.
- [ ] **Upload Modal**: File picker to select a local `.wav`, followed by `UploadOperation` with progress feedback.
- [ ] **Delete/Rename**: Modals for quick slot management.
- [ ] **Batch Ops**: Trigger `ko2 squash` or `ko2 optimize-all` from the TUI with visual progress.

### Step 4: Stretch Goals (Phase 3 Prep)
- [ ] Capture the "Audition" (0x76) protocol so the TUI can trigger remote playback.
- [ ] Pad mapping visualizer (if the Group A/B/C/D mapping is fully decoded).
