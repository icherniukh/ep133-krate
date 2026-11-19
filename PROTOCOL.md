# EP-133 SysEx protocol

A reference for the vendor SysEx protocol of the Teenage Engineering EP-133
K.O. II. It also applies to the EP-40 apart from the product byte. Lookup
tables come first; details and evidence follow.

- Sound storage, upload conversion, metadata keys and WAV export:
  [docs/sound-format.md](docs/sound-format.md)
- Project TAR members, byte by byte: [docs/project-format.md](docs/project-format.md)
- `.pak`/`.ppak` backups: [docs/pak-format.md](docs/pak-format.md)
- Error replies, firmware log frames and recovery: [docs/errors.md](docs/errors.md)
- Plain MIDI, pad numbering and device limits: [docs/midi.md](docs/midi.md)
- Evidence, firmware comparison and the gap matrix:
  [docs/protocol-evidence.md](docs/protocol-evidence.md)
- Open questions: [docs/capture-wishlist.md](docs/capture-wishlist.md)

**Confidence tags** used throughout:

| Tag | Meaning |
|---|---|
| **2.0.5** / **2.5.1** | Seen on the wire from an EP-133 on that OS, in a Krate capture. |
| **tool** | Read from the official EP Sample Tool's code (2.5.1-era web bundle). This describes the client, not the firmware, and is unconfirmed on the wire. |
| **upstream** | Bench result published by [kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex) (OS 2.5.1). |
| **open** | Not established. See the capture wishlist. |

Captures under `captures/firmware-2.5.1-*` are kept local because they
contain a full device library. Frames from them that carry no library
content or serial are excerpted in [`tests/fixtures/fw251-wire-excerpts.jsonl`](tests/fixtures/fw251-wire-excerpts.jsonl) and checked by
`tests/unit/test_fw251_wire_excerpts.py`. The other captures cited here
are checked in.

## Quick reference

### Frame

```text
request  F0 00 20 76 <prod> 40 [60 | id_hi] [id_lo] <cmd> <packed7 body> F7
reply    F0 00 20 76 <prod> 40 [20 | id_hi] [id_lo] <cmd> <status> <packed7 body> F7
event    F0 00 20 76 <prod> 40 40 00 <cmd> <packed7 body> F7
log      F0 00 20 76 <prod> 33 <ASCII text> F7
```

| Byte | Field | Notes |
|---|---|---|
| 1–3 | `00 20 76` | Teenage Engineering manufacturer ID |
| 4 | product | `33` EP-133, `3C` EP-40 (upstream) |
| 5 | frame type | `40` protocol frame, `33` firmware log text (tool, upstream) |
| 6 | flags + ID high 5 bits | `40` request bit, `20` request-ID-present bit. Requests `60`, replies `20`, events `40` (2.5.1) |
| 7 | ID low 7 bits | 12-bit ID = `(b6 & 1F) << 7 \| b7`. The official tool increments it modulo 4096 (2.5.1) |
| 8 | command | see below |
| 9 | status | replies only, **outside** Packed7 |

### Commands (byte 8)

