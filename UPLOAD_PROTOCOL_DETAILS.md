# EP-133 Upload Protocol - Detailed Analysis

## Overview

Based on analysis of `garrettjwilke/ep_133_sysex_thingy/send_tiny_sound/` directory, which contains 8 individual sysex files that transfer a "tiny sound" to the device.

## Message Sequence

The complete upload consists of **8 messages** sent in sequence:

### Message 1: Upload Init with Metadata
```
F0 00 20 76 33 40 7E 6B 05 40 02 00 05 00 01 03 68 08 00 00 00 44 ...
```

Structure breakdown:
- `F0 00 20 76 33 40` - Standard EP-133 header
- `7E` - Device ID (UPLOAD)
- `6B` - Sequence byte (starts around 0x6B)
- `05` - CMD_FILE
- `40` - Upload init flags (0x40 = upload mode)
- `02` - FileOp.PUT
- `00` - PUT_INIT sub-operation
- `05` - File type (sample)
- `00 01` - Slot encoding (big-endian: slot 1)
- `03 68 08 00 00 00 44` - 7-bit encoded metadata

Payload (decoded): Size (4 bytes) + filename + metadata JSON

### Message 2: Upload Data Chunk
```
F0 00 20 76 33 40 7E 6C 05 00 02 01 00 00 00 00 00 00 00 01 00 00 ...
```

Structure:
- `7E 6C` - Device ID + Sequence
- `05` - CMD_FILE
- `00` - Flags byte (first chunk?)
- `02` - FileOp.PUT
- `01` - PUT_DATA sub-operation
- `00 00` - Offset (little-endian)
- Encoded audio data follows

### Message 3: Commit Step 1
```
F0 00 20 76 33 40 7E 6D 05 00 02 01 00 01 F7
```

- `05 00 02 01 00 01` - Short commit pattern

### Message 4: Verify/Commit Step 2
```
F0 00 20 76 33 40 7E 6E 05 00 0B 00 01 F7
```

- `05 00 0B 00 01` - Verify pattern
- `0B` - May be a VERIFY operation

### Message 5: Re-Init
```
F0 00 20 76 33 40 7E 6F 05 00 01 01 00 40 00 00 F7
```

- Same pattern as init sequence message 2
- `05 00 01 01 00 40 00 00` - Re-init pattern

### Message 6: Commit Step 3
```
F0 00 20 76 33 40 7E 70 05 00 0B 00 01 F7
```

- Same as Message 4
- Duplicate verify/commit

### Message 7: Metadata Operation
```
F0 00 20 76 33 40 7E 71 05 00 07 02 00 01 00 00 F7
```

- `05 00 07 02 00 01 00 00` - Metadata operation
- `07` - FileOp.METADATA
- `02` - MetaType.SET (or similar)

### Message 8: Finalize with Size
```
F0 00 20 76 33 40 7E 72 05 08 07 02 03 68 00 00 F7
```

- `05 08 07 02` - Finalize header
- `03 68 00 00` - 7-bit encoded size (or part of size)

## Key Patterns

### Sub-operations (byte after FileOp.PUT):

| Value | Name | Usage |
|-------|------|-------|
| 0x00 | PUT_INIT | Initialize upload |
| 0x01 | PUT_DATA | Send audio data chunk |
| 0x02 | Unknown | Commit-related? |
| 0x0B | VERIFY | Verify commit |
| 0x07 | METADATA | Metadata operations |

### Sequence Bytes:

Each message increments the sequence byte:
- Message 1: `6B`
- Message 2: `6C`
- Message 3: `6D`
- Message 4: `6E`
- Message 5: `6F`
- Message 6: `70`
- Message 7: `71`
- Message 8: `72`

Starting value may vary; observed starting at `0x6B`.

### Flags Byte (after CMD_FILE):

The byte immediately after `CMD_FILE (0x05)` in these messages is **often just the 7-bit pack MSB bitmap** (the “pack flags” byte),
not a semantic “operation flags” field. For example, `0x40` commonly appears because the 7th raw byte in the first 7-byte group
is `0xE8` (parent node low byte for node 1000), which has MSB=1.

You’ll also see values like `0x50` for slots where the slot low byte has MSB=1 (e.g. slot 900 has low byte `0x84`), because the pack bitmap
reflects multiple MSBs in that first group.

## Slot Encoding

**Big-endian encoding observed in upload init:**
- Slot 1: `00 01`
- Slot 11: `00 0B`

This differs from download which may use little-endian.

## 7-Bit Encoding

All variable-length data (metadata, audio chunks, size) is 7-bit encoded:

```python
def encode_7bit(data: bytes) -> bytes:
    """Encode 8-bit data to 7-bit MIDI format."""
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
```

## Comparison with Current Implementation

### Our Implementation (ko2_client.py):

```python
# Uses DeviceId.UPLOAD_DATA (0x6C) for data messages
# Uses DeviceId.UPLOAD (0x7E) for control messages
```

### External Reference (garrettjwilke):

```python
# Uses ONLY 0x7E for all upload messages
```

### Recommendation:

Test both approaches. The external reference may be using an older protocol version, or the two device IDs may be interchangeable.

## Metadata Format

The JSON metadata embedded in upload includes:
- File size (4 bytes, little-endian)
- Filename (null-terminated ASCII)
- JSON with sample parameters

Example structure:
```
[SIZE: 4 bytes] [FILENAME] 0x00 {"channels":1}...
```

## Debug Notes

When implementing upload, watch for:
1. Sequence byte must increment each message
2. All variable data must be 7-bit encoded
3. Slot encoding is big-endian in init
4. Offset in data chunks is little-endian
5. Delay between messages (~50-100ms)
6. All 8 messages must be sent for complete upload

## Testing

To verify upload works:
1. Upload small sample (1-2 seconds)
2. Query metadata with `info()` command
3. Download sample and compare with original
4. Playback on device to verify audio quality
