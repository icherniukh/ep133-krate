# EP-133 errors and recovery

How the device reports failures over SysEx, the firmware error signatures
known so far, and how to recover. Signatures and causes come from the bench
incidents of [kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/errors.md)
(MIT; notice at the end) unless tagged **tool** (Sample Tool code) or
**krate** (Krate captures).

## Two kinds of failure

| | Error reply | Firmware log frame |
|---|---|---|
| Shape | normal reply, status byte ≠ 0 | `F0 00 20 76 <product> 33 <ASCII text> F7` |
| Body | ASCII reason, e.g. `invalid id`, `invalid area`, `can only create files`, `failed to delete` | log line, e.g. `main[331]: err pattern 187 2_5_1` |
| Device state | healthy; fix the request and continue | possibly wedged |
| Action | none | stop all FILE traffic, record the frames, power-cycle |

Detect log frames by byte 5 = `33`, not by a repeated product byte: on the
EP-133 the frame starts `33 33`, on the EP-40 `3C 33`. The tool extracts the
text from byte 6 to the byte before `F7` (tool).

Status codes are listed in [PROTOCOL.md](../PROTOCOL.md#reply-status-byte-9).
The tool treats `64` (IN_PROGRESS) as "keep waiting" and anything else
non-zero as an error (tool). Every reply in the 2.5.1 backup capture had
status 0 (krate).

## Signatures

| Signature | Firmware | Cause | Rule |
|---|---|---|---|
| `err pattern 71` | 2.5.1 | pattern header byte 0 ≠ 0; write aborted, FILE layer wedged | keep header byte 0 at 0 |
| `err pattern 187` | EP-133 2.5.1 | a scene with a zero group reference (`[1,0,0,0]`), or a written scene referencing a missing pattern | every defined scene references a pattern in every group |
| `err pattern 213` | EP-40 2.5.1 | EP-40 form of the same scene rule | same |
| `ERR PATTERN 189` | UI | 27-byte pad records at scene changes (upstream); most records a 2.5.1 device returns are 27 bytes, provenance unknown ([project-format.md](project-format.md#pad-record--padsgpnn)) | unresolved |
| `ERR CLOCK 43` | UI, fatal | a `settings` member built from scratch; needed a flash format | copy a device-written member |
| `err fader 93` | 2.5.1 | automation values above 32,767 | clamp to 0–32,767 |
| `err scene 109` | 2.0.5 | incoherent scene, pad or pattern references; TE's 2.5 notes fix a crash with this code when switching projects | keep references consistent |
| `err scene 156` | 2.5.1 | unused scene chunks with zeroed `04 04` | keep `00 00 00 00 04 04` |
| `err lfs 6327` | 2.0.5 | two FILE sessions at once, even read-only | one FILE client at a time |
| `err 82`, `err 8200` | 2.0.5, 2.5.1 | client-side session damage: status byte decoded as Packed7, reads past the end, retries after partial streams, overlap; also the first PUT after a killed GET | exact-size reads, no overlap, power-cycle after an abandoned stream |
| silence, no error | 2.5.1 | project assigns slots missing from `/sounds` | upload sounds before the project |

Notes from upstream's incidents:

- **Validation happens twice.** A write to the active project is checked
  when it commits; a write to another project is checked when that project
  is activated. Byte-exact readback does not prove a project will load.
- **The error can persist.** If the broken project is the active one, the
  device can boot back into the error loop, which is why some incidents
  needed a flash format. Test writes on a spare, inactive project.
- **Reads after an interrupted GET can look fine.** INIT, LIST, STAT and
  metadata worked, and then the first PUT open failed with `err 8200`.
- **Check for a log loop before writing.** Upstream listens passively for
  about 1.2 s and refuses to start if log frames arrive.

## Recovery

1. Error reply: fix the request.
2. Log frames or an error loop: stop, power-cycle, then check the project
   with read-only reads before any write.
3. A project that stays broken after a power-cycle: flash format, restore
   from a `.pak`, re-upload sounds. A format also resets system settings.

Krate's own observation: after a normal power cycle on 2.5.1, the device
answered again and its 458-sound inventory matched the backup (krate).

---

Signatures, causes and recovery steps are adapted from
[kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex),
Copyright (c) 2026 Kevin Morrill, under the MIT License
([full text](LICENSE-ep-series-sysex.txt)).
