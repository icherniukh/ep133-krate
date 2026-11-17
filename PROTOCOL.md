# EP-133 SysEx protocol

Krate's version-stamped captures are from the EP-133 on OS **2.0.5**.
Community bench tests extend coverage to **2.5.1**. See the [firmware
comparison, operation coverage and captures](docs/protocol-evidence.md) and the
[remaining capture scenarios](docs/capture-wishlist.md).

## Message structure

```text
request  F0 00 20 76 33 40 [60 | id_hi] [id_lo] [command] <packed7 body> F7
reply    F0 00 20 76 33 40 [20 | id_hi] [id_lo] [command] [status] <packed7 body> F7
event    F0 00 20 76 33 40 40 00 05 <packed7 event body> F7
```

- Bytes 4–5 are the EP-133 product byte `33` and normal protocol marker
  `40`. The EP-40 uses product byte `3C`. A marker of `33` carries firmware
  debug text. Upstream reports that FILE traffic should stop if the device
  enters a debug loop. [Debug frame evidence](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/errors.md)
- The 12-bit request ID is `((byte6 & 0x1F) << 7) | byte7`. Match replies by
  ID and command. Krate's `SysExCmd` names such as `DOWNLOAD = 0x7D` are
  fixed choices for byte 6. The command is byte 8 (`01` GREET, `05` FILE).
