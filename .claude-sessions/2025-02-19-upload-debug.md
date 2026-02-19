# Session Notes: Upload Protocol Debug (2025-02-19)

## Branch
`fix/upload-protocol`

## Current Status
⚠️ **Upload partially working** - Init succeeds (status=0), but upload fails at end marker (status=4) for empty slots. For slots with existing samples, old data persists.

## Key Discovery
Found working reference implementation: **rcy (abrilstudios)** on GitHub
- Works with FW 2.0.5
- Protocol differs from historical references

## What We Changed
1. **Sample rate**: 46875 → 44100 Hz
2. **Chunk size**: 440 → 433 bytes
3. **Parent node**: Added UPLOAD_PARENT_NODE = 1000
4. **Device IDs**: 0x6C for init/chunks, 0x6D for end marker
5. **Added**: Response checking after each message
6. **Added**: 20ms delay between chunks

## Files Modified
- `ko2_protocol.py` - New constants: UPLOAD_CHUNK_SIZE, UPLOAD_PARENT_NODE, UPLOAD_DELAY, SAMPLE_RATE=44100
- `ko2_client.py` - New methods: `_send_and_wait()`, `_check_response_status()`, rewritten `put()`
- `docs/REFERENCES.md` - New file tracking working implementations
- `UPLOAD_INVESTIGATION.md` - Updated findings

## Test Results

### Init Message - WORKS
```
TX: f000207633406c1305500200050176036800000022746465620075675f7465737400007b226368616e006e656c73223a31002c2273616d706c006572617465223a0034343130307df7
RX: f000207633402c130500020176f7  (status=0, SUCCESS!)
```

### End Marker - FAILS
```
TX: F0 00 20 76 33 40 6D 29 05 00 02 01 00 15 F7
RX: status=4 (ERROR)
```

## Next Steps

1. **Compare with working upload** - User will upload via official portal, we'll download and compare
2. **Debug end marker** - Status=4 suggests wrong format or missing step
3. **Check chunk responses** - May be failing silently

## Protocol Reference (from rcy)

### Init Payload Structure (before 7-bit encoding):
```
[PUT=0x02] [0x00] [filetype=0x05] [slot_hi] [slot_lo] [parent_hi] [parent_lo]
[size_be_4bytes] [filename] [null] [metadata_json]
```

### Chunk Payload:
```
[PUT=0x02] [0x01] [index_hi] [index_lo] [audio_data_433bytes_max]
```

### End Marker:
```
[PUT=0x02] [0x01] [final_index_hi] [final_index_lo]  (no audio data)
Command: 0x6D instead of 0x6C
```

## Questions to Investigate
1. Why does slot with existing sample show old data after "upload"?
2. What does status=4 mean?
3. Are chunk responses being checked correctly?
4. Is there a metadata update step missing?

## Resources
- rcy repo: abrilstudios/rcy
- Key files: src/python/ep133/device.py, src/python/ep133/protocol.py
- Issue #177: 20ms delay between chunks required