| Code | Name | Evidence |
|---|---|---|
| `01` | GREET: device info string | 2.0.5, 2.5.1 |
| `02` | ECHO | declared in the tool, never sent |
| `03` | DFU (bootloader and firmware update) | tool; see [below](#firmware-update-dfu) |
| `05` | FILE: filesystem, metadata, playback | 2.0.5, 2.5.1 |
| `7F` | PRODUCT_SPECIFIC | declared in the tool, never sent |

### Reply status (byte 9)

| Value | Meaning | Evidence |
|---|---|---|
| `0` | OK | 2.0.5, 2.5.1 (all 155,240 replies in the 2.5.1 backup capture) |
| `1` | ERROR | tool |
| `2` | COMMAND_NOT_FOUND | tool |
| `3` | BAD_REQUEST | tool |
| `16–63` | command-specific error (`63` = DFU denied) | tool |
| `≥ 64` | command-specific success; `64` = IN_PROGRESS, keep waiting | tool |

A non-zero error reply carries an ASCII reason as its body, for example
`invalid id` or `can only create files` (upstream).

### FILE operations (byte 8 = `05`)

Bodies are shown decoded from Packed7. Integers are big-endian. `fid` is a
16-bit node ID. Reply bodies start after the status byte.

| Op | Request body | Reply body | Evidence |
|---|---|---|---|
| [INIT](#init) | `01 <flags> <maxlen:u32>` | `<u8> <chunk:u32>` | 2.0.5, 2.5.1 |
| [PUT open](#upload-put) | `02 00 <flags> <fid> <parent> <size:u32> <name> 00 [json]` | `<fid>` | 2.0.5 |
| [PUT data](#upload-put) | `02 01 <page:u16> <data>`; empty data = EOF | empty | 2.0.5 |
| [GET open](#download-get) | `03 00 <fid> <offset:u32>` | `<fid> <flags> <size:u32> <name> 00` + zero padding | 2.5.1 |
| [GET open, preview](#waveform-preview) | `03 00 <fid> <offset:u32> <8 × 00> 01 <stride:u16> <points:u16>` | as GET open; size = preview bytes | 2.0.5, 2.5.1 |
| [GET data](#download-get) | `03 01 <page:u16>` | `<page echo:u16> <data>` | 2.0.5, 2.5.1 |
| [LIST](#list-and-stat) | `04 <page:u16> <fid>` | `<page:u16>` then entries `<fid> <flags> <size:u32> <name> 00` | 2.0.5, 2.5.1 |
| [PLAYBACK](#playback) | `05 <action> <fid> <offset:u32> <length:u32>`; action `1` start, `2` stop | empty | 2.0.5; start/stop pair in a local capture |
| [DELETE](#delete) | `06 <fid>` | empty | 2.0.5, upstream |
| [METADATA SET](#metadata) | `07 01 <fid> <json> 00` | empty | 2.0.5 |
| [METADATA GET](#metadata) | `07 02 <fid> <page:u16> [<key> 00]` | `<page:u16> <json fragment>`; the last ends `00` | 2.0.5, 2.5.1 |
| [METADATA SET, paged](#metadata) | `07 04 00 <fid> <size:u32>`, then `07 04 01 <page:u16> <data>`; empty page ends | — | tool |
| [STAT](#list-and-stat) | `0B <fid>` | `<fid> <parent> <flags> <size:u32> <name> 00` | 2.0.5 |
| [MOVE](#move) | `0C <fid> <parent> <new fid>` | `<old fid> <parent> <new fid>` | tool |

### Events (unsolicited, FILE)

| Code | Name | Body | Evidence |
|---|---|---|---|
| `03` | METADATA_UPDATED | `<fid> <json>` | 2.0.5 |
| `08` | FILE_ADDED | `<fid> <flags> <size:u32> <name> 00` | 2.0.5 |
| `09` | FILE_UPDATED | tool parses it like FILE_ADDED | tool |
| `0A` | FILE_DELETED | `<fid>` | 2.0.5 |
| `0D` | FILE_MOVED | `<old fid> <parent> <new fid>` | tool |

### Node flags

| Bit | Meaning |
|---|---|
| `01` | FILE |
| `02` | DIR |
| `04` | READ |
| `08` | WRITE |
| `10` | DELETE |
| `20` | MOVE |
| `40` | PLAYBACK |

The bit names come from the tool. The values seen on the wire fit them:
directories report `0E` (DIR, READ, WRITE) and sounds report `1D` (FILE,
READ, WRITE, DELETE) (2.0.5, 2.5.1). PUT flags use the same bits: `05` for a
sound and `06` for a project TAR.

### File IDs

| fid | Node |
|---|---|
| `0` | root; LIST returns only `sounds` (1000) and `projects` (2000) ([2.5.1](tests/fixtures/fw251-wire-excerpts.jsonl#L8-L11)) |
| `1000` (`03 E8`) | `/sounds`; children are sample slots, fid = slot `1–999` |
| `2000` (`07 D0`) | `/projects` |
| `2000 + 1000 × P` | project `P` (1–9): 3000 … 11000 |
| `project + 100` | its `groups` directory |
| `project + 200 + 100 × G` | group `G` (A=0 … D=3) |
| `group + N` | pad `N` (1–12), counted from the top-left key. Project TAR members `pNN` use the same order; MIDI notes do not ([pad numbering](docs/midi.md#pad-numbering)) |

```text
Keypad       pad N
7 8 9        01 02 03
4 5 6        04 05 06
1 2 3        07 08 09
. 0 Enter    10 11 12
```

## Message structure

### Packed7

SysEx data bytes must stay below `0x80`. Raw bodies are encoded in groups of
up to seven bytes: a control byte, then the low seven bits of each raw byte.
Control bit `i` holds the high bit of raw byte `i`. For example,
`07 D0 00 2C` becomes `02 07 50 00 2C`. Requests and events encode
everything after byte 8. Replies encode everything after the status byte;
decoding the status byte as part of the body shifts every group.

### Request IDs and matching

Match a reply to its request by the full 12-bit ID and the command. All
104,516 request/reply pairs in the 2.5.1 backup capture correlate this way
with no ambiguity. Krate's own client uses fixed byte-6 values per operation
type, which the device also accepts.

### Firmware log frames

A frame with `33` in byte 5 carries ASCII log text from byte 6 up to `F7`,
such as `main[331]: err pattern 187 2_5_1`. Stop all FILE traffic and
power-cycle when one appears. Known signatures:
[docs/errors.md](docs/errors.md).

### Client timing (official tool)

| Setting | Value |
|---|---|
| Reply timeout | 20 s per request; each IN_PROGRESS (`64`) reply restarts the wait |
| Device probe (GREET) | 2 s |
| Project TAR upload | 15 s |
| PUT data per page | `n − ⌊n / 8⌋` raw bytes with `n = chunk − 18`: 433 for a 512-byte chunk |

All values are from the tool's code (tool).

## Startup

1. **MIDI identity**: `F0 7E 7F 06 01 F7`. The 17-byte reply has zero
   version bytes on 2.0.5 and 2.5.x
   ([2.0.5](captures/sniffer-readmeta.jsonl#L3-L4), upstream), but it does
   carry the SKU: bytes 8–9 and 10–11 are 7-bit pairs, formatted as
   `TE<aaa>AS<bbb>` (tool). `… 20 00 01 00 …` is `TE032AS001`
   ([2.5.1](tests/fixtures/fw251-wire-excerpts.jsonl#L1-L2)).
2. **GREET** with an empty body. The reply is a Packed7 string of
   `key:value` pairs separated by semicolons. Both firmwares return
   `product`, `mode`, `base_sku`, `sku`, `os_version`, `sw_version`,
   `bl_version` and `serial`. Use `os_version` for the firmware version.
   [2.0.5](captures/sniffer-readmeta.jsonl#L5-L6)
3. **INIT**, see below.

The tool refuses firmware older than its per-SKU minimum: production 2.0.5
for `TE032AS001`, 1.0.2 for `TE032AS005` and 1.0.5 for `TE032AS006`.
Versions starting with `0.` are checked against separate beta minimums
(tool). GREET `mode` is `normal`, or `bootloader` in firmware-update mode.

### INIT

`01 <flags> <maxlen:u32>`. Both the official tool and Krate send
`01 01 00 40 00 00`: flags `01` and a 4 MiB maximum. The reply
`0C 00 00 02 00` reports a 512-byte chunk size; the tool ignores the leading
byte (`0C`) and its meaning is open.
[2.0.5 exchange](tests/fixtures/sniffer-upload-kick-official.jsonl#L472-L473),
[2.5.1 exchange](tests/fixtures/fw251-wire-excerpts.jsonl#L4-L5)

The tool names flag bit 0 "subscribe", meaning the client wants file
events; events do arrive after this INIT on the wire. Upstream describes the
same bit as read (0) versus write (1). The two readings conflict and the
effect of flags `00` is untested.

The official tool re-sends INIT after DELETE, MOVE, sound upload and
project upload, and not after GET (tool). Consecutive GETs in the 2.5.1
backup need no INIT between them (2.5.1).

## FILE operations

### LIST and STAT

LIST pages through a directory's children: `04 <page:u16> <fid>`. Each
reply echoes the page and then packs as many
`<fid> <flags> <size:u32> <name> 00` entries as fit. Stop when a reply has
no entries (the tool stops at 2 bytes or fewer). Sound sizes are PCM byte
counts. List projects with `04 00 00 07 D0`.

STAT returns one node with its parent:
`<fid> <parent> <flags> <size:u32> <name> 00`.
[2.0.5 STAT](tests/fixtures/sniffer-upload-kick-official.jsonl#L466-L467)

Sound nodes are named `NNN.pcm` after their slot, whatever name the upload
used; the display name lives in metadata `name`. The 2.0.5 upload of
`kick-46875hz` to slot 97 produces a node named `097.pcm`.
[FILE_ADDED event](tests/fixtures/sniffer-upload-kick-official.jsonl#L464)

### Download (GET)

1. **Open**: `03 00 <fid> <offset:u32>`. The official tool on 2.5.1 sends
   this 8-byte form with offset 0 for every whole-file read (238 files in
   the backup capture). The reply is 64 bytes: `<fid> <flags> <size:u32>
   <name> 00` padded with zeros. `size` is the exact byte count to read.
   [2.5.1 open](tests/fixtures/fw251-wire-excerpts.jsonl#L12-L13)
2. **Pages**: `03 01 <page:u16be>`, counting from 0. Each reply is
   `<page echo:u16> <data>`, with 324 data bytes per full page for a
   512-byte chunk. The 2.5.1 capture includes pages 1 (`00 01`), 128
   (`00 80`) and 256 (`01 00`), all echoed as sent
   ([requests](tests/fixtures/fw251-wire-excerpts.jsonl#L14-L17)).
3. **Stop** when `size` bytes have arrived. Upstream reports that reading
   past the end leaves the device in a bad session state.

Sounds arrive as raw interleaved little-endian s16 PCM with no header.
Projects arrive as TAR bytes. Between files the official tool reads the next
file's metadata and opens it directly (2.5.1).

**Krate difference**: Krate's GET open adds five zero bytes after the
fid, and it encodes the page as a 14-bit little-endian value. Both differ
from the official tool. Whether the device treats them the same for every
page is untested. The bead `ko2-tools-transfer-integrity-correlation`
tracks this.

### Waveform preview

GET open with extra arguments returns a reduced waveform instead of the
file: `03 00 <fid> <offset:u32=0> <8 × 00> 01 <stride:u16> <points:u16>`.
The tool asks for 200 points for sounds under 4,000 frames, otherwise 2,000,
with `stride = floor(frames / points)`. Data pages follow as usual, with 320
bytes per page in the 2.0.5 capture.
[2.0.5 open](tests/fixtures/sniffer-upload-kick-official.jsonl#L61-L63)

Each point is two s16 little-endian values. For a mono sound on 2.5.1,
both values equal the PCM sample at frame `k × stride`. All 2,000 points of
slot 12 match the backup PCM that way. The preview is point decimation,
not min/max peaks, so it misses transients.
[2.5.1 preview open](tests/fixtures/fw251-wire-excerpts.jsonl#L18-L19) A stereo preview is twice the
size (16,000 bytes for 2,000 points on 2.0.5); its channel layout is open.

### Upload (PUT)

| Step | Request | Evidence |
|---|---|---|
| Open | `02 00 05 <slot fid> 03 E8 <size:u32> <name> 00 <json>`. The reply returns the fid. | [2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L164-L166) |
| Data | `02 01 <page:u16> <433 bytes>` from page 0, for a 512-byte chunk | [2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L165-L461) |
| EOF | `02 01 <next page>` with no data | [2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L462-L463) |
| Device | FILE_ADDED event for `NNN.pcm` | [2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L464) |
| Metadata | STAT, METADATA SET, STAT | [2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L466-L471) |
| Re-init | INIT | [2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L472-L473) |

The data is the PCM frames with no WAV header. The JSON after the name
carries format fields: `{"channels":1,"samplerate":46875}` from the 2.0.5-era
tool. The 2.5.1-era tool sends `channels` and `samplerate` there, plus
`name`, `format` and `crc` when the source file's TE metadata has them,
then the full metadata in METADATA SET after EOF (tool). The
device takes the display `name` from the PUT name; later free-space updates
arrive as METADATA_UPDATED events on `/sounds`
([2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L169)).

The tool caps names at 54 characters before sending (tool). Upstream reports
that PUT flags `04` without the FILE bit fail with `can only create files`.
See [sound-format.md](docs/sound-format.md) for how the tool converts audio
before upload.

### Playback

`05 <action> <fid> <offset:u32> <length:u32>`, action `1` = start and `2` =
stop. The tool sends length `1000` when auditioning from the sound list,
including arrow-key browsing, and `0` from a pad (tool). The 2.0.5 capture
shows the list form `05 01 <slot> 00 00 00 00 00 00 03 E8`.
[2.0.5](captures/sniffer-rename54-txrx.jsonl#L117-L118)

Offset is always 0 in the tool. It sends length `1000` on the first click
of a list row and while arrow-key browsing, and length `0` when a pad is
clicked or the space bar goes down. Releasing the space bar sends STOP,
except for sounds shorter than one second (tool). A browse length of 1000
next to a one-second cutoff suggests milliseconds, but that is unverified. A local March 2026 capture (firmware not stamped, not checked in)
shows the pair on the wire: `05 01 00 04` and `05 02 00 04`, each followed
by eight zero bytes, and each answered with status 0.

The unit of `length`, and whether `0` means "play to the end", are open.
Upstream plays the short form `05 01 <fid>` on 2.5.1 and reports that it
plays the raw sample, ignoring trim and envelope, and that pad fids are
silent.

### Delete

`06 <fid>`. A FILE_DELETED event may arrive before the status-0 reply, and
a `/sounds` free-space update follows.
[2.0.5](captures/evidence-download-state-bug.jsonl#L33-L38) Upstream
reports that the older `06 02 <fid>` form fails or silently does nothing.
Confirm a delete with LIST on `/sounds`; metadata can read back stale for a
just-deleted slot ([audit](docs/protocol-evidence.md#metadata-audit)).

### Metadata

METADATA GET pages a node's JSON: `07 02 <fid> <page:u16>`. Each reply
echoes the page, followed by up to 320 bytes of JSON on 2.5.1. Continue
until a fragment ends with `00`. The official tool requests pages 0 and 1
back to back (2.0.5, 2.5.1). Adding `<key> 00` reads one field (upstream).

METADATA SET merges a JSON object into the node's record:
`07 01 <fid> <json> 00`. The device echoes changes as METADATA_UPDATED
events. When the JSON exceeds chunk size − 8 bytes, the tool switches to
the paged form `07 04` (tool).

Keys by node type:

| Node | Keys |
|---|---|
| `/sounds` (1000) | `max_capacity`, `free_space_in_bytes`, `formats` ([sound-format.md](docs/sound-format.md#format-negotiation)) |
| sound slot | 19 keys on 2.5.1, 17 on 2.0.5 ([sound-format.md](docs/sound-format.md#sample-metadata)) |
| `/projects` (2000) | `active`: the loaded project fid |
| `groups` directory, group | `active`: the selected group or pad fid |
| pad | `sym` (assigned slot), `sample.start`, `sample.end` and sound fields; see upstream for the [pad field list](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#pad-metadata-fields) |

Examples: read storage with `07 02 03 E8 00 00`
([2.0.5](captures/sniffer-readmeta.jsonl#L12-L15)). Switch to project 8 by
setting `{"active":10000}` on node 2000. Assign slot 74 to a pad with
`{"sym":74}` on the pad node
([evidence](docs/protocol-evidence.md#pad-assignment-and-trim)).

### Move

`0C <fid> <parent> <new fid>` moves or renumbers a node, and the reply
echoes old fid, parent and new fid (tool). The tool re-sends INIT afterwards.
No wire capture exists yet.

## Projects and backups

Project files are summarized here. Byte layouts, checked against a 2.5.1
backup: [docs/project-format.md](docs/project-format.md). Backup files:
[docs/pak-format.md](docs/pak-format.md).

- **Read**: GET on a project fid returns a TAR of its pads, patterns, scenes,
  `settings` and `fx_settings`. Sample PCM lives only in `/sounds` and is
  referenced by slot ([members](docs/project-format.md#members)).
- **Write**: PUT with flags `06` (DIR, READ), parent `2000` and the project
  fid as the target, then INIT. The tool allows 15 s for the reply (tool).
  Upstream reports that the device normalizes written archives:
  [writing a project TAR](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#writing-a-project-tar).
- **Activate**: set `active` on `/projects`, then on the groups directory
  and the group. Upstream switches away and back to reload a written project.
  The official tool reads `active` on `/projects` and the groups directory
  at startup ([2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L5-L13)).
- **Krate**: `fs-ls --node 2000` lists projects. Dedicated project read,
  write and activation are not implemented.
- **Swing** is project state in `settings` byte 220: value 0–12 for swing
  50–75 (50 → `00`, 60 → `05`, 65 → `07`, 75 → `0C` on 2.5.1, krate). Upstream calls it global.
- **Per-project scale and key**: TE's
  [2.5 release notes](https://teenage.engineering/guides/ep-133/whats-new)
  say scale and key now save per project: `settings` byte 222 is the scale
  type (blues = 10) and byte 223 the root pitch class (G = 7), present in
  the 224-byte form. Byte 221 is the scene length, stored as the
  value the device shows. Record quantize is global, and
  a root move from C3 to C4 left the TAR byte-identical, so the octave is
  not stored
  ([evidence](docs/protocol-evidence.md#project-settings-bytes)).
- **Backups**: `.pak` (whole device) and `.ppak` (one project) files are
  ZIP archives with leading-slash names: `/meta.json`, `/projects/PNN.tar`
  and `/sounds/NNN <name>.wav`. Sounds are WAVs with TE chunks
  ([sound-format.md](docs/sound-format.md#wav-files-in-backups)). Upstream:
  [container format](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/pak-container.md).
- **Not reachable**: system settings such as the system MIDI channel, sync, velocity
  curve and recording rate. The root holds only `/sounds` and `/projects`,
  GREET carries no settings, the tool sends no command besides GREET, FILE
  and DFU, and the official full-device backup stores none (2.5.1).

Pads, transport, CCs and program changes work over plain MIDI:
[docs/midi.md](docs/midi.md).

## Firmware update (DFU)

The tool code holds only the entry into and exit from bootloader mode
(tool). Nothing here has been tried on a device; do not send these outside
an official update.

Command byte `03`; bodies:

| Body | Meaning |
|---|---|
| `01 01 <delay ms:u16be>` | DFU_ENTER via MIDI; the tool uses a 200 ms delay. The device reboots and answers GREET with `mode:bootloader` |
| `05` | DFU_EXIT |
| `02`, `03`, `04` | DFU_BEGIN, DFU_CHUNK, DFU_PERFORM: declared, never sent by the Sample Tool |

Status `63` is DFU_DENIED.