- The reply status is a raw byte. Status `00` is success. Unsolicited events
  use the captured header above and have no reply status. Examples are
  `0A <fid:u16be>` for deletion and `03 <fid:u16be> <JSON>` for a metadata
  update. [Decoded event and reply pairs](docs/protocol-evidence.md#download-completion-and-recovery)

### Packed7

Build the raw body with full-width integers. Each group of up to seven
bytes is sent as a control byte followed by the low seven bits of each
byte. Control bit `i` carries the high bit for raw byte `i`. For example,
`07 D0 00 2C` becomes `02 07 50 00 2C`. Decode after the reply status or
immediately after the command on requests and on the captured unsolicited
events.

## Startup and device info

Krate starts with universal MIDI identity (`F0 7E 7F 06 01 F7`), then sends
GREET with an empty body, then FILE INIT. GREET returns a Packed7 string of
semicolon-separated `key:value` pairs such as `product`, `sku`,
`os_version`, and `serial`. Use GREET for the firmware version. The USB
identity reply carries zero version bytes in the cited captures.
[OS 2.0.5 startup exchanges](captures/sniffer-readmeta.jsonl#L1-L9)

An observed FILE INIT body is `01 01 00 40 00 00`. After operation `01`,
the request contains flags and a four-byte big-endian length limit (4 MiB
in this example). It returns `0C 00 00 02 00`. The final four bytes report
a 512-byte chunk size in this exchange. The meaning of the leading `0C`
and the full flags map need targeted captures.
[Upstream FILE INIT](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#sub-commands)

## FILE operations

Payloads below are decoded. `fid` is a 16-bit file ID. `u16be` and
`u32be` are big-endian integers. The reply column starts after status.

| Operation | Request body | Reply body |
|---|---|---|
| INIT | `01 <flags:u8> <maxlen:u32be>` | Leading byte, then chunk size as `u32be` |
| LIST | `04 <page:u16be> <fid:u16be>` | `<page:u16be>`, then zero or more `<fid:u16be> <flags:u8> <size:u32be> <name> 00` entries. Flag bit 1 marks a directory. |
| STAT | `0B <fid:u16be>` | `<fid:u16be> <parent:u16be> <flags:u8> <size:u32be> <name> 00` |
| METADATA GET | `07 02 <fid:u16be> <page:u16be>` | `<page:u16be>` and a JSON fragment. The last fragment ends with NUL in the captured example. |
| METADATA SET | `07 01 <fid:u16be> <JSON> 00` | Empty on success. The JSON fields merge with the existing record. |
| PLAY | `05 01 <fid:u16be>` with an optional suffix in the captured tool | Empty on success |
| DELETE | `06 <fid:u16be>` | Empty on success. A separate FILE_DELETED event can arrive before the reply. |
| GET open | `03 00 <fid:u16be> <offset:u32be>` in the reference client | Starts with `<fid:u16be> <flags:u8> <size:u32be> <name> 00` |
| GET page | `03 01 <page:u16be>` in the reference client | `<page echo:u16be> <data>` |
| PUT open | `02 00 <flags:u8> <fid:u16be> <parent:u16be> <size:u32be> <name> 00` | The official-tool sound example returns the file ID. |
| PUT page | `02 01 <page:u16be> <data>` | Empty on success. An empty data page at the next index ends the upload. |

Some clients add a NUL-terminated key to METADATA GET to read a single
field. For sound inventory and post-delete checks, use LIST on `/sounds`.
The repository's older slot-audit path sometimes returns stale metadata.
[Metadata audit](docs/protocol-evidence.md#metadata-audit), [Reference codec](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md)

### Storage and audition

Read METADATA GET page 0 on `/sounds` with `07 02 03 E8 00 00`. The JSON
contains `max_capacity`, `free_space_in_bytes`, and `formats`. `krate status`
reports capacity and free bytes from this reply and labels its estimate if
the query is unavailable. [Storage exchange on 2.0.5](captures/sniffer-readmeta.jsonl#L12-L15)

The official tool sends `05 01 <slot:u16be> 00 00 00 00 00 00 03 E8` on
2.0.5. Krate uses this form. The four-byte form is bench-tested upstream
on 2.5.1, where it plays raw slot audio without pad trim or envelope.
[PLAY on 2.0.5](captures/sniffer-rename54-txrx.jsonl#L117-L118), [PLAY on 2.5.1](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#play--audition-0x05-0x01)

### Download protocol

GET transfers raw little-endian signed 16-bit PCM for samples or TAR bytes
for projects. Stop at the size reported by GET open. Reference clients
use offset zero for whole files. Krate appends five zero bytes after the
file ID and uses a little-endian 14-bit page field. Its 2.0.5 trace shows
324 data bytes per full page and echoes the requested page bytes.

The official tool on **the same 2.0.5 device** uses a 21-byte preview open,
big-endian page numbers and 320-byte pages for a 16,000-byte preview.
Reference whole-file reads on **2.5.1** use big-endian pages and a shorter
open request. The meaning of the extended open fields and the effect of
Krate's page encoding on whole-file byte order remain open.
[Preview trace](captures/sniffer-rename54-txrx.jsonl#L15-L25), [Reference whole-file read](https://github.com/kmorrill/ep-series-sysex/blob/main/epsysex/fileclient.py#L361-L397)

Completed 2.0.5 GETs in the archive are followed by successful FILE
requests. Krate currently reinitializes after `get()`. Interrupted
transfer recovery still needs validation.
[Download completion and recovery](docs/protocol-evidence.md#download-completion-and-recovery)

### Upload protocol

Use flags `05` for a sound and parent `1000`. The 2.0.5 Sample Tool fixture
contains 433 content bytes per full PUT page for the 512-byte chunk
configuration. It carries PCM frames without a WAV header. The PUT open
may append JSON after the NUL-terminated name, and the tool also uses
METADATA SET after EOF. The `0B` requests around that edit are STAT
readbacks. Krate's upload client calls this operation `VERIFY`.
[2.0.5 PUT data](tests/fixtures/sniffer-upload-kick-official.jsonl#L171-L173), [2.0.5 EOF, STAT and metadata](tests/fixtures/sniffer-upload-kick-official.jsonl#L458-L479)

Krate converts input to 16-bit WAV where needed, preserves channels and
sample rates at or below 46,875 Hz, and sends frames with separate metadata.
Recent official tool support for sub-native rates is documented in the
[EP-133 sample tool guide](https://teenage.engineering/guides/ep-133/functions).
The runtime path is [prepare_for_upload](src/core/ops.py), then [UploadTransaction](src/core/operations.py).

## Filesystem and projects

| File ID | Node |
|---|---|
| `0` | Filesystem root |
| `1000` | `/sounds`; children are the global sample slots `1–999` |
| `2000` | `/projects` |
| `2000 + 1000 × P` | Project `P`, numbered 1–9 |
| `project_fid + 100` | Groups directory |
| `project_fid + 200 + 100 × G` | Group `G`, with A=0, B=1, C=2, D=3 |
| `group_fid + index` | Pad. Index 1–12 counts from the top left across each row. |

```text
Keypad       FILE pad index
7 8 9        01 02 03
4 5 6        04 05 06
1 2 3        07 08 09
. 0 Enter    10 11 12
```

List projects with `04 00 00 07 D0`. Read the active project with METADATA
GET on node `2000`. To switch, set `active` on that node to the target
project ID. For example, project 8 is `10000`. Set `sym` on a pad node to
assign a sample slot. The pad stores its own `sample.start` and
`sample.end` trim points in frames.
[Project selection exchange on 2.0.5](tests/fixtures/sniffer-upload-kick-official.jsonl#L5-L13), [Upstream project activation](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#project-reload--activation-sequence), [Pad evidence](docs/protocol-evidence.md#pad-assignment-and-trim)

GET on a project file yields its TAR. A project TAR references sample
IDs in the shared sound library. Upstream bench tests on 2.5.1 also
replace a TAR with PUT using flags `06` and parent `2000`, then reload
and verify the project. Krate exposes generic listing through
`fs-ls --node 2000`. Dedicated project read, write and activation remain
unimplemented.
[Upstream project TAR protocol](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#writing-a-project-tar), [Firmware compatibility](docs/protocol-evidence.md#firmware-changes-from-205-to-251)

## Known issues

See [unverified behavior and next captures](docs/capture-wishlist.md).
