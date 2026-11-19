# EP-133 sound format

How the EP-133 stores samples, which formats it accepts, how the official
Sample Tool converts audio before upload, and the metadata that travels with
each sound. Wire operations are in [PROTOCOL.md](../PROTOCOL.md); confidence
tags (**2.0.5**, **2.5.1**, **tool**, **upstream**, **open**) have the same
meaning as there.

## Quick reference

| Property | Value | Evidence |
|---|---|---|
| Sample encoding | signed 16-bit little-endian PCM, interleaved, no header | 2.0.5, 2.5.1 |
| Channels | 1 or 2 | 2.0.5, 2.5.1 |
| Native rate | 46,875 Hz | `/sounds` `formats`, 2.0.5 and 2.5.1 |
| Accepted rates | device advertises 1–65,535 Hz; rates up to 46,875 are stored as uploaded (44,100 Hz seen); higher rates are open | `/sounds` `formats`, 2.0.5 |
| Node name | `NNN.pcm` (slot number) | 2.0.5 |
| Size in LIST/STAT | PCM byte count | 2.0.5, 2.5.1 |
| Duration | `size / 2 / channels / samplerate` seconds | tool |
| `crc` | CRC-32 (zlib/IEEE) of the PCM bytes, computed by the device | 2.0.5, 2.5.1 |
| Slots | 1–999 in `/sounds`, shared by all projects | 2.0.5, 2.5.1 |

## Storage

A sound is a node under `/sounds` (fid 1000) whose fid is its slot number.
Its content is exactly the PCM that was uploaded: frames of one or two s16
little-endian samples. GET returns the same bytes, so a download needs only
a WAV header built from the `channels` and `samplerate` metadata.

