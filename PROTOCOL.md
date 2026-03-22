# EP-133 SysEx Protocol (Reverse Engineered)

## Message Structure

File-group commands use a semantic payload that is packed7-encoded for MIDI transport.

Wire format:
```
F0 00 20 76 33 40 [cmd] [seq] 05 <packed7(raw_payload)> F7
```

Fields:
- `F0` = SysEx start
- `00 20 76` = Teenage Engineering manufacturer ID
- `33 40` = Device family (EP-133)
- `[cmd]` = Session/device identifier byte — device echoes back with -0x40 offset in responses. Values like 0x61, 0x7E, 0x68 all work; the device does not enforce a specific value per operation.
- `[seq]` = Sequence byte (increments per message)
- `05` = CMD_FILE (file operations command group)
- `raw_payload` = semantic bytes (typically `[op][subop][data...]`)
- `packed7(...)` = transport encoding for MIDI safety
- `F7` = SysEx end

### Packed7 Transport Encoding
- Build `raw_payload` first.
- Encode it with packed7 for transport.
- On receive, unpack first, then parse fields.
- For each group: control bit `i` (0..6) corresponds to payload byte `i`.
- Final group may contain fewer than 7 payload bytes.

## SysEx Commands (cmd byte)

| ID | Name | Usage |
|----|------|-------|
| 0x61 | INIT | Initialization sequence |
| 0x77 | INFO | Device info, metadata queries |
| 0x7C | PROJECT | Project switching (NEW) |
| 0x7D | DOWNLOAD | File download (GET) |
| 0x7E | UPLOAD | File upload (PUT), DELETE |
| 0x6A | FILE | File ops (LIST/METADATA) — used by ko2 tools |
| 0x6B | FILE_ALT | File ops (LIST/METADATA) — used by official tool |
| 0x6F | FILE_META | File meta GET/SET — used by official tool (rename) |
| 0x60-0x6A | FILE_RANGE | File ops (LIST/METADATA) — observed in official app polling |
| 0x37 | RESPONSE | Standard device response |
| 0x3D | RESPONSE_ALT | Alternative response (downloads) |

## File Operations

| Op | Name | Usage |
|----|------|-------|
| 0x01 | INIT | Initialize communication |
| 0x02 | PUT | Upload file |
| 0x03 | GET | Download file |
| 0x04 | LIST | List files |
| 0x05 | PLAYBACK | Playback/audition control |
| 0x06 | DELETE | Delete sample |
| 0x07 | METADATA | Metadata operations |
| 0x0B | VERIFY | Verify commit (upload) |

## Official App Behavior (Observed)

