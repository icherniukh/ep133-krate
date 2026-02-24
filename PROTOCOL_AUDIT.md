# EP-133 KO-II Protocol Audit

Skeptical audit of what we actually know vs. what we're guessing.
Ground truth: device captures in `captures/`, 25 unit tests, confirmed device tests.

---

## Protocol Understanding

```
SOLID            SPECULATION      BLIND GUESS      UNKNOWN
~43%             ~27%             ~13%             ~17%
████████████     ███████          ████             █████
─────────────────────────────────────────────────────────
Confirmed on     Educated guess   Minimal wire     Zero evidence
device + tests   w/ captures      evidence
```

**What each band means:**
- **SOLID** — Wire-captured AND device-tested AND unit tested
- **SPECULATION** — Supported by captures but semantics partially decoded
- **BLIND GUESS** — Single observation or inferred from context
- **UNKNOWN** — Constant defined; no wire evidence at all

---

## Protocol Command Reference

| Operation | Device ID | FileOp | Evidence | Notes |
|-----------|-----------|--------|----------|-------|
| SysEx framing | all | — | ✅ SOLID | `F0 00 20 76 33 40 [devid] [seq] 05 ... F7` |
| 7-bit encoding | all | — | ✅ SOLID | Round-trip verified; unit tested |
| Init sequence | 0x61 | — | ✅ SOLID | Required before any operation |
| Device info | 0x77 | — | ✅ SOLID | Returns JSON-like (product, firmware) |
| File list | 0x6A | 0x04 | ✅ SOLID | Paged 100/page; first 2 header bytes meaning unknown |
| Download (GET) | 0x7D | 0x03 | ✅ SOLID | Chunked; little-endian slot; 14-bit page encoding |
| Upload init + data | 0x6C | 0x02 | ✅ SOLID | Big-endian slot; parent node 0x03E8 |
| Upload end marker | 0x6D | — | ✅ SOLID | Sent after all data chunks |
| Delete | 0x7E | 0x06 | ✅ SOLID | Big-endian slot confirmed (slot 467 capture) |
| Metadata GET | 0x6A | 0x07/0x02 | ✅ SOLID | Paged; reliable; replaces GET_META |
| Metadata SET / rename | 0x6A | 0x07/0x01 | ✅ SOLID | JSON payload: `{"name":"..."}` confirmed |
| Response filtering | 0x2x | — | ✅ SOLID | All device responses use 0x2x range |
| Slot encoding asymmetry | — | — | ✅ SOLID | Upload big-endian, download little-endian |
| Sample format | — | — | ✅ SOLID | 46875 Hz, 16-bit PCM, mono (stereo works) |
| VERIFY post-upload | — | 0x0B | ⚠️ SPEC | Observed in official app; semantics not decoded; our uploads work without it |
| Device ID rotation | 0x60–0x6A | — | ⚠️ SPEC | Official app rotates; ko2 uses fixed 0x6A and it works |
| Node hierarchy | multiple | — | ⚠️ SPEC | active/sym transitions observed (2000→5000 etc.); not semantically mapped |
| Group A pad mapping | 9201–9212 | — | ⚠️ SPEC | 12 pads captured (`sniffer-padmap-A.jsonl`); user-assignment semantics unvalidated |
| GET_META (legacy) | 0x75 | — | ⚠️ SPEC | Known unreliable: 20/160 stale, 23/160 empty (see `audit-1-160.jsonl`) |
| File list header | 0x6A | 0x04 | ⚠️ SPEC | First 2 response bytes skipped; meaning unknown |
| Upload parent node | — | — | ⚠️ SPEC | 0x03E8 assumed constant; not validated across firmware versions |
| Upload 0x7F variant | 0x7F | — | 🟡 BLIND | Seen in `sniffer-slot26.jsonl`; when/why vs 0x6C unclear |
| Memory total | — | — | 🟡 BLIND | Hardcoded 64 MB default; no device query command exists |
| Pad Groups B/C/D | — | — | 🟡 BLIND | 2/12 pads captured per group (`sniffer-padmap-B.bin`, `C.bin`); 72% unmapped |
| Playback / audition | 0x76 | 0x05 | ❌ NONE | Constant defined; zero wire evidence |
| Project file format | — | — | ❌ NONE | .ppak structure; no SysEx path identified |
| Pattern / sequence data | — | — | ❌ NONE | No captures, no reference; may not be MIDI-accessible |
| Project listing | 0x7C | — | ❌ NONE | Switching documented; listing not captured or implemented |

