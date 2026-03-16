# EP-133 KO-II Emulator

## Overview

`tests/emulator.py` provides a software emulator of the EP-133 KO-II sample device for use in
automated tests and local development. It exposes one or more virtual MIDI ports (via `mido`)
and responds to the subset of the KO-II SysEx protocol that the `src/core/client.py` client uses.

When to use it:

- **Unit and integration tests** — drive `EP133Client` without physical hardware.
- **CI pipelines** — no MIDI hardware required; virtual ports work on Linux and macOS.
- **Protocol exploration** — run the emulator standalone (`python tests/emulator.py`) and
  send commands with any SysEx tool to observe response shapes.

The emulator is intentionally minimal. It does not simulate playback, project switching, or
pad assignment. Its goal is to cover enough of the wire protocol so that the upload/download
/delete/list/metadata paths in `src/core/client.py` can be exercised end-to-end.

---

## Capabilities

### Implemented Opcodes

The emulator handles four `SysExCmd` values with real state-backed logic.

| Opcode | Hex | `SysExCmd` name | Handler method | Notes |
|--------|-----|-----------------|----------------|-------|
| LIST_FILES | `0x6A` | `LIST_FILES` | `_handle_list_files` | Serves `FileOp.LIST` (directory entries) and `FileOp.METADATA` GET/SET |
| DOWNLOAD | `0x7D` | `DOWNLOAD` | `_handle_download` | GET_INIT (`sub=0x00`) and GET_DATA chunks (`sub=0x01`) |
| UPLOAD_DATA | `0x6C` | `UPLOAD_DATA` | `_handle_upload_data` | PUT_INIT, PUT_DATA chunks, empty sentinel, and VERIFY |
| UPLOAD | `0x7E` | `UPLOAD` | `_handle_upload` | DELETE only (`FileOp.DELETE = 0x06`) |

All four handlers decode the payload with `Packed7.unpack` before dispatch and return
`(response_bytes, delay_seconds)` tuples matching the configurable `response_delay_ms` /
`page_delay_ms` values.

#### LIST_FILES (`0x6A`) — detail

`_handle_list_files` routes on the first payload byte (`op`):

- `FileOp.LIST (0x04)` — returns paginated directory entries for node `1000` (the `/sounds/`
  directory, per `PROTOCOL.md` § "Known node ranges"). Each entry encodes slot number as
  BE16 + flags byte + 4-byte size + null-terminated filename. Page size is 24 slots.
  Non-1000 node IDs return an empty entry list (no error).

- `FileOp.METADATA GET (0x07, sub=0x02)` — returns a JSON blob for any node ID. If the
  node matches a loaded slot, the slot's stored metadata dict is serialised. Otherwise a
  synthetic placeholder dict is returned. Pagination uses a 320-byte chunk size, matching
  the behaviour observed in `captures/sniffer-readmeta.jsonl` and documented in
  `docs/protocol-evidence.md` § "get_node_metadata Pagination".

- `FileOp.METADATA SET (0x07, sub=0x01)` — merges the supplied JSON patch into the target
  slot's metadata dict. If the patch contains a `"name"` key the `SampleSlot.name`
  attribute is also updated.

#### DOWNLOAD (`0x7D`) — detail

`_handle_download` only accepts `FileOp.GET (0x03)` as the outer op byte.

- `sub=0x00` (GET_INIT) — records the requested slot in `_download_slot`, then returns a
  payload whose structure mirrors the upload init: `[GET, 0x00, 0x05, size_be4, filename\0]`.
  Size is the raw PCM byte count (no RIFF header), matching `PROTOCOL.md` §
  "Download Protocol / 1. Get Init".

- `sub=0x01` (GET_DATA) — decodes the 14-bit page number from a `U14LE` pair, slices
  `DOWNLOAD_CHUNK_SIZE (433)` bytes from the sample's `data` buffer, and prepends a
  `U14LE`-encoded page echo. This matches the wire format described in `PROTOCOL.md` §
  "Download Protocol / 2. Get Data Chunk". The page echo must be stripped by the client
  (`src/core/client.py` does this).

#### UPLOAD_DATA (`0x6C`) — detail

`_handle_upload_data` routes on `op` + `sub` pairs from the decoded payload:

- `PUT + 0x00` (PUT_INIT) — parses slot, expected size, filename, and metadata JSON from
  the payload and creates a `PendingUpload` entry. The slot and size are at fixed byte
  offsets matching `PROTOCOL.md` § "Upload Protocol / 1. Upload Init".

- `PUT + 0x01` (PUT_DATA) — appends the chunk bytes to the pending upload's buffer. An
  empty chunk (no bytes after the 4-byte header) sets `PendingUpload.ended = True`,
  modelling the empty sentinel packet described in `docs/protocol-evidence.md` §
  "The working upload sequence".

