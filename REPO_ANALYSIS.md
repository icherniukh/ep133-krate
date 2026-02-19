# EP-133 KO-II Protocol Analysis: External Repositories

## Executive Summary

Analysis of public EP-133 repositories revealed valuable protocol insights. The two requested repositories (`nkatsube/ep133tools` and `with_roots/ep-133-file-tools`) could not be accessed (likely private or deleted), but significant findings were obtained from:

1. **garrettjwilke/ep_133_sysex_thingy** - Contains working sysex files and protocol documentation
2. **benjaminr/mcp-koii** - MIDI control interface (not file transfer, but has sound library)

## Key Findings

### 1. Repository Access Status

| Repository | Status | Notes |
|------------|--------|-------|
| `nkatsube/ep133tools` | ❌ Not Found | May be private, renamed, or deleted |
| `with_roots/ep-133-file-tools` | ❌ Not Found | May be private, renamed, or deleted |
| `garrettjwilke/ep_133_sysex_thingy` | ✅ Analyzed | Working sysex examples |
| `benjaminr/mcp-koii` | ✅ Analyzed | MIDI note control only |

### 2. Protocol Commands Discovered

#### From garrettjwilke/ep_133_sysex_thingy:

**Init Sequence (3 messages):**
```
F0 7E 7F 06 01 F7                                    # Device Identity Request
F0 00 20 76 33 40 61 17 01 F7                        # Init 1
F0 00 20 76 33 40 61 18 05 00 01 01 00 40 00 00 F7   # Init 2
```

**Get Device Info:**
```
F0 00 20 76 33 40 77 14 01 F7
```
- Device ID: `0x77` (matches our GET_INFO)

**Delete Sample (slot 11):**
```
F0 00 20 76 33 40 7E 07 05 00 06 00 0B F7
```
- Device ID: `0x7E` (matches our UPLOAD/DELETE)
- Data: `07 05 00 06 00 0B`
  - `07` - Sequence/counter
  - `05` - CMD_FILE
  - `00` - FIXED_BYTE
  - `06` - DELETE operation
  - `00 0B` - Slot encoding (big-endian: 0x00 = 0, 0x0B = 11)

**Switch to Project 6:**
```
F0 00 20 76 33 40 7C 2A 05 08 07 01 07 50 7B 22 61 00 63 74 69 76 65 22 3A 00 38 30 30 30 7D 00 F7
```
- Device ID: `0x7C` (NEW - Project switching!)
- Contains JSON-like payload: `{"active":8000}`

### 3. Upload Protocol Analysis (from send_tiny_sound/*.syx)

The upload sequence consists of **8 messages**:

| Step | Device ID | Pattern | Purpose |
|------|-----------|---------|---------|
| 01 | 0x7E | `6B 05 40 02 00 05...` | Upload Init with metadata |
| 02 | 0x7E | `6C 05 00 02 01...` | Upload Data (large chunk) |
| 03 | 0x7E | `6D 05 00 02 01 00 01` | Commit step 1 |
| 04 | 0x7E | `6E 05 00 0B 00 01` | Verify/Commit step 2 |
| 05 | 0x7E | `6F 05 00 01 01 00 40 00 00` | Re-Init |
| 06 | 0x7E | `70 05 00 0B 00 01` | Commit step 3 |
| 07 | 0x7E | `71 05 00 07 02 00 01 00 00` | Metadata operation |
| 08 | 0x7E | `72 05 08 07 02 03 68 00 00` | Finalize with size |

**Key observations:**
- All upload messages use `0x7E` (UPLOAD device ID)
- Sequence bytes increment: `6B → 6C → 6D → ...` (starting around 0x6B)
- Pattern `05` (CMD_FILE) appears in all
- Sub-operations: `02` (PUT), `0B`, `01`, `07` (METADATA)

### 4. WAV Header Format Confirmed

From garrettjwilke/notes/notes.hmls:

**Required WAV header structure:**
```
RIFF (4 bytes)
Chunk size (4 bytes)
WAVE (4 bytes)
fmt  (4 bytes)
...
smpl (36 bytes) - Sample chunk
LIST/INFO/TNGE - Contains JSON metadata
```

**Required JSON metadata:**
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

**Sample rate:** 46875 Hz (confirmed)

### 5. Audio Data Encoding

Comparing `data_chunk_original.data` vs `data_chunk_encoded.data`:
- Original: 437 bytes
- Encoded: 499 bytes
- Encoding is **NOT** simple XOR or bit manipulation
- Appears to be 7-bit MIDI encoding with additional transformation
- Our `encode_7bit()`/`decode_7bit()` functions should handle this

### 6. New Device ID Discovered

| Device ID | Usage | Status |
|-----------|-------|--------|
| 0x61 | Initialization | ✅ Known |
| 0x7C | Project Switch | 🆕 **NEW** |
| 0x7D | Download (GET) | ✅ Known |
| 0x7E | Upload (PUT/DELETE) | ✅ Known |
| 0x77 | Info/Metadata | ✅ Known |

