# EP-133 KO-II Protocol Evidence & Research Archive

This document serves as the historical "lab notebook" and forensic evidence for the EP-133 protocol reverse-engineering effort. It consolidates previous audits, wire validations, upload deep-dives, and metadata corruption risks.

---

## 1. Protocol Audit & Confidence Matrix

*Ground truth: device captures in `captures/`, 45 unit tests, confirmed device tests.*

```
SOLID            SPECULATION      BLIND GUESS      UNKNOWN
~43%             ~27%             ~13%             ~17%
████████████     ███████          ████             █████
```

### Validation Matrix

| Operation | Implementation | RCY alignment | Wire evidence | Status | Notes |
|---|---|---|---|---|---|
| Device info (GET_INFO 0x77) | `EP133Client.device_info()` | Unknown | `captures/sniffer-02-20-audit1.log` (raw SysEx 0x21, product info) | 🟡 | Response contains JSON-like payload |
| Slot meta (GET_META 0x75) | `EP133Client.get_meta_legacy()` | N/A | `captures/sniffer-02-20-audit1.log` (raw SysEx 0x35), `captures/2026-02-20-audit-001-099.jsonl` (decoded), `captures/2026-02-20-audit-100-199.jsonl` (decoded) | ⚠️ | Legacy API can return stale/ghost metadata |
| File list (/sounds) | `EP133Client.list_directory()` | Match | `captures/sniffer-02-20-audit1.log` (raw SysEx 0x2A), `captures/2026-02-20-audit-001-099.jsonl` (decoded) | ✅ | Uses 0x6A + FileOp.LIST |
| Node meta GET | `EP133Client.get_node_metadata()` | Match | `captures/2026-02-20-audit-001-099.jsonl` (decoded), `captures/sniffer-readmeta.jsonl` (raw SysEx) | ✅ | Uses FileOp.METADATA GET |
| Node meta SET | `EP133Client.rename()` | Match | `captures/sniffer-rename.jsonl` (raw SysEx) | ✅ | Official tool uses FileOp.METADATA SET with JSON name |
| Download (GET) | `EP133Client.get()` | Partial | _pending_ | 🟡 | Works in practice |
| Upload (PUT) | `EP133Client.put()` | Partial | `captures/sniffer-slot26.jsonl`, `captures/sniffer-upload21.jsonl`, `captures/sniffer-upload-clean-hi.bin` | ✅ | Official tool upload + META SET captured |
| Delete | `EP133Client.delete()` | Match | `captures/sniffer-delete-hi.bin` | ✅ | Big-endian slot confirmed (467) |
| Pad assign/trim | Not implemented | Unknown | `captures/sniffer-padtrim.jsonl` | 🟡 | Uses FileOp.METADATA SET on pad nodes (see below) |
| Project switch | Not implemented | Match | _pending_ | ⚠️ | Protocol documented, no CLI yet |

---

## 2. Wire Validation & Capture Logs

To capture new evidence, run: `python midi_proxy.py --proxy captures/sniffer-<name>.jsonl`

### 2026-02-21 official app hunter capture (open app)
Hunter summary after opening the official sample tool (no user actions):
- Observed FileOp.METADATA and FileOp.LIST traffic (plus VERIFY).
- **No GET_META (0x75) or META_RSP (0x35) observed.**
- Subsequent session with light interaction: `META_GET: 994`, `META_SET: 12`.
- Device IDs observed for META ops include `0x60`–`0x6A` (rotating).

### 2026-02-20 pad assignment + trim capture
*Capture: `captures/sniffer-padtrim.jsonl` (slot 74 upload + pad assign + trim)*

- Uses `SysExCmd 0x7F/0x60` (requests) and `0x3F/0x20` (responses) during upload.
- Metadata SET sequence (decoded raw):
  - Node `74`: sets core sample params (`sound.*`, `channels`, `samplerate`).
  - Node `9500`: `{"active":9502}` (selects active pad slot).
  - Node `9502`: `{"sym":74}` (assigns sample slot to pad node).
  - Node `9502`: `{"sample.start":0,"sample.end":8006}` (initial trim).
  - Node `9502`: `{"sample.start":2318,"sample.end":8006}` (trim edit).
- Multiple Metadata GETs for nodes `74`, `1000`, `2000`, `9100`, `9500`, `9502`.
- User report: this capture was pad labeled `8` in group `D` (pad layout is 0-9 plus `.` and `Enter`, mapping unknown).

### 2026-02-20 pad assign + rename (TX+RX)
*Capture: `captures/sniffer-rename54-txrx.jsonl`*
- TX METADATA SET:
  - Node `9506`: `{"sym":53}` (assign sample slot 53 to pad node).
  - Node `53`: `{"name":"53_name))"}` (rename sample).
