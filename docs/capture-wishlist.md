# Protocol Captures Still Needed

Follow the [capture guide](capture-format.md) and use one FILE client at a
time. For cross-version comparisons, use the same action and request body on
2.0.5 and 2.5.1 and record the GREET reply for each device.

## 1. Whole-file GET page numbers and size

Use a sample with known PCM bytes and enough data to cross pages 127 and 256
(at least 100 kB of PCM). Compare separate reads of the same sample using the
reference client's BE16 page encoding and Krate's existing encoding. Record
GET open, page 1, the boundary pages, and the final byte count and checksum.
Use the advertised size to end each stream.

Capture BE16 requests and echoes at pages 1 (`00 01`), 128 (`00 80`), and 256
(`01 00`). An echoed page field alone proves the device received those bytes.
The PCM comparison checks which page it actually returned. A direct export
from the official tool, if available, can also distinguish whole-file GET from
its captured 16,000-byte preview with an extended open request.

## 2. Recovery after interrupted GET

On separate sessions, complete one GET and stop another after a few pages.
Follow each with a read-only STAT or LIST on the same connection. Record
whether it replies normally, and compare FILE INIT alone with Krate's full
startup sequence if a reset is needed. Match replies on both request-ID
bytes and the command group. Record unsolicited events and any firmware
debug frame separately.

## 3. Project listing, TAR read and activation

Start with the existing CLI debug listing:

```bash
python krate.py fs-ls --node 2000 --raw
```

Capture its LIST replies. With a reference client, read a single project fid
and compare its TAR members and bytes with that project's official backup.
For activation, capture a switch between two saved projects and back, then
read node 2000 after each switch to check the active fid. This would tie the
upstream activation write to a local trace.

## 4. Hardware variants and metadata edits

- On 2.5.1, capture complete GREET and `/sounds` storage exchanges on the
  available 64 MB unit. Record the reported byte counts. A published
  firmware-stamped 128 MB capture can fill the corresponding evidence gap.
- Compare the short and long PLAY requests on each firmware against the
  same sample and trim settings.
- Use `--hunt meta_set` while changing one pad loop or trim control at a
  time. Capture loop start, loop end, enable and disable, and then read
  back the sample node and the pad node. The [existing pad trim
  trace](protocol-evidence.md#pad-assignment-and-trim)
  covers `sample.start` and `sample.end` on the pad.
- On groups B, C and D, capture each physical pad label with the resulting
  `active` fid to complete local coverage of the [upstream map](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/midi-reference.md#pad-numbering-warning).
