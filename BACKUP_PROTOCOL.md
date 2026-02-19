# EP-133 Backup Protocol Investigation

## Question
How does the official EP Sample Tool download samples from the device?

## What We Know

### Upload (Write) - ✅ Documented
- Uses SysEx messages
- Init sequence required
- Sample data sent in chunks
- Working examples in `ep_133_sysex_thingy` repo

### Download (Read) - ❓ Unknown
- **No SysEx commands found** for downloading samples
- Device doesn't respond to query commands we tried
- Official tool creates `.pak` (full) or `.ppak` (project) backups
- Backup contains all samples as WAV files

## Theories

### Theory 1: Bulk SysEx Dump
The device might support a "dump all data" SysEx command that:
- Sends entire memory as one large SysEx stream
- Tool receives and parses into WAV files
- Similar to how synthesizers dump patches

**Evidence:**
- Standard MIDI practice for backups
- Would explain why we can't query individual samples
- `.pak` files contain properly formatted WAVs with headers

### Theory 2: WebMIDI Streaming
The web tool might:
- Send a "start backup" command
- Device streams data continuously
- Tool assembles into files

**Evidence:**
- Web tool uses WebMIDI API
- BAK light indicates long operation
- Takes 1-3 minutes (streaming speed)

### Theory 3: USB Mass Storage Mode
Device might:
- Switch to USB storage mode
- Expose memory as filesystem
- Tool reads files directly

**Evidence:**
- ❌ Device doesn't appear as storage device
- ❌ Would be instant, not 1-3 minutes

## How to Investigate

### Method 1: MIDI Sniffer (Recommended)
```bash
python3 midi_sniffer.py
# Then trigger backup in official tool
# Watch for SysEx messages
```

### Method 2: Browser DevTools
1. Open https://teenage.engineering/apps/ep-sample-tool
2. Open DevTools → Console
3. Trigger backup
4. Look for WebMIDI API calls
5. Check Network tab for any HTTP requests

### Method 3: Reverse Engineer Web Tool
1. View page source
2. Find JavaScript files
3. Search for "backup", "download", "sysex"
4. Look for MIDI message construction

### Method 4: Test SysEx Commands
Try commands from repo:
- `unknown_sample_tool_01.syx` - Unknown command from tool
- `unknown_from_update.syx` - Unknown update command

## Next Steps

1. **Run MIDI sniffer** while doing backup
2. **Inspect browser console** during backup
3. **Try unknown SysEx commands** to see responses
4. **Check if device sends unsolicited data** after certain commands

## Current Conclusion

**We cannot programmatically trigger backups yet** because:
- ❌ No documented SysEx command for backup
- ❌ Device doesn't respond to sample query commands
- ❌ Protocol is write-only for individual samples

**Workaround:**
- Use official tool to create backups
- Work with `.pak`/`.ppak` files locally
- Our tools (ko2-list, ko2-optimize) work great with backups

## If We Discover the Protocol

If we find the backup SysEx command, we could build:
- `ko2-backup` - Trigger backup from command line
- `ko2-download` - Download specific samples
- `ko2-sync` - Sync device with local library
- Automated backup scripts

## References

- WebMIDI API: https://developer.mozilla.org/en-US/docs/Web/API/Web_MIDI_API
- SysEx format: https://www.midi.org/specifications
- EP-133 reverse engineering: https://github.com/garrettjwilke/ep_133_sysex_thingy
