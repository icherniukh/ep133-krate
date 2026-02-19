# Protocol Verification Needed

This document tracks protocol contradictions that need verification against actual device behavior. **This file is temporary and will be deleted once verified.**

## 1. Delete Slot Encoding (CRITICAL)

### Contradiction
| Source | Encoding | Evidence |
|--------|----------|----------|
| `ko2_client.py:640-641` | **Little-endian** | Current implementation |
| `PROTOCOL.md:84,195` | **Big-endian** | Documentation |
| `REPO_ANALYSIS.md:48` | **Big-endian** | External repo: `garrettjwilke/ep_133_sysex_thingy` |

### External Source Example
From `garrettjwilke/ep_133_sysex_thingy` - Delete slot 11:
```
F0 00 20 76 33 40 7E 07 05 00 06 00 0B F7
                                   ────
                              Slot 11 = 00 0B (big-endian)
```

### Current Code
```python
# ko2_client.py:640-641
slot_low = slot & 0x7F        # Little-endian low byte first
slot_high = (slot >> 7) & 0x7F
```

### Action Required
- [ ] Test current delete implementation on real device
- [ ] If fails, change to big-endian: `slot_high, slot_low = (slot >> 7) & 0x7F, slot & 0x7F`
- [ ] Document result

---

## 2. Upload Data Device ID

### Contradiction
| Source | Upload Data Device ID | Evidence |
|--------|----------------------|----------|
| `ko2_client.py` | **0x6C** for data chunks | `UPLOAD_DATA = 0x6C` |
| `ko2_protocol.py` | **0x6C** defined | `DeviceId.UPLOAD_DATA` |
| External repos | **All 0x7E** | `garrettjwilke` examples show 0x7E for all 8 steps |

### External Source Example
From `REPO_ANALYSIS.md:62-70` - All 8 upload steps use `0x7E`:
```
01: F0 ... 7E 6B 05 40 02 00 05...  (Upload Init)
02: F0 ... 7E 6C 05 00 02 01...     (Upload Data)
...
08: F0 ... 7E 72 05 08 07 02...     (Finalize)
```

### Current Code
`ko2_client.py:533` uses `DeviceId.UPLOAD_DATA (0x6C)` for init/data chunks, but `DeviceId.UPLOAD (0x7E)` for commit/verify steps.

**Note:** Leaving as-is for now. External examples might be packet captures showing what the device sends, not what we should send. Our upload may work correctly; testing required.

### Action Required
- [ ] Test current upload implementation on real device
- [ ] If works, document that 0x6C/0x7E split is correct
- [ ] If fails, try all 0x7E
- [ ] Document result

---

## 3. Metadata Query Endianness

### Current Understanding
| Operation | Encoding | Source |
|-----------|----------|--------|
| Upload | Big-endian | PROTOCOL.md |
| Download | Big-endian | PROTOCOL.md |
| Delete | **Big-endian** (external) / **Little-endian** (code) | CONTRADICTION |
| Metadata Query | Little-endian | PROTOCOL.md |

### Question
Is metadata query actually little-endian, or is this also wrong? External repos don't show metadata query examples.

### Action Required
- [ ] Verify metadata query endianness on real device
- [ ] Cross-check with download operation (both use 0x7D/0x75 range)

---

## 4. Playback/Audition Protocol (0x76)

### Current Status
- Constants defined: `DeviceId.PLAYBACK = 0x76`, `FileOp.PLAYBACK = 0x05`
- No implementation exists
- No external examples found

### Action Required
- [ ] MIDI sniffer during official tool playback
- [ ] Document message structure
- [ ] Implement `play()` method

---

## 5. Missing Constants

### VERIFY Operation (0x0B)
- Used inline in upload sequence
- NOT defined in `FileOp` enum
- Should be: `FileOp.VERIFY = 0x0B`

---

## Test Plan

1. **Delete Test** - Delete slot 11 on real device, verify it works
2. **Upload Device ID Test** - Try upload with all 0x7E vs mixed 0x6C/0x7E
3. **Metadata Query Test** - Query slot 11 metadata, verify endianness

---

## Sources

- `PROTOCOL.md` - Our protocol documentation
- `ko2_client.py` - Current implementation
- `ko2_protocol.py` - Protocol constants
- `REPO_ANALYSIS.md` - External repo analysis
- `garrettjwilke/ep_133_sysex_thingy` - Working sysex examples
