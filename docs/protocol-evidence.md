# EP-133 protocol evidence and firmware coverage

## Operation coverage

This inventory counts **15 named EP-133 operations**. Its scope is the
operations listed in the matrix. Field-level and firmware-specific gaps
appear beside the relevant evidence.

- **OS 2.0.5** has local TX/RX evidence for **12 of 15** operations and an
  upstream bench report for one more.
- **OS 2.5.1** has upstream hardware evidence for **13 of 15**. Two operations
  lack an explicit 2.5.1 exchange in the sources reviewed.
- **Krate** implements **11 of 15** directly, uses **one** inside upload, and
  has no dedicated support for **three**. Generic node listing and metadata
  access can serve as building blocks for those three.

**Capture** means a checked-in EP-133 exchange from a session identified by
GREET. **Bench** means a published hardware result scoped to the version
in the column. Both refer to the variants described in the linked evidence.
Wire layouts are in [PROTOCOL.md](../PROTOCOL.md).

| Operation | EP-133 OS 2.0.5 | EP-133 OS 2.5.1 | Krate |
|---|---|---|---|
| USB MIDI identity | [Capture](../captures/sniffer-readmeta.jsonl#L3-L4) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/sysex-protocol.md#firmware-version--midi-universal-identity-request) | Startup |
| GREET product fields | [Capture](../captures/sniffer-readmeta.jsonl#L5-L6) | GREET command documented; full version-stamped reply still needed | Startup |
| FILE INIT | [Capture](../captures/sniffer-readmeta.jsonl#L7-L9) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#sub-commands) | Startup |
| FILE LIST | [Capture](../captures/sniffer-readmeta.jsonl#L8-L13) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#the-node--file-id-tree) | Generic node listing |
| METADATA GET | [Capture](../captures/sniffer-rename54-txrx.jsonl#L124-L129) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#metadata) | Generic node reads |
| METADATA SET | [Capture](../captures/sniffer-rename54-txrx.jsonl#L119-L121) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#metadata) | Generic node writes |
| Storage query | [Capture](../captures/sniffer-readmeta.jsonl#L12-L19) | [Client code](https://github.com/seajaysec/ep-unity/blob/main/web/lib/kotu.bundle.js#L767-L775) available; version-stamped exchange still needed | Live capacity and free space in `krate status` |
| FILE STAT | [Capture](../tests/fixtures/sniffer-upload-kick-official.jsonl#L466-L467) | [Bench tree walk](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#the-node--file-id-tree) | Used inside upload |
| Sample audition | [Capture](../captures/sniffer-rename54-txrx.jsonl#L117-L118) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#play--audition-0x05-0x01) | Implemented |
| Sample GET | [Capture](../captures/sniffer-rename54-txrx.jsonl#L15-L25), [whole-file excerpt](../captures/evidence-download-state-bug.jsonl#L5-L34) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#beyond-project-io) | Implemented; page encoding needs byte comparison |
| Sample PUT | [Capture](../tests/fixtures/sniffer-upload-kick-official.jsonl), [PCM byte test](../tests/unit/test_upload_capture.py) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#beyond-project-io) | Implemented |
| Sample DELETE | [Capture](../captures/evidence-download-state-bug.jsonl#L35-L38) | [Bench library flow](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#beyond-project-io). The separate wrong-payload comparison used EP-40. | Implemented |
| Project activation | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/epsysex/fileclient.py#L563-L569), [local active project readback](../tests/fixtures/sniffer-upload-kick-official.jsonl#L5-L13) | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#project-reload--activation-sequence) | No dedicated operation |
| Project TAR GET | Version-stamped exchange still needed | [Bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#reading-a-project-tar) | No dedicated operation |
| Project TAR PUT | Version-stamped exchange still needed | [Bench write, reload and playback](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/file-protocol.md#writing-a-project-tar) | No dedicated operation |

## Firmware changes from 2.0.5 to 2.5.1

| Release | Manufacturer-documented changes relevant here |
|---|---|
| **2.0.5** · 2025-12-03 | Sample Tool and MIDI fixes, audio stability improvements, and restored continuous SYNC OUT. [Official download notes](https://teenage.engineering/downloads/ep-133) |
| **2.5** · 2026-06-24 | USB audio, reverse playback, selectable recording sample rates and up to 40 seconds of mono recording. Adds TRS MIDI identity replies, sustain (CC 64) and FX control (CC 12/13). Scale and key now save per project. Teenage Engineering also reports more reliable file transfers, better trim retention on Sample Tool export/import, and a fix for a project-switch crash. [Official 2.5 release notes](https://teenage.engineering/guides/ep-133/whats-new) |
| **2.5.1** · 2026-07-03 | Fixes for cropping long samples, a tempo shortcut, and intermittent Android USB audio. The published notes give no SysEx field or opcode changes. [Official download notes](https://teenage.engineering/downloads/ep-133) |

- **USB identity** works in both versions. Both sources report zero version
  bytes. TRS identity support is new in 2.5. [2.0.5 exchange](../captures/sniffer-readmeta.jsonl#L3-L6), [2.5.1 bench](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/sysex-protocol.md#firmware-version--midi-universal-identity-request)
- **Core FILE operations** have evidence in both versions for INIT, LIST,
  STAT, metadata, audition, sample GET/PUT/DELETE and project activation.
  The GET byte-order discrepancy already occurs between two clients on the
  same 2.0.5 unit. The long 2.0.5 PLAY request and short 2.5.1 request differ
  by client and lack a same-request cross-version test. [GET and PLAY layouts](../PROTOCOL.md#file-operations)
- **Project archive compatibility is member-specific.** Upstream tested a
  2.0.5-era `scenes` member on 2.5.1 and reported silent external playback.
  The tested legacy `settings` and `fx_settings` members worked. Keep native
  templates per firmware when authoring. The `settings` tail bytes differ
  in the published corpora, but neither their meaning nor the actual
  project-scale offsets are established. [Scene transplant result](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/project-format.md#scenes-member-712-b), [Open settings fields](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/coverage.md#settings)
- **Session failures still need paired tests.** Upstream reports overlapping
  FILE operations and interrupted streams can leave device state unreliable.
  The 2.5 reliability release note does not establish which recovery
  sequences are required on 2.5.1. [Bench error observations](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/errors.md)

## Capture findings

### Download completion and recovery

The original annotations in the archived download excerpt misidentified
unsolicited events as stale GET replies. The raw bytes show the following
exchanges on OS 2.0.5.

| Capture lines | Decoded exchange |
|---|---|
| [33–38](../captures/evidence-download-state-bug.jsonl#L33-L38) | After the last GET page, DELETE slot 914 uses request bytes `7E 4C`. The device emits `0A 03 92` (FILE_DELETED), then replies `3E 4C 05 00`. The next event is updated free space on `/sounds`. |
| [95–100](../captures/evidence-download-state-bug.jsonl#L95-L100) | DELETE slot 700 uses `7E 60`, emits `0A 02 BC`, and receives matching success reply `3E 60 05 00`. Another free-space update follows. |
| [114–118](../captures/sniffer-rename54-txrx.jsonl#L114-L118) | The official tool receives page 49, finishing a 16,000-byte preview. It immediately sends PLAY and gets status zero without an intervening INIT. |

### Storage measurements

Three reads in the metadata capture return **62,853,120 bytes capacity** and
**2,856,216 bytes free**. Another session after upload reports the same
capacity and **6,661,776 bytes free**. These are measurements of one device,
with free space changing across sessions.
[Repeated reads](../captures/sniffer-readmeta.jsonl#L12-L19), [Post-upload exchange](../tests/fixtures/sniffer-upload-kick-official.jsonl#L477-L479)

GREET `sku` identifies the hardware revision. Krate's 2.0.5 capture shows
`TE032AS001` (64 MiB), and ep-unity reports hardware testing on `TE032AS002`
(128 MiB). That project also uses `/sounds` for sample capacity. Its published
report gives the board sizes, while a firmware-stamped 128 MiB reply with the
exact `max_capacity` value remains open.
[Krate GREET](../captures/sniffer-readmeta.jsonl#L5-L6), [ep-unity hardware report](https://github.com/seajaysec/ep-unity/blob/main/README.md#two-skus-board-revision-and-firmware-lineage)

### Pad assignment and trim

On 2.0.5 the official tool selected pad node 9502 with `active` on group
node 9500, assigned slot 74 with `sym`, then changed `sample.start` from 0 to
2318 while `sample.end` stayed at 8006. A second capture associates Group D
pad label `6` with node 9506 and assigns slot 53. The dated Group A capture
covers all 12 nodes. Bare SysEx dumps show active nodes 9302, 9308, 9309 and
9311 for Group B, and 9402 and 9411 for Group C. Firmware is untagged in those
dumps. The original notes identify physical labels `8` and `0` in both.
[Pad 8 trim edits](../captures/sniffer-padtrim.jsonl#L141-L144), [Pad 6 assignment](../captures/sniffer-rename54-txrx.jsonl#L5), [Group A capture](../captures/sniffer-padmap-A.jsonl), [Group B dump](../captures/sniffer-padmap-B.bin), [Group C dump](../captures/sniffer-padmap-C.bin)

### Metadata audit

The February 20 audit compared filenames from LIST, node metadata, and
Krate's older query path. The recorded stale counts were 3 for slots 1–99
and 57 for slots 100–199. Name differences were 37 and 22 respectively.
Firmware is untagged in the exports. The counts describe those two audits.
[Slots 1–99](../captures/2026-02-20-audit-001-099.jsonl), [Slots 100–199](../captures/2026-02-20-audit-100-199.jsonl)

## Gap matrix

How Krate's reference compares with upstream and the Sample Tool. **2.0.5**
and **2.5.1** mean a Krate capture on that OS; the tool column names the
Sample Tool class or function the claim comes from.

| Item | Upstream (ep-series-sysex) | Sample Tool | Krate evidence | Status |
|---|---|---|---|---|
| Status codes other than 0 | non-zero = ASCII reason | `1`–`3`, `16–63`, `≥64`, `64` IN_PROGRESS | only 0 seen | tool |
| Commands ECHO, DFU, PRODUCT_SPECIFIC | — | declared; only DFU enter/exit is sent | — | tool |
| SKU in MIDI identity reply | version bytes zero | `parseIdentity`: bytes 8–11 | `TE032AS001` on 2.5.1 | 2.5.1 |
| Client timeouts, IN_PROGRESS | — | 20 s reply, 2 s probe, 15 s project PUT | — | tool |
| Minimum firmware per SKU | — | `validateDeviceVersion`: 2.0.5 for `TE032AS001` | — | tool |
| Pad numbering in TARs | contradictory ("bottom-up" vs calibrated table) | — | key 8 → N = 2, key 6 → N = 6; same slots and trim found in P07 `d/p02`, `d/p06` | 2.0.5 + backup |
| Pad trim bytes 4–11 | start, length | — | 2318 and 5688 = 8006 − 2318 | 2.0.5 + backup |
| Pad record size | 26 native, 27 tool | — | 423 of 432 device-returned records are 27; provenance unknown | 2.5.1 backup |
| Pad byte 25 | 255, padding | — | 0 in 425, 1–2 otherwise | 2.5.1 backup |
| Automation byte 7 | 0 on EP-133 | — | 106–255 | 2.5.1 backup |
| Note duration limit | 1 bar | — | up to 839 ticks | 2.5.1 backup |
| INIT flag bit 0 | read/write | `TE_SYSEX_FILE_INIT_SUBSCRIBE` | flags `01`, events arrive | conflict |
| INIT reply leading byte | "flags-ish" | not parsed | `0C` | open |
| GET open, whole file | same 8-byte form | `SysExGetFileInitRequest` | 8-byte form on 2.5.1 | 2.5.1 |
| GET page encoding | BE16 | BE16 | BE16, pages from 0, 324 bytes (2.5.1) | 2.5.1 |
| Waveform preview | — | `iterDownloadSoundPreview` | open form on 2.0.5; point decimation on 2.5.1 | 2.0.5, 2.5.1 |
| PLAYBACK layout | `05 01 fid`, suffix unknown | `SysExFilePlaybackRequest`: action, offset, length; STOP = 2 | long form on 2.0.5; START/STOP pair in a local capture | wire; `length` unit open |
| MOVE `0C` | inventoried, payload unverified | `SysExFileMoveRequest` | — | tool |
| Paged METADATA SET `07 04` | — | `SysExFileSetMetadataPaged*` | — | tool |
| Node flag bits | `05` READ\|FILE, `06` READ\|DIR | type and capability bits | `0E`, `1D` on the wire | 2.0.5, 2.5.1 |
| FILE_ADDED body | event code only | parser reads one byte late | `fid flags size name` | 2.0.5 |
| Sound node names | — | — | `NNN.pcm` | 2.0.5 |
| Slot metadata keys | 19 | validators, WAV export list | 17 on 2.0.5, 19 on 2.5.1 | 2.0.5, 2.5.1 |
| `crc` | read-only | passed through | CRC-32 of PCM, computed by device | 2.0.5, 2.5.1 |
| `formats` and target rate | — | `getTargetSampleRate` | same reply on 2.0.5 and 2.5.1 | 2.0.5, 2.5.1 |
| Value ranges | amplitude 0–100, bpm 1–200 | import checks 0–200, 60–180 | — | conflict |
| Backup WAV chunks | `smpl`, `LIST/INFO/TNGE` | `createWav` | plus `acid` when BPM is set | 2.5.1 backup |
| Settings byte 220 | disputed | — | swing 0–12 = 50–75: 50 → `00`, 60 → `05`, 65 → `07`, 75 → `0C` | 2.5.1 |
| Settings byte 221 | disputed | — | scene length, stored as displayed (12, 11) | 2.5.1 |
| Settings bytes 222–223 | — | — | scale type (blues = 10, H.MI = 11), root pitch class (D = 2, G = 7) | 2.5.1 |
| Swing scope | global, from byte-identical archives | — | project, byte 220 | refuted on 2.5.1 |
| Record quantize | — | — | global: project TAR unchanged | 2.5.1 |
| Global settings over SysEx | none | none | root, GREET, backup hold none | 2.5.1 |

## Project settings bytes

A 2.5.1 user backup (`EP-133_…_2026-11-10_backup.pak`, kept local) holds
nine project TARs. Their `settings` members, read offline:

| Project | P01 | P02 | P03 | P04 | P05 | P06 | P07 | P08 | P09 |
|---|---|---|---|---|---|---|---|---|---|
| Size (bytes) | 224 | 222 | 222 | 224 | 222 | 224 | 224 | 222 | 224 |
| BPM (bytes 4–7, f32 LE) | 90 | 128 | 115 | 170 | 130 | 120 | 170 | 110 | 115 |
| Byte 220 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Byte 221 | 2 | 4 | 4 | 2 | 2 | 1 | 2 | 1 | 2 |

Bytes 0–3 and 8–23 are zero in all nine. The 224-byte members end in two
zero bytes. P08 has no `fx_settings` member.

Controlled test on 2026-11-19 (P02, 2.5.1, local capture
`captures/swing-quantize-20261119T113024Z/`). Each step changed one thing on
the device, then P02 (fid 4000) was read with the official tool's GET
sequence and diffed against the previous read:

| Change on the device | Bytes changed in the 70,144-byte TAR |
|---|---|
| swing 65 → 50 | `settings` byte 220: `07` → `00`, nothing else |
| root note C3 → C4, record quantize off | none |
| swing 50 → 75, root note → G1, scale type changed | byte 220 `00` → `0C`; bytes 222–223 `00 00` → `03 07` |
| scale type → blues, swing 75 → 60 | byte 220 `0C` → `05`; byte 222 `03` → `0A` |
| scale type → H.MI | byte 222 `0A` → `0B` |
| root note G1 → D3 | byte 223 `07` → `02` |
| length one step down | byte 221 `0C` → `0B` |

So byte 220 is swing, 0–12 for 50–75 (25/12 per step, rounded for
display). Byte 222 is the scale type: it moved with each scale change and
reads 10 for blues. That matches the pre-2.5 system codes 310–319 (12T,
maj, min, dor, phr, lyd, mix, loc, major and minor pentatonic) as indices
0–9, with 2.5's BLU appended at 10
([scale index](project-format.md#scale-index)). H.MI read 11; M.MI = 12
is unmeasured. Byte 223 is the root pitch class: G = 7, D = 2, and
C3 → C4 left it at 0. Swing as
project state fits TE's OS 2.0.2 fix "Swing was not updated when loading a
new project". Record quantize is global. Byte 221 is the length setting (how long the
scene runs): it holds the displayed value, 12 → 11 when the display went
from 12 to 11. Some edits reached the TAR only on a later read, two
reads after they were made, so a save delay can hide a change. P02's fader assignments (bytes 216–219) read 0 = LVL,
matching the device's LEVEL setting. Bytes 8–23, upstream's other candidates, are zero in all nine projects
here.

The same session found no SysEx event for any of these changes: after a
FILE INIT, the device sent nothing while swing, root note and projects were
changed or pads pressed.

## Preview decimation

The 2.5.1 backup capture contains two extended GETs of slot 12 (mono,
12,525 frames, stride 6, 2,000 points, 8,000 bytes). Decoding the preview as
s16 little-endian gives 4,000 values in 2,000 equal pairs, and each pair
equals the backup PCM at frame `6 × k` for all 2,000 points. Other offsets
match 2–5% of points, as chance would. Min/max over each six-frame window
matches none.

## Third-party sources

| Source | Evidence to reuse |
|---|---|
| [kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex) | Best lead for shared 2.5.1 device fixtures. EP-133 and EP-40 hardware work covers project TAR I/O, pad mapping, FILE behavior, and measured playback. [Test method](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/hardware-testing.md), [Coverage and provenance](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/coverage.md) |
| [phones24/ep133-export-to-daw](https://github.com/phones24/ep133-export-to-daw) | Independent AGPL-3.0 WebMIDI codec for checking GET, STAT and LIST. Supports EP-133, EP-1320 and EP-40. [FILE codec](https://github.com/phones24/ep133-export-to-daw/blob/main/src/lib/midi/fsSysex.ts) |
| [seajaysec/ep-unity](https://github.com/seajaysec/ep-unity) | Bundled Kotu client independently points to `/sounds` metadata for storage. [Storage query](https://github.com/seajaysec/ep-unity/blob/main/web/lib/kotu.bundle.js#L767-L775) |
| [ZacharySBrown/ep133-ppak](https://github.com/ZacharySBrown/ep133-ppak) | Complementary MIT archive and pad-record tooling. Reports 2.0.5 sample-mode hardware validation and credits Krate for prior SysEx research. [Prior work and test status](https://github.com/ZacharySBrown/ep133-ppak#building-on-prior-work) |
| [trusch/ko2-io](https://github.com/trusch/ko2-io) | Rust CLI, FUSE and project editor. Its FILE implementation follows ep-series-sysex. Useful for comparing end-to-end behavior. [FILE client](https://github.com/trusch/ko2-io/blob/main/src/fileclient.rs) |
| [propann/EP-133-KO-II-Studio](https://github.com/propann/EP-133-KO-II-Studio) | Companion app built on epsysex. Reports a real-device clone and checksum-verified inventory for nine projects and 527 sounds. Candidate for exchanging workflow fixtures. [Clone results and bridge](https://github.com/propann/EP-133-KO-II-Studio/blob/main/README.md#clone--biblioth%C3%A8que-sonore) |
| [wmealing/KO2-SYSEX](https://github.com/wmealing/KO2-SYSEX/blob/main/SAMPLE-TOOL-START.md) | Independent OS 1.1.2 startup capture for historical GREET, INIT and root LIST. |
| [garrettjwilke/ep_133_sysex_thingy](https://github.com/garrettjwilke/ep_133_sysex_thingy) | Pre-2.0 `.syx` examples for playback, upload, delete and switching. |
| [abrilstudios/rcy](https://github.com/abrilstudios/rcy/issues/179), [benjaminr/mcp-koii](https://github.com/benjaminr/mcp-koii/blob/main/TECHNICAL_REFERENCE.md) | Earlier sample-upload tooling and adjacent MIDI note-to-pad reference. |
