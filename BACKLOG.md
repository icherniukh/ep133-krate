# EP-133 KO-II Tools - Backlog

**Last Updated:** 2026-03-06  
**Total Items:** 39  
**Source:** Agent analysis + user feedback + STATUS.md + code audit

---

## Priority Legend

| Priority | Meaning | Action |
|----------|---------|--------|
| **P0** | Critical/Blocking | Do immediately |
| **P1** | High | Do this week |
| **P2** | Normal | Do this month |
| **P3** | Low | Future consideration |

---

## P0 - Critical/Blocking (8 items)

### ARCH-001: Split ko2.py into modules
- **Why:** 2072 lines in single file is unmaintainable
- **Current:** All 16 commands, argparse, helpers in one file
- **Target:**
  ```
  ko2/
    cli.py           # Entry point
    commands/
      ls.py
      transfer.py    # get/put/mv/cp
      optimize.py
      squash.py
      ...
    parser.py        # Argparse setup
    helpers.py
  ```
- **Effort:** 2-3 days
- **Agent:** Architecture

### ARCH-002: Extract shared service layer
- **Why:** Move/copy/squash/optimize duplicated between CLI and TUI worker
- **Locations:** `ko2.py:1007-1308`, `worker.py:165-351`
- **Target:**
  ```python
  # ko2/services/transfer.py
  class TransferService:
      def move(self, src, dst): ...
      def copy(self, src, dst): ...
      def squash(self, start, end): ...
  ```
- **Effort:** 2 days
- **Agent:** Architecture

### TEST-001: Verify KO2-009 squash fix on hardware
- **Why:** Download state fix needs hardware verification
- **Command:** `pytest tests/e2e/test_squash.py -v -m e2e`
- **Effort:** 5 minutes (with hardware)
- **Agent:** Testing
- **Status from STATUS.md:** KO2-009

### PROT-001: Capture Playback/Audition protocol (0x76)
- **Why:** Blocks Tab-to-play (TUI-006), Phase 3 features
- **Current:** TX format, parameters, response completely unknown
- **Action:**
  ```bash
  python midi_proxy.py --proxy --spoof --hunt cmd=0x76 captures/sniffer-playback.jsonl
  ```
- **Effort:** 30 min capture + analysis
- **Agent:** Protocol
- **Status from STATUS.md:** KO2-007 dependency

### PROT-002: Implement device_info() or remove stub
- **Why:** Always returns None, memory stats wrong
- **Location:** `ko2_client.py:380-387`
- **Options:**
  - A: Implement INFO (0x77/0x78) response parsing
  - B: Remove method, make 64MB fallback explicit
- **Effort:** 2-4 hours
- **Agent:** Protocol
- **Status from STATUS.md:** KO2-010
- **Introduced:** Feb 20, 2026 (commit 5995544c)

### TUI-001: Enter key confirmation in popups
- **Why:** Intuitive expectation - Enter should confirm
- **Broken:**
  - `ConfirmModal` (ui.py:194-220) - no Enter binding
  - `OptimizeModal` (ui.py:223-270) - no Enter binding
- **Working:**
  - `TextInputModal` - has Input.Submitted handler
  - `UploadModal` - has Input.Submitted for both fields
- **Fix:** Add `Binding("enter", "confirm", "Confirm")` to both
- **Effort:** 1 hour
- **Agent:** User feedback

### TUI-002: Keyboard help overlay
- **Why:** No discoverable help for keybindings
- **Current:** Footer shows only active bindings
- **Fix:** Add `?` or `h` key to display full keybinding reference modal
- **Effort:** 2 hours
- **Agent:** TUI

### ARCH-003: Remove "ko2_" prefix from class names
- **Why:** Redundant naming, especially for TUI-specific classes
- **Current naming:**
  ```
  ko2_client.py    → EP133Client
  ko2_tui/app.py   → KO2TUIApp  ← Should be just TUIApp or DeviceApp
  ko2_tui/worker.py → DeviceWorker ✓ (already good)
  ```
- **Principle:** TUI-specific classes shouldn't expand the ko2_ prefix
- **Note:** Run separate research on industry standards before implementation
- **Effort:** 2-3 hours (find/replace + imports)
- **Agent:** User feedback

---

## P1 - High Priority (15 items)

### DATA-001: Central sample database with sync operation
- **Why:** Enable hot-swap, deduplication, prevent data loss
- **Requirements:**
  - Local database of all samples (hash + metadata + WAV)
  - `ko2 sync` operation: download samples not in database
  - Quick upload from database to device
  - Duplicate detection
  - Unlimited library space beyond 999 device slots