From hunter captures (e.g. `captures/sniffer-2026-02-20-220918.jsonl`):
- Uses FileOp.LIST and FileOp.METADATA GET heavily; **does not use GET_META (0x75)**.
- Sends FileOp.METADATA GET/SET with device IDs in the **0x60–0x6A range** (rotating).
- Uses FileOp.METADATA SET with JSON payloads to drive UI navigation and pad assignment.
- `{"active":<node>}` toggles active child nodes (UI selection/navigation).
- `{"sym":<n>}` appears to assign a sample slot to a pad node (needs more confirmation).
- `{"sample.start":..., "sample.end":...}` used for trim edits (see pad-trim capture).
- META_GET targets nodes that match **sample slot numbers** (e.g. 53, 67, 77, 220, 434, 442, 568, 569, 572, 807 in `captures/sniffer-2026-02-20-220918.jsonl`), suggesting sample nodes may be addressed by slot id (not fully confirmed).

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
F0 00 20 76 33 40 75 [seq] 05 <packed_payload> F7
```
- Device ID: `0x75` (GET_META)
- Raw payload: `07 02 [slot_hi] [slot_lo] 00 00`
- Returns JSON with: name, sym, samplerate, format
- This legacy API still uses normal packed7 encoding.
- **Slot Encoding:** `slot_hi slot_lo` are BE16 bytes in the raw payload before packed7.
- GET_META appears unreliable/stale in OS 2.0+ (returning ghost data for deleted slots). The official app relies entirely on `/sounds` (FILE LIST) and Node `METADATA GET` instead. Treat `GET_META` as legacy/debug only.

### Delete Sample
```
F0 00 20 76 33 40 7E [seq] 05 00 06 [slot_hi] [slot_lo] F7
```
- Device ID: `0x7E` (UPLOAD)
- Operation: `0x06` (DELETE)
- Slot encoding: big-endian (confirmed from captures)
- Device may return a "failed" status in the response, but the operation completes — file data is removed, though GET_META may still return stale metadata for the deleted slot.

### Switch Project (NEW)
```
F0 00 20 76 33 40 7C [seq] 05 08 07 01 07 50 [json_data] 00 F7
```
- Device ID: `0x7C` (PROJECT)
- JSON payload: `{"active":8000}` for project 8
- Project numbers are encoded as value * 1000

## Upload Protocol (PUT)

The upload consists of a sequence of messages. The official app uses chunking and expects an ACK for each message.

### 1. Upload Init
```
F0 00 20 76 33 40 7E [seq] 05 <packed_payload> F7
```
- Command byte: `0x7E` (UPLOAD) — confirmed from tests/fixtures/sniffer-upload21.jsonl
- Group byte: `0x05` (CMD_FILE)
- Raw payload before packed7 encoding:
  - `0x02` (PUT)
  - `0x00` (PUT_INIT)
  - `0x05` (audio file type)
  - `slot_hi`, `slot_lo` (Big-endian)
  - `node_hi`, `node_lo` (Parent node, usually `0x03E8` for 1000)
  - `size` (4 bytes, big-endian)
  - `name` (UTF-8, null-terminated)
  - `metadata JSON` (e.g. `{"channels":1,"samplerate":44100}`)

### 2. Upload Data Chunk
```
F0 00 20 76 33 40 7E [seq] 05 <packed_payload> F7
```
- Raw payload before packed7 encoding starts with:
  - `0x02` (PUT)
  - `0x01` (PUT_DATA)
  - `chunk_index_hi`, `chunk_index_lo` (16-bit big-endian index, NOT byte offset)
  - audio data: **raw LE s16 PCM** — WAV frames sent as-is, no byte swap.
    Confirmed SOLID: byte-for-byte match between official TE app upload capture
    (`tests/fixtures/sniffer-upload-kick-official.jsonl`) and `tests/fixtures/kick-46875hz.wav`.
- Device responds with an ACK (usually echoing the command in the `0x2x` response range). It does **not** return a standard `status=0x00` response, so clients should only check that an ACK was received.

### 3. Commit/Verify Steps (Observed)
```
F0 00 20 76 33 40 7E [seq] 05 00 02 01 00 01 F7           # Commit 1
F0 00 20 76 33 40 7E [seq] 05 00 0B 00 01 F7              # Verify
F0 00 20 76 33 40 7E [seq] 05 00 01 01 00 40 00 00 F7     # Re-init
F0 00 20 76 33 40 7E [seq] 05 00 0B 00 01 F7              # Verify again
```

### 7. Metadata Operation (observed)
```
F0 00 20 76 33 40 7E [seq] 05 <packed_payload> F7
```
- Operation: `0x07` (METADATA)
- Sub-op: `0x02` (observed)
  - Seen with slot and node variants during official tool uploads.
  - Responses may be plain JSON with interleaved null bytes (no packed7 encoding),
    prefixed by 4 bytes (observed as `page_hi page_lo node_hi node_lo`).
    Example capture: `captures/sniffer-rename54.jsonl` (RX-only).
- Official tool also sends METADATA SET (0x07 0x01) after upload:
  - Node = slot number
  - JSON contains at least `channels` and `samplerate`, and may include `sound.loopstart`, `sound.loopend`, `sound.rootnote` (see `captures/sniffer-upload-clean-hi.bin`, `captures/sniffer-upload-clean-lo.bin`).

### 8. Finalize
```
F0 00 20 76 33 40 7E [seq] 05 08 07 02 <packed_size> 00 00 F7
```
- Flags: `0x08` (finalize mode)
- Final packed7-encoded size value

## Pad Assignment + Trim (Observed)

Captured in `captures/sniffer-padtrim.jsonl` (slot 74 upload + pad assign + trim):

### Assign sample to pad
- Uses FileOp.METADATA SET (0x07 0x01) with JSON payloads:
  - `{"active":9502}` on node `9500` (selects active pad node)
  - `{"sym":74}` on node `9502` (assigns slot 74 to pad)

### Trim sample on pad
- Uses FileOp.METADATA SET on node `9502`:
  - `{"sample.start":0,"sample.end":8006}`
  - `{"sample.start":2318,"sample.end":8006}`

### Notes
- Pad nodes appear to be in the 9500+ range.
- Official tool uses FileOp.METADATA GET (0x07 0x02) for these nodes before/after updates.
- Field names observed: `sym`, `sample.start`, `sample.end`, `active`.
- Additional META_SET observations from `captures/sniffer-2026-02-20-220918.jsonl`:
  - `{"active":<node>}` toggles active child nodes (UI navigation/group selection).
  - Examples: `2000 -> 5000`, `5100 -> 5300/5400`, `9100 -> 9300/9400`, `9500 -> 9501/9503/9506`.
  - `{"sym":807}` on node `5407` suggests a pad/sample assignment outside the 9500+ range (needs confirmation).
- META_GET also targets nodes that match slot numbers (e.g., `53`, `67`, `77`, `220`, `434`, `442`, `568`, `569`, `572`, `807`), suggesting sample nodes may be addressed by slot id.
- User report: this capture corresponded to pad labeled `8` in group `D`.
- Pad labels are `0-9` plus `.` and `Enter` (12 pads total).
- TX+RX capture shows pad node `9506` assigned with `{"sym":53}` and sample rename via node `53` (see `captures/sniffer-rename54-txrx.jsonl`); user reports this was pad `6` in group `D`.
- **Pad-to-node formula:** `node = 2000 + (project × 1000) + 100 + group_offset + file_num`
  - `group_offset`: A=100, B=200, C=300, D=400
  - `file_num`: 1–12, mapped from physical pad via row inversion (pads numbered bottom-to-top, files stored top-to-bottom):
    ```
    Physical:  10 11 12    Files:  01 02 03
                7  8  9            04 05 06
                4  5  6            07 08 09
                1  2  3            10 11 12
    ```
  - Group A fully confirmed from captures; B/C/D confirmed at 2 points each — all follow the same +100 offset pattern.

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
- Response: packed7-encoded metadata. The payload structure mirrors upload init: `[0x03, 0x00, 0x05, size_hi, size_mh, size_ml, size_lo, filename...]`
  - `0x03` = GET
  - `0x00` = INIT
  - `0x05` = Audio file type
  - Size: 4-byte big-endian value at decoded bytes [3:7]. **Size = raw PCM byte count (no RIFF header); use as trim target.**
  - Filename: Null-terminated string (usually ending in `.pcm`).

### 2. Get Data Chunk
```
F0 00 20 76 33 40 7D [seq] 05 00 03 01 [page_lo] [page_hi] F7
```
- Sub-op: `0x01` (GET_DATA)
- Page: 14-bit value split into two 7-bit bytes (`page_lo`, `page_hi`)
  - `page_lo = page & 0x7F`
  - `page_hi = (page >> 7) & 0x7F`
  - Max page: 16383 (14 bits)
- Response: packed7-encoded chunk; assembled pages are **raw LE s16 PCM** (not RIFF WAV)
  - Each decoded chunk starts with a 2-byte page-number echo `[page_lo, page_hi]` — must strip
  - After stripping prefix, bytes are LE s16 — write directly, no byte swap needed.
  - Confirmed: downloaded bytes from slot 21 (official TE sample) match original WAV exactly.
  - Trim to `file_info["size"]` bytes (= raw PCM byte count from GET_INIT response)
  - Confirmed SOLID by `test_encoding.py` sample-level roundtrip (440 Hz sine, 30+ slots)

## Numeric Encoding Rules

- Slot and node identifiers in raw payloads are standard **BE16** (`hi`, then `lo`) unless a command explicitly uses another format.
- Download `GET_DATA` page echo/request uses a 14-bit page number split into two 7-bit bytes (`page_lo`, then `page_hi`).
- Do not pre-split BE16 fields into 7-bit pieces; packed7 already handles MSB transport.

## WAV File Requirements

### Format
- Sample rate: **46875 Hz** (official TE spec; 24 MHz / 512, Cirrus Logic CS42L52 codec).
  OS 2.0+: samples below 46875 Hz are stored at their original rate. Samples above are
  downsampled on import. No need to force-convert to 46875 Hz.
- Bit depth: 16-bit
- Channels: Mono or stereo
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


## Sample Slots

- Total: **999 slots** (001-999)
- Slot numbers encoded as described above
- Empty slots return no metadata response

## Projects

- Total: **9 projects** (1-9)
- Switch via Device ID 0x7C
- Each project has independent samples
- Project value in JSON is encoded as `project_num * 1000`

## Implementation Notes

1. **Init is required** - Always send init sequence before file operations
2. **Sequence bytes** - Must increment for each message (0-127, wraps)
3. **Packed7 transport** - Build semantic raw payload first, then packed7-encode it
4. **Timing** - Delays of 20-100ms between messages are commonly needed
5. **Response filtering** - Filter by TE header + expected response opcode

## Known Issues

1. **Upload Command IDs** - The `[cmd]` byte (position 6) is a **session identifier**, not a fixed opcode — the device accepts any value and echoes it back with a -0x40 offset in responses. Official TE app uses rotating IDs (observed: `0x68`/`0x69` in `tests/fixtures/sniffer-upload-kick-official.jsonl`, `0x7E` in `tests/fixtures/sniffer-upload21.jsonl`). Our tool uses `0x7E` consistently. All values work.
2. **Playback** - Protocol not fully documented (Command `0x76`).
3. **Project files** - `.ppak` format known, but SysEx extraction path unknown.
4. **"invalid file" Error Response** - When querying a missing or invalid node (e.g., via `METADATA GET`), the device may return a non-standard error payload (including high-byte content). Clients should treat these response payloads as raw bytes and avoid strict semantic decoding.

## Tools

### Convert audio:
```bash
sox input.wav -c 1 -r 46875 -b 16 output.wav
```

### Python tools (this repo):
```bash
krate info <slot>      # Get sample metadata
krate get <slot>       # Download sample
krate put <file>       # Upload sample
krate rm <slot>        # Delete sample
krate ls               # List all samples
```

## References

- https://github.com/garrettjwilke/ep_133_sysex_thingy - Working sysex examples (pre-FW 2.0)
- https://github.com/benjaminr/mcp-koii - MIDI control interface; contains complete sound-to-pad mapping that may aid pad group B/C/D research
- abrilstudios/rcy - Reference implementation (Dec 2025, FW 2.0.5); key reference for upload protocol

## Slot IDs vs node IDs

Two different addressing schemes exist and must not be conflated.

### Slot IDs (1–999)

Used for sample/audio data locations. These are the flat list of 999 sound slots.
Upload, download, rename, and delete all address slots. Slot numbers are global across projects.

### Node IDs

Used for the internal filesystem: pads, projects, groups, folders.

- Node `1000` = `/sounds/` directory (parent node for all uploads)
- Pad nodes: `2000 + (project_num * 1000) + 100 + group_offset + file_num`
  - `project_num`: 1–9
  - `group_offset`: A=100, B=200, C=300, D=400
  - Physical pads numbered bottom-to-top; filesystem stores top-to-bottom

**Example:** Project 1, Group A, Pad 1 → node `3210`

To assign a sample to a pad, set `{"sym": <slot_id>}` on the pad's node via `METADATA SET`.

### Known node ranges

| Range | Purpose |
|---|---|
| `1000` | `/sounds/` directory |
| `2000` | Root filesystem node |
| `X201–X212` | Group A pads (per formula above; X = project prefix) |
| `X301–X312` | Group B pads |
| `X401–X412` | Group C pads |
| `X501–X512` | Group D pads |
