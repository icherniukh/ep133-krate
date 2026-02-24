# Protocol Validation Matrix

This file tracks current protocol validation status, alignment with the RCY
reference implementation, and wire evidence.

## How to capture wire evidence

Recommended workflow:
1. Run `python midi_proxy.py --proxy captures/sniffer-<name>.jsonl` to capture device traffic.
2. Run the command under test (e.g., `ko2 ls`, `ko2 info 1`).
3. Save the capture output and reference it below.

You can also use `ko2 audit --dump-json` to capture raw metadata responses
for diffing (not raw SysEx, but useful for semantic validation).

Note: CoreMIDI permission issues can prevent device access. If you hit
`RtMidiError: MidiInCore::initialize` you need to grant MIDI permissions
and re-run the capture.

## 2026-02-21 official app hunter capture (open app)

Hunter summary after opening the official sample tool (no user actions):
- Observed FileOp.METADATA and FileOp.LIST traffic (plus VERIFY).
- **No GET_META (0x75) or META_RSP (0x35) observed.**
- Subsequent session with light interaction: `META_GET: 994`, `META_SET: 12`.
- Device IDs observed for META ops include `0x60`–`0x6A` (rotating).

## 2026-02-20 hunter capture with interactions

Capture: `captures/sniffer-2026-02-20-220918.jsonl`

Observed META_SET payloads (decoded from FileOp.METADATA SET):
- Node `2000`: `{"active":5000}`
- Node `5100`: `{"active":5300}` and `{"active":5400}`
- Node `5300`: `{"active":5301}`, `{"active":5302}`, `{"active":5303}`, `{"active":5304}`
- Node `5400`: `{"active":5403}`, `{"active":5404}`, `{"active":5405}`, `{"active":5407}`, `{"active":5408}`, `{"active":5411}`, `{"active":5412}`
- Node `5407`: `{"sym":807}`
- Node `9100`: `{"active":9300}` and `{"active":9400}`
- Node `9300`: `{"active":9306}`
- Node `9500`: `{"active":9501}`, `{"active":9503}`, `{"active":9506}`

Interpretation (preliminary):
- `{"active":<node>}` appears to switch active child nodes (UI navigation/group selection).
- `{"sym":<n>}` on a pad-like node likely assigns a sample slot (needs confirmation).
- META_GET requests include nodes that match slot numbers (e.g. 53, 67, 77, 220, 434, 442, 568, 569, 572, 807 in the same capture), suggesting sample nodes can be addressed by slot id.

## Status legend
- ✅ Verified on device
- 🟡 Observed but not fully decoded
- ⚠️ Suspected / partial
- ❌ Not working / unverified

## Validation matrix

| Operation | Implementation | RCY alignment | Wire evidence | Status | Notes |
|---|---|---|---|---|---|
| Device info (GET_INFO 0x77) | `EP133Client.device_info()` | Unknown | `captures/sniffer-02-20-audit1.log` (raw SysEx 0x21, product info) | 🟡 | Response contains JSON-like payload |
| Slot meta (GET_META 0x75) | `EP133Client.get_meta()` | N/A | `captures/sniffer-02-20-audit1.log` (raw SysEx 0x35), `captures/2026-02-20-audit-001-099.jsonl` (decoded), `captures/2026-02-20-audit-100-199.jsonl` (decoded) | ⚠️ | Names offset >127 |
| File list (/sounds) | `EP133Client.list_directory()` | Match | `captures/sniffer-02-20-audit1.log` (raw SysEx 0x2A), `captures/2026-02-20-audit-001-099.jsonl` (decoded) | ✅ | Uses 0x6A + FileOp.LIST |
| Node meta GET | `EP133Client.get_node_metadata()` | Match | `captures/2026-02-20-audit-001-099.jsonl` (decoded), `captures/sniffer-readmeta.jsonl` (raw SysEx) | ✅ | Uses FileOp.METADATA GET |
| Node meta SET | `EP133Client.rename()` | Match | `captures/sniffer-rename.jsonl` (raw SysEx) | ✅ | Official tool uses FileOp.METADATA SET with JSON name |
| Download (GET) | `EP133Client.get()` | Partial | _pending_ | 🟡 | Works in practice |
| Upload (PUT) | `EP133Client.put()` | Partial | `captures/sniffer-slot26.jsonl`, `captures/sniffer-upload21.jsonl`, `captures/sniffer-upload-clean-hi.bin` | ✅ | Official tool upload + META SET captured |
| Delete | `EP133Client.delete()` | Match | `captures/sniffer-delete-hi.bin` | ✅ | Big-endian slot confirmed (467) |
| Pad assign/trim | Not implemented | Unknown | `captures/sniffer-padtrim.jsonl` | 🟡 | Uses FileOp.METADATA SET on pad nodes (see below) |
| Project switch | Not implemented | Match | _pending_ | ⚠️ | Protocol documented, no CLI yet |

## Automated test coverage

- `tests/unit/test_protocol_builds.py` — verifies payload builds for LIST/GET/DELETE/METADATA/UPLOAD init.
- `tests/unit/test_info_merge.py` — verifies `info()` merges node metadata + GET_META safely for slots >127.

## Notes

- RCY alignment is based on `references/rcy/src/python/ep133/protocol.py`.
- Wire evidence should cite a capture file (path + date).
- Audit JSONL files are decoded metadata (not raw SysEx), but still reflect device responses.
- `captures/sniffer-02-20-audit1.log` contains raw responses: 0x2A (FILE response), 0x35 (META response), 0x21 (device/product info during init).

## 2026-02-20 official tool upload captures (slot 26, slot 21)

