# EP-133 OS 2.5.1: evidence and impact on krate

Research date: 2026-11-10. Repository baseline: `40359e000484885e46b3402c0bf3eccb6e576825`.

## Executive assessment

**The main sample-management protocol still works, but successful PCM roundtrips do not establish safe preservation of a musical project.** The largest actionable risks are existing channel/metadata handling and transfer/session validation—not evidence that 2.5.1 requires a protocol rewrite.

OS **2.5** is the substantial feature release; **2.5.1** is its three-fix follow-up. We have no controlled pre-2.5 device/firmware comparison. Do not label every discovered defect a new firmware regression.

This research used official documentation, two Sample Tool artifacts, the saved official backup, recorded traffic, offline execution of current code with archived data, host USB-audio enumeration, and bounded read-only device queries. **No content writes, restore, firmware update, or abort/recovery experiments were performed in this research phase.** Earlier authorized hardware tests are a separate phase.

## Evidence inventory

Local evidence directory, abbreviated **E** below:

`captures/firmware-2.5.1-20261110T084539Z/`

| Evidence | Identity / location | What it establishes |
|---|---|---|
| Official downloads | <https://teenage.engineering/downloads/ep-133>; `E/research/official/downloads.{html,txt}` | Latest listed version, dates and maintenance fixes |
| Official full release notes | <https://teenage.engineering/guides/ep-133/whats-new>; `E/research/official/whats-new.{html,txt}` | Documented OS 2.5 features and behavior changes |
| Official current Sample Tool | `E/ep-sample-tool/assets/index-mzHAnDsS.js`; SHA-256 `ad10f8c52b03f1a94bc341321c53719ef8894f5be3add3e9f8b73dd6d530f847` | Static protocol, export and UI contracts; not firmware source |
| Installed offline Sample Tool | `/Applications/EP-133 Sample Tool.app/Contents/Resources/app.asar`; SHA-256 `e779061c694b3b92f909620b927b5213ab00825823946a27de8f3bc895c50fdb` | A second implementation artifact; wrapper version 1.2.0, not a known pre-2.5 firmware control |
| Official backup | `~/Downloads/EP-133_<serial>_2026-11-10_backup.pak`; SHA-256 `d9b5bde19467433309bbf20ea5ab408a4eb219787a2950f1967502eace9bbb1a` | Saved earlier sample PCM, represented settings and nine project TARs |
| Passive RX | `E/official-backup-passive-20261110T095111Z.jsonl`; SHA-256 `ad40f4fdd1c290648a4cae36f607296a104194606afce1fd35fe7883fa270a80` | 155,240 observed device replies |
| Passive TX | `E/official-backup-tx-spy-20261110T095310Z.jsonl`; SHA-256 `94f2cec781d78c62ca27414840eb0e9e531e43e8ffc0cb0c7c3c5bff0b1d4f02` | 104,517 observed outgoing frames |
| Earlier hardware validation | `E/validation-report.md`, retained XML/JSON results | Passing tested workflows and known failures on 2.5.1 |

Captures began mid-backup; TX began later than RX. The capture is not a complete startup/project-backup trace. Although the TX format permits packet fragments, every actual TX record in this recording contains a complete SysEx frame. Originals were not modified.

## 1. What officially changed

### OS 2.5.1 — 2026-07-03

The downloads page explicitly lists:

> “fix: crash when cropping long samples.”
>
> “fix: GROUP+PAD shortcut broken in TEMPO.”
>
> “fix: choppy USB audio when streaming from android devices (e.g. Pixel 9).”

These notes do **not** claim a wholesale file-protocol change. Our earlier project-download error is not demonstrated to be the same defect as the crop crash.

### OS 2.5 — 2026-06-24

The full notes say:

> “ko2 supports stereo audio in, as both a sample source and an audio source. as well as usb audio out”
>
> “now you can record mono samples up to 40 seconds long.”
>
> “fix: Sample trim points preserved when exporting/re-importing via EP SAMPLE TOOL.”
>
> “fix: Crash when transferring samples via EP Sample Tool with unstable USB connections.”

Other documented changes with product implications:

