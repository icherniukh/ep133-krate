# EP-133 KO-II Tools - Project Status

## 📊 Progress Overview (as of 2026-02-27)

**Current Milestone:** Phase 2 (TUI) MVP foundation implemented.

**Protocol Understanding:** `[########--] 80%`
- Confirmed: LIST/GET/PUT/DELETE, METADATA SET, VERIFY, upload metadata fields, pad mapping A + partial B/C/D.
- Partial: Project ops, memory reporting, node hierarchy semantics.
- Unknown: PLAYBACK/AUDITION wire protocol.

**Project Phases:**
- Phase 1 (CLI): `[##########] 100% Done`
- Phase 2 (TUI): `[###-------] 30% (MVP in progress)`
- Phase 3 (Desktop/Web/Mobile): `[----------] 0%`

---

## 🏛 Architectural Decisions

### 2026-03-02: View-oriented CLI output architecture
**Context**:
`ko2.py` had ~80 bare `print()+Colors.*` calls inline in command functions, making them untestable and coupling business logic to terminal formatting. The `RendererProtocol` name was also misleading ("renderer" implies transform-and-return, not fire-and-forget I/O).

**Decision**:
Introduced `View` protocol in `ko2_display.py` with 10 domain-semantic methods (`section`, `step`, `success`, `error`, `warn`, `info`, `kv`, `progress`, `render_samples`, `sample_detail`). Three implementations:
- **`TerminalView`**: colored ANSI output (default)
- **`SilentView`**: all no-ops — `--quiet` backend and test double
- **`JsonView`**: structured JSON output — `--json` backend

All 16 `cmd_*` functions receive `view: View` as an injected parameter. `main()` constructs the view from `--json`/`--quiet` flags. Layout helpers (`_row`, `_table_header`, etc.) are private to `TerminalView`.

**Consequences**:
- Every `cmd_*` function is unit-testable via `Mock(spec=View)` — no stdout patching needed.
- `--json` and `--quiet` output modes added at zero cost to command logic.
- `Colors.*` fully removed from `ko2.py`; `ko2_utils.py` deleted (utilities consolidated into `ko2_display.SampleFormat`).

---

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
| **Query Metadata** | `ko2 info <slot\|range>` | Get name, size, duration. |
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
   - `GET_META` is known to be unreliable because it can return stale data for deleted slots. The official app relies entirely on `/sounds` (FILE LIST) and Node `METADATA GET` instead. Our runtime paths now do the same; `GET_META` is retained only for explicit audit/debug comparisons.
6. **Project file format (.ppak)**
   - Documented in `PPAK_FORMAT.md`, but no SysEx path for extracting it has been found. It might rely on USB Mass Storage or undocumented bulk transfers.

---

## 🗂 CLI Backlog

- [ ] **Configurable upload metadata defaults** — `sound.amplitude`, `sound.playmode`, `envelope.*` etc. are currently hardcoded to match official TE app defaults. Should be overridable via a config file or CLI flags so users can set their own defaults (e.g. different amplitude, looping mode).
- [x] **Protocol docs nomenclature cleanup (`pack_bytes`)** — standardized docs around packed7 payload encoding (`pack_flags` vs legacy `pack_bytes`/`sub_byte`) and removed ambiguous examples.

---

## 📅 Task List: Phase 2 (Textual TUI)

Our core objective is to wrap the robust `ko2_client` into a responsive, async-safe terminal UI using the `textual` framework.

### Step 1: TUI Foundation & Async Threading
- [x] Initialize `textual` app structure (`ko2_tui/app.py`, `ko2_tui/ui.py`, `ko2_tui/worker.py`).
- [x] Implement a background worker (queue-based) to decouple MIDI I/O from the UI event loop.
- [x] Add thread-safe state container (`ko2_tui/state.py`) for slot inventory + details.

### Step 2: Core Views
- [x] **Slot Browser**: `DataTable` view for all 999 slots (Slot, Name, Size, Channels, Rate, Duration).
- [x] **Detail Pane**: Sidebar details for selected slot metadata.
- [x] **Log Console**: In-app operation log plus raw MIDI TX/RX lines in `--debug` mode.

### Step 3: Interactive Operations
- [x] **Download Modal**: Trigger download to a user-provided output path.
- [x] **Upload Modal**: Input path + optional name, then upload to selected slot.
- [x] **Delete/Rename**: Quick slot operations from TUI keybinds/modals.
- [ ] **Batch Ops**: Trigger `ko2 squash` or `ko2 optimize-all` from the TUI with visual progress.

### Step 4: Stretch Goals (Phase 3 Prep)
- [ ] Capture the "Audition" (0x76) protocol so the TUI can trigger remote playback.
- [ ] Pad mapping visualizer (if the Group A/B/C/D mapping is fully decoded).

---

## 🚧 Active Work Items (2026-03-02)

Tracking convention:
- Priority: `P0` critical, `P1` high, `P2` normal.
- Status: `[ ]` todo, `[x]` done.
- Done means: implementation + tests + short note in this file.

### KO2-001 (`P0`) Download latency bug hunt and timer/sleep removal
- [x] Scan active runtime paths for fixed delays (`sleep`, timer polling loops), especially download paths.
- [x] Remove/replace avoidable fixed waits in hot paths; document any protocol-required delay.
- [x] Profile a real download run and attach timing breakdown.
- [x] Acceptance: measurable download wall-time improvement on repeated runs.
- Result:
  - Removed fixed sleeps from active receive/download paths in `ko2_client.py` (`_download_data`, `_recv_matching`, `_recv_sysex`, `_send_and_wait`, `_initialize`), and replaced delete sleep with response-based ack handling.
  - On-device benchmark (slot `001`, size `28636` bytes, `~67` download pages): old fixed-sleep floor was `~3.350s` (`67 * 50ms`); new measured median download time is `0.655s` (5 runs), total median for `info+download+save` is `0.816s`.
  - cProfile-guided follow-up optimization replaced hot-spin polling with blocking queue receive in `ko2_client.py`; same-slot `ko2 get 43` (size `279502` bytes, ~272KB) improved from `~6.34s` total profile run to `~2.60s` profiled runtime, and plain wall clock is now `~2.08s`.

