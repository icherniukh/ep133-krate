# EP-133 KO-II Tools

Toolkit for managing Teenage Engineering EP-133 KO-II samples and backups.

## Quick Start

```bash
# List samples in backup
ko2-list backup.pak

# Optimize entire backup
ko2-optimize backup.pak

# Launch interactive device TUI
python ko2.py tui
```

## Progress (rough estimates)

**Protocol Understanding:** `[########--] 80%`  
**Phase 1 (CLI):** `[##########] 100%`  
**Phase 2 (TUI):** `[###-------] 30%`  
**Phase 3 (Desktop/Web/Mobile):** `[----------] 0%`

## Performance Notes (2026-03-02)

- Download receive path is now event-driven (blocking MIDI queue reads) instead of hot-spin polling.
- On-device profile run for a ~272KB sample improved from ~6.34s to ~2.60s (`ko2 get`, cProfile run).
- TUI worker now emits operation timing telemetry and uses selective metadata hydration for post-op refresh.

## Tools

### 1. ko2-list - Backup Sample Lister

List all samples from EP-133 backup file (`.pak`).

**Usage:**
```bash
ko2-list <backup.pak>
```

**Output:**
```
📊 EP-133 Backup Analysis

File: backup.pak
Size: 47.1 MB

Device: EP-133 v2.0.5
Backup: 2026-02-11T10:43:05.026Z

================================================================================
Slot   Name                                     Size     Type     Duration
================================================================================
001    micro kick                                 44.0KB Mono      0.48s
002    nt kick                                    42.5KB Mono      0.46s
724    kicksub_08_641                            207.0KB Stereo    1.20s
...

📈 Summary:
   Total samples: 413
   Total size: 58.1 MB
   Empty slots: 586
   Memory used: 45.4%
```

---

### 2. ko2-optimize - Backup Optimizer

Optimize all samples in a backup file.

**Usage:**
```bash
ko2-optimize <input.pak> [output.pak]
```

**Features:**
- Converts all samples to optimal format (46.875kHz, 16-bit, mono)
- Shows progress for each sample
- Displays before/after statistics
- Creates new optimized backup

**Example:**
```bash
ko2-optimize "My Backup.pak"
# Creates: My Backup_optimized.pak

ko2-optimize old.pak new.pak
# Creates: new.pak
```

**Note:** Uses `audio2ko2` from parent directory

---

### 3. ko2 tui - Interactive Device TUI (Phase 2 MVP)

Browse slots and run core operations from a Textual interface.

**Usage:**
```bash
# Device is auto-selected
python ko2.py tui

# Auto log path in captures/tui-*.jsonl
python ko2.py tui --debug

# Explicit debug log path
python ko2.py tui --debug captures/session.jsonl

# Optional separate dialog/status log file (with --debug)
python ko2.py tui --debug captures/session.jsonl --dialog-log captures/session-dialog.log
```

**Current TUI features:**
- 999-slot browser table
- Detail pane for selected slot with high-resolution stylized waveform preview
- Core actions: download (`d`), upload (`u`), rename (`r`), delete (`backspace`)
- Selection ergonomics: `space` toggles selection (auto-advance only on select), `enter` uses current context, `escape` cancels move mode
- Manual refresh (`ctrl+r`) and post-operation refresh
- Operation log pane + concise debug protocol summaries in debug mode (chunk-level chatter suppressed)
- Debug trace and dialog/status logs are written to separate files in debug mode
- Waveform previews are persisted in a single-file KV store: `captures/waveform-kv.json`
- Background waveform precalc for all used slots (idle/low-load only)

**Waveform precalc tuning (optional):**
```bash
# Single-core render path (default)
KO2_TUI_WAVEFORM_PRECALC_MODE=single python ko2.py tui

# Threaded render path for comparison
KO2_TUI_WAVEFORM_PRECALC_MODE=threaded python ko2.py tui

# Keep background precalc chill on busy systems (default 0.75)
KO2_TUI_WAVEFORM_PRECALC_MAX_LOAD=0.60 python ko2.py tui
```

### 4. ko2 fingerprint - KV Fingerprint Store

Use one-file waveform/hash storage for fast reuse and verification.

```bash
# Download slot, compute hash + waveform bins, store in captures/waveform-kv.json
python ko2.py fingerprint write 43

# Read cached fingerprint info for a slot
python ko2.py fingerprint read 43

# Verify device slot against cached hash (and optional WAV file)
python ko2.py fingerprint verify 43 ./sample.wav
```

---

## MIDI Sniffer / Proxy

Use `midi_proxy.py` to capture SysEx traffic (official tool or ko2 commands).

Capture (TX+RX) via proxy:
```bash
python midi_proxy.py --proxy captures/sniffer.jsonl
```

Hunt for specific traffic during capture (prints matches to stdout):
```bash
python midi_proxy.py --proxy --hunt get_meta
python midi_proxy.py --proxy --hunt get_meta --hunt meta_rsp
python midi_proxy.py --proxy --hunt meta_get --hunt meta_set
python midi_proxy.py --proxy --hunt cmd=0x75 --hunt fileop=0x04
```
HUNT lines now include parsed META_SET fields (`active`, `sym`, `sample.start`, `sample.end`) when present.

