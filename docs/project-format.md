# EP-133 project archive format

Byte layout of the project TAR that GET returns for a project fid and that
`.pak`/`.ppak` backups store as `/projects/PNN.tar`. The wire side is in
[PROTOCOL.md](../PROTOCOL.md#projects-and-backups).

Integers inside members are **little-endian**, unlike FILE payloads.

**Sources and tags.** Most field meanings come from the bench work of
[kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex)
(MIT; notice at the end), written up here in Krate's own words. Each claim
carries one tag:

| Tag | Meaning |
|---|---|
| **upstream** | Bench result on OS 2.5.1 from ep-series-sysex: write, reload and audio or MIDI measurement. |
| **backup** | Checked structurally across the nine device-written TARs of an EP-133 OS 2.5.1 user backup (432 pad records, 276 patterns). This confirms sizes, ranges and consistency, not meaning. |
| **open** | Not established. |

Where the backup disagrees with upstream, the table says so.

## Safety rules for writing archives

Upstream learned these by breaking devices. Follow them before any write.

1. Pattern header byte 0 must be 0. Writing 3 produced `err pattern 71`,
   aborted the write and wedged the FILE layer until a power-cycle (upstream).
2. Pad record byte 0 must be 0; any other value silences the pad (upstream).
3. Never build a `settings` member from scratch. A fabricated one caused a
   fatal `ERR CLOCK 43` that needed a flash format. Copy a device-written
   member, or generate one byte-for-byte from the rules below (upstream).
4. Every defined scene must reference a pattern for every group. A scene
   such as `[1,0,0,0]` triggers `err pattern 187` on the EP-133 (upstream). No
   device-written scene in the backup has a zero reference (backup).
5. Fader-automation values stay within 0–32,767; wider values loop
   `err fader 93` (upstream).
6. Keep unused scene chunks as `00 00 00 00 04 04`; zeroing the `04 04`
   triggers `err scene 156` (upstream).
7. Write a project only after every slot it assigns exists in `/sounds`;
   otherwise it plays silently (upstream).

Error signatures and recovery: [errors.md](errors.md).

## TAR dialect

Device TARs are uncompressed, 512-byte-block TARs without the `ustar`
marker:

| Header field | Device form |
|---|---|
| name | path, NUL-terminated, bytes 0–99 |
| mode | octal ASCII, `0000644` for files, `0000755` for directories |
| uid, gid, mtime | all NUL |
| size | octal ASCII without leading zeros, then NULs; NUL for directories |
| checksum | standard TAR checksum, octal ASCII then NUL and spaces |
| type | `0` file, `5` directory |
| magic | all NUL |

The archive ends with two zero blocks. Every header in the backup matches
this, and every checksum verifies (backup). Upstream reports that the device
accepts generic `ustar` headers but treats that as untested tolerance.

## Members

| Member | Content | Backup |
|---|---|---|
| `pads/`, `pads/a` … `pads/d`, `patterns/` | directories | present in all nine |
| `pads/{a-d}/p01` … `p12` | pad records | 48 per project, 432 in all |
| `patterns/{a-d}NN` | one group pattern: notes and fader automation | 276 in all |
| `scenes` | scene table and song list, 712 bytes | all nine |
| `settings` | tempo, fader positions and assignment, per-project bytes | all nine |
| `fx_settings` | master FX, output compressor, sidechain, 160 bytes on 2.5.1 | eight; P08 has none |

Pattern members sit directly in `patterns/`; the group is the letter in the
name (`a01` = group A, pattern 1). A project need not contain every member.

Upstream reports how the device rewrites what it receives: it adds the
directories and all 48 pad records, sorts patterns, and keeps the payload of
every member. It accepts one pad record plus one pattern as a playable
project. It does not create missing `scenes` or patterns. Byte-exact
readback is therefore only expected for archives already in device form, and
a project that reads back fine can still fail when activated.

### Pad numbering

`pNN` counts from the top-left key across each row, the same order as SysEx
pad fids. The backup confirms it: the slots and trim that 2.0.5 captures
wrote to pad nodes 9502 and 9506 sit in P07 `pads/d/p02` and `pads/d/p06`.
MIDI notes run from the bottom row instead.
[midi.md](midi.md#pad-numbering) has the full table.

## Scope

| Level | Holds | In the TAR |
|---|---|---|
| Sample | PCM and slot metadata (`/sounds`) | no |
| Project | tempo, swing, FX, scenes, patterns, pad assignments | yes |
| Group | fader assignment and base positions, 12 pads, the group's patterns | yes |
| System | MIDI clock, channel and thru, sync, velocity curve, LEDs, recording rate, record quantize | no |

Upstream places swing at system level. On 2.5.1 it is project state:
changing only P02's swing from 65 to 50 changed only `settings` byte 220
(krate, 2026-11-19), matching TE's OS 2.0.2 fix "Swing was not updated when
loading a new project". Record quantize is global. Moving the root note
from C3 to C4 left the project TAR byte-identical, which fits a key stored
as a pitch class (both are C). Scale type and root note are
project state in bytes 222 and 223. See [settings](#settings).

## Pad record — `pads/{g}/pNN`

Upstream calls 26 bytes the native size and 27 bytes a Sample Tool form that
adds byte 26. In the backup, which holds the device's own GET output, 423 of
432 records are 27 bytes and 9 (all in P01) are 26 bytes (backup). P01 mixes
both sizes in one archive, so the device appears to keep each record as it
was last written rather than re-serialize it. Whether these 27-byte records
came from the firmware or from an earlier Sample Tool restore is unknown.
Upstream links the 27-byte form to `ERR PATTERN 189` at scene changes; that
is unconfirmed here.

| Byte | Field | Meaning (upstream) | Backup |
|---|---|---|---|
| 0 | must be 0 | non-zero silences the pad | 0 in all |
| 1–2 | sample slot, u16 | 1–999, 0 = none | 430 assigned; 20 point at slots missing from `/sounds`. P07 `d/p02` = 74 and `d/p06` = 53, as the 2.0.5 captures set for nodes 9502 and 9506 |
| 3 | MIDI channel | 0 = channel 1 | 0 in all |
| 4–7 | trim start, frames | width u24 or u32 is open | 2318 in P07 `d/p02`, matching the captured `sample.start`; byte 7 is 0 in all |
| 8–11 | trim length, u32 frames | truncates playback | 5688 in P07 `d/p02` = captured `sample.end` 8006 − start 2318: a length, not an end point |
| 12–15 | sample BPM, f32 | with time mode 1, rate = clock BPM ÷ sample BPM | 132 and 170 on stretched pads |
| 16 | amplitude | 0–200, 100 ≈ unity, about 0.5 dB per step below 100 | 0–173 seen |
| 17 | pitch, i8 semitones | −12…+12 | −12…+12 |
| 18 | pan, i8 | −16…+16, constant-power | −16, 0, +16 |
| 19 | attack | 0–255 | — |
| 20 | release | 255 = play through; lower values fade (one-shot: from note-on) | — |
| 21 | time-stretch mode | 0 off, 1 BPM, 2 bar, 3 reverse | 0 or 1 |
| 22 | mute group | any non-zero value joins the one choke group | 0 or 1 |
| 23 | play mode | 0 one-shot, 1 key, 2 legato | 0, 1, 2 |
| 24 | root note | MIDI note; rate = 2^((note − root) / 12) in every mode | 24–84 |
| 25 | unknown | upstream: inert at 255, presumed padding | **0 in 425 records, 1 or 2 in the rest, never 255** |
| 26 | pitch fraction (27-byte form) | pitch = byte 17 + byte 26 / 100 | 0 in 410, 3–93 in 17 |

Pads are monophonic: a retrigger cuts the previous voice (upstream). When
changing the slot, rewrite trim, length, BPM, amplitude, release, modes and
root together; stale trim bytes make a new sample play as a fragment
(upstream).

The SysEx pad node exposes the same data as metadata (`sym`,
`sample.start`, `sample.end`, `sound.*`, `envelope.*`, `time.mode`,
`midi.channel`); see [PROTOCOL.md](../PROTOCOL.md#metadata).

## Pattern — `patterns/{g}NN`

A 4-byte header, then 8-byte records. Timing is 96 ticks per quarter note;
a 16th step is 24 ticks.

| Header byte | Meaning | Backup |
|---|---|---|
| 0 | must be 0 (firmware-validated) | 0 in all |
| 1 | bars, 1–99 | 1, 2, 4 |
| 2 | record count: notes and automation together | size = 4 + 8 × count in all 276 |
| 3 | unknown; not the time signature (that is per scene) | 0 in all |

### Note record

| Byte | Field | Meaning (upstream) | Backup |
|---|---|---|---|
| 0–1 | position, u16 ticks | free timing is stored in the position | — |
| 2 | pad | `(pNN − 1) × 8` | multiples of 8 |
| 3 | note | pitch relative to the pad's root; also the MIDI note sent | — |
| 4 | velocity | 1–127; 128+ is sent as velocity 1 | 100, 119 |
| 5–6 | duration, u16 ticks | audible in key and legato modes; upstream gives 1 bar as maximum | **up to 839 ticks (over 2 bars) in 2-bar patterns** |
| 7 | flags | upstream: 0/2/4/6/8/255 sound identical; write 0 | 0, 6, 8, 13, 16, 31, 62, 63, 129, 214, 222, 239, 245, 255 |

### Fader-automation record

Recorded fader moves are stored between the notes and counted in the same
header count. A record whose byte 2 is not a pad multiple of 8 is automation.

| Byte | Field | Meaning (upstream) | Backup |
|---|---|---|---|
| 0–1 | tick, u16 | sampled every 6 ticks while the fader moves | — |
| 2 | record type | `01` (`05` also accepted) | `01` in all 185 |
| 3 | fader parameter, 0–11 | see [fader parameters](#fader-parameters) | 3 (LPF) in all |
| 4 | 0 | | 0 |
| 5–6 | value, u16 | 0–32,767; base f32 = value ÷ 32,767 | all ≤ 32,767 |
| 7 | upstream: 0 on the EP-133 | | **106–255, varies per record**; meaning open |

A value holds until the next record for the same parameter, and overrides
the group's fader base from that tick on (upstream).

## Scenes — `scenes` (712 bytes)

| Bytes | Content | Meaning (upstream) | Backup |
|---|---|---|---|
| 0–6 | header | `00 00 00 00 00 04 04`; the last two are the default 4/4 | identical in all |
| 7–600 | 99 chunks of 6 bytes | bytes 0–3: pattern number per group A–D (1-based); bytes 4–5: time signature numerator, denominator | all `04 04`; no chunk has a zero group reference |
| 601–711 | 111-byte trailer | byte 3: scene played by external MIDI start (the cursor); byte 11: song length; bytes 12…: 1-based scene numbers in song order | song length 1 in all |

Scene 1 is the live arrangement: changing a group's pattern writes it.
Committing a scene (SHIFT+MAIN) copies the playing patterns into the next
scene (upstream). Trailer byte 3 does not count the defined chunks; P04 has
10 defined chunks and byte 3 = 4 (backup), which fits upstream's cursor
reading.

Device-written scenes can reference pattern numbers that have no member;
seven of the nine projects do (backup). Upstream reports that the device
tolerates this in its own projects but that a written archive referencing a
missing pattern triggers `err pattern 187`. A 2.0.5-era `scenes` member does
not work on 2.5.1 (upstream).

## Settings

| Bytes | Content | Meaning (upstream) | Backup |
|---|---|---|---|
| 0–3 | unknown | | 0 in all |
| 4–7 | project BPM, f32 | applied on reload | 90–170 |
| 8–23 | unknown | candidates: quantize, input gain | 0 in all |
| 24–215 | fader bases: 4 groups × 12 parameters × f32 at `24 + 48g + 4p` | −1.0 = untouched, else 0–1; always applied; parameter 5 is the group FX send, which gates the master FX | all −1.0 or within 0–1 |
| 216–219 | fader assignment per group A–D | parameter index 0–11 | 0–11 |
| 220 | swing, 0–12 = 50–75 | upstream: disputed | 50 → 0, 60 → 5, 65 → 7, 75 → 12 (krate); 0 or 5 in the backup |
| 221 | scene length, the value shown on the device | upstream: disputed | 1, 2 or 4 in the backup; 12 and 11 read as shown (krate) |
| 222 | scale type (224-byte form), see [scale index](#scale-index) | | 0 in the backup; 10 = blues, 11 = H.MI (krate) |
| 223 | root note pitch class, C = 0 (224-byte form) | | 0 in the backup; D = 2, G = 7 (krate) |

Members are 222 or 224 bytes; both sizes occur on the same device (backup).
Byte 220 is swing: on P02, swing 50 read `00`, 65 read `07` and 75 read
`0C`; the swing-only change touched no other byte of the 70,144-byte TAR
(krate, 2026-11-19). Swing 60 read `05`, so one step is 25/12 ≈ 2.08 and
the device rounds for display: swing ≈ 50 + 25 × value / 12. Byte 222 moved
only with the scale type (to 10 for blues) and byte 223 with the root note
(to 7 for G1; C3 → C4 kept 0), so the 224-byte form stores scale and root
per project, as TE's OS 2.5 notes say. The 222-byte form lacks both bytes;
the device writes the 224-byte form when it saves. See the [scale index](#scale-index). Byte 221 is the length setting
(how long the scene runs, per the device owner): the byte holds the value the
device shows (12 → 11 when the display went from 12 to 11), and nothing else
in the TAR changed. The device saved some edits only
after a delay, so read a TAR again if a change does not appear at once.
[Evidence table](protocol-evidence.md#project-settings-bytes).

Upstream reports that a member generated from these rules (zero prefix,
BPM, 48 × −1.0, assignment, tail `00 01`) is byte-identical to a default
device member.

## FX settings — `fx_settings` (160 bytes on 2.5.1)

| Bytes | Content (upstream) | Backup |
|---|---|---|
| 4 | master FX type: 0 off, 1 delay, 2 reverb, 3 distortion, 4 chorus, 5 filter, 6 compressor. Heard only when a group FX send is above 0 | 0 or 1 |
| 8–11 | f32, unknown | |
| `12 + 4 × (type − 1)` | knob X per type, f32: delay length @12, reverb length @16, distortion drive @20, chorus modulation @24, filter cutoff @28, compressor drive @32 | all floats in 12–147 within 0–1 |
| `76 + 4 × (type − 1)` | knob Y per type, f32: delay feedback @76, reverb color @80, distortion color @84, chorus feedback @88, filter resonance @92, compressor speed @96 | |
| 136–139 | output compressor drive (SHIFT + knob X), f32 | |
| 140–143 | output compressor speed (SHIFT + knob Y), f32 | |
| 144–147 | sidechain length, f32 | |
| 148–151 | sidechain shape, f32 (placed by elimination) | |
| 152–159 | sidechain routing, u16 per group A–D: bit 15 = ducked group, bits 0–11 = source pads | `0x8000`, `0x0600` |

Older firmware wrote 144 or 152 bytes; a 2.0.5-era member still works on
2.5.1 (upstream).

## Scale index

`settings` byte 222. Indices 0–9 follow the pre-2.5 system codes 310–319
(index = code − 310), where scale was a device-wide setting; OS 2.5 added
three scales and made scale and key per project (TE). Indices 10 and 11
are measured (krate); 12 assumes M.MI follows in the order TE lists them.

| Index | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Scale | 12T (chromatic, default) | maj | min | dor | phr | lyd | mix | loc | major pentatonic | minor pentatonic | BLU | H.MI | M.MI |

Sources: TE's [how-to guide](https://teenage.engineering/guides/ep-133/how-to)
for 12T through loc, a third-party manual ([gabrielroth.com/ko2](https://gabrielroth.com/ko2))
for codes 318–319, and TE's [2.5 notes](https://teenage.engineering/guides/ep-133/whats-new)
for BLU, H.MI and M.MI.

Byte 223 holds the root as a pitch class, C = 0 … B = 11 (measured: C = 0,
D = 2, G = 7). The octave shown with it (C3, D3) is not stored.

## Fader parameters

Used by fader bases, fader assignment and automation records:

| Index | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fader | LVL | PTC | TIM | LPF | HPF | FX | ATK | REL | PAN | TUNE | VEL | MOD |

## Method

The backup checks are offline and read-only: unpack each `/projects/PNN.tar`
from the backup, parse TAR headers, and test each field's size and range
against the tables above. No archive was written to a device.

---

Field meanings in this file are adapted from
[kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex),
Copyright (c) 2026 Kevin Morrill, under the MIT License
([full text](LICENSE-ep-series-sysex.txt)).
