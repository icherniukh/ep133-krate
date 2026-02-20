# EP-133 KO-II Upload Investigation

**Last Updated:** 2026-02-20
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

## 2026-02-20: 7-bit packing vs “flags”, node IDs, and slot > 127 bugs

### 1) The “flags” byte after `0x05` is usually **7-bit pack flags** (MSB bitmap)

Teenage Engineering uses a 7-bit packing scheme for variable payloads:
- Every 7 raw bytes become 8 wire bytes.
- The first wire byte is a bitmap of which of the next 7 raw bytes had their MSB set.

That means the byte immediately after `CMD_FILE (0x05)` in many captures is **not** a semantic “mode flags” field.
Values like `0x40`, `0x08`, `0x50` frequently occur simply because certain raw bytes (like `0xE8`) have MSB=1.

Concrete examples (raw → 7-bit packed):
- `node_id=1000 (0x03E8)` becomes `... 03 68 ...` on the wire with pack-flags bit set.
- Upload init header bytes include `parent_lo=0xE8`, so the first pack-flags byte is often `0x40`.
- For slots whose low byte has MSB set (e.g. slot `900` has low byte `0x84`), the first pack-flags byte becomes `0x50` (two MSBs present in that 7-byte group).

### 2) `03 68` is not node `0x0368`

When you unpack 7-bit data, `03 68` with the pack-flags bit set restores to `03 E8` (1000).
So the “`03 68`” pattern in historical `send_tiny_sound` captures corresponds to **parent node 1000** (`/sounds/`), not `872`.

### 3) Slot-number “7-bit encoding” is not a hi/lo swap

For operations that carry *raw bytes* (slot, node_id, size, etc.), the device expects:
- raw 16-bit/32-bit values inside the **packed** payload (pack_7bit / unpack_7bit), or
- explicit `(value >> 7) & 0x7F` splits where the protocol defines *14-bit* fields.

Mixing these two approaches (e.g. treating a 16-bit node_id request as a 14-bit “slot split”) works for small values but breaks at higher values (slots > 127, node_id low bytes ≥ 0x80).

### 4) Fixes applied in code

- Removed the incorrect “force `0x40`” behavior in upload init packing (that byte is pack-flags, not a semantic flag).
- Rewrote upload to the working sequence:
  1. `0x6C` upload init
  2. `0x6C` data chunks (433 bytes)
  3. `0x6D` end marker
  4. sync/init
- Dropped the old “commit/verify/finalize/metadata verify” messages that were using the wrong field layout for higher slots.
- Response handling: the device emits async notifications; we now ignore non-responses and wait specifically for `cmd` in the `0x2x` response range (rcy behavior). End-marker `status` can be non-zero even when the upload persists, so we treat non-zero end-marker status as a warning.

## References

- rcy (abrilstudios) - Working Python implementation, Dec 2025
- ep_133_sysex_thingy - Historical reference (pre-FW 2.0)