---

## Phase Status

```
Phase 1 (CLI):   [████████████████████]  Done
Phase 2 (TUI):   [░░░░░░░░░░░░░░░░░░░░]  0%
Phase 3 (App):   [░░░░░░░░░░░░░░░░░░░░]  0%
```

### Phase 1 — CLI (Done)

All implemented and working:
- ✅ `ls`, `info`, `status`, `audit`, `fs-ls`
- ✅ `get`, `put`, `rm` / `remove` / `delete`
- ✅ `rename`, `mv` / `move`, `cp` / `copy`
- ✅ `optimize` (single sample: backup + optimize + replace)
- ✅ `optimize-all` (stereo samples; downmix to mono)
- ✅ `squash` (gap-fill, dry-run default, `--execute` flag)
- ✅ `group` (compaction preview)

Not implemented but not a CLI phase goal:
- ❌ `get --all` / `get --bank N` — batch download
- ❌ `backup` / `restore` — .pak archive (project listing protocol unknown)
- ❌ `project ls` / `switch` / `backup`

### Phase 2 — TUI (0%)

Not started.

### Phase 3 — Desktop/Web/Mobile (0%)

Not started.

---

## Unit Test Coverage

**25 tests, all passing** (`python -m pytest tests/unit/ -v`)

| Test File | Covers |
|-----------|--------|
| `test_file_list.py` | FILE LIST response parsing; slot-to-node ID mapping |
| `test_protocol_builds.py` | SysEx payload construction for all major operations |
| `test_upload_metadata.py` | Metadata building; loop fields for small vs large samples |
| `test_info_merge.py` | Node name vs GET_META priority for slots > 127 |
| `test_move_copy.py` | Move/copy: empty slot, swap, and overwrite paths |
| `test_protocol_packing.py` | 7-bit encode/decode round-trip |
| `test_send_and_wait.py` | MIDI send/receive, response filtering, timeout handling |
| `test_wav_validation.py` | WAV pre-upload validation (46875 Hz, 16-bit, mono) |

**Not covered by unit tests:**
- Pad assignment / pad-node mapping
- Project operations (ls, switch, backup)
- Playback (protocol unknown)
- `squash --execute` path (dry-run only tested)
- Batch ops: `get --all`, `backup`, `restore`
- End-to-end flows (4 e2e tests in `tests/e2e/` require physical device)

---

## Investigation Priorities

### From existing captures (no device needed)
1. **File list header** — first 2 response bytes skipped; analyze `sniffer-2026-02-20-220918.jsonl`
2. **VERIFY (0x0B) necessity** — our uploads skip it and work; confirm from `sniffer-upload-clean-*.bin`
3. **GET_META stale pattern** — 20 stale + 23 empty in `audit-1-160.jsonl`; what determines failure?
4. **Node hierarchy map** — build complete map from `sniffer-2026-02-20-220918.jsonl`

### Requires new device capture
5. **Playback (0x76)** — capture official app triggering audition; unblocks Phase 3 + stretch goal
6. **Project listing** — needed before backup/restore can be built
7. **Upload 0x7F variant** — when does official tool use 0x7F vs 0x6C?
8. **Pad Groups B/C/D** — need 10 more pads per group; current 2/12 is insufficient; `benjaminr/mcp-koii` contains a complete sound-to-pad mapping that may give useful reference data
9. **Sequence byte value** — does the device validate the seq byte value, or only that messages arrive in some order? Current code starts at 0x00; external examples start at 0x07. Never explicitly tested.

### May not be MIDI-accessible
9. **Project file format (.ppak)** — no SysEx path found; may be USB mass storage
10. **Pattern/sequence storage** — zero evidence of MIDI access
11. **Memory total query** — no known command; 64 MB default may be hardcoded in firmware

---

## Code Debt

- **`SysExCmd` in `ko2_protocol.py`** - Renamed from `DeviceId`. The byte is a command opcode (selects operation handler), not a device identifier. `rcy` calls it `cmd`.

---

*Ground truth sources: `captures/sniffer-2026-02-20-220918.jsonl` (960 KB), `captures/audit-1-160.jsonl` (85 KB), `captures/sniffer-upload-clean-*.bin`, `captures/sniffer-padmap-A.jsonl` (1 MB), `references/rcy/` (37 MB reference impl)*