- **Deliverables:**
  - SampleDatabase class
  - sync command (CLI + TUI)
  - Database schema (SQLite?)
- **Effort:** 3-5 days
- **Agent:** User feedback
- **Related:** state.py:21 TODO

### TUI-003: Upload overwrite warning
- **Why:** Silent data loss risk
- **Current:** `action_upload()` directly queues request
- **Fix:** Check if target slot exists, show confirmation modal
- **Effort:** 1 hour
- **Agent:** User feedback

### TEST-002: Add _detect_channels tests
- **Why:** Wrong channel count corrupts downloaded WAVs
- **Location:** `ko2_client.py:79-98`
- **Gap:** Heuristic untested
- **Fix:** Unit tests for mono/stereo detection with synthetic PCM
- **Effort:** 2 hours
- **Agent:** Testing

### PROT-003: Capture Project Listing (0x7C)
- **Why:** Cannot implement backup/restore, multi-project support
- **Current:** Switch documented, listing not captured
- **Action:**
  ```bash
  python midi_proxy.py --proxy --spoof --hunt cmd=0x7C captures/sniffer-project-ops.jsonl
  ```
- **Effort:** 30 min
- **Agent:** Protocol

### TUI-004: Sorting with in-place constraints
- **Why:** Feature gap, users expect sortable tables
- **Scope:**
  - Add column header click sorting
  - Implement "sorted mode" that disables move/copy to empty slots
  - Preserve slot integrity while sorted
- **Effort:** Medium-High
- **Agent:** TUI
- **Status from STATUS.md:** KO2-008

### TEST-003: Add upload error recovery tests
- **Why:** Device could be left in inconsistent state
- **Gaps:**
  - Partial upload failure
  - Rollback tests
  - Mid-upload timeout
- **Effort:** 1 day
- **Agent:** Testing

### ARCH-004: Refactor long command functions
- **Why:** Single functions doing too much
- **Targets:**
  - `cmd_optimize_all` (130 lines)
  - `cmd_squash` (126 lines)
  - `cmd_ls` (133 lines)
- **Fix:** Extract scan phase, process phase, reporting
- **Effort:** 1 day
- **Agent:** Architecture

### TUI-005: Progress bar visibility and operation blocking
- **Why:** Progress not visible enough, users can trigger conflicting ops
- **Issues:**
  - Progress indicator hard to see
  - No prevention of user actions during long operations
  - Escape doesn't cancel operations
- **Requirements:**
  - More prominent progress display (overlay?)
  - Block UI during operations or show clear warning
  - Research where Escape cancellation makes sense
- **Effort:** 1-2 days
- **Agent:** User feedback

### ARCH-005: Extract argparse to separate file
- **Why:** 400+ lines of argparse in main() hard to navigate
- **Location:** `ko2.py:1618-2021`
- **Fix:** Move to `ko2/parser.py`
- **Effort:** 4 hours
- **Agent:** Architecture

### PROT-004: Capture Memory/Storage Statistics
- **Why:** Cannot show accurate free memory
- **Current:** Falls back to 64MB assumption
- **Evidence:** `sniffer-slot22.jsonl` event 59 shows `free_space_in_bytes`
- **Action:**
  ```bash
  python midi_proxy.py --proxy --spoof --hunt any captures/sniffer-storage-stats.jsonl
  ```
- **Effort:** 30 min
- **Agent:** Protocol

### PROT-005: Complete Pad Mapping Groups B/C/D
- **Why:** Only Group A complete (9201-9212)
- **Current:**
  - Group B: 2 pads (9302, 9311)
  - Group C: 2 pads (9402, 9411)
  - Group D: 2 pads (9502, 9506)
- **Action:**
  ```bash
  python midi_proxy.py --proxy --spoof --hunt meta_set --hunt meta_get captures/sniffer-padmap-BCD.jsonl
  ```
- **Effort:** 1 hour
- **Agent:** Protocol

### TUI-006: Tab to play/audition sample
- **Why:** Quick preview without download
- **Blocked by:** PROT-001 (Playback protocol unknown)
- **Scope:**
  - Bind Tab to play selected non-empty slot
  - Handle empty slot gracefully
- **Effort:** Medium (after protocol captured)
- **Agent:** TUI
- **Status from STATUS.md:** KO2-007

### TUI-007: Batch optimize-all with progress in TUI
- **Why:** Missing from TUI (exists in CLI)
- **Current:** `action_optimize()` only handles single slot/selection
- **Fix:** Add to optimize modal or separate keybinding
- **Effort:** Low
- **Agent:** TUI

