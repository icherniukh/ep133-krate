# EP-133 SysEx Protocol (Reverse Engineered)

## Message Structure

All EP-133 commands follow this format:
```
F0 00 20 76 33 40 [devid] [seq] 05 [flags] [op] [subop] [data...] F7
```

Where:
- `F0` = SysEx start
- `00 20 76` = Teenage Engineering manufacturer ID
- `33 40` = Device family (EP-133)
- `[devid]` = Device ID byte (0x61, 0x77, 0x7C, 0x7D, 0x7E, etc.)
- `[seq]` = Sequence byte (increments per message)
- `05` = CMD_FILE (file operations command group)
- `[flags]` = Operation flags (0x00, 0x08, 0x40, etc.)
- `[op]` = File operation (0x01-0x07)
- `[subop]` = Sub-operation type
- `[data...]` = Operation-specific data (7-bit encoded if large)
- `F7` = SysEx end

## Device IDs

| ID | Name | Usage |
|----|------|-------|
| 0x61 | INIT | Initialization sequence |
| 0x77 | INFO | Device info, metadata queries |
| 0x7C | PROJECT | Project switching (NEW) |
| 0x7D | DOWNLOAD | File download (GET) |
| 0x7E | UPLOAD | File upload (PUT), DELETE |
| 0x37 | RESPONSE | Standard device response |
| 0x3D | RESPONSE_ALT | Alternative response (downloads) |

## File Operations

| Op | Name | Usage |
|----|------|-------|
| 0x01 | INIT | Initialize communication |
| 0x02 | PUT | Upload file |
| 0x03 | GET | Download file |
| 0x04 | LIST | List files (unconfirmed) |
| 0x05 | PLAYBACK | Playback/audition control |
| 0x06 | DELETE | Delete sample |
| 0x07 | METADATA | Metadata operations |
| 0x0B | VERIFY | Verify commit (upload) |

## Common Commands

### Device Identity Request
```
F0 7E 7F 06 01 F7
```
Universal MIDI device inquiry.

### Initialization Sequence (Required before operations)
```
F0 00 20 76 33 40 61 17 01 F7
F0 00 20 76 33 40 61 18 05 00 01 01 00 40 00 00 F7
```
- Device ID: `0x61` (INIT)
- Second message sets up communication parameters

### Get Device Info
```
F0 00 20 76 33 40 77 14 01 F7
```
- Device ID: `0x77` (INFO)
- Response contains device information

### Get Sample Metadata
```
F0 00 20 76 33 40 75 [slot] 05 08 07 02 [slot_hi] [slot_lo] 00 00 F7
```
- Device ID: `0x75` (GET_META)
- Returns JSON with: name, sym, samplerate, format

### Delete Sample
```
F0 00 20 76 33 40 7E [seq] 05 00 06 [slot_lo] [slot_hi] F7
```
- Device ID: `0x7E` (UPLOAD)
- Operation: `0x06` (DELETE)
- Slot encoding: big-endian (confirmed from external refs)

### Switch Project (NEW)
```
F0 00 20 76 33 40 7C [seq] 05 08 07 01 07 50 [json_data] 00 F7
```
- Device ID: `0x7C` (PROJECT)
- JSON payload: `{"active":8000}` for project 8
- Project numbers are encoded as value * 1000

## Upload Protocol (PUT)

The upload consists of **8 messages** sent in sequence:

### 1. Upload Init
```
F0 00 20 76 33 40 7E [seq] 05 40 02 00 05 [slot_hi] [slot_lo] [7bit: size+name+meta] F7
```
- Flags: `0x40` (upload init mode)
- Operation: `0x02` (PUT)
- Sub-op: `0x00` (PUT_INIT)
- File type: `0x05` (sample)
- Data: 7-bit encoded (size + filename + metadata JSON)

### 2. Upload Data Chunk
```
F0 00 20 76 33 40 7E [seq] 05 [flags] 02 01 [offset_lo] [offset_hi] [7bit: audio_data] F7
```
- Sub-op: `0x01` (PUT_DATA)
- Offset: little-endian byte offset into file
- Data: 7-bit encoded audio samples (~440 bytes per chunk)

### 3-6. Commit/Verify Steps
```
F0 00 20 76 33 40 7E [seq] 05 00 02 01 00 01 F7           # Commit 1
F0 00 20 76 33 40 7E [seq] 05 00 0B 00 01 F7              # Verify
F0 00 20 76 33 40 7E [seq] 05 00 01 01 00 40 00 00 F7     # Re-init
F0 00 20 76 33 40 7E [seq] 05 00 0B 00 01 F7              # Verify again
```

### 7. Metadata Operation
```
F0 00 20 76 33 40 7E [seq] 05 00 07 02 00 01 00 00 F7
```
- Operation: `0x07` (METADATA)
- Sub-op: `0x02` (likely SET)