- Sample reverse through SOUND EDIT → TIM → REV.
- Lo/Mid/Hi recording rates, listed numerically as 26,250 / 32,000 / 46,875; the guide inconsistently spells the units `khz`. Treat these as advertised audio-rate settings, not newly measured limits. Lower-rate import was already documented in OS 2.0.
- Equal-length autochop, an arpeggiator, improved timestretching and playback-position display.
- Destructive on-device crop to trim points; fixes for disk-full handling and uploads while in SAMPLE mode.
- Scale and key saved per project; new scales and per-pad pattern copying/time shifts.
- CC64 sustain for Key/Legato voices; CC12/13 FX controls; MIDI identity over TRS; sync, SPP and stuck-note fixes.
- Improved transfer reliability/audio pops, firmware-update transfer robustness and battery-dip handling.

For krate, the important distinction is **preserving new musical settings** versus merely moving PCM. Sequencer/MIDI performance features are not automatically new sample-file commands.

## 2. Confirmed live capabilities—and snapshot boundaries

A successful read-only metadata GET for `/sounds` (node 1000) returned:

```json
{
  "max_capacity": 62853120,
  "free_space_in_bytes": 28418940,
  "formats": [{"type":"pcm","formats":[{
    "samplerate.range":[1,65535],
    "samplerate.native":46875,
    "channels":[1,2],
    "format":["s16"]
  }]}]
}
```

Evidence: `E/research/sounds-root-metadata.json` and `sounds-root-metadata-wire.jsonl`.

This establishes what this unit **advertises**, not that every rate in the range has been upload/playback tested. Our hardcoded 46,875 Hz ceiling is stricter than that advertised range; do not change conversion policy without bounded acceptance tests. Current 128 MB marketing must not be interpreted as a firmware upgrade doubling this older unit's storage.

macOS independently enumerated EP-133 as USB audio with **two inputs, two outputs and a current 48,000 Hz host audio rate**. Evidence: `E/research/host-usb-audio.json`. USB stream rate and native sample-file rate are different capabilities; this is not an audio-quality, supported-rate-list, roundtrip-latency or Android-stability test.

**Snapshot warning:** a later complete, successful read-only listing contains **467 samples / 33,328,330 logical bytes**, not the earlier 458-sample snapshot. It has 135 added slots, 126 absent old slots, and 332 changed shared entries. Evidence: `E/research/current-inventory-delta.json`. The cause/timing is unknown; no content-write commands were issued in this research. Do not attribute these differences to firmware or infer compression/deduplication from unlike snapshots. The verified backup is a snapshot of the earlier library, not a claim about the current library. Do not restore it automatically.

## 3. Backup: strong content evidence, bounded settings guarantees

Independent stdlib checks passed:

- **468 ZIP entries:** 458 WAVs, nine project TARs and `/meta.json`; ZIP CRCs valid, no duplicate filenames/slots.
- Sample slots exactly match saved inventory and metadata. **58,493,926 decoded PCM bytes**; all 458 size/CRC32/channel/rate/format checks match.
- Formats: 344 mono/46,875 Hz, 50 mono/44,100 Hz, one mono/22,050 Hz, 37 stereo/46,875 Hz and 26 stereo/44,100 Hz. All signed 16-bit PCM.
- P01–P09 have valid TAR headers, payload bounds and zero terminators. Across nine projects: 788 members, 734 regular files, 54 directories; 48 pad files per project and 276 pattern files total. No links, unsafe TAR paths or duplicate members were found.
- WAVs contain `smpl` and `LIST/INFO/TNGE`, not only audio. **4,805 represented TNGE field comparisons match** the saved metadata.

Limits:

- Restore was **not** performed. Structural/content verification is not proof of successful restore or every musical setting's fidelity.
- The original full project trees were not independently saved before backup; TAR parseability cannot prove all project semantics. P08 lacks `fx_settings`, unlike the other eight; whether that is expected is unknown.
- `sound.bars` is not explicitly represented in TNGE, including six samples whose saved value is 2 or 4. The 21 ACID tempos match saved BPM, but ACID beat fields are zero. Bar-count reconstruction/fidelity is unproven.
- Forty-seven saved empty names become `sample` filenames; exact empty-name roundtrip is unproven.
- Provisional pad-reference decoding surfaces slots absent from both the archive and pre-backup inventory. That is not evidence the backup lost existing samples or that firmware introduced broken references.