### TEST-004: Add coverage reporting
- **Why:** No visibility into test coverage
- **Fix:**
  ```bash
  pip install pytest-cov
  pytest --cov=ko2_client --cov=ko2_models --cov=ko2_operations
  ```
- **Effort:** 1 hour
- **Agent:** Testing

### EMU-001: Document emulator capabilities and roadmap
- **Why:** Need clarity on what emulator can do and how to extend
- **Deliverables:**
  - Document current capabilities
  - Checklist for protocol coverage
  - Guide for adding new opcodes
- **Effort:** 4 hours
- **Agent:** User feedback

---

## P2 - Normal Priority (11 items)

### TUI-008: Fold empty sample areas
- **Why:** 999 slots with many empty = visual noise
- **Requirements:**
  - Config setting to fold/collapse empty ranges
  - TUI interaction: when walking into folded area, suggest unfold
  - Button/hotkey to toggle fold state
- **Effort:** Medium
- **Agent:** User feedback

### TUI-009: Eliminate full table rebuild
- **Why:** Visible flicker, lost scroll position
- **Current:** `_refresh_table()` clears and rebuilds all 999 rows
- **Fix:** Use `DataTable.add_row()` / `update_cell()` for incremental updates
- **Effort:** Medium
- **Agent:** TUI

### TUI-010: Waveform auto-load option
- **Why:** "Press Enter to load" adds friction
- **Current:** Only loads on Enter or background precalc
- **Fix:** Option to auto-load on cursor movement (with throttling)
- **Trade-off:** Increased MIDI traffic
- **Effort:** Medium
- **Agent:** TUI

### ARCH-006: Add configuration file support
- **Why:** Hardcoded values scattered
- **Locations:**
  - 64MB memory assumption (ko2.py:455, app.py:541)
  - 5KB savings threshold (ko2.py:802, 931)
  - audio2ko2 path (ko2.py:697)
- **Fix:** YAML/TOML config file
- **Effort:** 1 day
- **Agent:** Architecture
- **Related:** ui.py:234 TODO for optimize modal defaults

### TEST-005: Add TUI widget tests
- **Why:** No Textual pilot tests for key interactions
- **Gap:** Regressions in keybinds, modal flows
- **Fix:** `test_tui_keybinds.py` using Textual's `app.press()` API
- **Effort:** 1 day
- **Agent:** Testing

### TUI-011: Selection feedback enhancement
- **Why:** Multi-slot selection hard to see
- **Current:** Small dot marker and count in status
- **Fix:**
  - Highlight selected rows with background color
  - Show selection summary in dedicated panel/overlay
  - Add "select all filled slots" shortcut
- **Effort:** Medium
- **Agent:** TUI

### ARCH-007: Standardize error handling
- **Why:** Mix of try/except with pass, silent failures
- **Issues:** 141 matches for `pass$|return None$` patterns
- **Fix:**
  - Define custom exception hierarchy
  - Replace bare `except: pass` with specific handling
  - Add logging for suppressed errors
- **Effort:** 1-2 days
- **Agent:** Architecture

### TEST-006: Parametrize existing tests
- **Why:** Tests use hardcoded values
- **Targets:**
  - `test_wire_robustness.py`
  - `test_cli_output.py` error cases
- **Fix:** Use `@pytest.mark.parametrize`
- **Effort:** 4 hours
- **Agent:** Testing

### TUI-012: Move mode visual clarity
- **Why:** Swap preview is subtle
- **Current:** Visual row swap, status bar text
- **Fix:**
  - Distinct highlight/color for source slot
  - Show "Move: 043 → 087" in floating overlay
  - Animate or pulse affected rows
- **Effort:** Medium
- **Agent:** TUI

### ARCH-008: Consolidate CLI command aliases
- **Why:** mv/move, cp/copy, rm/delete/remove have duplicated definitions
- **Fix:** Factory function for repeated patterns
  ```python
  def add_move_parser(subparsers, name, aliases):
      parser = subparsers.add_parser(name, aliases=aliases, ...)
  ```
- **Effort:** 2 hours
- **Agent:** Architecture

### PROT-006: Capture full session startup/INIT handshake
- **Why:** May reveal skipped initialization steps
- **Current:** We send 0x61, official app may send 0x78
- **Action:**
  ```bash
  python midi_proxy.py --proxy --spoof --hunt any captures/sniffer-startup.jsonl
  ```
- **Effort:** 30 min
- **Agent:** Protocol
- **From:** CAPTURE_WISHLIST.md item 7

---

## P3 - Low Priority/Future (5 items)

