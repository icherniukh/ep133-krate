# EP-133 KO-II Tools - TODO List

## High Priority

### 1. Fix ko2-optimize to reuse audio2ko2
**Status:** TODO
**Issue:** Currently calls audio2ko2 as subprocess, should reuse the existing script properly
**Solution:** 
- Call audio2ko2 directly with proper path handling
- Or refactor audio2ko2 logic into a Python module
- Ensure backup files are handled correctly

### 2. Interactive TUI Sample Manager
**Status:** TODO
**Description:** Build a text-based interactive interface for managing samples

**Features:**
- Display sample library in a nice table/list
- Command-line input at bottom
- Real-time updates

**Commands:**
```
swap 204 301          # Swap samples in slots 204 and 301
move 204 301          # Move sample from 204 to 301
delete 204            # Delete sample in slot 204
copy 204 301          # Copy sample from 204 to 301
rename 204 "kick"     # Rename sample in slot 204
info 204              # Show detailed info about slot 204
play 204              # Play sample (if possible)
export 204 kick.wav   # Export sample to file
import kick.wav 204   # Import file to slot 204
search "kick"         # Search for samples by name
filter mono           # Filter by type (mono/stereo)
sort name             # Sort by name/slot/size/duration
optimize 204          # Optimize single sample
optimize all          # Optimize all samples
save backup.pak       # Save changes to backup
quit                  # Exit
help                  # Show all commands
```

**TUI Library Options:**
- `rich` - Beautiful terminal formatting, tables, progress bars
- `textual` - Full TUI framework with widgets
- `urwid` - Mature TUI library
- `prompt_toolkit` - Advanced CLI with autocomplete

**Recommended:** `rich` + `prompt_toolkit`
- `rich` for display (tables, colors, formatting)
- `prompt_toolkit` for command input (autocomplete, history)

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ EP-133 Sample Manager - backup.pak                              │
│ 413 samples | 58.1 MB / 128 MB (45.4%) | 586 empty slots       │
├─────────────────────────────────────────────────────────────────┤
│ Slot │ Name                    │ Size    │ Type   │ Duration   │
├──────┼─────────────────────────┼─────────┼────────┼────────────┤
│ 001  │ micro kick              │  44.0KB │ Mono   │ 0.48s      │
│ 002  │ nt kick                 │  42.5KB │ Mono   │ 0.46s      │
│ 003  │ nt kick b               │  65.7KB │ Mono   │ 0.71s      │
│ ...  │ ...                     │ ...     │ ...    │ ...        │
│ 724  │ kicksub_08_641          │ 207.0KB │ Stereo │ 1.20s      │
│ 729  │ ivan-the-best           │  91.5KB │ Mono   │ 1.00s      │
│ 730  │ pey-pivo                │  82.3KB │ Mono   │ 0.90s      │
├─────────────────────────────────────────────────────────────────┤
│ > swap 729 730                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```bash
ko2-tui backup.pak
```

## Medium Priority

### 3. Extract Samples from Backup
**Status:** TODO
```bash
ko2-extract backup.pak --output samples/
ko2-extract backup.pak --slot 724 --output kick.wav
ko2-extract backup.pak --slots 1-100 --output kicks/
```

### 4. Add Samples to Backup
**Status:** TODO
```bash
ko2-add backup.pak samples/*.wav --start-slot 100
ko2-add backup.pak kick.wav --slot 42
ko2-add backup.pak --auto  # Auto-assign to empty slots
```

### 5. Organize Backup by Type
**Status:** TODO
```bash
ko2-organize backup.pak --by-type
ko2-organize backup.pak --custom-layout layout.json
```

### 6. Direct Upload via SysEx
**Status:** TODO
```bash
ko2-upload sample.wav --slot 42
ko2-batch-upload samples/*.wav --start-slot 100
```

## Low Priority

### 7. Sample Library Database
**Status:** TODO
- SQLite database of all samples
- Track samples across backups
- Tag and categorize samples
- Search and filter

### 8. Watch Folder Auto-Convert
**Status:** TODO
- Monitor folder for new samples
- Auto-convert with audio2ko2
- Add to backup automatically

### 9. Sync Tool
**Status:** TODO
- Keep local library in sync with device
- Detect changes
- Bidirectional sync

### 10. Sample Pack Creator
**Status:** TODO
```bash
ko2-pack create "My Kicks" --slots 1-50 --output my-kicks.pak
ko2-pack merge pack1.pak pack2.pak --output combined.pak
```

## Completed ✅

- ✅ audio2ko2 - Audio converter with volume analysis
- ✅ macOS Quick Action integration
- ✅ ko2-list - Backup sample lister
- ✅ ko2-optimize - Backup optimizer (needs fix)
- ✅ Device detection and communication
- ✅ Protocol documentation
- ✅ Backup format analysis

## Notes

### TUI Implementation Plan
1. Install dependencies: `pip install rich prompt_toolkit`
2. Create `ko2-tui` script
3. Load backup into memory
4. Display with `rich.table.Table`
5. Command parser with `prompt_toolkit`
6. Implement core commands (swap, move, delete, copy)
7. Add search/filter/sort
8. Save changes back to backup
9. Add keyboard shortcuts (arrow keys, vim keys)
10. Add help system

### Command Parser Structure
```python
commands = {
    'swap': swap_samples,
    'move': move_sample,
    'delete': delete_sample,
    'copy': copy_sample,
    'rename': rename_sample,
    'info': show_info,
    'search': search_samples,
    'filter': filter_samples,
    'sort': sort_samples,
    'optimize': optimize_sample,
    'save': save_backup,
    'quit': exit_app,
    'help': show_help,
}
```

### Autocomplete
- Command names
- Slot numbers (001-999)
- Sample names
- File paths