Reproducible audit: `E/research/backup/verify_backup.py`; results: `backup-verification.json`. The original `.pak` hash remained unchanged.

## 4. Our most important correctness problems

### Known mono metadata is overridden

Current `src/core/client.py:547–549` re-runs `detect_channels()` even when mono metadata is known. Of the backup's **395 known-mono samples, 26** are classified as stereo by that heuristic.

An offline execution of the actual `EP133Client.get()` with only I/O replaced by archived-data functions reproduces slot 3:

| | Source | Current GET output |
|---|---:|---:|
| Channels | 1 | 2 |
| Rate | 46,875 | 46,875 |
| Frames | 4,092 | 2,046 |
| PCM bytes | identical | identical |

This changes channel/duration semantics while a PCM-only test still passes. It is an existing implementation defect observed using 2.5.1 data, **not a proven new firmware regression**. Evidence: `E/research/backup/current-get-reproducer.json`. Issue: **ko2-tools-known-mono-export**.

### Re-upload workflows rebuild rather than preserve musical settings

`get()` writes PCM-only WAV; `put()` generates fresh metadata, including:

> `"sound.playmode": "oneshot"` … `"sound.rootnote": 60` … `"time.mode": "off"`

Shared copy/move/swap/squash (`src/core/ops.py`) and CLI/TUI optimize paths carry name/audio but not the original playback/edit metadata. An offline comparison finds default differences for playmode in 74 samples, root note in 82, amplitude in 96, pitch in nine, release in 58 and attack in two. Loop defaults differ for 317 eligible samples; a difference in loop sentinel values is not automatically an audible change in every play mode.

The official exporter, by contrast, explicitly retains:

> `"time.mode","sample.start","sample.end","sample.mode","regions"`

This matters more as users use reverse, trim, timestretch and slicing. All saved `time.mode` values in this backup are `off`, so preservation of actual reverse settings has not been tested. The earlier default/sine-based copy tests did not cover this contract. Issue: **ko2-tools-sample-metadata-fidelity** (P0).

### Metadata SET and name contracts

Earlier real-device probes established:

- Intended pitch/pan/amplitude patches succeed directly, but `update_slot_metadata()` fails after merging the full readback dictionary.
- Unchanged `format`, `crc` and BPM=0 values were individually rejected; a full object excluding these three was accepted. Do not call all BPM values unsupported: the official validator accepts BPM 60–180.
- Direct custom `krate.fp.v` is rejected. Patch-only SET does not by itself enable custom fingerprint persistence. Keep local fingerprints separate; JSON output currently hides the warning.
- ASCII renames of length 16 succeed; tested longer values fail. The official tool caps names to 16 using its own shortening policy. Unicode/byte-limit semantics remain unverified.

Issues: **ko2-tools-fw251-metadata-write**, **ko2-tools-fw251-rename-limit**.

## 5. What the official wire recording proves

`E/research/wire/analyze.py` replays offline with self-tests and accounting assertions. It matches **104,516 unique request/reply pairs**, with no ambiguous primary matches, using full 12-bit IDs and a bounded callback-time window.