The device keeps the uploaded sample rate. The 2.0.5 library in the upload
fixture holds mono and stereo samples at 44,100 Hz next to 46,875 Hz ones
([metadata replies](../tests/fixtures/sniffer-upload-kick-official.jsonl#L52-L62)).
TE's [Sample Tool guide](https://teenage.engineering/guides/ep-133/functions)
documents that OS 2.0 keeps lower-rate samples at their original rate, and
the [2.5 notes](https://teenage.engineering/guides/ep-133/whats-new) say
samples can be imported "at any sample rate directly onto ko2 using the
ep-sample-tool".

The `crc` field is the standard CRC-32 of the PCM bytes. The device fills it
in itself: the 2.0.5 upload of `tests/fixtures/kick-46875hz.wav` sent no
`crc`, and the stored value `253864875` equals `zlib.crc32` of that file's
60,936 PCM bytes
([readback](../tests/fixtures/sniffer-upload-kick-official.jsonl#L475)).
Two sounds in a 2.5.1 backup match the same way.

## Format negotiation

METADATA GET on `/sounds` returns the device's capacity and its accepted
formats. The reply is identical on 2.0.5 and 2.5.1:

```json
{
  "max_capacity": 62853120,
  "free_space_in_bytes": 2856216,
  "formats": [{
    "type": "pcm",
    "formats": [{
      "samplerate.range": [1, 65535],
      "samplerate.native": 46875,
      "channels": [1, 2],
      "format": ["s16"]
    }]
  }]
}
```

[2.0.5 exchange](../captures/sniffer-readmeta.jsonl#L12-L15), [2.5.1 exchange](../tests/fixtures/fw251-wire-excerpts.jsonl#L6-L7). Capacity is
for a 64 MB `TE032AS001` unit, and free space changes with the library.

The official tool picks a format entry of type `pcm` that lists `s16` and
the source's channel count. Its target rate is the smaller of the source
rate and the top of `samplerate.range`, falling back to `samplerate.native`
and then to 46,875 Hz (tool). With the range above, 44.1 kHz and 48 kHz
sources upload at their own rate without resampling.

## Upload conversion in the official tool

The tool reads the source with a WebAssembly build of libsndfile, then:

1. Rejects files that are not audio, report a length over 40 (likely
   seconds), or have a sample rate outside 3,000–768,000 Hz.
2. **Fast path**: a WAV that is already s16 at the target rate with one or
   two channels is sent as is. Only the `data` chunk is sent.
3. **Otherwise**: the browser decodes the file to interleaved float samples
   at the source rate (AIFF goes to the resampler directly), and libsamplerate
   converts them to s16 at the target rate. Channel count is kept.
4. Builds metadata from the source:
   - `channels` and `samplerate` (target rate)
   - loop start and end from the WAV, rescaled by target rate ÷ source rate
   - `sound.rootnote` from the MIDI root note, unless it is 0
   - `sound.bpm` from the file's tempo
   - any keys in the WAV's TE JSON chunk (see below) that pass the tool's
     value checks
5. PUT open carries `channels` and `samplerate` (with `name`, `format` and
   `crc` if known), the PCM follows, then METADATA SET writes the full set
   and INIT follows.

All of this is tool code; the device only sees PCM plus JSON. Krate
resamples rates above 46,875 Hz to 46,875 Hz, which the tool does not do.
Whether the device plays 48 kHz uploads correctly is open.

## Sample metadata

METADATA GET on a slot returns one JSON object. 2.5.1 has 19 keys; 2.0.5
has 17 (no `sample.start`, `sample.end`). Example from 2.5.1:

```json
{"channels":2,"samplerate":46875,"format":"s16","crc":547694721,
 "sound.loopstart":0,"sound.loopend":70312,"name":"toaster bell",
 "sound.amplitude":100,"sound.playmode":"oneshot","sound.pan":0,
 "sound.pitch":0.00,"sound.rootnote":60,"time.mode":"off","sound.bpm":0.00,
 "sound.bars":1.00,"envelope.attack":0,"envelope.release":255,
 "sample.start":0,"sample.end":70313}
```

| Key | Type, observed values | Tool check | Notes |
|---|---|---|---|
| `channels` | 1, 2 | — | set at upload |
| `samplerate` | Hz | — | set at upload |
| `format` | `"s16"` | — | set at upload |
| `crc` | u32, CRC-32 of PCM | — | computed by device |
| `name` | string | — | upstream: up to 20 ASCII characters |
| `sound.loopstart`, `sound.loopend` | frames; `-1` = no loop | ≥ 0 | `-1` seen on 2.0.5 |
| `sound.amplitude` | 100 default | 0–200 | upstream gives 0–100 |
| `sound.playmode` | `"oneshot"`; upstream adds `"key"`, `"legato"` | non-empty | write as a string (upstream) |
| `sound.pan` | 0 | −16…16 | |
| `sound.pitch` | float semitones, e.g. `-12.00` | −12…12 | |
| `sound.rootnote` | MIDI note, 60 default | 0–127 | |
| `time.mode` | `"off"`; upstream adds `"bar"`, `"bpm"` | non-empty | write as a string (upstream) |
| `sound.bpm` | float, e.g. `129.76`; `0.00` = unset | 60–180 | upstream gives 1–200 |
| `sound.bars` | float, `1.00`, `2.00` | — | |
| `envelope.attack` | 0 | 0–255 | |
| `envelope.release` | 255 | 0–255 | upstream: write with `sound.playmode` |
| `sample.start`, `sample.end` | frames | — | 2.5.1 only; trim |

The tool's checks apply to metadata it imports from WAV files. They are
not device limits. The tool also carries `sample.mode` and `regions` when
exporting WAVs, but neither key appears on the device or in a 2.5.1 backup.

Slot metadata seeds a pad when the sound is assigned. After that the pad
node holds its own values (upstream).

## Waveform preview

The device can return a decimated waveform instead of the PCM; see
[PROTOCOL.md](../PROTOCOL.md#waveform-preview). Each point is the PCM
sample at `k × stride`, sent twice as s16. It is point decimation, so draw
detailed waveforms from the full PCM.

## WAV files in backups

The official tool exports sounds as WAV files, inside `.pak`/`.ppak`
backups as `/sounds/NNN <name>.wav`. All 458 files in a 2.5.1 user backup
share one layout, and every rule below holds for all of them:

| Chunk | Content |
|---|---|
| `fmt ` | PCM, 16-bit, the sound's channels and rate |
| `smpl` | MIDI unity note = `sound.rootnote` (458 of 458); one loop record holding `sound.loopstart`/`sound.loopend` exactly when the loop is set (102), none otherwise (356) |
| `acid` | exactly when `sound.bpm` is non-zero (21 of 458); tempo = `sound.bpm` as f32 LE at offset 20 |
| `LIST`/`INFO` | holds a `TNGE` sub-chunk with a JSON object |
| `data` | the device PCM, unchanged |

The `TNGE` JSON holds the playback keys: `sound.loopstart`,
`sound.loopend`, `sound.playmode`, `sound.rootnote`, `sound.pitch`,
`sound.pan`, `sound.amplitude`, `sound.bpm`, `envelope.attack`,
`envelope.release`, `time.mode`, `sample.start`, `sample.end`. Format fields,
`crc` and `name` are not in it; the name is in the file name. On import the
tool reads this chunk back (step 4 above).

## Krate

- Upload: `prepare_for_upload` converts to 16-bit, keeps the channel count,
  keeps rates at or below 46,875 Hz and resamples higher rates.
- Download: writes the PCM with a WAV header, but guesses mono or stereo
  from the samples (`detect_channels`) instead of reading `channels`. Bead
  `ko2-tools-known-mono-export` tracks mono sounds exported as stereo.
- Krate does not yet write `smpl`, `acid` or `TNGE` chunks, so its exports
  lose loop, root note and playback settings that the official tool keeps.