Observed from `captures/sniffer-slot26.jsonl` and `captures/sniffer-upload21.jsonl`:
- Upload init is `SysExCmd 0x7E` (slot 21) and also `0x7F` (slot 26), with seq byte following.
- Payload uses `CMD_FILE 0x05` + 7-bit encoded raw:
  - `02 00 05 slot_hi slot_lo node_hi node_lo size_be name 00 json`
- Name + JSON metadata are embedded in upload init (no separate rename needed).
- PUT_DATA uses `02 01` with 16-bit offset stepping by 0x0100.
- Additional short ops after data:
  - `0x0B 00 <slot>` (verify, observed twice)
  - `0x01 01 00 40 00 00` (re-init, observed once)
  - `0x07 02 ...` (metadata op, observed with slot + node variants)

Open questions:
- Why official tool sometimes uses `SysExCmd 0x7F` vs `0x7E` for upload.
- Meaning of `0x0B` and `0x01` ops beyond verify/reinit.

## 2026-02-20 official tool read + rename captures

Read metadata (`captures/sniffer-readmeta.jsonl`):
- Official tool does **not** use GET_META (0x75).
- Uses `SysExCmd 0x6B` requests and `0x2B` responses.
- File list requests: raw `04 page_hi page_lo node_hi node_lo` (node `0x03E8` = /sounds).
- Metadata GET requests: raw `07 02 node_hi node_lo 00 00` for multiple nodes.

Rename (`captures/sniffer-rename.jsonl`):
- Uses `SysExCmd 0x6F` requests and `0x2F` responses.
- Metadata SET raw: `07 01 node_hi node_lo {"name":"..."}`
- Followed by Metadata GET for verification.

## 2026-02-20 pad assignment + trim capture

From `captures/sniffer-padtrim.jsonl` (slot 74 upload + pad assign + trim):
- Uses `SysExCmd 0x7F/0x60` (requests) and `0x3F/0x20` (responses) during upload.
- Metadata SET sequence (decoded raw):
  - Node `74`: sets core sample params (`sound.*`, `channels`, `samplerate`).
  - Node `9500`: `{"active":9502}` (selects active pad slot).
  - Node `9502`: `{"sym":74}` (assigns sample slot to pad node).
  - Node `9502`: `{"sample.start":0,"sample.end":8006}` (initial trim).
  - Node `9502`: `{"sample.start":2318,"sample.end":8006}` (trim edit).
- Multiple Metadata GETs for nodes `74`, `1000`, `2000`, `9100`, `9500`, `9502`.
- User report: this capture was pad labeled `8` in group `D` (pad layout is 0-9 plus `.` and `Enter`, mapping unknown).

## 2026-02-20 pad assign + rename (RX-only)

From `captures/sniffer-rename54.jsonl` (RX-only; no TX captured):
- User flow: assigned sample slot 54 to pad labeled `6` in group `D`, then renamed sample to `new_name` (pad name updated).
- Responses include JSON payloads with interleaved null bytes (drop `0x00` to decode).
- Observed JSON (decoded):
  - `{"active":9000}`, `{"active":9500}`, `{"active":9502}`, `{"active":9506}`
  - `{"sym":54}` and `{"sample.end":32753}` (pad node)
  - Sample metadata with name before rename: `name:"pr - kicks 10"`
  - Sample metadata after rename: `name:"new_name"`
- JSON responses appear prefixed by 4 bytes (`page_hi page_lo node_hi node_lo` observed as `0003 251C` and `0003 2522`).

Notes:
- `captures/sniffer-rename54-errors.jsonl` contains RX-only traffic from a failed attempt (no explicit error JSON found).

## 2026-02-20 pad assign + rename (TX+RX)

From `captures/sniffer-rename54-txrx.jsonl` (TX+RX):
- TX METADATA SET:
  - Node `9506`: `{"sym":53}` (assign sample slot 53 to pad node).
  - Node `53`: `{"name":"53_name))"}` (rename sample).
- TX METADATA GET:
  - Node `53`: pages `0` and `1` (before and after rename).
- RX metadata JSON confirms:
  - Pre-rename: `name:"pr - kicks 9"`
  - Post-rename: `name:"53_name))"`
- User report: sample slot `53` was used; pad label was `6` in group `D`.

## 2026-02-20 pad mapping (raw)

From `captures/sniffer-padmap-B.bin`:
- Group `B`: pad `8` -> node `9302`, pad `0` -> node `9311`.

From `captures/sniffer-padmap-C.bin`:
- Group `C`: pad `8` -> node `9402`, pad `0` -> node `9411`.

## 2026-02-20 clean upload + delete (raw)

From `captures/sniffer-upload-clean-hi.bin` (slot 466):
- PUT_INIT includes `{"channels":2,"samplerate":44100}` metadata.
- METADATA SET on node `466` with `{"channels":2,"samplerate":44100}`.
- Two VERIFY messages observed.

From `captures/sniffer-upload-clean-lo.bin` (slot 18):
- PUT_INIT includes `{"channels":2,"samplerate":44100}` metadata.
- METADATA SET on node `18` with `{"sound.loopstart":0,"sound.loopend":81414,"sound.rootnote":60,"channels":2,"samplerate":44100}`.
- Two VERIFY messages observed.

From `captures/sniffer-delete-hi.bin` (slot 467):
- DELETE payload `06 01 D3` (big-endian slot 467).

## 2026-02-20 audit summary (decoded)

- `captures/2026-02-20-audit-001-099.jsonl` (99 slots)
  - `name:diff`: 37
  - `channels:diff`: 5
  - `samplerate:diff`: 5
  - `node-name-empty`: 23
  - `stale`: 3
  - clean: 47
- `captures/2026-02-20-audit-100-199.jsonl` (100 slots)
  - `stale`: 57
  - `name:diff`: 22
  - `channels:diff`: 6
  - clean: 21