| Contract | Observed evidence | Current implication |
|---|---|---|
| Header byte 6 | Flags + request-ID high five bits; byte 7 is low seven bits. IDs increment modulo 4096 | `SysExCmd` opcode names obscure framing; current matcher omits the low ID bits. Fixed valid request IDs are not inherently wrong |
| GET INIT | Eight decoded bytes: `03 00 node_BE16 offset_BE32` with zero offsets observed | Current request has nine bytes. Rejection of the extra zero is not demonstrated |
| GET DATA | `03 01 page_BE16`; reply echoes the same two bytes, including pages 128 and 256 | Current U14LE representation differs. Sequential/opaque echo versus true random-access semantics remain unresolved; passing helper transfers are not disproved |
| INIT reply | Node BE16, observed flags `1d`, size BE32 at `[3:7]`, filename/padding | Current magic-prefix assumption is wrong for these replies, but its active fallback extracts correct sizes for all 240 observed INITs |
| Metadata | 699 real continuations plus 118 one-page JSON objects; all echoes match | The comment claiming repeated page zero is contradicted. Actual core paging works on this trace but should validate echo/termination instead of tolerating truncation |
| Normal file-to-file sequence | 237 transitions: data → two metadata reads → next GET INIT, no full reinitialization | Can inform safe optimization; does not prove GET→DELETE or directory-abort recovery works without reset |
| Transfer size/status | All recorded statuses zero; ordinary content chunks 324 bytes, variable final chunk | These are observed negotiated sizes, not universal constants. Current code must still fail closed on errors/short reads |

There are 50,724 unmatched RX frames and one unmatched TX. Most RX predates TX capture. One matching-ID/page candidate has −13.007 ms callback timing and remains excluded from the primary −10 ms tolerance; widening to −20 ms adds exactly that candidate. Thus 237 ordinary transfers fully correlate, with one ordinary transfer excluded from a full-size match because of timing—not proven device truncation. Two extended reads also complete.

Observed ordinary payload throughput is about **136.7 kB/s over 242.626 seconds**, including inter-file metadata, for the captured segment. Do not present that as a universal benchmark.

Source gaps remain even though these captures succeed: status checks, full request correlation, exact completion checks, fail-closed directory enumeration, page echoes, negotiated limits and cancellation/session state. Issue: **ko2-tools-transfer-integrity-correlation**.

## 6. Native waveform preview is a concrete opportunity

The current official app calls `iterDownloadSoundPreview` with extra GET args:

`[1, stride_BE16, bin_count_BE16]`, after eight additional zero bytes.

Two captured 21-byte INITs for node 12 use stride 6/count 2000 and return **8,000 bytes each in 25 data replies**, versus that sample's 25,050 raw PCM bytes. Both preview payloads have the same hash. The official consumer interprets interleaved signed-16 min/max pairs; all 2,000 pairs in each recording are ordered min≤max.

A simple contiguous six-frame min/max computation does **not** match these values exactly; the precise device reduction/normalization algorithm is not established. Use the observed format, not an invented averaging algorithm. Compact previews are not raw PCM and cannot supply a PCM fingerprint.

This is a practical way to replace full-PCM waveform downloads in the TUI/shared workflow, retaining full transfers only where audio/hash is needed. It is not established as newly introduced by 2.5.1. Evidence: `E/research/wire/preview-pcm-comparison.json` and static `preview_consumer` excerpt. Investigation: **ko2-tools-qqc**.

## 7. Static capabilities beyond our current implementation

Exact source excerpts and 14 compared repository hashes are independently verified in `E/research/app/static-source-evidence.json`.

- Official requests correlate full IDs and handle in-progress statuses.
- FILE INIT returns a chunk size; uploads derive payload size, await chunk responses, and support paged metadata SET. Our fixed 433-byte pipeline does not check each ACK status. Backup traffic does not validate uploads or justify switching strategy blindly.
- File flags expose read/write/delete/move/playback capabilities. Do not assume every listed node is writable or removable.
- Direct move exists: `0C + file_BE16 + parent_BE16 + new_file_BE16`. It may avoid audio/metadata roundtrips; occupied-destination swaps, pad-reference rewriting and timeout outcomes need validation before adoption.
- Official trim UI writes frame-index `sample.start/end` on a **project pad**. Do not confuse that with destructive crop or global sample metadata.
- `/sounds` capacity/formats are available now; CLI's fallback and TUI's hardcoded 64 MiB are not device capability discovery.

### Version-comparison limit

Nine selected protocol classes from the installed offline app and current app have matching components for **15 normalized static function fingerprints**. Their original byte ranges/hashes are retained. This supports continuity for those selected serializers—not whole-app equivalence or a historical firmware A/B.

REA whole-bundle analysis hit its 90-second per-source timeout; partial inventory Evidence was retained. Narrow, provenance-linked extracts analyzed successfully:

