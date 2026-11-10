# ep133-krate

Manage samples on your Teenage Engineering EP-133 KO-II from your computer — no official app required.

`krate` connects to the EP-133 over USB and lets you upload, download, rename, move, copy, and delete
samples from the command line or a terminal UI. It also optimizes audio files to the device's native
format, and can compact fragmented slot layouts automatically.

> **Note:** The device protocol is reverse-engineered. Most operations work reliably, but behavior
> may vary across firmware versions. See [PROTOCOL.md](../../PROTOCOL.md) for the full specification.

---

## Requirements

- Python 3.11 or newer
- EP-133 KO-II connected via USB
- [sox](https://sox.sourceforge.net/) — used for audio conversion

---

## Installation

**1. Install system dependencies**

macOS:
```bash
brew install sox
```

Linux (Debian/Ubuntu):
```bash
sudo apt install sox
```

**2. Install Python dependencies**

```bash
pip install -r requirements.txt
```

This installs `mido` (MIDI I/O) and `textual` (terminal UI).

**3. Verify**

```bash
krate --help
```

If you see the help output, you're ready to go. If not, see [Troubleshooting](#troubleshooting).

---

## Quick Start

Connect your EP-133 via USB. The device should appear as a MIDI port automatically.

```bash
krate tui          # open the terminal UI — the easiest way to get started
krate ls           # list first 99 slots from the command line
```

---

## Terminal UI

```bash
krate tui
```

The TUI is the main interface for browsing and managing samples interactively. Use the arrow keys to
navigate slots. Press `?` to see all available keybindings.

You can rename, move, copy, delete, upload, download, and optimize samples directly from the TUI
without typing individual commands.

---

## All Commands

Every command accepts `--device <name>` to target a specific MIDI port (see [Troubleshooting](#troubleshooting)),
and `--help` for usage details.

### Listing and inspecting

```bash
krate ls                  # list first 99 slots (page 1)
krate ls --page 2         # slots 100–199
krate ls --page 3         # slots 200–299
krate ls --all            # all 999 slots (can be slow)

krate info 43             # name, size, and duration for slot 43
krate info 1-50           # info for a range of slots
```

### Uploading and downloading

```bash
krate get 43 ./kick.wav              # download slot 43 to a WAV file
krate put ./kick.wav 43              # upload a WAV file to slot 43
krate put ./kick.wav 43 --name "afterparty kick"   # upload with a custom name
```

Audio is uploaded as-is if it is already in the device's native format (16-bit mono, 46875 Hz).
Use `krate optimize` (below) to convert files that aren't in that format before uploading.

### Organizing slots

```bash
krate mv 43 50            # move slot 43 to slot 50
krate cp 43 50            # copy slot 43 to slot 50
krate rm 43               # delete slot 43
krate rename 43 "new name"
```

Slots are numbered 1–999. Destination slots must be empty for `mv` and `cp` unless you confirm overwrite.

### Optimizing memory

The EP-133 has 128 MB of sample memory. Stereo files use twice as much space as mono, and files
recorded at high sample rates are also larger than necessary.

```bash
krate optimize 43         # convert slot 43: stereo → mono, downsample to 46875 Hz if needed
krate optimize-all        # optimize every stereo sample on the device
```

`optimize` only converts what needs converting — it skips files that are already in the native format.

### Squashing gaps

When you delete samples, they leave gaps in your slot layout. `squash` packs all samples into a
contiguous range starting from slot 1.

```bash
krate squash              # dry run — shows what would move, makes no changes
krate squash --execute    # apply the squash
```

Always run the dry run first to review the proposed moves.

---

## Audio Format

The EP-133 stores samples at **46875 Hz** (its native clock rate). Files above this rate are
downsampled automatically by `krate optimize`. Files at or below 46875 Hz are stored at their
original rate on OS 2.0 and later — `krate` does not upsample them.

Upload expects a standard WAV file. If audio sounds wrong on the device after uploading, verify the
file format:

```bash
ffprobe ./kick.wav
```

---

## Troubleshooting

### Device not found

If `krate` can't find the EP-133, list the available MIDI ports:

```bash
python -c "import mido; print(mido.get_input_names())"
```

Then pass the port name explicitly:

```bash
krate --device "EP-133" ls
```

The exact port name may include a suffix like `:0` depending on your OS and MIDI driver. Try the
name shown in the list.

### Slow listing with `--all`

Querying all 999 slots takes time — each slot requires a round-trip to the device. Use `ls` without
`--all` for day-to-day browsing, and `--all` only when you need a full inventory.

### Command fails mid-operation

`krate` operations are designed to be safe: moves and copies check for empty destinations before
committing. If a command is interrupted, the device may be left in a mid-operation state. Reconnect
the USB cable and try again, or power-cycle the EP-133.

### Wrong or missing samples after upload

Verify the WAV file parameters (sample rate, bit depth, channel count) with `ffprobe`. Files that
are not standard WAV may not upload correctly. See [PROTOCOL.md](../../PROTOCOL.md) for the exact
format requirements.

### macOS USB permissions

On macOS, you may need to grant terminal access to MIDI devices in System Settings → Privacy &
Security → Bluetooth (for some versions) or via the MIDI Studio app in Audio MIDI Setup.

---

## Known Limitations

- **Firmware compatibility**: The protocol is reverse-engineered from a specific firmware version.
  Some operations may behave differently or fail on other versions.
- **Audition from CLI**: On-device sample playback via `krate` is not yet implemented.
  Use the TUI for audition functionality.
- **Memory statistics**: The device exposes free memory in its protocol, but the command that
  requests it has not been fully identified. Memory estimates may not be exact.
- **Pad mapping**: Group A pad mapping (slots 9201–9212) is fully captured. Groups B/C/D are
  partially known.

---

## Documentation

- [Protocol Specification](../../PROTOCOL.md) — full SysEx format, opcodes, byte layouts
- [Contributing](../../CONTRIBUTING.md) — development setup, protocol gaps, capture workflow