### 8. Finalize
```
F0 00 20 76 33 40 7E [seq] 05 08 07 02 [7bit: size] 00 00 F7
```
- Flags: `0x08` (finalize mode)
- Final 7-bit encoded size value

## Download Protocol (GET)

### 1. Get Init
```
F0 00 20 76 33 40 7D [seq] 05 00 03 00 [slot_hi] [slot_lo] [offset: 5 bytes] F7
```
- Device ID: `0x7D` (DOWNLOAD)
- Operation: `0x03` (GET)
- Sub-op: `0x00` (GET_INIT)
- Slot encoding: **big-endian**
- Offset: 5 zero bytes
- Response: file info including size (in 7-bit encoded .pcm filename)

### 2. Get Data Chunk
```
F0 00 20 76 33 40 7D [seq] 05 00 03 01 [page_hi] [page_lo] F7
```
- Sub-op: `0x01` (GET_DATA)
- Page: big-endian, **each byte must be 7-bit (0-127)**
  - `page_lo = page & 0x7F`
  - `page_hi = (page >> 7) & 0x7F`
  - Max page: 16383 (14 bits)
- Response: 7-bit encoded audio chunk

## 7-Bit Encoding

All variable-length data must be 7-bit encoded for MIDI transmission:

```python
def encode_7bit(data: bytes) -> bytes:
    result = bytearray()
    i = 0
    while i < len(data):
        chunk = data[i:i+7]
        high_bits = 0
        for j, byte in enumerate(chunk):
            high_bits |= ((byte >> 7) << j)
        result.append(high_bits)
        for byte in chunk:
            result.append(byte & 0x7F)
        i += 7
    return bytes(result)

def decode_7bit(data: bytes) -> bytes:
    result = bytearray()
    i = 0
    while i < len(data):
        high_bits = data[i]
        for j in range(min(7, len(data) - i - 1)):
            result.append(data[i + 1 + j] | (((high_bits >> j) & 0x01) << 7))
        i += 8
    return bytes(result)
```

## Slot Encoding

| Operation | Encoding | Notes |
|-----------|----------|-------|
| Upload | Big-endian | High byte first |
| Download | Big-endian | High byte first |
| Delete | Big-endian | High byte first |
| Metadata Query | Little-endian | Low byte first |

Example for slot 11 (0x0B):
- Big-endian: `00 0B`
- Little-endian: `0B 00`

## WAV File Requirements

### Format
- Sample rate: **46875 Hz** (critical!)
- Bit depth: 16-bit
- Channels: Mono (stereo may work but mono is standard)
- Sample format: Little-endian signed 16-bit

### Required WAV Header

Standard WAV headers work, but EP-133 adds:

1. **smpl chunk** (36 bytes) - Sample loop information
2. **LIST/INFO/TNGE chunk** - JSON metadata

Required JSON metadata:
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

### Audio Conversion

Convert to EP-133 format:
```bash
sox input.wav -c 1 -r 46875 -b 16 output.wav
```

Or use the `audio2ko2` tool.

## Sample Slots

- Total: **999 slots** (001-999)
- Slot numbers encoded as described above
- Empty slots return no metadata response

## Projects

- Total: **16 projects** (1-16)
- Switch via Device ID 0x7C
- Each project has independent samples
- Project value in JSON is encoded as `project_num * 1000`

## Implementation Notes

1. **Init is required** - Always send init sequence before file operations
2. **Sequence bytes** - Must increment for each message (0-127, wraps)
3. **7-bit encoding** - All large data payloads must be encoded
4. **Timing** - Delays of 50-100ms between messages recommended
5. **Endianness** - Varies by operation (see table above)
6. **Response filtering** - Filter by Device ID in response byte

## Known Issues

1. **Delete endianness** - Some sources show little-endian, external refs show big-endian
2. **Upload device IDs** - Some use 0x6C for data, external refs show all 0x7E
3. **Playback** - Protocol not fully documented
4. **Project files** - .ppak format unknown

## Tools

### Convert audio:
```bash
sox input.wav -c 1 -r 46875 -b 16 output.wav
audio2ko2 input.mp3  # Creates properly formatted WAV
```

### Python tools (this repo):
```bash
ko2.py info <slot>     # Get sample metadata
ko2.py get <slot>      # Download sample
ko2.py put <file>      # Upload sample (in progress)
ko2.py rm <slot>       # Delete sample
ko2.py scan            # List all samples
```

## References

- https://github.com/garrettjwilke/ep_133_sysex_thingy - Working sysex examples
- https://github.com/benjaminr/mcp-koii - MIDI control interface
- REPO_ANALYSIS.md - Detailed comparison of external repositories
- UPLOAD_PROTOCOL_DETAILS.md - Upload protocol deep dive
