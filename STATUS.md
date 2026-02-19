# EP-133 KO-II Tools - Status

## Currently Working Operations

### Device Operations (via MIDI SysEx)

| Operation | Status | Command | Notes |
|-----------|--------|---------|-------|
| **List Samples** | ✅ Working | `ko2 ls [--page N] [--all]` | Scan by pages (100 slots), show size/duration |
| **Query Metadata** | ✅ Working | `ko2 info <slot\|range>` | Get name, size, duration |
| **Download Sample** | ✅ Working | `ko2 get <slot> [file]` | Downloads to WAV (46875Hz) |
| **Upload Sample** | ✅ Working | `ko2 put <file> <slot>` | Upload with progress |
| **Delete Sample** | ✅ Working | `ko2 rm <slot>` | `delete` alias also works |
| **Optimize Sample** | ✅ Working | `ko2 optimize <slot>` | Backup + optimize + replace |
| **Optimize All** | ✅ Working | `ko2 optimize-all [--min KB]` | Batch optimize oversized samples |
| **Compact/Group** | ✅ Preview | `ko2 group <range>` | Preview only (needs move operation) |

### Optimization Features

**Single Sample:**
```bash
ko2 optimize 123     # Download, optimize, backup .bak, replace
```

**Batch Optimization:**
```bash
ko2 optimize-all             # Find samples >100KB, optimize all
ko2 optimize-all --min 50    # Find samples >50KB
ko2 optimize-all --force     # Skip confirmation
```

**What it does:**
1. Scans all 999 slots for oversized samples
2. Downloads candidate to temp file
3. Creates `file.wav.bak` backup
4. Optimizes with audio2ko2 (or sox fallback)
5. Replaces if savings >5KB
6. Shows total savings

### Backup File Operations (.pak files = ZIP)

| Operation | Status | Script | Notes |
|-----------|--------|--------|-------|
| **List Backup Contents** | ✅ Working | `ko2-list` | Shows all samples, sizes, types |
| **Optimize Backup** | ✅ Working | `ko2-optimize` | Converts to 46.875kHz mono |
| **Create Backup** | ❌ Official Tool Only | | Requires web UI |
| **Restore Backup** | ❌ Official Tool Only | | Requires web UI |

### Audio Conversion

| Operation | Status | Script | Notes |
|-----------|--------|--------|-------|
| **Convert to EP-133 Format** | ✅ Working | `../audio2ko2` | Converts to 46875Hz WAV |
| **Extract from Backup** | ✅ Working | `../extract-ko2` | Extracts .pak contents |

---

## Protocol Implementation Status

### Device IDs
| ID | Name | Status | Notes |
|----|------|--------|-------|
| 0x61 | INIT | ✅ Working | Initialization sequence |
| 0x75 | GET_META | ✅ Working | Metadata queries (little-endian) |
| 0x76 | PLAYBACK | ⏳ Unknown | Audition - needs packet capture |
| 0x77 | INFO | ✅ Working | Device info |
| 0x7C | PROJECT | ✅ Documented | Project switching (not implemented) |
| 0x7D | DOWNLOAD | ✅ Working | GET with chunking |
| 0x7E | UPLOAD | ✅ Working | PUT with 8-step sequence |
| 0x37 | RESPONSE | ✅ Working | Standard response parsing |
| 0x3D | RESPONSE_ALT | ✅ Working | Alternative response parsing |

### File Operations
| Op | Hex | Name | Status |
|----|-----|------|--------|
| 0x01 | INIT | Initialize | ✅ Working |
| 0x02 | PUT | Upload | ✅ Working |
| 0x03 | GET | Download | ✅ Working |
| 0x04 | LIST | List files | ⚠️ Unconfirmed (not needed) |
| 0x05 | PLAYBACK | Playback | ⏳ Unknown |
| 0x06 | DELETE | Delete | ✅ Working |
| 0x07 | METADATA | Metadata ops | ✅ Working |
| 0x0B | VERIFY | Verify | ✅ Working (upload) |

---

## Wishlist / Future Features

### Phase 1 - Core (DONE ✅)
- [x] ko2 ls - List samples by pages
- [x] ko2 get - Download sample
- [x] ko2 put - Upload sample
- [x] ko2 rm/delete - Delete sample
- [x] ko2 info - Show metadata
- [ ] ko2 play - Audition (protocol unknown)

### Phase 2 - Batch Operations (PARTIAL)
- [x] ko2 optimize-all - Optimize oversized samples
- [ ] ko2 get --all - Download all samples
- [ ] ko2 get --bank 7 - Download entire bank
- [ ] ko2 backup - Create full backup (device -> .pak)
- [ ] ko2 restore <file> - Restore backup to device

### Phase 3 - TUI Interface
- [ ] ko2 tui - Interactive terminal UI
  - Slot browser (10 pages × 100 slots)
  - Preview playback (when protocol known)
  - Batch operations
  - Visual memory usage

### Phase 4 - Sample Management
- [ ] ko2 rename <slot> <name> - Rename sample
- [ ] ko2 mv <src> <dst> - Move sample
- [ ] ko2 cp <src> <dst> - Copy sample
- [ ] ko2 normalize <slot> - Normalize volume
- [ ] ko2 trim <slot> - Trim silence

### Phase 5 - Project Operations
- [ ] ko2 project ls - List projects
- [ ] ko2 project switch <n> - Switch active project
- [ ] ko2 project backup <n> - Backup project
- [ ] ko2 project export <n> - Export to .ppak

---

## Technical Gaps

1. **Playback/Audition (0x76)** - Protocol unknown, needs MIDI sniffer
2. **Project Query** - No command to list/query projects
3. **Sample Rename** - Metadata SET exists but not tested
4. **Sample Move/Copy** - Would require download+re-upload
5. **Memory Statistics** - No command to query free memory

---

## Files

| File | Purpose |
|------|---------|
| `ko2.py` | Main CLI tool |
| `ko2_client.py` | MIDI client implementation |
| `ko2_protocol.py` | Protocol constants and utilities |
| `PROTOCOL.md` | Complete protocol documentation |
| `PPAK_FORMAT.md` | .ppak file format spec |
| `PROJECT_OPERATIONS.md` | Project switching docs |
| `PROTOCOL_TEST_RESULTS.md` | Device testing results |
| `TO_VERIFY.md` | Resolved protocol issues (reference) |
