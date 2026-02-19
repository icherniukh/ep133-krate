# EP-133 Protocol Analysis Summary

## Task Completed

Analysis of GitHub repositories for EP-133 KO-II protocol reverse engineering.

## Repositories Analyzed

| Repository | Status | Findings |
|------------|--------|----------|
| `nkatsube/ep133tools` | ❌ Not Found | Likely private/deleted |
| `with_roots/ep-133-file-tools` | ❌ Not Found | Likely private/deleted |
| `garrettjwilke/ep_133_sysex_thingy` | ✅ Analyzed | Sysex files, upload protocol, docs |
| `benjaminr/mcp-koii` | ✅ Analyzed | MIDI control, sound library |

## Key Discoveries

### 1. New Device ID: Project Switching (0x7C)
```
F0 00 20 76 33 40 7C [seq] 05 08 07 01 07 50 [json] 00 F7
```
- Enables switching between 16 projects
- JSON payload: `{"active":8000}` for project 8

### 2. Upload Protocol Confirmed (8-step sequence)
1. Upload Init with metadata (0x6B seq)
2. Upload Data chunk (0x6C seq)
3. Commit step 1 (0x6D seq)
4. Verify step (0x6E seq)
5. Re-init (0x6F seq)
6. Verify again (0x70 seq)
7. Metadata operation (0x71 seq)
8. Finalize with size (0x72 seq)

### 3. Slot Encoding Clarification
- **Upload/Delete**: Big-endian confirmed (external refs show `00 0B` for slot 11)
- **Download**: Big-endian
- **Metadata query**: Little-endian

### 4. Complete WAV Header Spec
- Required smpl chunk (36 bytes)
- LIST/INFO/TNGE with JSON metadata
- Sample rate: 46875 Hz (non-negotiable)

## Files Created

1. **REPO_ANALYSIS.md** - Comprehensive comparison of external repos vs our code
2. **UPLOAD_PROTOCOL_DETAILS.md** - Deep dive into upload sequence
3. **PROTOCOL.md** - Updated with all new findings
4. **ko2_protocol.py** - Added `GET_META` and `PROJECT` Device IDs

## What We Know That They Don't

1. Full download implementation (GET with chunking)
2. 7-bit encoding/decoding functions
3. Clean Python client interface
4. Slot scanning across all 999 slots
5. Error handling with proper exceptions
6. Batch operations (group/compact)

## What They Know That We Don't

1. Project switching protocol (0x7C)
2. Complete 8-step upload sequence
3. Exact WAV header chunk layout
4. Complete sound library mapping (benjaminr repo)

## Gaps in Both

1. Playback/audition protocol (partially documented)
2. Sample rename on device
3. Project file format (.ppak)
4. Pattern/sequence storage

## Next Steps Recommended

1. **Implement project switching**
   ```python
   def switch_project(self, project: int) -> None:
       """Switch to project (1-16)."""
   ```

2. **Verify upload with all 0x7E device IDs**
   - External shows all upload messages using 0x7E
   - We use 0x6C for data, 0x7E for control
   - Test both approaches

3. **Fix delete to use big-endian**
   - Current uses little-endian
   - External confirms big-endian

4. **Add playback/audition**
   - Device ID 0x76 documented but not implemented

## Protocol Constants Reference

```
TE_MFG_ID:     00 20 76
DEVICE_FAMILY: 33 40
CMD_FILE:      05

File Operations:
  01 - INIT
  02 - PUT (upload)
  03 - GET (download)
  06 - DELETE
  07 - METADATA
  0B - VERIFY

Sub-operations:
  PUT:     00=init, 01=data
  GET:     00=init, 01=data
  METADATA: 01=set, 02=get
```

## Sources

- garrettjwilke/ep_133_sysex_thingy: https://github.com/garrettjwilke/ep_133_sysex_thingy
- benjaminr/mcp-koii: https://github.com/benjaminr/mcp-koii