### UTIL-001: .ppak Export/Import
- **Why:** Backup/restore, project sharing
- **Status:** Format fully documented in PPAK_FORMAT.md
- **Implementation:** EP133Project class sketched in PPAK_FORMAT.md
- **Effort:** 2-3 days
- **Agent:** Protocol

### TUI-013: Status command in TUI
- **Why:** No way to view device memory/project info
- **Current:** `cmd_status` exists in CLI only
- **Fix:** Add `i` binding for info/status modal
- **Effort:** Low-Medium
- **Agent:** TUI

### TUI-014: Waveform cache by content hash
- **Why:** False cache hits if same-named sample changes
- **Current:** Keyed by signature (name/size/channels/rate)
- **Fix:** Use SHA256 fingerprint as primary key
- **Effort:** Medium
- **Agent:** TUI

### TEST-007: Add protocol fuzz tests
- **Why:** Adversarial input coverage
- **Targets:**
  - Random SysEx to parse_file_list_response
  - Malformed JSON to _parse_json_tolerant
- **Effort:** 1 day
- **Agent:** Testing

### TEST-008: Add ko2_backup.py tests
- **Why:** Used in optimize/move/copy but untested
- **Scope:**
  - Backup file naming
  - Backup directory creation
  - Collision handling
- **Effort:** 4 hours
- **Agent:** Testing

---

## Meta/Publishing Tasks (P2)

### META-001: Git history cleanup and repo preparation for publishing
- **Why:** Prepare for open source release
- **Scope:**
  - Clean up git history (squash WIP commits, etc.)
  - Reorganize repo structure:
    - Separate page/directory for reverse-engineered protocol specification
    - Main project README
  - Package as single installable app
  - Create Homebrew tap
  - Set up versioning (semantic versioning)
- **Effort:** 2-3 days
- **Agent:** User feedback

### TUI-015: Consolidate shortcuts view to vertical list/table
- **Why:** Current footer view in one line is hard to read
- **Fix:** Display shortcuts as vertical list or table in help overlay
- **Effort:** 2 hours
- **Agent:** User feedback

---

## Completed Items (from STATUS.md)

### KO2-012: TUI class design refactoring (2026-03-06)
- [x] WaveformStore.is_valid_bins() extracted as static method
- [x] WaveformWidget(Static) extracted to ko2_tui/waveform_widget.py
- [x] DetailsWidget(Static) added to ko2_tui/ui.py
- [x] _waveform_signature moved to module-level function
- [x] DeviceWorker._process_request split into _handle_copy, _handle_move, _handle_squash, _handle_optimize
- [x] 157/157 unit tests pass
- [x] app.py reduced from ~1190 to ~1037 lines

---

## Statistics

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----| ----- |
| Architecture | 3 | 2 | 2 | 0 | 7 |
| TUI | 2 | 4 | 4 | 2 | 12 |
| Testing | 1 | 3 | 1 | 2 | 7 |
| Protocol | 2 | 3 | 1 | 0 | 6 |
| Data | 0 | 1 | 0 | 0 | 1 |
| Emulator | 0 | 1 | 0 | 0 | 1 |
| Meta | 0 | 0 | 2 | 0 | 2 |
| Utils | 0 | 0 | 0 | 1 | 1 |
| **Total** | **8** | **15** | **11** | **5** | **39** |

---

## Notes

### Waveform Loading Behavior (Verified)
- **NOT auto-loading on cursor move**
- `_update_waveform()` only displays already-loaded data
- Loading triggers:
  1. Enter key (calls `_ensure_waveform`)
  2. Background precalc (when idle, system load < 75%)
  3. Explicit details fetch
- States: empty, pending, not_loaded ("Press Enter"), loaded

### device_info() Stub History
- **Introduced:** Feb 20, 2026 (commit 5995544c)
- **Original:** Had JSON parsing logic
- **Current:** Response loop body is `pass`, returns None
- **Impact:** Memory stats always fall back to 64MB

### Emulator Coverage (Needs Verification)
**Note:** This section needs careful review. The following is a preliminary assessment that should be verified:

Possibly implements:
- INIT (no response)
- LIST_FILES
- DOWNLOAD (GET + chunks)
- UPLOAD_DATA (PUT + chunks + VERIFY)
- UPLOAD (DELETE)
- INFO (basic)
- METADATA GET/SET

**Action Required:** Audit ko2_emulator.py to confirm actual coverage and identify gaps. See EMU-001.

---

## References

- `STATUS.md` - Active work items and completed tasks
- `docs/CAPTURE_WISHLIST.md` - Protocol capture scenarios
- `PROTOCOL.md` - Protocol documentation
- `PPAK_FORMAT.md` - Project backup format
- `tests/README.md` - Test structure