- Installed extract: `ev_6fb2b850a3d23b6003386df84614763970af7a797ae85b61f62242d28614a89b`.
- Current extract: `ev_1f7c29639d4cc6fed95ae9fd24a15aaa1f38edf542b4740d66373c82eae6e14d`.

Static unknowns remain; fingerprint equality is not a runtime guarantee. The generic module comparison did not align the derived modules, so its added/removed nodes are not product-feature findings. Direct source excerpts are ordinary artifact evidence, not falsely attributed REA decompilation.

## 8. Impact by layer and recommended order

| Layer | Impact and next boundary |
|---|---|
| Transport | Keep MIDI I/O platform-specific and protocol-neutral. USB audio enumeration is a separate capability, not permission to replace the MIDI transport |
| Protocol/session | Own request IDs, framing, status, paging, capabilities, completion and validated recovery centrally in core |
| Shared workflows | Preserve metadata/format/project semantics through copy/move/optimize; separate preview from full-audio download and hashing |
| CLI | Correct GET format, metadata warnings, capacity and broken `group` dispatch; preserve output modes and nonzero error contracts |
| TUI | Consume the shared fixes; use realistic operation-completion waits and compact previews instead of blocking full-library PCM work |
| Native app | `src/app/app.py` still has a stub `connect_device`; active `DeviceTab` uses placeholder rows/statistics. Core/TUI tests do not establish native app readiness. Wire the shared workflows rather than copying TUI session logic |
| Debug surface | Make trace/evidence/capability inspection visible through the same shared protocol/workflow boundary |

This follows [ARCH-002](architecture/ARCH-002-app-first-core-ui.md). No large transport rewrite or new platform-specific protocol copy is justified.

Recommended order:

1. Protect metadata and known channel/format fidelity; avoid mutating existing user samples until these contracts and backups are addressed.
2. Make hardware tests ownership-safe, and protocol failures/cancellation explicit. Reuse bounded captured fixtures, not valuable device content.
3. Integrate real capacity/formats and native previews; retain local fingerprinting.
4. Validate direct move and archive completion semantics safely, without repeating the earlier partial directory GET/reset sequence.
5. Wire app/CLI/TUI to shared corrected workflows; then add reverse/long-sample/USB-audio product coverage.

Existing concrete issues also remain: **ko2-tools-cli-group-missing**, **ko2-tools-e2e-safety**, **ko2-tools-e2e-startup-timeout**, **ko2-tools-fw251-project-archive-error**. Firmware feature-contract follow-up: **ko2-tools-fw25-feature-contracts**. Broader boundary work remains in **ko2-tools-6kp.2** and **ko2-tools-6kp.3**. Statistics/preview investigations **ko2-tools-kt6** and **ko2-tools-qqc** are answered; implementation is tracked by **ko2-tools-device-capabilities** and **ko2-tools-native-waveform-preview**. Archive import/export remains **ko2-tools-dpp**; the verified historical backup task is closed without claiming restore success.

## 9. What remains unknown

- Controlled older-firmware behavior, binary-level firmware differences and exact cause of the earlier `err 8200` project-abort state.
- Full restore success and complete settings/project semantic fidelity; no automatic restore should be inferred from structural validation.
- Reverse/time-mode enums, full region schemas, newly long sample boundaries, disk-full/power-loss/disconnect behavior and occupied encoding boundaries.
- Direct move's project-reference and swap semantics; safe generic abort/finalization for project TAR downloads.
- USB audio quality, latency, supported host stream rates and actual Android streaming stability.
- Why the current library differs from the earlier snapshot; no causal claim is made.

The earlier 504 unit tests and 15 core hardware E2Es passed in their recorded phase. They were **not rerun as part of this research**, nor should the unsafe whole hardware suite be rerun unguarded. New offline archive/framing/packing checks passed; the actual-GET offline reproducer confirmed the known-mono defect. No production fix or new all-protocol compatibility certification is claimed.

The `.pak` remains in Downloads and most raw evidence is gitignored; this report and `INBOX.md` are not substitute backup copies. Keep the archive and captures before cleaning local data.
