# EP-133 KO-II Tool Ideas

## 3 Most Useful Yet Simple Features

### 1. **Batch Sample Uploader**
**What**: Upload multiple WAV files to EP-133 in one command
**Why**: Currently requires using the web tool one-by-one
**Complexity**: Medium
**Command**: `ko2-upload samples/*.wav --start-slot 100`

**Benefits**:
- Save time when loading sample packs
- Organize samples by folder structure
- Auto-convert to 46.875kHz if needed
- Show progress bar

---

### 2. **Sample Inventory Lister**
**What**: List all samples currently on the device with metadata
**Why**: No easy way to see what's loaded without the web tool
**Complexity**: Low (read-only)
**Command**: `ko2-list --format table`

**Output**:
```
Slot  Name              Size    Duration  Type
001   kick_01.wav       45KB    0.5s      Mono
002   snare_heavy.wav   67KB    0.8s      Stereo
...
```

**Benefits**:
- Quick inventory check
- Export to CSV/JSON
- Find empty slots
- Search by name

---

### 3. **Quick Backup Tool**
**What**: Fast project-only backup (no samples)
**Why**: Official tool backs up everything (slow)
**Complexity**: Medium
**Command**: `ko2-backup --project-only backup.zip`

**Benefits**:
- Backup in under 1 minute
- Version control friendly
- Restore specific projects
- Automated backups via cron

---

## Implementation Priority

1. **Start with #2 (Sample Lister)** - Read-only, safest, most useful for learning protocol
2. **Then #1 (Batch Uploader)** - Builds on lister, adds write capability
3. **Finally #3 (Quick Backup)** - Most complex, requires understanding full protocol

## Next Steps

1. Test `detect.py` with device plugged in
2. Capture SysEx messages from official tool
3. Implement sample listing (read-only)
4. Test and iterate
