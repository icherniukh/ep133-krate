# EP-133 KO-II Tools - Status & Wishlist

## Currently Working Operations

### Device Operations (via MIDI SysEx)

| Operation | Status | Script | Notes |
|-----------|--------|--------|-------|
| **Download Sample** | ✅ Working | `ko2_download.py` | Downloads from slot to WAV (46875Hz) |
| **Query Metadata** | ✅ Working | `ko2_download.py` | Get sample name, rate, format |
| **Scan All Slots** | ⚠️ Needs Update | `ko2_scan_slots.py` | Broken after protocol refactor |
| **Delete Sample** | 🔧 Protocol Known | | 0x06 DELETE op documented |
| **Upload Sample** | 🔧 Protocol Known | | 0x02 PUT op documented, complex |

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

## Wishlist (for butter-smooth TUI)

### Audio Preparation (NEW)

```
[ ] ko2-prepare <file>         - Prepare audio for upload
    ├── Convert to 46875Hz/16-bit/mono
    ├── Trim silence (start/end)
    ├── Normalize volume
    └── Auto-name output

[ ] ko2-prepare --chop <file>   - Chop at transients into parts
[ ] ko2-prepare --split N <file> - Split into N equal parts
[ ] ko2-prepare --batch <files>  - Process multiple files
[ ] ko2-prepare --threshold -40dB <files>  # Custom trim level
```

**Integration:** Base conversion via `audio2ko2`, output ready for `ko2 put`

### Phase 1 - Core Device Operations

```
[ ] ko2 ls                    - List all slots on device
[ ] ko2 get <slot> [file]     - Download sample from slot
[ ] ko2 put <file> <slot>     - Upload sample to slot
[ ] ko2 rm <slot>             - Delete sample from slot
[ ] ko2 info <slot>           - Show sample metadata
[ ] ko2 play <slot>           - Audition sample (playback)
```

### Phase 2 - Batch Operations

```
[ ] ko2 ls --banks            - List samples grouped by bank
[ ] ko2 get --all             - Download all samples
[ ] ko2 get --bank 7          - Download entire bank
[ ] ko2 rm --empty            - Delete all empty slots
[ ] ko2 backup                - Create full backup (device -> .pak)
[ ] ko2 restore <file>        - Restore backup to device
```

### Phase 3 - TUI Interface

```
[ ] ko2 tui                   - Interactive terminal UI
    ├── Slot browser (10 banks × 100 slots)
    ├── Preview playback (audition)
    ├── Drag-drop reorganization
    ├── Batch operations
    └── Visual memory usage
```

### Phase 4 - Sample Management

```
[ ] ko2 rename <slot> <name>  - Rename sample on device
[ ] ko2 mv <src> <dst>         - Move sample between slots
[ ] ko2 cp <src> <dst>         - Copy sample between slots
[ ] ko2 normalize <slot>       - Normalize sample volume
[ ] ko2 trim <slot>            - Trim silence from start/end
[ ] ko2 reverse <slot>         - Reverse sample
```

### Phase 5 - Project Operations

```
[ ] ko2 project ls            - List projects on device
[ ] ko2 project backup <n>    - Backup single project
[ ] ko2 project restore <n>   - Restore project to device
[ ] ko2 project export <n>    - Export project to .ppak
```

---

## Protocol Implementation Status

### Message Structure (Working)
```
F0 00 20 76 33 40 [DEVID] [SEQ] 05 00 [OP] [SUBOP] [DATA] F7
```

### Device IDs (Working)
| ID | Usage | Status |
|----|-------|--------|
| 0x61 | Initialization | ✅ Working |
| 0x76 | Playback/Audition | 🔧 Protocol known |
| 0x77 | Info/Metadata | ✅ Working |
| 0x7D | Download (GET) | ✅ Working |
| 0x7E | Upload (PUT) | 🔧 Protocol known |
| 0x37 | Standard Response | ✅ Working |
| 0x3D | Alternative Response | ✅ Working |

### Operations (Implemented)
| Op | Name | Status |
|----|------|--------|
| 0x01 | INIT | ✅ Working |
| 0x02 | PUT (Upload) | 🔧 Protocol documented |
| 0x03 | GET (Download) | ✅ Working |
| 0x06 | DELETE | 🔧 Protocol documented |
| 0x07 | METADATA | ✅ Working |

---

## Technical Gaps

1. **Upload Protocol** - Documented but complex (chunked data, commit phase)
2. **Playback/Audition** - Protocol known, needs implementation
3. **Project Format** - .pcm format unknown, needs RE
4. **Slot Renaming** - Metadata SET operation needs testing

---

## Next Steps

1. Fix `ko2_scan_slots.py` (import errors after protocol refactor)
2. Implement `ko2 ls` command (scan all slots)
3. Implement `ko2 rm` command (delete)
4. Add `ko2 play` (audition)
5. Start TUI framework (curses/textual?)
