# EP-133 KO-II Upload Investigation

**Last Updated:** 2025-02-19
**Status:** ⚠️ PARTIAL - Audio uploads, metadata stale

## Current State

Upload **IS WORKING** for audio data:
- ✅ Audio data is correctly uploaded and persisted
- ✅ Downloaded audio shows our sample rate (44100 Hz)
- ⚠️ Metadata (name, displayed sample rate) may show stale values

Reference: Working implementation at [rcy (abrilstudios)](abrilstudios/rcy)

## Solution Applied

Based on rcy protocol analysis (Dec 2025, works with FW 2.0.5):

### Key Protocol Changes
1. **Sample rate**: 44100 Hz (not 46875)
2. **Chunk size**: 433 bytes
3. **Parent node**: 1000 (sounds directory)
4. **Device IDs**: 0x6C for init/chunks, 0x6D for end marker
5. **Response handling**: Wait for ACK after each message
6. **20ms delay**: Required between chunks
7. **Big-endian size**: In init payload

### Upload Sequence
```
1. INIT (0x6C) - with slot, parent node, size BE, name, metadata
2. CHUNKS (0x6C) - 433 bytes each, wait for ACK, 20ms delay
3. END (0x6D) - signal completion
4. SYNC - re-initialize file protocol
```

## Known Issue: Metadata Stale

After upload, `ko2 info` may show:
- Old sample name
- Sample rate as 46875 (device default)

But `ko2 get` returns:
- Correct audio data at 44100 Hz

This suggests the device maintains separate metadata/audio storage.

## Files Modified

- `ko2_protocol.py` - Added UPLOAD_CHUNK_SIZE, UPLOAD_PARENT_NODE, UPLOAD_DELAY
- `ko2_client.py` - New put() implementation with response handling

## References

- rcy (abrilstudios) - Working Python implementation, Dec 2025
- ep_133_sysex_thingy - Historical reference (pre-FW 2.0)
