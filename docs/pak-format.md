# EP-133 backup files (`.pak`, `.ppak`)

The official Sample Tool saves backups as ZIP files. A `.pak` is a whole
device; a `.ppak` is one project with the sounds it uses. Project members
are described in [project-format.md](project-format.md) and sound files in
[sound-format.md](sound-format.md#wav-files-in-backups).

Tags: **backup** = checked against an EP-133 OS 2.5.1 user backup made by
the official tool (kept local); **tool** = read from the tool's code;
**upstream** = [kmorrill/ep-series-sysex](https://github.com/kmorrill/ep-series-sysex/blob/main/docs/pak-container.md).

## Layout

```text
/meta.json
/projects/P01.tar … /projects/P09.tar
/sounds/001 afterparty kick.wav
/sounds/246 toaster bell.wav
…
```

- Entry names start with `/`. Upstream reports that the tool shows
  `PAK FILE IS EMPTY` when the slash is missing.
- Sound entries are `/sounds/<slot, three digits> <name>.wav`. The tool's
  importer matches `/sounds/NNN <anything>.wav` (or `.json`), groups by slot,
  and uses the WAV (tool).
- Project entries are `/projects/PNN.tar`, the device's TAR unchanged: the
  tool writes the GET bytes straight into the ZIP (tool).
- The importer also accepts `/projects/PNN/<A-D>/pads.json` next to a TAR
  and parses it as JSON, but this tool version does not apply it (tool).

The 2.5.1 user backup holds `meta.json`, all nine project TARs and 458
sounds, and nothing else: no system settings (backup).

## `meta.json`

```json
{
  "info": "teenage engineering - pak file",
  "pak_version": 1,
  "pak_type": "user",
  "pak_release": "1.2.3",
  "device_name": "EP-133",
  "device_sku": "TE032AS001",
  "device_version": "2.5.1",
  "generated_at": "2026-11-10T09:49:50.051Z",
  "author": "computer",
  "base_sku": "TE032AS001"
}
```

| Field | Source | Notes |
|---|---|---|
| `pak_type` | `user` for a device backup, `project` for a `.ppak` (tool) | Factory packs use `factory` (upstream) |
| `pak_release` | fixed `1.2.3` in this tool version (tool) | upstream saw `1.2.0` and, in a factory pack, `1.1.0` |
| `device_name`, `device_sku` | the connected device | |
| `device_version` | GREET `os_version` | the reliable firmware stamp; the MIDI identity reply has no version |
| `generated_at` | ISO time of the backup | |
| `author` | `computer` | |
| `base_sku` | GREET `base_sku`, only when present | |

## File names the tool uses

| Backup | File name (tool) |
|---|---|
| Whole device | `<device name>_<serial>_<YYYY-MM-DD>_backup.pak` |
| One project | `<device name>_<serial>_<YYYY-MM-DD>_P<N>_backup.ppak` |
| Several projects | each `.ppak` inside `<device name>_<serial>_<YYYY-MM-DD>_projects.zip` |

A device backup includes all nine projects, empty ones too. A project-only
backup skips empty projects and stops with "nothing to backup - all
projects are empty" when none has content (tool). The file name carries the device serial; strip it before sharing a
backup.

## Restore

The tool uploads a project TAR with PUT (flags `06`, parent `/projects`,
15 s timeout) and then INIT; sounds go through the normal sound upload path,
including the conversion described in
[sound-format.md](sound-format.md#upload-conversion-in-the-official-tool)
(tool). Upstream lists open acceptance questions: which `pak_type` each
import path takes, compression and entry order, timestamps and SKU checks.
