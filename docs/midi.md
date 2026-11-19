# EP-133 MIDI, pads and device limits

What the EP-133 does over plain MIDI (no SysEx), how its pads are numbered
in each addressing scheme, and the device limits. Sources are tagged:
**krate** (Krate captures), **TE** (official guide and release notes),
**upstream** ([kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/midi-reference.md),
MIT; notice at the end).

## Pad numbering

Three numbering schemes are in use, and only two of them agree.

| Key | SysEx pad N, TAR `pNN` | MIDI note offset |
|---|---|---:|
| 7 | 01 | +9 |
| 8 | 02 | +10 |
| 9 | 03 | +11 |
| 4 | 04 | +6 |
| 5 | 05 | +7 |
| 6 | 06 | +8 |
| 1 | 07 | +3 |
| 2 | 08 | +4 |
| 3 | 09 | +5 |
| . | 10 | +0 |
| 0 | 11 | +1 |
| ENTER | 12 | +2 |

- SysEx pad nodes are `group fid + N` ([PROTOCOL.md](../PROTOCOL.md#file-ids)).
  Krate's 2.0.5 captures tie key 8 to node 9502 (N = 2) and key 6 to node
  9506 (N = 6) ([evidence](protocol-evidence.md#pad-assignment-and-trim)).
- Archive members `pads/{g}/pNN` follow the same order. Upstream calibrated
  this by pressing every pad and reading the `active` metadata events.
  Upstream's project-format page calls this order "bottom-up", which
  contradicts its own table; the table is the calibrated one.
- MIDI notes run from the bottom row: `note = 36 + 12 × group + offset`,
  group A = 0 … D = 3. Group A spans 36–47, B 48–59, C 60–71, D 72–83.
  Keys mode plays chromatically over 0–127 (upstream).
- Pattern note records store the pad as `(pNN − 1) × 8`
  ([project-format.md](project-format.md#note-record)).

## MIDI input

| Message | Effect | Source |
|---|---|---|
| Note on/off | plays pads by the note map above | upstream |
| CC 1 | modulation / vibrato | upstream |
| CC 12, CC 13 | FX knob X and Y | TE 2.5 |
| CC 64 | sustain for key and legato voices | TE 2.5 |
| Bank select (CC 0/32) + program change | selects sounds 1–999; unconfirmed on 2.5.1 | upstream |
| Clock, start, stop, continue | drive the sequencer when clock input is on (system code 101) | upstream |
| Identity request | answered over USB, and over TRS MIDI since 2.5 | TE 2.5 |

MIDI clock is 24 PPQN; the sequencer runs at 96 ticks per quarter note.
MIDI stop cuts ringing one-shots. No CC controls the 12 group faders, so
fader automation exists only in pattern data (upstream).

The identity reply carries the SKU but no firmware version: bytes 8–9 and
10–11 are two 7-bit pairs that the tool formats as `TE<aaa>AS<bbb>`
(tool). The 2.5.1 reply `F0 7E 33 06 02 00 20 76 20 00 01 00 …` decodes to
`TE032AS001` ([capture](../tests/fixtures/fw251-wire-excerpts.jsonl#L2)).

## MIDI output

During playback the device sends each note record's note and velocity;
pressing a pad sends its mapped note. The MIDI channel is per pad (pad record
byte 3). Fader automation changes what is sent: PTC at 32,767 transposes by
+12 semitones (16,384 is neutral) and VEL scales velocity. External start
plays the scene in trailer byte 3 of `scenes`, at that scene's time
signature (upstream).

## System settings (SHIFT + ERASE codes)

These live on the device, outside projects and backups, and no known SysEx
command reads or writes them (see [PROTOCOL.md](../PROTOCOL.md#projects-and-backups)).

| Setting | Codes |
|---|---|
| MIDI clock | 100 off, 101 in, 102 out (upstream) |
| MIDI channel | 110 receive all, send channel 1 (default); 111–126 fixed channel 1–16; 127 = OFF: pads send and receive only if a channel is assigned in SOUND EDIT (TE 2.0.1 notes) |
| MIDI thru | 130 off, 131 on (upstream) |
| Reset controllers on stop | 140 on, 141 off (TE 2.0.2 notes) |
| Keys-mode scale (before OS 2.5) | 310–319: 12T, maj, min, dor, phr, lyd, mix, loc, major and minor pentatonic. Since 2.5 scale and key are project settings, held with KEYS + knobs ([scale index](project-format.md#scale-index)) |
| Sync rate (TRS sync jack, not MIDI clock) | 200–212 (upstream) |
| Recording rate | `smp` → `rec`: lo 26,250 Hz, mid 32,000 Hz, hi 46,875 Hz (TE 2.5) |

Upstream lists code 140 as "don't reset" and 141 as "reset"; TE's 2.0.2
notes say 140 is on and 141 off.

## USB

- USB MIDI and 5-pin DIN carry the same messages, including SysEx (upstream).
- USB audio (OS 2.5+): macOS sees 2 inputs and 2 outputs at 48,000 Hz, while
  the engine runs at 46,875 Hz (krate, on 2.5.1).
- Sounds move only through the FILE protocol; there is no mass-storage mode.
- Firmware updates use the browser updater. The Sample Tool code also holds
  the entry into bootloader mode ([PROTOCOL.md](../PROTOCOL.md#firmware-update-dfu));
  do not use it outside an official update.

## Limits

| Item | Limit |
|---|---|
| Sample slots | 1–999 |
| Sample memory | per SKU: `TE032AS001` reports 62,853,120 bytes (krate); upstream and ep-unity cite 128 MB units |
| Sample rate on import | device advertises 1–65,535 Hz; stored as uploaded up to 46,875 Hz (44,100 Hz seen); higher rates open ([sound-format.md](sound-format.md#format-negotiation)) |
| Recording | up to 40 s mono since 2.5, at 26,250 / 32,000 / 46,875 Hz (TE 2.5) |
| Projects | 9, each with 4 groups × 12 pads |
| Tempo | 40–399 BPM, decimals allowed (upstream, from the guide) |
| Pattern length | 1–99 bars |
| Scenes | 99; song list up to 99 positions |
| Note length | 1 tick upward; upstream gives one bar as the limit, but device-written patterns hold notes over two bars ([project-format.md](project-format.md#note-record)) |

Factory sound banks: kick 1–99, snare 100–199, hat 200–299, percussion
300–399, bass 400–499, melodic 500–599 (upstream).

---

Note maps, CC and system-code tables are adapted from
[kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex),
Copyright (c) 2026 Kevin Morrill, under the MIT License
([full text](LICENSE-ep-series-sysex.txt)).
