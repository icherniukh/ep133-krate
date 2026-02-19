# EP-133 KO-II Sample Management - Final Findings

## Summary

After extensive testing, we've determined the optimal workflow for managing EP-133 samples.

## Key Discoveries

### 1. Device Communication Protocol

**What Works:**
- ✅ Device detection via MIDI
- ✅ Device info query (firmware, serial, model)
- ✅ Sample upload via SysEx
- ✅ Sample deletion via SysEx
- ✅ Project switching via SysEx

**What Doesn't Work:**
- ❌ Direct sample download/reading
- ❌ Sample listing via SysEx
- ❌ Sample metadata queries

**Conclusion:** The EP-133 protocol is **write-only** for sample operations.

### 2. Backup File Format

**File Extension:** `.pak` (actually a ZIP file)

**Structure:**
```
backup.pak (ZIP)
├── meta.json          # Device info, firmware version, timestamp
├── projects/          # Project files (P01-P16.tar)
│   ├── P01.tar
│   ├── P02.tar
│   └── ...
└── sounds/            # All samples
    ├── 001 sample name.wav
    ├── 002 another sample.wav
    └── ...
```

**Filename Format:** `NNN name.wav`
- First 3 characters: Slot number (001-999)
- Space separator
- Rest: Sample name
- Extension: `.wav`

**Audio Format:**
- Sample rate: 46.875 kHz
- Bit depth: 16-bit
- Channels: Mono or Stereo
- Special header with JSON metadata (added by device)

### 3. Sample Management Workflow

**Current Best Practice:**
1. Create backup via official tool (saves as `.pak`)
2. Analyze backup with `ko2-list`
3. Extract/modify samples locally
4. Prepare samples with `audio2ko2` (converts to correct format)
5. Add to backup or upload individually

## Tools We Built

### 1. Audio Conversion
**Script:** `audio2ko2`
- Converts any audio to EP-133 format (46.875kHz, 16-bit, mono WAV)
- Creates backup of original
- Shows volume analysis with color-coded verdicts
- Calculates memory savings
- Optional normalization

**Usage:**
```bash
audio2ko2 sample.mp3           # Convert to mono WAV
audio2ko2 -s sample.wav        # Convert to stereo
audio2ko2 -n sample.flac       # Normalize
```

**macOS Integration:**
- Right-click → Quick Actions → "Optimize for KO-II"

### 2. Backup Analysis
**Script:** `ko2-list`
- Lists all samples from `.pak` backup
- Shows slot number, name, size, type, duration
- Calculates total memory usage
- Identifies empty slots

**Usage:**
```bash
ko2-list backup.pak
```

**Output:**
```
Slot   Name                                     Size     Type     Duration
001    micro kick                                 44.0KB Mono      0.48s
002    nt kick                                    42.5KB Mono      0.46s
...
📈 Summary:
   Total samples: 413
   Total size: 58.1 MB
   Empty slots: 586
   Memory used: 45.4%
```

## Integration Plan

### Phase 1: Backup-Based Workflow (Recommended)
Build tools that work with `.pak` files:

1. **ko2-extract** - Extract samples from backup
   ```bash
   ko2-extract backup.pak --output samples/
   ko2-extract backup.pak --slot 724 --output kick.wav
   ```

2. **ko2-add** - Add samples to backup
   ```bash
   ko2-add backup.pak samples/*.wav --start-slot 100
   ```

3. **ko2-optimize** - Batch optimize all samples in backup
   ```bash
   ko2-optimize backup.pak --output optimized.pak
   ```
   - Converts all samples to optimal format
   - Removes duplicates
   - Compresses backup

4. **ko2-organize** - Reorganize samples by type
   ```bash
   ko2-organize backup.pak --by-type
   ```
   - Kicks: 001-100
   - Snares: 101-200
   - Hats: 201-300
   - etc.

### Phase 2: Direct Upload (Advanced)
For samples that need immediate upload:

1. **ko2-upload** - Upload single sample
   ```bash
   ko2-upload sample.wav --slot 42
   ```
   - Auto-converts with `audio2ko2`
   - Sends via SysEx
   - Verifies upload

2. **ko2-batch-upload** - Upload multiple samples
   ```bash
   ko2-batch-upload samples/*.wav --start-slot 100
   ```

### Phase 3: Automation
1. **Watch folder** - Auto-convert and add to backup
2. **Sync tool** - Keep local library in sync with device
3. **Sample library manager** - SQLite database of samples

## File Locations

```
/Users/ivan/proj/dotfiles-stow/scripts/.scripts/
├── audio2ko2                    # Audio converter ✅
├── extract-exif                 # EXIF extractor ✅
├── extract-images               # Image extractor ✅
├── md2pdf                       # Markdown to PDF ✅
├── install-ko2-quickaction      # macOS Quick Action ✅
└── ko2-tools/                   # EP-133 tools
    ├── ko2-list                 # Backup lister ✅
    ├── ko2-extract              # TODO
    ├── ko2-add                  # TODO
    ├── ko2-optimize             # TODO (integrates audio2ko2)
    ├── ko2-organize             # TODO
    ├── ko2-upload               # TODO
    └── ko2-batch-upload         # TODO
```

## Next Steps

1. **Immediate:** Build `ko2-optimize` that:
   - Reads `.pak` backup
   - Runs `audio2ko2` on each sample
   - Creates optimized backup
   - Shows before/after stats

2. **Short-term:** Build extraction and addition tools

3. **Long-term:** Direct upload tools using SysEx protocol

## Technical Notes

### Sample Header Format
EP-133 adds this JSON header to WAV files:
```json
{
  "sound.playmode":"oneshot",
  "sound.rootnote":60,
  "sound.pitch":0,
  "sound.pan":0,
  "sound.amplitude":100,
  "envelope.attack":0,
  "envelope.release":255,
  "time.mode":"off"
}
```

### SysEx Protocol
```
F0 00 20 76 33 40 [command] [data...] F7

Commands:
- 0x77: Get device info
- 0x7E: Delete sample
- 0x6C: Upload sample (requires init sequence)
- 0x7C: Switch project
```

### Memory Limits
- Total slots: 999
- Total memory: 128 MB (newer models)
- Typical sample: 50-200 KB
- Average capacity: ~400-600 samples

## References

- Reverse engineering: https://github.com/garrettjwilke/ep_133_sysex_thingy
- Official tool: https://teenage.engineering/apps/ep-sample-tool
- Audio specs: 46.875 kHz, 16-bit, mono/stereo WAV
