# EP-133 protocol evidence and firmware coverage

## Operation coverage

This inventory counts **15 named EP-133 operations**. Its scope is the
operations listed in the matrix. Field-level and firmware-specific gaps
appear beside the relevant evidence.

- **OS 2.0.5** has local TX/RX evidence for **12 of 15** operations and an
  upstream bench report for one more.
- **OS 2.5.1** has upstream hardware evidence for **13 of 15**. Two operations
  lack an explicit 2.5.1 exchange in the sources reviewed.
- **Krate** implements **10 of 15** directly, uses **one** inside upload, and
  has no dedicated support for **four**. Generic node listing and metadata
  access can serve as building blocks for those four.

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
| Storage query | [Capture](../captures/sniffer-readmeta.jsonl#L12-L19) | [Client code](https://github.com/seajaysec/ep-unity/blob/main/web/lib/kotu.bundle.js#L767-L775) available; version-stamped exchange still needed | Estimated in CLI |
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