- TX METADATA GET:
  - Node `53`: pages `0` and `1` (before and after rename).
- RX metadata JSON confirms pre-rename: `name:"pr - kicks 9"` and post-rename: `name:"53_name))"`.
- User report: sample slot `53` was used; pad label was `6` in group `D`.

### Pad Mapping (raw observations)
- `captures/sniffer-padmap-A.jsonl`: Pad 0 -> `9211`, Pad 1 -> `9207`, etc.
- `captures/sniffer-padmap-B.bin`: Pad 8 -> `9302`, Pad 0 -> `9311`.
- `captures/sniffer-padmap-C.bin`: Pad 8 -> `9402`, Pad 0 -> `9411`.

---

## 3. Upload Deep-Dive & Encoding Quirks

### 2026-02-20 official tool upload captures (slot 26, slot 21)
*Captures: `captures/sniffer-slot26.jsonl` and `captures/sniffer-upload21.jsonl`*
- Upload init is `SysExCmd 0x7E` (slot 21) and also `0x7F` (slot 26), with seq byte following.
- Payload uses `CMD_FILE 0x05` + packed7(raw_payload):
  - `02 00 05 slot_hi slot_lo node_hi node_lo size_be name 00 json`
- Name + JSON metadata are embedded in upload init (no separate rename needed).
- PUT_DATA uses `02 01` with a 16-bit chunk index stepping by `0x0100`.
- Additional short ops after data:
  - `0x0B 00 <slot>` (verify, observed twice)
  - `0x01 01 00 40 00 00` (re-init, observed once)
  - `0x07 02 ...` (metadata op, observed with slot + node variants)

**Open questions:**
- Why official tool sometimes uses `SysExCmd 0x7F` vs `0x7E` for upload.
- Meaning of `0x0B` and `0x01` ops beyond verify/reinit.

### Packed7 Transport Layer
- Protocol fields are built first as raw payload bytes (`op`, `subop`, `slot_hi slot_lo`, etc.), then packed7 is applied for MIDI transport.
- Every 7 raw payload bytes become 8 wire bytes: one packed7 control byte + seven 7-bit-clean data bytes.
- Control bit `i` corresponds to payload byte `i` (0..6); final group may contain fewer than 7 payload bytes.

### Endianness & 14-bit splits
- Mixing `pack_7bit` payloads with explicit 14-bit splits `((val >> 7) & 0x7F)` breaks at higher values.
- Uploads expect raw 16-bit/32-bit values **inside** the packed payload.

### The Working Upload Sequence
1. **INIT (0x6C/0x7E family)**: slot, parent node (1000), size BE, name, JSON metadata.
2. **CHUNKS (0x6C)**: 433-byte data chunks, wait for ACK response (0x2C), short delay.
3. **SENTINEL + VERIFY**: empty `PUT_DATA` sentinel chunk, then VERIFY.

---

## 4. Metadata Corruption Risks

There are multiple sources of truth on the device, and they can diverge:

1. **Filesystem entry name** from `/sounds` (via `FileOp.LIST`).
2. **Filesystem node metadata** (via `FileOp.METADATA GET` on a node_id).
3. **Slot metadata** (via legacy `GET_META` 0x75).

### Known Risks
- **No Active +128 Bug:** Earlier revisions incorrectly reported a `GET_META` slot-offset bug for slots >127. Root cause was host-side encoding mistakes (U14 bytes interpreted by device as BE16). With correct BE16 + 7-bit packing, slot mapping behaves as expected.
- **Stale Metadata:** The device can return `GET_META` responses for deleted slots, resulting in "ghost" names.
- **Lost Sound Params:** Move/Copy via download+upload resets sound parameters (start/end/loop/pitch) because the upload only carries name + channels + samplerate.

### 2026-02-20 audit summary (decoded)
- `captures/2026-02-20-audit-001-099.jsonl` (99 slots)
  - `name:diff`: 37, `channels:diff`: 5, `node-name-empty`: 23, `stale`: 3, clean: 47
- `captures/2026-02-20-audit-100-199.jsonl` (100 slots)
  - `stale`: 57, `name:diff`: 22, clean: 21

### Implemented Mitigations
- `ko2 info` and `ko2 ls` now use `/sounds` + node metadata (`FileOp.METADATA GET`) only.
- `GET_META` is retained only as an explicit legacy audit/debug source (`ko2 audit` path).
- The inventory command (`ko2 ls`) relies entirely on the filesystem listing (`/sounds`), ensuring empty slots are reported accurately.
- `ko2 audit` exists to compare the three sources and flag `name:diff` or `stale` states.
