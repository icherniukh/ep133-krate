# Sample Management Strategy for EP-133 KO-II

## What We Need to Discover

### Device State (Read-Only)
1. **Sample Inventory**
   - Which slots are occupied (001-999)
   - Sample names
   - Sample sizes
   - Sample metadata (playmode, pitch, pan, etc.)
   - Total memory used/available

2. **Current Project Info**
   - Active project number (1-16)
   - Project name (if available)
   - Patterns in use

3. **Device Status**
   - Firmware version
   - Serial number (optional)
   - Memory statistics

## Efficient Sample Management Ideas

### 1. **Smart Sample Library**
Keep a local database of samples with metadata:
```
~/.ko2-library/
  ├── samples/
  │   ├── kicks/
  │   ├── snares/
  │   └── ...
  ├── library.db (SQLite)
  └── device-state.json
```

**Benefits:**
- Track what's on device vs local
- Avoid re-uploading duplicates
- Tag and search samples
- Sync state across backups

### 2. **Slot Organization System**
Define slot ranges for different purposes:
```
001-100: Kicks
101-200: Snares
201-300: Hats
301-400: Percussion
401-500: Bass
501-600: Melodic
601-700: FX
701-800: Vocals
801-900: Custom
901-999: Temporary/Scratch
```

### 3. **Project-Based Sample Sets**
Each project could have a "sample manifest":
```json
{
  "project": 1,
  "name": "Track 01",
  "samples": [
    {"slot": 1, "file": "kick_808.wav", "hash": "abc123"},
    {"slot": 2, "file": "snare_clap.wav", "hash": "def456"}
  ]
}
```

## Commands to Implement

### Read Operations (Priority)
```bash
ko2 status              # Device info, memory, current project
ko2 list                # List all samples on device
ko2 list --empty        # Show empty slots
ko2 list --project 1    # Samples used in project 1
ko2 info --slot 42      # Detailed info about slot 42
ko2 export-manifest     # Export current device state to JSON
```

### Write Operations (Later)
```bash
ko2 upload sample.wav --slot 42
ko2 upload-batch samples/ --start 100
ko2 delete --slot 42
ko2 organize --auto     # Auto-organize by type
ko2 sync library/       # Sync local library to device
```

## Next Steps

1. **Run monitor.py** - Capture messages while:
   - Pressing pads
   - Switching projects
   - Using the official sample tool
   
2. **Analyze patterns** - Identify SysEx commands for:
   - Querying sample list
   - Reading sample metadata
   - Getting memory info

3. **Build read-only tools first** - Safe exploration before writes

## Test Plan

Try the monitor while doing these actions:
- Press different pads (see if it sends sample info)
- Switch between projects
- Open official sample tool and connect
- Load a sample via official tool
- Delete a sample via official tool
