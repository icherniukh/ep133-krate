# EP-133 KO-II Tools - Session Summary

## What We Built Today

### 1. Audio Conversion Tools
- ✅ **audio2ko2** - Convert any audio to EP-133 format (46.875kHz, 16-bit, mono WAV)
  - Auto-backup original files
  - Volume analysis with color-coded verdicts
  - Memory savings calculation
  - Optional normalization

- ✅ **macOS Quick Action** - Right-click "Optimize for KO-II" in Finder

### 2. Document Tools
- ✅ **md2pdf** - Convert markdown to PDF
  - Three engines: weasyprint (default), Chrome, LaTeX
  - Clean output for documentation

### 3. Media Extraction Tools
- ✅ **extract-exif** - Extract all EXIF metadata from files
  - Comprehensive data extraction
  - Unknown tags included
  - Multiple output formats

- ✅ **extract-images** - Extract embedded images from PDFs
  - Extracts all image types
  - Organized output naming

### 4. EP-133 Communication Tools

#### Working
- ✅ **Device detection** - Find EP-133 via MIDI
- ✅ **Device info query** - Get firmware, serial, model
- ✅ **Protocol documentation** - Reverse-engineered SysEx format

#### Discovered Protocol
```
F0 00 20 76 33 40 [command] [data...] F7
```

Commands:
- `0x77` - Get device info ✅
- `0x7E` - Delete sample ✅
- `0x6C` - Upload sample ✅
- `0x7C` - Switch project ✅
- `0x75/0x76` - Query samples ❓ (needs more testing)

## Current Status

### What Works
- Device communication established
- Can send commands
- Can receive responses
- Protocol structure understood

### What Needs Testing (After Reboot)
- Sample listing/download
- Actual sample data retrieval
- Batch operations

### Alternative Approach
If direct sample reading doesn't work:
- Work with backup ZIP files
- Parse backup format
- Build backup manipulation tools

## Next Steps

1. **After device reboot:**
   - Test sample queries with fresh device state
   - Try with known occupied slots
   - Monitor official tool's communication

2. **If reading still doesn't work:**
   - Build backup file parser
   - Create sample inventory from backups
   - Batch backup modification tools

## Files Created

```
/Users/ivan/proj/dotfiles-stow/scripts/.scripts/
├── audio2ko2                    # Audio converter
├── extract-exif                 # EXIF extractor
├── extract-images               # Image extractor
├── md2pdf                       # Markdown to PDF
├── install-ko2-quickaction      # macOS Quick Action installer
└── ko2-tools/                   # EP-133 tools
    ├── README.md                # Protocol overview
    ├── PROTOCOL.md              # Detailed protocol docs
    ├── IDEAS.md                 # Feature ideas
    ├── MANAGEMENT.md            # Sample management strategy
    ├── DISCOVERY.md             # Discovery results
    ├── REALITY.md               # Protocol limitations
    ├── detect.py                # Device detection
    ├── test_comm.py             # Basic communication test
    ├── test_protocol.py         # Protocol verification
    ├── monitor.py               # Message monitor
    ├── probe.py                 # Command probe
    ├── query_samples.py         # Sample query attempts
    ├── decode_info.py           # Response decoder
    ├── test_download.py         # Download test
    ├── scan_slots.py            # Slot scanner
    └── quick_scan.py            # Fast full scan
```

## Achievements 🎉

- Created 4 production-ready utility scripts
- Established EP-133 MIDI communication
- Documented reverse-engineered protocol
- Built comprehensive testing suite
- macOS integration with Quick Actions

Ready to continue after reboot!

## 2026-02-20 CLI work

- Added filesystem-based `/sounds` listing helpers and slot resolution utilities so `ko2 ls` can reflect the device inventory instead of slot scan; introduced `ko2 fs-ls` for raw FILE LIST debugging and `ko2 rename` backed by the filesystem metadata API. (`ko2.py`)
- Wired `optimize`, `optimize-all`, and `squash --execute` to download via temporary files, create `.ko2-backups` `.bak` copies, and re-upload through `ko2_backup.backup_copy` before mutating the device. (`ko2.py`, `ko2_backup.py`)
- Documented slot-node resolution utility and extended `EP133Client` to expose `list_sounds()` + `slot_from_sound_entry()` for future TUI workflows. (`ko2_client.py`, `ko2_protocol.py`)
- Added unit tests covering FILE LIST parsing/slot resolution and documented the new helpers; pytest run `python -m pytest`. (`tests/unit/test_file_list.py`, `pytest.ini`)