Capture raw binary:
```bash
python midi_proxy.py --proxy --format raw captures/sniffer-raw.bin
```

Capture as standard MIDI file:
```bash
python midi_proxy.py --proxy --format mid captures/sniffer.mid
```

Pretty-print a capture:
```bash
python midi_proxy.py --pretty captures/sniffer.jsonl
python midi_proxy.py --pretty --format raw captures/sniffer-raw.bin
```
See `docs/CAPTURE_FORMAT.md` for raw/.mid file format details.

---

## Getting Backups from Device

### Full Backup (All Samples + All Projects)

1. Open https://teenage.engineering/apps/ep-sample-tool in browser
2. Connect EP-133 via USB
3. Click "Backup" button
4. Wait for BAK light to finish
5. Download saves as `.pak` file

**Time:** 1-3 minutes depending on number of samples

### Project-Only Backup (Faster!)

The official tool supports backing up individual projects:

1. Open EP Sample Tool
2. Click "Backup" → Select specific project
3. Much faster (< 1 minute)
4. Saves as `.ppak` file
5. **Includes only samples used in that project**

**Results:**
- File size: ~11 MB (vs 47 MB full backup)
- Samples: Only those used in the project (~46 vs 413)
- Time: ~1 minute (vs 2-3 minutes)
- 4x smaller and faster!

**When to use:**
- ✅ Quick project snapshots
- ✅ Sharing specific projects with their samples
- ✅ Version control for individual projects
- ✅ When you only need one project's data
- ❌ Don't use if you need all samples

**Note:** Despite the name, it's not "project only" - it includes the samples used in that project!

---

## Backup File Format

EP-133 backups are ZIP files with `.pak` extension:

```
backup.pak (ZIP)
├── meta.json          # Device info, firmware, timestamp
├── projects/          # Project files (P01-P16.tar)
│   ├── P01.tar
│   ├── P02.tar
│   └── ...
└── sounds/            # All samples
    ├── 001 sample name.wav
    ├── 002 another sample.wav
    └── ...
```

**Filename format:** `NNN name.wav`
- First 3 digits: Slot number (001-999)
- Space separator
- Rest: Sample name

---

## Audio Specifications

**EP-133 Requirements:**
- Sample rate: 46.875 kHz (not 44.1 or 48!)
- Bit depth: 16-bit
- Format: WAV
- Channels: Mono or Stereo

**Memory:**
- Total slots: 999
- Total memory: 128 MB (newer models)
- Typical sample: 50-200 KB
- Average capacity: 400-600 samples

---

## Workflow Examples

### Basic Workflow
```bash
# 1. Get backup from device (via official tool)
# 2. List samples
ko2-list "My Backup.pak"

# 3. Optimize if needed
ko2-optimize "My Backup.pak"

# 4. Upload optimized backup back to device (via official tool)
```

### Quick Project Backup
```bash
# For quick pattern/sequence backups without samples:
# 1. Use "Projects Only" backup in official tool
# 2. Much faster (< 1 minute)
# 3. Smaller file size
# 4. Samples remain unchanged on device
```

### Preparing New Samples
```bash
# Use audio2ko2 from parent directory:
cd ..
./audio2ko2 kick.mp3
./audio2ko2 snare.wav
./audio2ko2 -s pad.flac  # Keep stereo for pads
```

---

## Troubleshooting

### "Permission denied" errors
```bash
chmod +x audio2ko2 ko2-list ko2-optimize
```

### "Command not found"
Add to PATH or use full path:
```bash
/Users/ivan/proj/dotfiles-stow/scripts/.scripts/audio2ko2 sample.mp3
```

### Backup won't open
Backups are ZIP files, verify:
```bash
file backup.pak
unzip -l backup.pak
```

### Sample not playing on device
- Check format: Must be 46.875 kHz, 16-bit WAV
- Use audio2ko2 to convert
- Verify with: `ffprobe sample.wav`

---

## Development

### Project Structure
```
ko2-tools/
├── README.md              # This file
├── PROTOCOL.md            # SysEx protocol docs (reverse-engineered)
├── STATUS.md              # Implementation status + tech gaps
├── PPAK_FORMAT.md         # .ppak project file format
├── ko2.py                 # Main CLI
├── ko2_client.py          # Thin MIDI transport client
├── ko2_models.py          # Declarative Descriptor DSL & Messages
├── ko2_operations.py      # Stateful multi-step operations
├── ko2_types.py           # Primitive wire-format types
├── ko2_tui/               # Textual TUI app/state/worker
├── tests/unit/            # Unit tests (no device required)
├── tests/e2e/             # E2E tests (require EP-133)
└── scripts/legacy/        # Archived protocol-probing scripts
```
- `monitor.py` - Monitor MIDI messages

---

## References

- [EP-133 Official Site](https://teenage.engineering/products/ep-133)
- [EP Sample Tool](https://teenage.engineering/apps/ep-sample-tool)
- [SysEx Protocol Research](https://github.com/garrettjwilke/ep_133_sysex_thingy)

---

## License

MIT

---

## Contributing

Found a bug? Have a feature request? Open an issue or submit a PR!