- `FileOp.VERIFY (0x0B)` — calls `_commit_upload`, which trims the buffer to
  `expected_size` and creates a `SampleSlot` in `self._samples`. This is the point at
  which the upload becomes visible to subsequent LIST/DOWNLOAD/METADATA calls.

#### UPLOAD (`0x7E`) — detail

Only `FileOp.DELETE (0x06)` is handled. The slot is read from payload bytes `[1:3]` as a
BE16 and removed from `self._samples`. This matches `PROTOCOL.md` § "Delete Sample".

### Stub Opcodes

The following `SysExCmd` values are parsed for routing but return without error or state
change:

| Opcode | Hex | Current behavior | Missing behavior |
|--------|-----|-----------------|-----------------|
| INIT | `0x61` | Returns an empty response list (no-op). | The real device expects the two-message init handshake from `PROTOCOL.md` § "Initialization Sequence" and enters a ready state. The emulator skips this state machine entirely. |
| INFO | `0x77` | Returns a synthetic one-shot response: `cmd=0x21`, payload `\x01\x00\x00emulator:ep133;fw:2.0.5`. Not packed7-wrapped. | The real device response format and field layout are only partially captured (`docs/protocol-evidence.md` § "Device info"). The firmware version string is fabricated. |

### Missing / Unimplemented

The following opcodes appear in `PROTOCOL.md` or `src/core/models.py` (`SysExCmd`) but have no
handler in the emulator. Any message with one of these command bytes is silently dropped
(the `handle_sysex` dispatch falls through to `return []`).

| Opcode | Hex | Description (from `PROTOCOL.md`) |
|--------|-----|----------------------------------|
| GET_META | `0x75` | Legacy slot-metadata query. Documented as unreliable/stale on OS 2.0+; the client exposes `get_meta_legacy()` but the emulator does not respond. |
| PLAYBACK | `0x76` | Sample playback/audition control. Protocol not fully documented (`PROTOCOL.md` § "Known Issues"). |
| PROJECT | `0x7C` | Project switching. Protocol documented in `PROTOCOL.md` § "Switch Project" but not implemented in the client CLI either. |
| UPLOAD_END | `0x6D` | Upload end sentinel (alternate command byte for the empty-chunk signal). The emulator handles the empty-chunk path inside `UPLOAD_DATA (0x6C)` via `PendingUpload.ended`; a separate `0x6D` message is not dispatched. |
| RESPONSE | `0x37` | Standard device response opcode. Emulator never receives this; it is a device-to-host opcode. Listed for completeness. |
| RESPONSE_ALT | `0x3D` | Alternative response opcode used in download ACKs. Same note as RESPONSE. |
| FILE_ALT | `0x6B` | File ops used by the official TE tool (observed in captures). Not used by this client. |
| FILE_META | `0x6F` | File metadata GET/SET used by the official tool for rename. Not used by this client. |

---

## Protocol Coverage Summary

Based on the opcodes defined in `src/core/models.py` (`SysExCmd`) and `PROTOCOL.md`:

| Status | Count | Opcodes |
|--------|-------|---------|
| Implemented (state-backed) | 4 | `LIST_FILES`, `DOWNLOAD`, `UPLOAD_DATA`, `UPLOAD` |
| Stub (parsed, minimal response) | 2 | `INIT`, `INFO` |
| Missing (silently dropped) | 6 | `GET_META`, `PLAYBACK`, `PROJECT`, `UPLOAD_END`, `FILE_ALT`, `FILE_META` |

**Coverage: 4 of 8 client-facing opcodes fully implemented (~50%).**

The four implemented opcodes cover every operation exercised by `src/core/client.py` in normal
usage: list, download, upload (init + data + verify), and delete. The missing opcodes are
either legacy, unused by this client, or not yet implemented in the CLI.

---

## Developer Guide: Adding a New Opcode Handler

### Step 1 — Identify the opcode

Check `src/core/models.py` for the `SysExCmd` enum value. If the opcode is new, add it there
first. Confirm the wire format in `PROTOCOL.md` before writing any code.

### Step 2 — Add a dispatch branch in `handle_sysex`

`handle_sysex` is the single entry point. After the Packed7 decode at line 175, add an
`if` branch:

```python
if cmd == SysExCmd.YOUR_OPCODE:
    return self._handle_your_opcode(seq, payload)
```

Place it before the final `return []` fallthrough.

### Step 3 — Write the handler method

Handler signature:

```python
def _handle_your_opcode(self, seq: int, payload: bytes) -> list[tuple[bytes, float]]:
    ...
```

`seq` is the sequence byte from the incoming message. `payload` is the already-decoded
(post-`Packed7.unpack`) semantic bytes.