## Comparison: What We Know vs What They Know

### External Repositories Have That We Don't:

1. **Project Switching (0x7C)** - We haven't implemented this
2. **Working upload examples** - Full 8-step sequence documented
3. **Complete WAV header spec** - Exact chunk layout
4. **Sound library mapping** - benjaminr/mcp-koii has complete sound-to-pad mapping

### We Have That External Repositories Don't:

1. **7-bit encoding/decoding** - Our `encode_7bit()`/`decode_7bit()` functions
2. **Download protocol** - Fully working GET implementation
3. **Slot scanning** - Metadata query for all slots
4. **Python client class** - Clean `EP133Client` interface
5. **Error handling** - Proper exception types
6. **Batch operations** - `group()` for compacting samples

### Gaps in Both:

1. **Playback/Audition** - Protocol mentioned but not fully documented
2. **Sample rename on device** - Metadata SET needs testing
3. **Project file format** - `.ppak` structure unknown
4. **Pattern/sequence data** - How patterns are stored/retrieved

## Conflicting Information

| Aspect | Our Understanding | External Finding | Resolution |
|--------|-------------------|------------------|------------|
| Init sequence | Same 3-message sequence | Same 3-message sequence | ✅ Confirmed |
| Delete slot encoding | Little-endian | Big-endian (`00 0B` for slot 11) | ⚠️ Needs verification |
| Upload device ID | 0x6C for data, 0x7E for control | All messages use 0x7E | ⚠️ May need clarification |
| Sample rate | 46875 Hz | 46875 Hz | ✅ Confirmed |

## Recommended Actions

### High Priority:

1. **Add Project Switching (0x7C)**
   ```python
   def switch_project(self, project_num: int) -> None:
       """Switch to project 1-16."""
       # F0 00 20 76 33 40 7C [SEQ] 05 08 07 01 07 50 [JSON] F7
   ```

2. **Verify Delete Endianness**
   - Test both little-endian and big-endian slot encoding
   - Current code uses little-endian; external examples show big-endian

3. **Verify Upload Device IDs**
   - External shows all 0x7E
   - We use 0x6C for data chunks, 0x7E for control
   - May need to consolidate to 0x7E

### Medium Priority:

4. **Add Playback/Audition**
   - Device ID 0x76 mentioned in our code
   - Needs implementation

5. **Import Sound Library**
   - From benjaminr/mcp-koii
   - Useful for pad-to-sound mapping

### Low Priority:

6. **WAV Header Generator**
   - Create proper headers with JSON metadata
   - Useful for upload preparation

## Protocol Additions

### New Constants to Add:

```python
class DeviceId(IntEnum):
    # ... existing ...
    PROJECT = 0x7C         # NEW: Project switching

class FileOp(IntEnum):
    # ... existing ...
    VERIFY = 0x0B          # NEW: Verify commit step
```

### New Command to Add:

```python
def switch_project(self, project: int) -> None:
    """Switch to project (1-16)."""
    if not 1 <= project <= 16:
        raise ValueError(f"Project must be 1-16, got {project}")

    # JSON payload for project switch
    payload = f'{{"active":{project * 1000}}}'.encode()

    msg = bytes([
        SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.PROJECT,
        self._next_seq(), CMD_FILE, 0x08, 0x07, 0x01, 0x07, 0x50
    ]) + payload + bytes([0x00, SYSEX_END])

    self._send_sysex(msg)
```

## Code Snippets from External Repos

### Complete Upload Sequence (garrettjwilke):

```python
# Step 1: Upload Init
msg = bytes([F0, 0x00, 0x20, 0x76, 0x33, 0x40, 0x7E, 0x6B,
             0x05, 0x40, 0x02, 0x00, 0x05, ...]) + encoded_metadata + [F7]

# Step 2: Upload Data
msg = bytes([F0, 0x00, 0x20, 0x76, 0x33, 0x40, 0x7E, 0x6C,
             0x05, 0x00, 0x02, 0x01, ...]) + encoded_data + [F7]

# Steps 3-8: Various commit/verify messages
# All use device ID 0x7E with incrementing sequence bytes
```

## Conclusion

The external repositories validate most of our protocol understanding while revealing a few gaps (notably project switching). The main discrepancies are in upload device ID usage and delete slot encoding, which should be tested against actual hardware.

Our implementation is more complete for download operations and has better code organization. The external repositories provide valuable reference implementations but lack the full-featured client interface we've built.

## Sources

- garrettjwilke/ep_133_sysex_thingy: https://github.com/garrettjwilke/ep_133_sysex_thingy
- benjaminr/mcp-koii: https://github.com/benjaminr/mcp-koii
- nkatsube/ep133tools: NOT FOUND
- with_roots/ep-133-file-tools: NOT FOUND