### KO2-002 (`P1`) Log view hide/unhide via `l`
- [x] Add `l` keybinding in TUI to toggle log panel visibility.
- [x] Preserve log content while hidden.
- [x] Acceptance: no focus or interaction regressions while toggling during active work.
- Note:
  - Added `l` binding to hide/unhide the log pane without destroying the widget or clearing `RichLog` lines.
  - Status bar now indicates hidden state (`logs:hidden`) and navigation remains stable while toggling.

### KO2-003 (`P0`) Investigate why some operations are slow
- [x] Instrument operation timings (refresh, details, copy/move, optimize, squash, download/upload).
- [x] Identify top bottlenecks and separate protocol wait vs app overhead.
- [x] Fix at least the top bottlenecks or split into follow-up items with numbers.
- [x] Acceptance: before/after timing report with p50/p95 for major operations.
- Note:
  - `ko2_tui.worker.DeviceWorker` now emits per-operation timing telemetry (`op_timing`) including total runtime, phase breakdown, rolling p50, and rolling p95.
  - Post-op metadata hydration now supports selective slot hydration (instead of always hydrating all slots), reducing avoidable refresh overhead after single-slot operations.
  - Added idle-only waveform precalc scheduling with CPU-load gating (`KO2_TUI_WAVEFORM_PRECALC_MAX_LOAD`) and mode toggle (`KO2_TUI_WAVEFORM_PRECALC_MODE=single|threaded`) for side-by-side testing.
  - **Bottleneck analysis:** Top two overhead sources were `device.list_sounds` (multi-page scan) + `device.get_node_metadata` running after every single-slot op unnecessarily.
  - **Rename fix:** Eliminated `list_sounds` + `get_node_metadata` round trips; now emits `inventory_enriched` directly with the known new name. Saves 2+ MIDI round trips per rename.
  - **Delete fix:** Eliminated `list_sounds` scan; now emits `slot_removed` and calls `TuiState.clear_slot`. Saves 1+ MIDI round trips per delete.
  - **Phase visibility:** `op_timing` log now includes per-phase breakdown so protocol wait vs app overhead is visible in the dialog log.

### KO2-004 (`P1`) Optimize checklist ergonomics and key flow
- [x] `space`: toggle selection and move cursor down only when toggled ON.
- [x] `enter`: use current selection/context and proceed.
- [x] `escape`: cancel current modal/mode consistently.
- [x] Rename first optimize option label to either `Unstereofy` or `Unstereo` (pick one).
- [x] Acceptance: keyboard flow validated by tests and manual pass.
- Note:
  - `space` now advances only when selection flips ON; deselect keeps cursor in place.
  - App-level `escape` routes through a single cancel action so move mode cancels consistently.
  - Optimize modal first option is now labeled `Unstereo (Stereo -> Mono)`.
  - Added/updated TUI tests for `space`, `enter`, `escape`, and optimize modal label.

### KO2-005 (`P1`) Show progress indicator during processing
- [x] Add always-visible busy indicator while worker is processing.
- [x] Add progress feedback for long operations (download/optimize/squash/bulk actions).
- [x] Acceptance: user can see active processing and completion state at all times.
- Note:
  - Status bar now shows ⚪/🟢/🟡/🔴 circle for device state (unknown/online/busy/error).
  - Background changes: blue when active, red when last op errored, neutral when idle.
  - Worker emits structured `progress` events for download/upload/copy/move and long loops (`bulk_delete`, `squash`, `optimize`), and the app reflects them live in status.

### KO2-006 (`P1`) Show operation duration and split debug/dialog logs
- [x] Include elapsed time in completion messages for operations.
- [x] Rework debug view into dialog-style informational output.
- [x] Stop showing command lines in dialog view.
- [x] Log commands/debug trace to one file and dialog messages to a separate file.
- [x] Acceptance: two independent log files, both validated and documented.
- Note:
  - TUI debug trace lines now render as concise user-facing messages (for example, "download requested for slot ..."), no longer raw command/payload style lines.
  - High-frequency chunk chatter (`GET_DATA`/`PUT_DATA`) is suppressed from the dialog log to keep it readable.
  - Worker success messages now include elapsed runtime suffix (for example, `(... 1.23s)`).
  - Added `ko2_tui/dialog_log.py` and wired it to `KO2TUIApp`; with `--debug`, protocol trace stays in JSONL and dialog/status messages go to a separate `tui-dialog-*.log` file (or `--dialog-log PATH`).

### KO2-007 (`P2`) `Tab` key should play/audition sample
- [ ] Bind `Tab` to play selected non-empty slot.
- [ ] Handle empty slot gracefully.
- [ ] If playback protocol remains unknown, capture/decode required wire traffic first.
- [ ] Acceptance: audition works from current selection in TUI.

### KO2-008 (`P1`) Sorting with in-place-only constraints
- [ ] Implement sample sorting in TUI list.
- [ ] In sorted mode, block invalid behavior: no move/copy/interact with empty slots.
- [ ] Allow only in-place-safe operations while sorted.
- [ ] Acceptance: sorted mode preserves slot integrity and enforces constraints clearly.