Return a list of `(response_bytes, delay_seconds)` tuples. Almost always one tuple.

Use `self._build_file_response` to construct the response:

```python
def _handle_your_opcode(self, seq: int, payload: bytes) -> list[tuple[bytes, float]]:
    if len(payload) < MINIMUM_EXPECTED_LENGTH:
        return [(self._build_file_response(RESPONSE_CMD, seq, status=1, payload=b""), self._delay())]

    # Parse payload fields per PROTOCOL.md
    slot = int.from_bytes(payload[1:3], "big")

    # Build response payload
    out = b"\x00" + slot.to_bytes(2, "big")

    return [(self._build_file_response(RESPONSE_CMD, seq, status=0, payload=out), self._delay())]
```

`RESPONSE_CMD` is typically `cmd - 0x40` for file-group response opcodes (e.g., `0x6A`
requests get `0x2A` responses), matching the pattern used throughout the emulator.

### Step 4 — Update `self._samples` state if needed

If the handler modifies device state, hold `self._lock` during the mutation:

```python
with self._lock:
    self._samples[slot] = SampleSlot(...)
```

All reads from `self._samples` in the `_run` loop share this lock.

### Step 5 — Write a test

Add a test to `tests/unit/test_emulator.py`. Use `EP133Emulator()` directly (no MIDI
ports needed) and call `emu.handle_sysex(req)` with a built request message. The existing
`_decode_file_response` helper in that file decodes the response tuple.

---

## Known Limitations

### Single active upload

`_latest_pending_upload` returns the last entry in `self._pending` by insertion order.
Concurrent uploads to different slots are not modelled — only the most recently initiated
upload receives chunk data. This is sufficient for the current client, which never
interleaves uploads.

### Download slot state is not reset after commit

`_download_slot` is set on GET_INIT and never explicitly cleared. If a second GET_INIT
for a different slot arrives before GET_DATA chunks are consumed, `_current_download_sample`
will serve the new slot's data. This matches the real device's stateful download mode
described in the project memory ("_initialize() After Stateful Sessions").

`_current_download_sample` also has a fallback: if `_download_slot` is not set or not
found, it serves the first slot in sorted order. This prevents a crash when tests call
GET_DATA without GET_INIT, at the cost of returning unexpected data.

### No INIT state machine

The real device requires the two-message INIT handshake (`0x61`) before accepting file
operations. The emulator accepts all file operations immediately. Tests should not rely on
INIT being enforced.

### Node 1000 is the only listable directory

`_encode_directory_entries` returns entries only for `node_id == 1000` (the `/sounds/`
root, per `PROTOCOL.md` § "Known node ranges"). Requests for any other node ID return an
empty listing with `status=0` rather than an error. The real device has a deeper node
hierarchy (pad nodes 9200+, project nodes, etc.) that is not modelled.

### Threading

`EP133Emulator` is thread-safe for state mutations (`self._samples`, `self._pending`)
via `self._lock`. However, `handle_sysex` itself does not acquire `self._lock` for the
dispatch phase — only individual state-mutating helpers do. Callers that invoke
`handle_sysex` directly in tests do not need to worry about the lock, since they run
single-threaded.

When the emulator is started with `start()` or used as a context manager, the `_run`
loop runs in a daemon thread. The MIDI port is opened as a single virtual `ioport` where
the backend supports it, with a fallback to separate input/output ports. The comment in
`start()` notes this is to avoid CoreMIDI instability on macOS.

### Response opcode values are hardcoded

Each handler passes a literal response `cmd` value (e.g., `0x2A` for LIST_FILES,
`0x3D` for DOWNLOAD, `0x2C` for UPLOAD_DATA, `0x3E` for UPLOAD/DELETE). These are not
derived from a table — they match the values the real device returns, as confirmed from
captures referenced in `docs/protocol-evidence.md`. If a new opcode is added, the correct
response `cmd` must be determined from a real capture or from `PROTOCOL.md`.

### Metadata pagination uses 320-byte chunks

The page size for METADATA GET is 320 bytes, matching the observed behaviour in
`captures/sniffer-readmeta.jsonl`. The real device's exact chunk boundary is not
independently confirmed for all firmware versions. Metadata blobs longer than 320 bytes
(unusual in practice) will be served across multiple pages correctly by the emulator's
slice logic, but this path has no dedicated test.

### PCM data format

Default sample data is generated by `_make_pcm`: a sine wave at a slot-dependent
frequency (110 Hz + `(slot % 24) * 11` Hz), 0.22 seconds, at 46875 Hz, LE s16 —
identical to what the client uploads and downloads. The emulator stores and serves raw
PCM bytes with no RIFF header, matching `PROTOCOL.md` § "Download Protocol".
