# Protocol Captures Still Needed

Follow the [capture guide](capture-format.md) and use one FILE client at a
time. For cross-version comparisons, use the same action and request body on
2.0.5 and 2.5.1 and record the GREET reply for each device.

## 1. Krate's GET page encoding

The official tool's encoding is settled on 2.5.1: an 8-byte open and BE16
pages counted from 0, echoed at pages 1, 128 and 256, and 237 files read to
their exact size ([PROTOCOL.md](../PROTOCOL.md#download-get)). What remains
is Krate's own form: a 9-byte open and 14-bit little-endian pages.

Read one sample of at least 100 kB (past pages 127 and 256) once with BE16
pages and once with Krate's encoding. Compare the byte counts and CRC-32
of the two results with the slot's `crc` metadata, which is CRC-32 of the
PCM.

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

## 5. Project settings bytes 220–223

Settled: byte 220 is swing, 221 the scene length as displayed, 222 the scale
type, 223 the root pitch class.
Still open: confirm M.MI = 12 and one of 0–9 against the
[scale index](project-format.md#scale-index).
Compare with the [settings table](protocol-evidence.md#project-settings-bytes).

## 6. PLAYBACK length and stop

Capture the official tool auditioning from the sound list and from a pad on
2.5.1. Record whether it sends STOP (action `2`), and how long playback lasts
for `length` 1000 versus 0 on a sample longer than a few seconds.

## 7. INIT flags

Compare INIT `01 00 …` with `01 01 …` on one connection and record which
file events arrive afterwards.

## 8. Upload above the native rate

Upload one 48 kHz s16 WAV with the official tool and record the PUT JSON
and the stored `samplerate`. Then audition it to compare its pitch.

## 9. Stereo preview and MOVE

Capture the waveform preview of a stereo sample whose PCM is known, and an
official-tool slot move, to settle the preview channel layout and the MOVE
body on the wire.
